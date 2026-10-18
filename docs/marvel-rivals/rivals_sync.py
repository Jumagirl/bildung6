#!/usr/bin/env python3
"""Rivals-Data-Sync für den Rivals Coach.

Holt deine öffentlichen Marvel-Rivals-Daten von RivalsData (über die
Community-Bibliothek ``rivals-api``) und schreibt sie in eine JSON-Datei,
die du im Rivals Coach unter „Daten → Rivals Data importieren“ einliest.

Installation (einmalig):
    python -m pip install rivals-api

Benutzung:
    python rivals_sync.py "DeinSpielername"
    python rivals_sync.py 1970288503 --limit 100
    python rivals_sync.py "DeinSpielername" --no-details   # schneller, ohne Teams

Hinweise:
- Deine Match-History muss öffentlich sein, sonst liefert RivalsData keine Matches.
- ``rivals-api`` ist inoffiziell und nutzt eine nicht dokumentierte Schnittstelle;
  Felder können sich ändern. Das Skript überspringt Matches, die es nicht lesen kann.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

FORMAT = "rivals-coach-sync"
VERSION = 1

# Namen, die in der App anders heissen als in rivals-api
NAME_FIXES = {
    "Tankpool": "Deadpool (Vanguard)",
    "DPSpool": "Deadpool (Duelist)",
    "Stratpool": "Deadpool (Strategist)",
    "Gorr the God Butcher": "Gorr",
}
# Queue-Codes laut rivals-api: 1 Quick Match, 2 Competitive, 3 Custom, 4 Arcade
MODES = {1: "Quick Match", 2: "Competitive", 3: "Custom / Training", 4: "Arcade / Event"}
GAME_TYPES = ("Domination", "Convoy", "Convergence", "Doom Match", "Conquest")


# ---------- Hilfsfunktionen (ohne Netzwerk, testbar) ----------

def as_dict(value: Any) -> Any:
    """Wandelt rivals-api-Modelle rekursiv in normale dicts/lists um."""
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {k: as_dict(v) for k, v in value.items()}
    if isinstance(value, list):
        return [as_dict(v) for v in value]
    return value


def values(container: Any) -> list:
    """Teams und Spieler kommen als Liste oder als dict (nach Slot) – beides erlauben."""
    if isinstance(container, Mapping):
        return list(container.values())
    if isinstance(container, list):
        return container
    return []


def to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ref_name(ref: Any) -> str | None:
    """Name aus einer serialisierten Referenz ({id, name, is_known}) lesen."""
    if isinstance(ref, Mapping):
        if ref.get("is_known") is False:
            return None
        return ref.get("name")
    if isinstance(ref, str):
        return ref
    return None


def hero_label(hero_id: Any, fallback: Any = None) -> str | None:
    try:
        from rivals_api import hero_name
    except ImportError:  # in Tests ohne installierte Bibliothek
        hero_name = None
    name = hero_name(hero_id) if hero_name and hero_id is not None else None
    name = name or ref_name(fallback)
    if not name or name.lower().startswith("unknown"):
        return None
    if name == "Deadpool":  # Rolle unbekannt
        return "Deadpool (Duelist)"
    return NAME_FIXES.get(name, name)


def timestamp_ms(value: Any) -> int | None:
    if value is None:
        return None
    number = to_int(value)
    if number is not None:
        return number if number > 10**12 else number * 1000
    try:
        text = str(value).replace("Z", "+00:00")
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        return None


def map_label(row: Mapping[str, Any]) -> tuple[str, str]:
    """Liefert (Map-Name im App-Format, Spieltyp)."""
    ref = row.get("map") if isinstance(row.get("map"), Mapping) else {}
    name = ref_name(ref) or (row.get("map_name") if isinstance(row.get("map_name"), str) else None)
    location = ref.get("location") if isinstance(ref, Mapping) else None
    label = f"{location}: {name}" if name and location and location not in name else (name or "")
    gameplay = ref.get("gameplay_name") if isinstance(ref, Mapping) else None
    gameplay = gameplay or row.get("map_mode_name") or ref_name(row.get("gameplay_mode"))
    game_type = next((t for t in GAME_TYPES if gameplay and t.lower() in str(gameplay).lower()), "Anderer")
    return label, game_type


def main_hero(player: Mapping[str, Any]) -> tuple[str | None, bool]:
    """Längstgespielter Held eines Match-Teilnehmers und ob gewechselt wurde."""
    heroes = [h for h in values(player.get("heroes") or player.get("top_heroes")) if isinstance(h, Mapping)]
    if heroes:
        def play_time(h: Mapping[str, Any]) -> float:
            try:
                return float(h.get("play_time") or 0)
            except (TypeError, ValueError):
                return 0.0
        totals: dict[str, float] = {}
        for h in heroes:
            name = hero_label(h.get("hero_id", h.get("id")), h)
            if name:
                totals[name] = totals.get(name, 0.0) + play_time(h)
        if totals:
            best = max(totals, key=totals.get)
            swapped = sum(1 for t in totals.values() if t >= 30) > 1
            return best, swapped
    hero = player.get("hero") if isinstance(player.get("hero"), Mapping) else {}
    return hero_label(player.get("hero_id", hero.get("hero_id")), hero), False


def number(value: Any) -> int | None:
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


DURATION_SECONDS_KEYS = ("duration_seconds", "match_play_duration", "match_duration_seconds")


def duration_minutes(*sources: Any) -> float | None:
    """Matchdauer in Minuten. Rivals Data liefert sie in den Match-Details als ``duration_seconds``."""
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        for key in DURATION_SECONDS_KEYS:
            try:
                value = float(source.get(key))
            except (TypeError, ValueError):
                continue
            if value > 0:
                return round(value / 60, 1)
    return None


def convert_match(row: Mapping[str, Any], uid: Any, details: Mapping[str, Any] | None) -> dict | None:
    """Wandelt einen History-Eintrag (+ optionale Details) ins Match-Format der App um."""
    match_id = row.get("match_uid")
    if match_id is None:
        return None
    is_win = row.get("is_win")
    if to_int(row.get("winner_camp")) == 12 or is_win is None:
        return None  # Unentschieden oder unbekanntes Ergebnis
    ts = timestamp_ms(row.get("timestamp")) or int(datetime.now(timezone.utc).timestamp() * 1000)
    map_name, game_type = map_label(row)
    hero = hero_label(row.get("hero_id"), row.get("hero"))
    match = {
        "extId": str(match_id),
        "source": "rivalsdata",
        "ts": ts,
        "date": datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d"),
        "hero": hero,
        "mode": MODES.get(to_int(row.get("game_mode_id")), "Anderer"),
        "type": game_type,
        "map": map_name,
        "result": "W" if is_win else "L",
        "k": to_int(row.get("kills")) or 0,
        "d": to_int(row.get("deaths")) or 0,
        "a": to_int(row.get("assists")) or 0,
        "dmg": None, "heal": None, "block": None,
        "dur": duration_minutes(row, details),
        "mvp": bool(row.get("is_mvp")), "svp": bool(row.get("is_svp")),
        "enemies": [], "allies": [], "swapped": False,
    }
    if details:
        apply_details(match, details, uid)
    if not match["hero"]:
        return None
    return match


def apply_details(match: dict, details: Mapping[str, Any], uid: Any) -> None:
    """Ergänzt Teams, Schaden, Heilung und Heldenwechsel aus den Match-Details."""
    if not match["map"]:
        match["map"], match["type"] = map_label(details)
    me_team = None
    entries: list[tuple[Any, Mapping[str, Any]]] = []
    for team in values(details.get("teams")):
        if not isinstance(team, Mapping):
            continue
        camp = team.get("camp", team.get("team_id", team.get("side")))
        for player in values(team.get("players")):
            if not isinstance(player, Mapping):
                continue
            player_camp = player.get("camp", camp)
            entries.append((player_camp, player))
            if str(player.get("uid", player.get("player_uid"))) == str(uid):
                me_team = player_camp
                hero, swapped = main_hero(player)
                match["hero"] = hero or match["hero"]
                match["swapped"] = swapped
                match["dmg"] = number(player.get("damage"))
                match["heal"] = number(player.get("healing"))
                match["block"] = number(player.get("blocked"))
    if me_team is None:
        return
    for camp, player in entries:
        if str(player.get("uid", player.get("player_uid"))) == str(uid):
            continue
        hero, _ = main_hero(player)
        if hero:
            (match["allies"] if str(camp) == str(me_team) else match["enemies"]).append(hero)


def percent(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(v * 100, 1) if v <= 1 else round(v, 1)


def first(row: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None


def convert_meta(tier_list: Mapping[str, Any]) -> list[dict]:
    rows = []
    for row in values(tier_list.get("heroes")):
        if not isinstance(row, Mapping):
            continue
        hero = hero_label(row.get("hero_id", row.get("id")), row)
        if not hero:
            continue
        rows.append({
            "hero": hero,
            "winrate": percent(first(row, ("winrate", "win_rate", "wr"))),
            "winrateNoMirror": percent(row.get("winrate_no_mirror")),
            "pickrate": percent(first(row, ("pick_rate", "pickrate"))),
            "banrate": percent(first(row, ("ban_rate", "banrate"))),
            "games": to_int(first(row, ("total_games", "games", "picks"))),
            "tier": row.get("tier"),
        })
    return rows


def convert_player_heroes(rows: Iterable[Any]) -> list[dict]:
    out = []
    for row in rows:
        row = as_dict(row)
        if not isinstance(row, Mapping):
            continue
        hero = hero_label(row.get("hero_id"), row)
        games = to_int(row.get("games"))
        if not hero or not games:
            continue
        wins = to_int(row.get("wins"))
        out.append({"hero": hero, "games": games, "wins": wins, "losses": to_int(row.get("losses")),
                    "winrate": round(wins / games * 100, 1) if wins is not None else None,
                    "kda": row.get("kda")})
    return out


# ---------- Abruf ----------

def sync(args: argparse.Namespace) -> dict:
    from rivals_api import RivalsClient

    result: dict[str, Any] = {"format": FORMAT, "version": VERSION, "source": "rivalsdata",
                              "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "matches": [], "playerHeroes": [], "meta": None, "warnings": []}
    with RivalsClient(use_browser_fallback=args.browser) as client:
        player = client.get_player(args.player)
        uid = player.uid
        result["player"] = {"name": getattr(player, "name", None) or str(args.player), "uid": uid,
                            "level": getattr(player, "level", None)}
        print(f"Spieler gefunden: {result['player']['name']} (UID {uid})")

        try:
            history = player.matches.fetch(limit=args.limit)
            rows = list(history.matches)
        except Exception as exc:  # z.B. private Match-History
            rows = []
            result["warnings"].append(f"Match-History nicht abrufbar: {exc}")
            print(f"! Match-History nicht abrufbar: {exc}")

        skipped = 0
        for i, row in enumerate(rows, 1):
            details = None
            if args.details:
                try:
                    details = as_dict(row.get_details())
                except Exception as exc:
                    result["warnings"].append(f"Details zu {row.match_uid} fehlen: {exc}")
            try:
                match = convert_match(as_dict(row), uid, details)
            except Exception as exc:
                match = None
                result["warnings"].append(f"Match übersprungen: {exc}")
            if match:
                result["matches"].append(match)
            else:
                skipped += 1
            print(f"\rMatches: {i}/{len(rows)}", end="", flush=True)
        if rows:
            print()
        if skipped:
            print(f"{skipped} Match(es) übersprungen (Unentschieden oder unvollständig).")

        try:
            result["playerHeroes"] = convert_player_heroes(player.heroes.summary(season="all"))
        except Exception as exc:
            result["warnings"].append(f"Helden-Statistik nicht abrufbar: {exc}")

        try:
            tier = as_dict(client.heroes.tier_list(platform=args.platform, rank=args.rank))
            result["meta"] = {"rank": args.rank, "platform": args.platform,
                              "updated": tier.get("last_update"), "heroes": convert_meta(tier)}
        except Exception as exc:
            result["warnings"].append(f"Globale Tierlist nicht abrufbar: {exc}")
    return result


# ---------- Ausgabe für den automatischen Abgleich ----------

CHAT_LIMIT = 24000  # Zeichen; längere Werkzeug-Ergebnisse werden abgeschnitten


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def chat_line(data: dict, request_id: str) -> str:
    """Eine Zeile mit dem Ergebnis (nur Matches), die die App aus dem Sitzungsprotokoll liest.

    Base64 (URL-sicher) übersteht jede Weitergabe unverändert. Passt es nicht in die Zeile,
    fallen die ältesten Matches weg.
    """
    slim = {k: data[k] for k in ("format", "version", "source", "generated", "player", "warnings") if k in data}
    slim["partial"] = True  # ohne Helden-Statistik und Tierlist: die App behält ihre bisherigen Werte
    matches = list(data.get("matches", []))
    while True:
        slim["matches"] = matches
        raw = json.dumps(slim, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        # BEGINZ = gzip + Base64: etwa fünfmal kürzer, schont das Sitzungsprotokoll des Helfers und die Verbindung der App
        line = f"@@RIVALS-SYNC:BEGINZ {request_id}@@ " + b64url(gzip.compress(raw, 9, mtime=0)) + " @@RIVALS-SYNC:END@@"
        if len(line) <= CHAT_LIMIT or not matches:
            return line
        matches = sorted(matches, key=lambda m: m.get("ts") or 0, reverse=True)[:-1]


def write_inbox(path: str, doc: dict) -> None:
    """Schreibt das fertige Eingangs-Dokument für den automatischen Abgleich (die App liest es aus ihrer Datenbank)."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))


