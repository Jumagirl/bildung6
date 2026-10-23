#!/usr/bin/env python3
"""Sammelt Kampfwerte aus Matches der besten Spieler (öffentliche Daten von Rivals Data).

Daraus entstehen die Vergleichswerte «So spielen die Besten» im Rivals Coach (siehe ``top_bench_build.py``).

Ablauf:
  1. Pro Held die Rangliste der besten Spieler laden und ein paar Startspieler (Seeds) wählen, die den Helden wirklich oft spielen.
  2. Von jedem Startspieler die letzten Competitive-Matches laden. Weil dort fast nur Spieler von Celestial aufwärts sitzen,
     liefert jedes Match zwölf Datenpunkte aus dem oberen Ende der Leiter.
  3. Pro Match die Details laden und kompakt ablegen. Namen und Spieler-Kennungen werden nicht gespeichert, nur ein Kurzwert,
     damit derselbe Spieler nicht zu oft zählt.

Der Lauf ist wiederholbar: Schon geladene Matches stehen in ``matches.jsonl`` und werden übersprungen.

Benutzung:
    python top_bench_collect.py --out-dir ~/rivals-bench --seeds 4 --limit 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any


def vals(x: Any) -> list:
    return list(x.values()) if isinstance(x, dict) else list(x or [])


def short(uid: Any) -> str:
    return hashlib.sha1(str(uid).encode()).hexdigest()[:8]


def pause(sec: float) -> None:
    if sec > 0:
        time.sleep(sec)


def retry(fn, tries: int = 3, base: float = 4.0):
    """Ruft fn auf und versucht es bei Fehlern mit wachsendem Abstand erneut."""
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - jeder Netzwerkfehler soll nur zu einer Wiederholung führen
            last = exc
            name = type(exc).__name__
            if name in ("PrivacyError", "PlayerNotFoundError"):
                break
            time.sleep(base * (2 ** i))
    raise last  # type: ignore[misc]


def compact(details: dict) -> dict | None:
    """Schlanker Datensatz pro Match: nur Zahlen, keine Namen."""
    mode = (details.get("game_mode") or {}).get("name") if isinstance(details.get("game_mode"), dict) else None
    out = {"id": str(details.get("match_uid")), "ts": details.get("timestamp"), "dur": details.get("duration_seconds"),
           "season": details.get("season"), "mode": mode, "win": details.get("winner_camp"),
           "map": (details.get("map") or {}).get("name") if isinstance(details.get("map"), dict) else None, "players": [], "bans": []}
    for d in vals(details.get("draft")):
        if isinstance(d, dict) and d.get("is_pick") is False and d.get("hero_name"):
            out["bans"].append(d["hero_name"])
    for team in vals(details.get("teams")):
        if not isinstance(team, dict):
            continue
        camp = team.get("camp")
        for p in vals(team.get("players")):
            if not isinstance(p, dict) or p.get("ai"):
                continue
            heroes = [h for h in vals(p.get("heroes")) if isinstance(h, dict)]
            # Nur Spieler, die das ganze Match bei einem Helden geblieben sind: sonst lassen sich die Werte nicht einem Helden zuordnen
            hero = None
            pt = None
            if len(heroes) == 1:
                h = heroes[0]
                hid = h.get("hero_id")
                hero = hid
                pt = h.get("play_time")
            out["players"].append({
                "u": short(p.get("player_uid", p.get("uid"))), "c": camp, "h": hero, "t": pt,
                "k": p.get("kills"), "d": p.get("deaths"), "a": p.get("assists"), "f": p.get("final_hits"),
                "dmg": p.get("damage"), "blk": p.get("blocked"), "heal": p.get("healing"), "acc": p.get("accuracy"),
                "tk": p.get("damage_taken"), "rl": p.get("rank_level"), "rs": p.get("rank_score"),
                "mvp": bool(p.get("is_mvp")), "svp": bool(p.get("is_svp")), "w": team.get("is_win")})
    return out if out["players"] else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Matches der besten Spieler sammeln")
    ap.add_argument("--out-dir", default="rivals-bench")
    ap.add_argument("--seeds", type=int, default=4, help="Startspieler pro Held")
    ap.add_argument("--limit", type=int, default=10, help="Matches pro Startspieler")
    ap.add_argument("--max-matches", type=int, default=2600)
    ap.add_argument("--min-rank", type=int, default=21, help="kleinster Rang-Level der Startspieler (21 = Celestial 1)")
    ap.add_argument("--pause", type=float, default=0.2)
    ap.add_argument("--shard", default="0/1", help="k/n: nur jeden n-ten Helden ab dem k-ten bearbeiten (für mehrere Läufe nebeneinander)")
    ap.add_argument("--seeds-file", help="vorhandene seeds.json verwenden (spart das Laden der Ranglisten)")
    ap.add_argument("--only", help="nur diese Helden (Namen mit Komma getrennt), zum Nachholen selten gespielter Helden")
    args = ap.parse_args()
    shard_k, shard_n = (int(x) for x in args.shard.split("/"))

    from rivals_api import RivalsClient

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mpath, spath = out / "matches.jsonl", out / "seeds.json"
    if args.seeds_file and not spath.exists():
        spath.write_text(Path(args.seeds_file).read_text(encoding="utf-8"), encoding="utf-8")
    done: set[str] = set()
    if mpath.exists():
        for line in mpath.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["id"])
            except (ValueError, KeyError):
                pass
    print(f"{len(done)} Matches schon vorhanden")

    with RivalsClient() as client:
        tier = client.heroes.tier_list(platform=1, rank="celestial_plus")
        tier = tier.to_dict() if hasattr(tier, "to_dict") else dict(tier)
        hero_ids = [(h["hero_id"], h.get("name") or h.get("hero_name")) for h in tier.get("heroes", [])]
        if args.only:
            wanted = {x.strip() for x in args.only.split(",")}
            hero_ids = [(i, n) for i, n in hero_ids if n in wanted]
        print(f"{len(hero_ids)} Helden")

        seeds: dict[str, list] = json.loads(spath.read_text(encoding="utf-8")) if spath.exists() else {}
        if not seeds:
            used: set[str] = set()
            for hid, hname in hero_ids:
                try:
                    lb = retry(lambda: client.heroes.leaderboard(hid))
                except Exception as exc:  # noqa: BLE001
                    print(f"! Rangliste {hname}: {exc}")
                    continue
                ps = sorted([p for p in lb.players if (p.rank_level or 0) >= args.min_rank and (p.games or 0) >= 8],
                            key=lambda p: -(p.score or 0))
                picked = []
                for p in ps:
                    if str(p.uid) in used:
                        continue
                    picked.append(p.uid)
                    used.add(str(p.uid))
                    if len(picked) >= args.seeds:
                        break
                seeds[str(hid)] = picked
                print(f"  {hname}: {len(picked)} Startspieler")
                pause(args.pause)
            spath.write_text(json.dumps(seeds), encoding="utf-8")

        names = dict(hero_ids)
        total_new = 0
        with mpath.open("a", encoding="utf-8") as fh:
            for idx, (hid, uids) in enumerate(seeds.items()):
                if idx % shard_n != shard_k:
                    continue
                for uid in uids:
                    if len(done) >= args.max_matches:
                        break
                    try:
                        player = retry(lambda: client.get_player_by_uid(uid))
                        hist = retry(lambda: player.matches.fetch(limit=args.limit * 2))
                        rows = [r for r in list(hist.matches) if getattr(getattr(r, "game_mode", None), "name", None) == "Competitive"][: args.limit]
                    except Exception as exc:  # noqa: BLE001
                        print(f"! Verlauf von einem Startspieler ({names.get(int(hid), hid)}): {type(exc).__name__}")
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
                            print(f"! Details {mid}: {type(exc).__name__}")
                            continue
                        if rec:
                            fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
                            fh.flush()
                            done.add(mid)
                            new += 1
                            total_new += 1
                        pause(args.pause)
                    print(f"{names.get(int(hid), hid)}: +{new} (gesamt {len(done)})", flush=True)
        print(f"Fertig: {total_new} neue Matches, {len(done)} insgesamt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
