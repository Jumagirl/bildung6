#!/usr/bin/env python3
"""Sammelt Kampfwerte aus Competitive-Matches über die ganze Rangleiter (Bronze bis Eternity, öffentliche Daten von Rivals Data).

Daraus entstehen die Vergleichswerte pro Rang auf «Rang-Weg» im Rivals Coach (siehe ``rank_bench_aggregate.py``).

Ablauf (Schneeball):
  1. Startspieler aus den Helden-Ranglisten holen. Dort stehen auch Spieler aus Diamond und Grandmaster.
  2. Immer das Rangband mit den wenigsten Matches wählen und einen Spieler aus diesem Band nehmen. Gibt es dort noch keinen,
     den nächsten Spieler darüber oder darunter: Die Matchsuche mischt nahe Ränge, so wandert die Sammlung Schritt für Schritt
     nach unten oder oben.
  3. Von diesem Spieler die letzten Competitive-Matches laden, pro Match die Details. Alle zwölf Spieler eines Matches kommen
     mit ihrem Rang in den Vorrat für die nächsten Schritte.

Gespeichert wird pro Match dasselbe wie bei ``top_bench_collect.py``: nur Zahlen und ein Kurzwert pro Spieler, keine Namen.
Spieler-Kennungen bleiben nur im Arbeitsspeicher, nichts davon landet auf der Platte.

Der Lauf ist wiederholbar: Schon geladene Matches stehen in ``matches.jsonl`` und werden übersprungen.

Benutzung:
    python rank_bench_collect.py --out-dir ~/rivals-ranks --per-band 300
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

from top_bench_collect import compact, pause, retry, vals

# Rang-Level laut Matchdaten: 1 bis 3 Bronze, 4 bis 6 Silver … 19 bis 21 Celestial, 22 Eternity, 23 One Above All
BANDS = [("bronze", 1, 3), ("silver", 4, 6), ("gold", 7, 9), ("platinum", 10, 12), ("diamond", 13, 15),
         ("grandmaster", 16, 18), ("celestial", 19, 21), ("eternity", 22, 23)]


def band_of(level: int) -> int | None:
    for i, (_, lo, hi) in enumerate(BANDS):
        if lo <= level <= hi:
            return i
    return None


def match_band(rec: dict) -> int | None:
    """Band eines Matches: Median der Rang-Level aller erfassten Spieler."""
    lv = [p["rl"] for p in rec["players"] if p.get("rl")]
    return band_of(round(statistics.median(lv))) if len(lv) >= 8 else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Matches über die ganze Rangleiter sammeln")
    ap.add_argument("--out-dir", default="rivals-ranks")
    ap.add_argument("--per-band", type=int, default=300, help="Ziel: so viele Matches pro Rangband")
    ap.add_argument("--limit", type=int, default=8, help="Matches pro Spieler")
    ap.add_argument("--max-days", type=float, default=30, help="nur Matches der letzten so vielen Tage")
    ap.add_argument("--pause", type=float, default=0.2)
    ap.add_argument("--max-steps", type=int, default=4000, help="höchstens so viele Spieler abfragen")
    ap.add_argument("--bands", help="nur diese Rangbänder füllen (Namen mit Komma), für mehrere Läufe nebeneinander")
    args = ap.parse_args()

    from rivals_api import RivalsClient

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mpath = out / "matches.jsonl"
    done: set[str] = set()
    count = [0] * len(BANDS)
    if mpath.exists():
        for line in mpath.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            done.add(rec["id"])
            b = match_band(rec)
            if b is not None:
                count[b] += 1
    print(f"{len(done)} Matches schon vorhanden: " + ", ".join(f"{n} {c}" for (n, _, _), c in zip(BANDS, count)))

    pool: list[dict] = [dict() for _ in BANDS]   # pro Band: Spieler-Kennung -> Rang-Level (nur im Arbeitsspeicher)
    used: set[str] = set()
    cutoff = time.time() - args.max_days * 86400
    wanted = {b.strip() for b in args.bands.split(",")} if args.bands else set()

    def add(uid, level) -> None:
        b = band_of(level or 0)
        if b is not None and uid and str(uid) not in used:
            pool[b][str(uid)] = level

    with RivalsClient() as client:
        seeds: list[str] = []
        tier = client.heroes.tier_list(platform=1, rank="diamond")
        tier = tier.to_dict() if hasattr(tier, "to_dict") else dict(tier)
        for h in tier.get("heroes", []):
            try:
                lb = retry(lambda: client.heroes.leaderboard(h["hero_id"]))
            except Exception as exc:  # noqa: BLE001
                print(f"! Rangliste {h['hero_id']}: {type(exc).__name__}")
                continue
            # Der Rang in der Rangliste ist oft veraltet (Startspieler mit «Bronze» spielten in Grandmaster-Lobbys).
            # Deshalb dienen diese Spieler nur als Einstieg; verlässlich ist der Rang aus den Matchdetails.
            seeds.extend(str(p.uid) for p in lb.players if (p.games or 0) >= 5 and 13 <= (p.rank_level or 0) <= 18)
            pause(args.pause)
        random.shuffle(seeds)
        print(f"{len(seeds)} Startspieler (Diamond bis Grandmaster laut Rangliste)")

        steps = 0
        with mpath.open("a", encoding="utf-8") as fh:
            while steps < args.max_steps:
                open_bands = [i for i in range(len(BANDS)) if count[i] < args.per_band and (not wanted or BANDS[i][0] in wanted)]
                if not open_bands:
                    break
                target = min(open_bands, key=lambda i: count[i])
                # Spieler aus dem Zielband, sonst der nächste darüber oder darunter
                src = None
                for dist in range(len(BANDS)):
                    for b in (target + dist, target - dist):
                        if 0 <= b < len(BANDS) and pool[b]:
                            src = b
                            break
                    if src is not None:
                        break
                if src is None:
                    seeds[:] = [u for u in seeds if u not in used]
                    if not seeds:
                        print("Kein Spieler mehr im Vorrat")
                        break
                    src, uid = None, seeds.pop()
                elif src == target:
                    uid = random.choice(list(pool[src]))
                else:   # auf das Ziel zu: der Spieler, der dem Zielband am nächsten liegt
                    uid = (min if src > target else max)(pool[src], key=lambda u: pool[src][u])
                if src is not None:
                    pool[src].pop(uid, None)
                used.add(uid)
                steps += 1
                try:
                    player = retry(lambda: client.get_player_by_uid(uid), tries=2)
                    hist = retry(lambda: player.matches.fetch(limit=args.limit * 2), tries=2)
                    rows = [r for r in list(hist.matches) if getattr(getattr(r, "game_mode", None), "name", None) == "Competitive"][: args.limit]
                except Exception as exc:  # noqa: BLE001
                    print(f"! Verlauf: {type(exc).__name__}")
                    continue
                new = 0
                for row in rows:
                    mid = str(getattr(row, "match_uid", ""))
                    if not mid or mid in done:
                        continue
                    try:
                        det = retry(lambda: row.get_details(), tries=2, base=3.0)
                        det = det.to_dict() if hasattr(det, "to_dict") else dict(det)
                        rec = compact(det)
                    except Exception as exc:  # noqa: BLE001
                        print(f"! Details: {type(exc).__name__}")
                        continue
                    pause(args.pause)
                    if not rec or (rec.get("ts") or 0) < cutoff:
                        continue
                    for team in vals(det.get("teams")):
                        for p in vals(team.get("players")) if isinstance(team, dict) else []:
                            if isinstance(p, dict) and not p.get("ai"):
                                add(p.get("player_uid", p.get("uid")), p.get("rank_level"))
                    fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
                    fh.flush()
                    done.add(mid)
                    b = match_band(rec)
                    if b is not None:
                        count[b] += 1
                    new += 1
                print(f"[{steps}] Ziel {BANDS[target][0]}, Spieler aus {BANDS[src][0] if src is not None else 'Rangliste'}: +{new} | " +
                      " ".join(f"{n[:3]} {c}" for (n, _, _), c in zip(BANDS, count)), flush=True)
    print("Fertig: " + ", ".join(f"{n} {c}" for (n, _, _), c in zip(BANDS, count)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
