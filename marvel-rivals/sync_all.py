#!/usr/bin/env python3
"""Gratis-Abgleich für den Rivals Coach über GitHub Actions.

Liest eine Liste von Spielernamen (eine Zeile pro Name, Zeilen mit # am Anfang sind Kommentare), holt für jeden
die öffentlichen Daten von Rivals Data (über ``rivals_sync``) und schreibt pro Spieler eine Datei:

    <ausgabe>/<slug>.json          die Matches im Format von rivals_sync.py (die App liest sie ein)
    <ausgabe>/<slug>.error.json    nur wenn der Abruf scheiterte und es noch keine gute Datei gibt: {"error": "...", "at": "..."}

Den Dateinamen (``slug``) bildet ``rivals_sync.player_slug``; die App berechnet ihn genauso aus dem Spielernamen.
Scheitert der Abruf eines Spielers, bleibt seine letzte gute Datei erhalten und bekommt das Feld ``syncError``. Der Workflow ``.github/workflows/sync.yml``
ruft das Skript alle zwei Stunden auf und legt die Dateien im Branch ``sync-data`` ab.

Benutzung:
    python sync_all.py players.txt --out-dir out/data --limit 50 --prune
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import rivals_sync as rs


def read_players(path: str) -> list[str]:
    """Namen aus der Liste; doppelte Namen (gleicher Dateiname) zählen einmal."""
    names: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            names.setdefault(rs.player_slug(line), line)
    return list(names.values())


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch(name: str, limit: int, details: bool, rank: str, platform: int, known: dict | None = None) -> tuple[dict | None, str | None]:
    """Gibt (Daten, None) oder (None, Fehlertext) zurück. ``known``: schon abgerufene Matches (extId -> Match)."""
    from rivals_api import CloudflareError, PlayerNotFoundError, PrivacyError, RivalsDataError

    args = SimpleNamespace(player=name, limit=limit, details=details, rank=rank, platform=platform, browser=False, known=known)
    try:
        data = rs.sync(args)
    except PlayerNotFoundError:
        return None, "Spieler nicht gefunden (Name genau wie bei Rivals Data schreiben)"
    except PrivacyError:
        return None, "Profil oder Match-History ist privat (im Spiel auf öffentlich stellen)"
    except CloudflareError:
        return None, "Cloudflare blockiert die Anfrage"
    except RivalsDataError as exc:
        return None, f"Abruf fehlgeschlagen: {exc}"
    except Exception as exc:  # unerwartet: nicht den ganzen Lauf abbrechen
        return None, f"Unerwarteter Fehler: {type(exc).__name__}: {exc}"
    if not data["matches"]:
        why = next((w for w in data["warnings"] if w.startswith("Match-History nicht abrufbar")), None)
        if why:
            return None, why
    return data, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Rivals-Data-Abgleich für mehrere Spieler (GitHub Actions)")
    ap.add_argument("players", help="Datei mit den Spielernamen")
    ap.add_argument("--out-dir", default="data", help="Ausgabeordner (Standard: data)")
    ap.add_argument("--limit", type=int, default=50, help="Anzahl Matches pro Spieler")
    ap.add_argument("--no-details", dest="details", action="store_false", help="Ohne Match-Details (schneller, aber ohne Teams)")
    ap.add_argument("--rank", default="grandmaster_plus")
    ap.add_argument("--platform", default=1, type=int)
    ap.add_argument("--prune", action="store_true", help="Dateien von Spielern löschen, die nicht mehr in der Liste stehen")
    args = ap.parse_args()

    try:
        import rivals_api  # noqa: F401
    except ImportError:
        print("Bitte zuerst installieren:  python -m pip install rivals-api")
        return 1

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    names = read_players(args.players)
    print(f"{len(names)} Spieler in der Liste")
    if args.prune:
        keep = {rs.player_slug(n) for n in names}
        for f in sorted(out.glob("*.json")):
            if f.name.removesuffix(".error.json").removesuffix(".json") not in keep:
                f.unlink()
                print(f"- {f.name} gelöscht (Spieler steht nicht mehr in der Liste)")
    ok = failed = 0
    for name in names:
        slug = rs.player_slug(name)
        print(f"- {name} → {slug}")
        good, bad = out / f"{slug}.json", out / f"{slug}.error.json"
        known = None
        if good.exists():
            try:
                known = {str(m["extId"]): m for m in json.loads(good.read_text(encoding="utf-8")).get("matches", []) if m.get("extId")}
            except (OSError, ValueError, AttributeError, TypeError):
                known = None   # kaputte Datei: alles neu holen
        data, error = fetch(name, args.limit, args.details, args.rank, args.platform, known)
        if data is not None:
            good.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            bad.unlink(missing_ok=True)
            ok += 1
            print(f"  {len(data['matches'])} Matches, {len(data['warnings'])} Hinweise")
        else:
            stamp = {"error": error, "at": now()}
            if good.exists():
                # Die letzte gute Datei bleibt, trägt aber den Fehler (so sieht die App beides mit einer Anfrage)
                try:
                    old = json.loads(good.read_text(encoding="utf-8"))
                    old["syncError"] = stamp
                    good.write_text(json.dumps(old, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                except (OSError, ValueError):
                    bad.write_text(json.dumps(stamp, ensure_ascii=False), encoding="utf-8")
            else:
                bad.write_text(json.dumps(stamp, ensure_ascii=False), encoding="utf-8")
            failed += 1
            print(f"  FEHLER: {error}")
    print(f"Fertig: {ok} ok, {failed} mit Fehler")
    return 0


if __name__ == "__main__":
    sys.exit(main())
