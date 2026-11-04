#!/usr/bin/env python3
"""Wie stark hängen die Werte pro 10 Minuten von der Teamzusammenstellung ab? Ergibt die Teamfaktoren für den Rivals Coach.

Hat ein Team nur einen Tank, blockt dieser mehr; bei drei Supports heilt jeder weniger. Für jede Rolle und jede Anzahl Spieler dieser Rolle
im eigenen Team (1, 2, 3 oder mehr) rechnet das Skript aus den gesammelten Matches (``rank_bench_collect.py``, ``qp_bench_collect.py``,
``top_bench_collect.py``) den Faktor: Mitte der Werte in dieser Zusammenstellung geteilt durch die Mitte aller Spieler der Rolle.
Damit Modus und Rang nicht hineinspielen, wird jeder Wert zuerst durch die Mitte seiner Gruppe (Modus, Rolle, Rangband) geteilt.

Gezählt werden nur Teams, in denen alle sechs Spieler das ganze Match bei einem Helden blieben (sonst ist die Rolle eines Spielers
unbekannt), und nur Felder mit mindestens ``MIN_ROWS`` Datenpunkten. Felder mit weniger Daten fehlen; die App sagt dort «nicht vergleichbar».

Benutzung:
    python team_factor_aggregate.py team_factors.json hero_roles.json ranks/matches.jsonl qp/matches.jsonl [weitere …]
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

from rank_bench_collect import band_of
from rivals_sync import NAME_FIXES

METRICS = ["dmg", "heal", "blk", "tk", "d"]
MIN_ROWS = 40
MIN_SECONDS = 240


def main(out: str, roles_path: str, *sources: str) -> int:
    from rivals_api import HERO_NAMES

    names = {int(k): NAME_FIXES.get(v, v) for k, v in HERO_NAMES.items()}
    roles = json.load(open(roles_path, encoding="utf-8"))
    seen: set[str] = set()
    rows: list[dict] = []
    teams = known = 0
    for src in sources:
        for line in open(src, encoding="utf-8"):
            try:
                m = json.loads(line)
            except ValueError:
                continue
            mode = m.get("mode")
            if m["id"] in seen or mode not in ("Competitive", "Quick Match") or (m.get("dur") or 0) < MIN_SECONDS:
                continue
            seen.add(m["id"])
            by_camp = defaultdict(list)
            for p in m["players"]:
                by_camp[p.get("c")].append(p)
            for ps in by_camp.values():
                teams += 1
                rl = [roles.get(names.get(int(p["h"]))) if p.get("h") else None for p in ps]
                if len(ps) != 6 or None in rl:
                    continue
                known += 1
                for p, r in zip(ps, rl):
                    secs = p.get("t") or m["dur"]
                    if not secs or secs < MIN_SECONDS * 0.8 or p.get("d") is None:
                        continue
                    if all(not p.get(k) for k in ("dmg", "heal", "blk", "k", "d", "a")):
                        continue
                    per = {k: (None if p.get(k) is None else p[k] / (secs / 60) * 10) for k in METRICS}
                    rows.append({"mode": mode, "r": r, "n": min(3, rl.count(r)), "band": band_of(p.get("rl") or 0), **per})
    print(f"{len(seen)} Matches, {teams} Teams, davon {known} vollständig bekannt, {len(rows)} Datenpunkte")

    # Mitte pro Gruppe (Modus, Rolle, Rangband); ohne Rang zählt die Gruppe «ohne Band»
    groups = defaultdict(list)
    for x in rows:
        groups[(x["mode"], x["r"], x["band"])].append(x)
    med = {}
    for g, xs in groups.items():
        for k in METRICS:
            vs = [x[k] for x in xs if x[k] is not None and x[k] > 0]
            if len(vs) >= 10:
                med[g + (k,)] = statistics.median(vs)
    norm = defaultdict(list)   # (Rolle, n, Kennzahl) -> normierte Werte
    allr = defaultdict(list)   # (Rolle, Kennzahl) -> normierte Werte
    for x in rows:
        for k in METRICS:
            b = med.get((x["mode"], x["r"], x["band"], k))
            if b and x[k] is not None:
                norm[(x["r"], x["n"], k)].append(x[k] / b)
                allr[(x["r"], k)].append(x[k] / b)
    factors: dict = {}
    counts: dict = {}
    for (r, n, k), vs in sorted(norm.items()):
        counts.setdefault(r, {}).setdefault(str(n), len([x for x in rows if x["r"] == r and x["n"] == n]))
        base = statistics.median(allr[(r, k)]) if allr[(r, k)] else 0
        if len(vs) < MIN_ROWS or not base:
            continue
        factors.setdefault(r, {}).setdefault(str(n), {})[k] = [round(statistics.median(vs) / base, 3), len(vs)]
    res = {"stand": datetime.now(timezone.utc).date().isoformat(), "matches": len(seen), "teams": teams, "known": known, "rows": len(rows),
           "minRows": MIN_ROWS, "factors": factors, "counts": counts,
           "note": "Faktor = Mitte der Werte pro 10 Minuten mit dieser Anzahl Spieler deiner Rolle im Team, geteilt durch die Mitte aller Spieler "
                   "der Rolle (je Modus und Rangband normiert). Nur Teams mit sechs bekannten Helden, nur Felder mit mindestens "
                   f"{MIN_ROWS} Datenpunkten."}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, separators=(",", ":"))
    for r, ns in factors.items():
        print(r, {n: {k: v[0] for k, v in ks.items()} for n, ks in ns.items()}, counts.get(r))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
