#!/usr/bin/env python3
"""Holt Daten nach Rangband für den Rivals Coach: Helden-Tierlisten (Winrate, Pickrate, Banrate) für Celestial, Celestial+ und Eternity+,
Matchup-Winrates aller Helden gegeneinander und die Verteilung der Ränge. Alles öffentliche Daten von Rivals Data.

Benutzung:
    python rank_data_fetch.py rank_data.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from rivals_sync import NAME_FIXES

BANDS = ["celestial", "celestial_plus", "eternity_plus", "grandmaster_plus"]
RANK_NAMES = {14: "Diamond 2", 15: "Diamond 1", 16: "Grandmaster 3", 17: "Grandmaster 2", 18: "Grandmaster 1",
              19: "Celestial 3", 20: "Celestial 2", 21: "Celestial 1", 22: "Eternity", 23: "One Above All"}


def main(out: str) -> int:
    from rivals_api import RivalsClient

    result: dict = {"stand": datetime.now(timezone.utc).date().isoformat(), "source": "Rivals Data (rivalsdata.com) und Rivals Tracker, über rivals-api",
                    "bands": {}, "matchups": {}, "ranks": []}
    with RivalsClient() as client:
        names: dict[str, str] = {}
        for band in BANDS:
            t = client.heroes.tier_list(platform=1, rank=band)
            t = t.to_dict() if hasattr(t, "to_dict") else dict(t)
            heroes = {}
            for h in t.get("heroes", []):
                name = NAME_FIXES.get(h.get("name") or h.get("hero_name"), h.get("name") or h.get("hero_name"))
                names[str(h["hero_id"])] = name
                heroes[name] = {"wr": h.get("winrate"), "wrn": h.get("winrate_no_mirror"), "pick": h.get("pick_rate"), "ban": h.get("ban_rate"),
                                "picks": h.get("picks"), "games": h.get("total_games")}
            games = max((h["games"] or 0 for h in heroes.values()), default=0)
            result["bands"][band] = {"games": games, "heroes": heroes}
            print(f"{band}: {len(heroes)} Helden, {games} Spiele")
        mu = client.providers.rt.request("/hero-matchups")
        for a, row in mu.items():
            an = names.get(str(a))
            if not an:
                continue
            out_row = {}
            for b, v in row.items():
                bn = names.get(str(b))
                if bn and isinstance(v, dict) and v.get("matches"):
                    out_row[bn] = [v.get("wins", 0), v["matches"]]
            result["matchups"][an] = out_row
        print(f"Matchups: {len(result['matchups'])} Helden")
        rd = client.providers.rt.request("/rank-distribution/data")
        total = sum(r.get("total", 0) for r in rd)
        result["ranks"] = [{"level": r["rank"], "name": RANK_NAMES.get(r["rank"]), "n": r["total"]} for r in sorted(rd, key=lambda r: -r["rank"]) if r["rank"] >= 14]
        result["rankTotal"] = total
        print(f"Rangverteilung: {total} erfasste Spieler")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "rank_data.json"))