def chat_error(message: str, request_id: str) -> str:
    return f"@@RIVALS-SYNC:ERROR {request_id}@@ " + b64url(message.encode("utf-8")) + " @@RIVALS-SYNC:END@@"


def main() -> int:
    parser = argparse.ArgumentParser(description="Rivals-Data-Sync für den Rivals Coach")
    parser.add_argument("player", help="Spielername oder numerische UID")
    parser.add_argument("--limit", type=int, default=50, help="Anzahl Matches (Standard: 50)")
    parser.add_argument("--no-details", dest="details", action="store_false",
                        help="Keine Match-Details abrufen (schneller, aber ohne Teams, Schaden und Heilung)")
    parser.add_argument("--rank", default="grandmaster_plus",
                        help="Rang-Filter für die globale Tierlist (Standard: grandmaster_plus)")
    parser.add_argument("--platform", default=1, type=int, help="1 = PC, 2 = PlayStation, 4 = Xbox")
    parser.add_argument("--browser", action="store_true",
                        help='Browser-Fallback bei Cloudflare-Sperre (vorher: pip install "rivals-api[browser]")')
    parser.add_argument("-o", "--out", default="rivals-sync.json", help="Ausgabedatei")
    parser.add_argument("--chat", metavar="ID", help="Zusätzlich das Ergebnis als eine Zeile ausgeben (für den automatischen Abgleich der App)")
    parser.add_argument("--inbox", metavar="DATEI",
                        help="Zusätzlich das Ergebnis als fertiges Eingangs-Dokument {payload, at} in diese Datei schreiben "
                             "(der Sync-Helfer legt es mit ArtifactData in der App-Datenbank ab)")
    args = parser.parse_args()

    try:
        import rivals_api  # noqa: F401
    except ImportError:
        print("Bitte zuerst installieren:  python -m pip install rivals-api")
        return 1
    from rivals_api import CloudflareError, PlayerNotFoundError, PrivacyError, RivalsDataError

    def fail(console: str, short: str, *extra: str) -> int:
        print(console)
        for line in extra:
            print(line)
        if args.chat:
            print(chat_error(short, args.chat))
        if args.inbox:
            write_inbox(args.inbox, {"error": short, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return 1

    try:
        data = sync(args)
    except PlayerNotFoundError:
        return fail(f"Spieler „{args.player}“ nicht gefunden. Tipp: Probiere deine numerische UID.", "Spieler nicht gefunden")
    except PrivacyError:
        return fail("Dein Profil oder deine Match-History ist privat. Stelle sie im Spiel auf öffentlich.", "Profil oder Match-History ist privat")
    except CloudflareError:
        return fail('Cloudflare blockiert die Anfrage. Installiere  pip install "rivals-api[browser]"  '
                    "und starte das Skript mit --browser.", "Cloudflare blockiert die Anfrage")
    except RivalsDataError as exc:
        return fail(f"Abruf fehlgeschlagen: {exc}", f"Abruf fehlgeschlagen: {exc}",
                    "Prüfe deine Internetverbindung und versuche es später erneut "
                    '(bei Cloudflare-Problemen: pip install "rivals-api[browser]" und --browser).')

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"Fertig: {len(data['matches'])} Matches, {len(data['playerHeroes'])} Helden-Statistiken"
          f"{', globale Tierlist' if data['meta'] else ''} → {args.out}")
    for warning in data["warnings"][:5]:
        print(f"  Hinweis: {warning}")
    print("Jetzt im Rivals Coach unter „Daten → Rivals Data importieren“ einlesen.")
    if args.chat:
        print(chat_line(data, args.chat))
    if args.inbox:
        data["_id"] = args.chat or "auto-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        write_inbox(args.inbox, {"payload": json.dumps(data, ensure_ascii=False, separators=(",", ":")), "at": data["generated"]})
        print(f"Eingangs-Dokument geschrieben: {args.inbox} ({data['_id']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
