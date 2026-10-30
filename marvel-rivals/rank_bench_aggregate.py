#!/usr/bin/env python3
"""Macht aus den Matches über die ganze Rangleiter (``rank_bench_collect.py``) die Vergleichswerte pro Rang für den Rivals Coach.

Pro Held und Rangband (Bronze bis Eternity) werden Quartile der Werte pro 10 Minuten berechnet, genau wie in
``top_bench_aggregate.py``: Schaden, Heilung, Geblockt, Tode, Kills, Assists, Schaden eingesteckt, dazu Treffgenauigkeit und der
Anteil an MVP/SVP. Massgebend ist der Rang jedes einzelnen Spielers laut Matchdaten, nicht der Rang der Lobby. Dazu pro Rolle und
Band: Mitte der Werte über alle Helden der Rolle und die Carry-Quote (MVP oder SVP). Gezählt werden nur Spieler, die das ganze
Match bei einem Helden geblieben sind.

Mit ``--mode qp`` zählen statt Competitive-Matches die Quick Matches aus ``qp_bench_collect.py``; der Rang steht dort im Feld ``rl``
(aus dem Profil), weil Quick-Match-Daten selbst keinen Rang enthalten.

Benutzung:
    python rank_bench_aggregate.py rank_bench.json hero_roles.json matches.jsonl [weitere matches.jsonl …]
    python rank_bench_aggregate.py --mode qp qp_bench.json hero_roles.json qp/matches.jsonl [weitere …]
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

from rank_bench_collect import BANDS, band_of, match_band
from rivals_sync import NAME_FIXES
from top_bench_aggregate import METRICS, MIN_PLAYERS, MIN_ROWS, MIN_SECONDS, PER_PLAYER_CAP, q, rnd

ROLE_MIN = 40   # so viele Datenpunkte braucht eine Rolle pro Band für Mitte und Carry-Quote


def main(out: str, roles_path: str, *sources: str, mode: str = "Competitive") -> int:
    from rivals_api import HERO_NAMES

    names = {int(k): NAME_FIXES.get(v, v) for k, v in HERO_NAMES.items()}
    roles = json.load(open(roles_path, encoding="utf-8"))
    rows: list[dict] = []
    seen: set[str] = set()
    per_band = [0] * len(BANDS)
    for src in sources:
        for line in open(src, encoding="utf-8"):
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m["id"] in seen or (m.get("dur") or 0) < MIN_SECONDS or m.get("mode") != mode:
                continue
            seen.add(m["id"])
            mb = match_band(m) if mode == "Competitive" else None   # Quick-Match-Lobbys mischen Ränge: dort zählen nur Datenpunkte
            if mb is not None:
                per_band[mb] += 1
            for p in m["players"]:
                hero = names.get(int(p["h"])) if p.get("h") else None
                b = band_of(p.get("rl") or 0)
                if not hero or b is None:
                    continue
                secs = p.get("t") or m["dur"]
                if not secs or secs < MIN_SECONDS * 0.8 or p.get("d") is None:
                    continue
                # Fehlende Werte bleiben None und fallen bei dieser Kennzahl weg: Rivals Data liefert «Geblockt» und «Schaden eingesteckt»
                # nicht in jedem Match (in Quick Match bei rund 40 % der Spieler nicht). Als 0 gezählt, würden sie die Mitte nach unten ziehen.
                per = lambda v: None if v is None else v / (secs / 60) * 10
                if all(not p.get(k) for k in ("dmg", "heal", "blk", "k", "d", "a")):
                    continue   # ganz leere Zeile (zum Beispiel abwesend): kein Datenpunkt
                rows.append({"hero": hero, "u": p["u"], "band": b, "dmg": per(p.get("dmg")), "heal": per(p.get("heal")),
                             "blk": per(p.get("blk")), "d": per(p.get("d")), "k": per(p.get("k")), "a": per(p.get("a")),
                             "tk": per(p.get("tk")), "acc": p.get("acc"), "mvp": 1 if p.get("mvp") else 0, "svp": 1 if p.get("svp") else 0})
    print(f"{len(seen)} Matches, {len(rows)} Datenpunkte")

    cnt: dict[tuple, int] = defaultdict(int)
    kept = []
    for r in rows:
        k = (r["hero"], r["u"], r["band"])
        cnt[k] += 1
        if cnt[k] <= PER_PLAYER_CAP:
            kept.append(r)
    rows = kept

    def summarize(rs: list[dict]) -> dict | None:
        if len(rs) < MIN_ROWS or len({r["u"] for r in rs}) < MIN_PLAYERS:
            return None
        o: dict = {"n": len(rs), "p": len({r["u"] for r in rs})}
        for m in METRICS:
            vs = [r[m] for r in rs if r[m] is not None]
            if len(vs) >= MIN_ROWS:
                o[m] = [rnd(v, 1 if m in ("d", "k", "a") else 0) for v in q(vs)]
        accs = [r["acc"] for r in rs if r["acc"] not in (None, 0)]
        if len(accs) >= MIN_ROWS:
            o["acc"] = [rnd(v, 1) for v in q(accs)]
        o["mvp"] = rnd(sum(r["mvp"] for r in rs) / len(rs), 3)
        o["svp"] = rnd(sum(r["svp"] for r in rs) / len(rs), 3)
        return o

    heroes: dict[str, dict] = {}
    by = defaultdict(list)
    for r in rows:
        by[(r["hero"], r["band"])].append(r)
    for (hero, b), rs in sorted(by.items()):
        s = summarize(rs)
        if s:
            heroes.setdefault(hero, {})[BANDS[b][0]] = s
    role_stats: dict[str, dict] = {}
    byr = defaultdict(list)
    for r in rows:
        rl = roles.get(r["hero"])
        if rl:
            byr[(rl, r["band"])].append(r)
    for (rl, b), rs in sorted(byr.items()):
        if len(rs) >= ROLE_MIN:
            role_stats.setdefault(rl, {})[BANDS[b][0]] = {
                "n": len(rs), "carry": rnd(sum(r["mvp"] + r["svp"] for r in rs) / len(rs), 3),
                **{m: rnd(statistics.median(vs), 1 if m in ("d", "k", "a") else 0) for m in METRICS
                   for vs in [[r[m] for r in rs if r[m] is not None]] if len(vs) >= ROLE_MIN // 2}}
    band_rows = defaultdict(int)
    for r in rows:
        band_rows[r["band"]] += 1
    res = {"stand": datetime.now(timezone.utc).date().isoformat(), "mode": mode, "matches": len(seen), "rows": len(rows),
           "bands": [[k, lo, hi, per_band[i], band_rows[i]] for i, (k, lo, hi) in enumerate(BANDS)],
           "heroes": heroes, "roles": role_stats,
           "note": ("Quartile pro 10 Minuten aus Competitive-Matches über die ganze Rangleiter, gesammelt per Schneeball ab Spielern aus den Helden-Ranglisten. "
                    "Massgebend ist der Rang jedes Spielers laut Matchdaten." if mode == "Competitive" else
                    "Quartile pro 10 Minuten aus Quick Matches über die ganze Rangleiter, gesammelt per Schneeball ab Spielern aus den Helden-Ranglisten. "
                    "Massgebend ist der Competitive-Rang jedes Spielers laut Profil (neuste Season, höchstens 120 Tage alt).")
                   + " Nur Spieler, die das ganze Match bei einem Helden blieben."}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, separators=(",", ":"))
    print("Matches pro Band: " + ", ".join(f"{k} {per_band[i]}" for i, (k, _, _) in enumerate(BANDS)))
    print(f"{len(heroes)} Helden mit Werten → {out}")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    mode = "Competitive"
    if argv[:1] == ["--mode"]:
        mode = {"qp": "Quick Match", "ranked": "Competitive"}.get(argv[1], argv[1])
        argv = argv[2:]
    sys.exit(main(*argv, mode=mode))
