#!/usr/bin/env python3
"""Sammelt Kampfwerte aus Quick Matches über die ganze Rangleiter (öffentliche Daten von Rivals Data).

Daraus entstehen die Quick-Match-Vergleichswerte pro Rang im Rivals Coach (siehe ``rank_bench_aggregate.py --mode qp``).

In Quick Match stehen in den Matchdaten keine Ränge: Alle Spieler haben dort Rang-Level 1. Deshalb holt das Skript den Rang jedes
verwendeten Spielers aus dessen Profil (Rang der neusten Competitive-Season in ``rank_game_season``, nur wenn er höchstens 120 Tage alt
ist). Abgefragt werden nur Spieler, die das ganze Match bei einem Helden blieben, denn nur deren Werte gehen in die Auswertung ein.

Ablauf (Schneeball wie bei ``rank_bench_collect.py``): Startspieler aus den Helden-Ranglisten (Rang aus dem Profil), dann immer ein
Spieler aus dem Rangband mit den wenigsten Datenpunkten, sonst der nächste darüber oder darunter. Von ihm die letzten Quick Matches mit
Details. Gespeichert wird pro Match dasselbe wie bei ``top_bench_collect.py`` (nur Zahlen und ein Kurzwert pro Spieler, keine Namen),
dazu im Feld ``rl`` der Rang aus dem Profil. Spieler-Kennungen bleiben nur im Arbeitsspeicher.

Benutzung:
    python qp_bench_collect.py --out-dir ~/rivals-qp --per-band 1200 --bands bronze,silver
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rank_bench_collect import BANDS, band_of
from top_bench_collect import compact, pause, retry, short, vals

MAX_AGE = 120 * 86400   # Rang aus dem Profil nur, wenn die Season-Angabe höchstens so alt ist
MIN_SECONDS = 240


def profile_level(profile: dict, now: float) -> int | None:
    """Rang-Level der neusten Competitive-Season aus dem Profil, sonst None."""
    seasons = [s for s in vals(profile.get("rank_game_season")) if isinstance(s, dict) and s.get("update_time")]
    if not seasons:
        return None
    last = max(seasons, key=lambda s: s["update_time"])
    level = last.get("level")
    if not isinstance(level, int) or not 1 <= level <= 23 or now - last["update_time"] > MAX_AGE:
        return None
    return level


def main() -> int:
    ap = argparse.ArgumentParser(description="Quick Matches über die ganze Rangleiter sammeln")
    ap.add_argument("--out-dir", default="rivals-qp")
    ap.add_argument("--per-band", type=int, default=1200, help="Ziel: so viele Datenpunkte pro Rangband")
    ap.add_argument("--limit", type=int, default=8, help="Matches pro Spieler")
    ap.add_argument("--max-days", type=float, default=30, help="nur Matches der letzten so vielen Tage")
    ap.add_argument("--pause", type=float, default=0.2)
    ap.add_argument("--max-steps", type=int, default=3000)
    ap.add_argument("--bands", help="nur diese Rangbänder füllen (Namen mit Komma), für mehrere Läufe nebeneinander")
    ap.add_argument("--workers", type=int, default=6, help="so viele Profile gleichzeitig abfragen")
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
            for p in rec["players"]:
                b = band_of(p.get("rl") or 0)
                if b is not None:
                    count[b] += 1
    wanted = {b.strip() for b in args.bands.split(",")} if args.bands else set()
    now = time.time()
    cutoff = now - args.max_days * 86400
    pool: list[dict] = [dict() for _ in BANDS]   # pro Band: Spieler-Kennung -> Rang-Level (nur im Arbeitsspeicher)
    level_of: dict[str, int | None] = {}          # Profil-Rang, einmal pro Spieler abgefragt
    used: set[str] = set()

    local = threading.local()   # ein Client pro Arbeits-Thread für die Profil-Abfragen

    def fetch_level(key: str) -> int | None:
        if not hasattr(local, "client"):
            local.client = RivalsClient()
        try:
            prof = retry(lambda: local.client.get_player_by_uid(key), tries=2)
            prof = prof.to_dict() if hasattr(prof, "to_dict") else dict(prof)
            return profile_level(prof, now)
        except Exception:  # noqa: BLE001 - privates oder unbekanntes Profil: kein Rang
            return None

    workers = ThreadPoolExecutor(max_workers=max(1, args.workers))
    with RivalsClient() as client:
        def prefetch(uids) -> None:
            keys = [str(u) for u in uids if u and str(u) not in level_of]
            for key, lv in zip(keys, workers.map(fetch_level, keys)):
                level_of[key] = lv

        def level(uid) -> int | None:
            key = str(uid)
            if key not in level_of:
                prefetch([key])
            lv = level_of[key]
            b = band_of(lv or 0)
            if b is not None and key not in used:
                pool[b][key] = lv
            return lv

        seeds: list[str] = []
        tier = client.heroes.tier_list(platform=1, rank="diamond")
        tier = tier.to_dict() if hasattr(tier, "to_dict") else dict(tier)
        for h in tier.get("heroes", []):
            try:
                lb = retry(lambda: client.heroes.leaderboard(h["hero_id"]))
            except Exception as exc:  # noqa: BLE001
                print(f"! Rangliste {h['hero_id']}: {type(exc).__name__}")
                continue
            seeds.extend(str(p.uid) for p in lb.players if (p.games or 0) >= 5)
            pause(args.pause)
        random.shuffle(seeds)
        print(f"{len(seeds)} mögliche Startspieler; Datenpunkte pro Band: " + ", ".join(f"{n} {c}" for (n, _, _), c in zip(BANDS, count)))

        steps = 0
        with mpath.open("a", encoding="utf-8") as fh:
            while steps < args.max_steps:
                open_bands = [i for i in range(len(BANDS)) if count[i] < args.per_band and (not wanted or BANDS[i][0] in wanted)]
                if not open_bands:
                    break
                target = min(open_bands, key=lambda i: count[i])
                src = None
                for dist in range(len(BANDS)):
                    for b in (target + dist, target - dist):
                        if 0 <= b < len(BANDS) and pool[b]:
                            src = b
                            break
                    if src is not None:
                        break
                if src is None:
                    # Noch kein Spieler mit bekanntem Rang: Startspieler nachschlagen (mehrere gleichzeitig), bis einer einen Rang hat
                    while seeds and src is None:
                        batch = [seeds.pop() for _ in range(min(len(seeds), max(1, args.workers)))]
                        prefetch(batch)
                        for uid in batch:
                            if level(uid) and src is None:
                                src = band_of(level_of[uid])
                    if src is None:
                        print("Kein Spieler mehr im Vorrat")
                        break
                    continue
                if src == target:
                    uid = random.choice(list(pool[src]))
                else:
                    uid = (min if src > target else max)(pool[src], key=lambda u: pool[src][u])
                pool[src].pop(uid, None)
                used.add(uid)
                steps += 1
                try:
                    player = retry(lambda: client.get_player_by_uid(uid), tries=2)
                    hist = retry(lambda: player.matches.fetch(limit=args.limit * 2), tries=2)
                    rows = [r for r in list(hist.matches) if getattr(getattr(r, "game_mode", None), "name", None) == "Quick Match"][: args.limit]
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
                    if not rec or (rec.get("ts") or 0) < cutoff or (rec.get("dur") or 0) < 300:
                        continue
                    # Rang aus dem Profil, nur für Spieler, die das ganze Match bei einem Helden blieben
                    raw = {}
                    for team in vals(det.get("teams")):
                        for p in vals(team.get("players")) if isinstance(team, dict) else []:
                            if isinstance(p, dict) and not p.get("ai"):
                                raw[short(p.get("player_uid", p.get("uid")))] = p.get("player_uid", p.get("uid"))
                    prefetch([raw[p["u"]] for p in rec["players"] if p.get("h") and (p.get("t") or 0) >= MIN_SECONDS and raw.get(p["u"])])
                    for p in rec["players"]:
                        p["rl"] = None
                        if p.get("h") and (p.get("t") or 0) >= MIN_SECONDS and raw.get(p["u"]):
                            p["rl"] = level(raw[p["u"]])
                            b = band_of(p["rl"] or 0)
                            if b is not None:
                                count[b] += 1
                    rec["rankSource"] = "profile"
                    fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
                    fh.flush()
                    done.add(mid)
                    new += 1
                print(f"[{steps}] Ziel {BANDS[target][0]}, Spieler aus {BANDS[src][0]}: +{new} | " +
                      " ".join(f"{n[:3]} {c}" for (n, _, _), c in zip(BANDS, count)), flush=True)
    print("Fertig: " + ", ".join(f"{n} {c}" for (n, _, _), c in zip(BANDS, count)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
