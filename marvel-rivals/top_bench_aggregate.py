#!/usr/bin/env python3
"""Macht aus den gesammelten Top-Matches (``top_bench_collect.py``) die Vergleichswerte für den Rivals Coach.

Pro Held und Rangband (Eternity und höher, Celestial) werden Quartile der Werte pro 10 Minuten berechnet: Schaden, Heilung, Geblockt,
Tode, Kills, Assists, Schaden eingesteckt, dazu Treffgenauigkeit und der Anteil an MVP/SVP-Auszeichnungen. Dazu pro Rolle: was
Spieler in Siegen anders machen als in Niederlagen. Gezählt werden nur Spieler, die das ganze Match bei einem Helden geblieben sind.

Benutzung:
    python top_bench_aggregate.py matches.jsonl top_bench.json
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

from rivals_sync import NAME_FIXES

ROLE_OF = {"Vanguard": "Vanguard", "Duelist": "Duelist", "Strategist": "Strategist"}
MIN_ROWS, MIN_PLAYERS, PER_PLAYER_CAP, MIN_SECONDS = 12, 6, 8, 300
METRICS = ["dmg", "heal", "blk", "d", "k", "a", "tk"]   # pro 10 Minuten


def q(values: list[float]) -> list[float]:
    s = sorted(values)
    if len(s) < 4:
        m = statistics.median(s)
        return [m, m, m]
    qs = statistics.quantiles(s, n=4, method="inclusive")
    return [qs[0], qs[1], qs[2]]


def rnd(v: float, digits: int) -> float:
    return round(v, digits) if digits else round(v)


def main(src: str, out: str, roles_path: str | None = None) -> int:
    from rivals_api import HERO_NAMES

    names = {int(k): NAME_FIXES.get(v, v) for k, v in HERO_NAMES.items()}
    roles = json.load(open(roles_path, encoding="utf-8")) if roles_path else {}
    rows: list[dict] = []
    matches = 0
    seen: set[str] = set()
    for line in open(src, encoding="utf-8"):
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m["id"] in seen or (m.get("dur") or 0) < MIN_SECONDS:
            continue
        seen.add(m["id"])
        matches += 1
        for p in m["players"]:
            hero = names.get(int(p["h"])) if p.get("h") else None
            rl = p.get("rl") or 0
            if not hero or rl < 19:
                continue
            secs = p.get("t") or m["dur"]
            if not secs or secs < MIN_SECONDS * 0.8 or p.get("d") is None:
                continue
            per = lambda v: (v or 0) / (secs / 60) * 10
            rows.append({"mid": m["id"], "camp": p.get("c"), "hero": hero, "u": p["u"], "band": "e" if rl >= 22 else "c", "win": bool(p.get("w")),
                         "dmg": per(p.get("dmg")), "heal": per(p.get("heal")), "blk": per(p.get("blk")), "d": per(p.get("d")),
                         "k": per(p.get("k")), "a": per(p.get("a")), "tk": per(p.get("tk")), "acc": p.get("acc"),
                         "mvp": 1 if p.get("mvp") else 0, "svp": 1 if p.get("svp") else 0})
    print(f"{matches} Matches, {len(rows)} Datenpunkte")

    # Pro Spieler und Held höchstens PER_PLAYER_CAP Datenpunkte, damit einzelne Spieler nicht dominieren
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
            o[m] = [rnd(v, 1 if m in ("d", "k", "a") else 0) for v in q([r[m] for r in rs])]
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
    for (hero, band), rs in by.items():
        s = summarize(rs)
        if s:
            heroes.setdefault(hero, {})[band] = s
    # Rollen: Siege gegen Niederlagen (alle Datenpunkte ab Celestial)
    role_stats: dict[str, dict] = {}
    if roles:
        byr = defaultdict(list)
        for r in rows:
            rl = roles.get(r["hero"])
            if rl:
                byr[(rl, r["win"])].append(r)
        for rl in ("Strategist", "Vanguard", "Duelist"):
            w, l = byr.get((rl, True), []), byr.get((rl, False), [])
            if len(w) >= 40 and len(l) >= 40:
                role_stats[rl] = {"n": [len(w), len(l)], **{m: [rnd(statistics.median([r[m] for r in w]), 1 if m in ("d", "k", "a") else 0),
                                                              rnd(statistics.median([r[m] for r in l]), 1 if m in ("d", "k", "a") else 0)] for m in METRICS}}
        # Carry-Quote (MVP oder SVP) pro Rolle und Band
        for rl in ("Strategist", "Vanguard", "Duelist"):
            for band in ("e", "c"):
                rs = [r for r in rows if roles.get(r["hero"]) == rl and r["band"] == band]
                if len(rs) >= 40:
                    role_stats.setdefault(rl, {}).setdefault("carry", {})[band] = rnd(sum(r["mvp"] + r["svp"] for r in rs) / len(rs), 3)
                    role_stats[rl].setdefault("rows", {})[band] = len(rs)
    # Carry-Profil: Werte von Spielern, die MVP oder SVP wurden, gegen die übrigen derselben Rolle (alle Datenpunkte ab Celestial)
    if roles:
        for rl in ("Strategist", "Vanguard", "Duelist"):
            rs = [r for r in rows if roles.get(r["hero"]) == rl]
            c1, c0 = [r for r in rs if r["mvp"] or r["svp"]], [r for r in rs if not (r["mvp"] or r["svp"])]
            if len(c1) >= 40 and len(c0) >= 40:
                role_stats.setdefault(rl, {})["carryMed"] = {"n": [len(c1), len(c0)], **{m: [rnd(statistics.median([r[m] for r in c1]), 1 if m in ("d", "k", "a") else 0),
                                                                                   rnd(statistics.median([r[m] for r in c0]), 1 if m in ("d", "k", "a") else 0)] for m in METRICS}}
    # Häufigste Mitspieler pro Held in Matches der Besten (gleiches Team) mit Winrate dieser Paare
    team: dict[tuple, list] = defaultdict(list)
    for r in rows:
        team[(r["mid"], r["camp"])].append(r)
    pair: dict[tuple, list] = defaultdict(lambda: [0, 0])
    appear: dict[str, int] = defaultdict(int)
    for rs in team.values():
        for r in rs:
            appear[r["hero"]] += 1
            for o in rs:
                if o is not r and o["hero"] != r["hero"]:
                    pair[(r["hero"], o["hero"])][0] += 1
                    pair[(r["hero"], o["hero"])][1] += 1 if r["win"] else 0
    mates: dict[str, list] = {}
    for (h, o), (n, w) in pair.items():
        if n >= 10:
            mates.setdefault(h, []).append([o, n, round(w / n * 100)])
    mates = {h: sorted(v, key=lambda x: -x[1])[:5] for h, v in mates.items()}
    for h, v in mates.items():
        if h in heroes:
            heroes[h]["mates"] = v
    res = {"stand": datetime.now(timezone.utc).date().isoformat(), "matches": matches, "rows": len(rows), "heroes": heroes, "roles": role_stats,
           "note": "Medianwerte und Quartile pro 10 Minuten aus Competitive-Matches der besten Spieler (Rang-Level 22+ = Eternity und höher, 19 bis 21 = Celestial). Nur Spieler, die das ganze Match bei einem Helden blieben."}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(heroes)} Helden mit Werten, {len(mates)} mit Mitspielern → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
