#!/usr/bin/env python3
"""Baut die private Artifact-Version des Rivals Coach, optional mit Heldenbildern.

Die Heldenbilder gehören Marvel/NetEase. Deshalb stehen sie NICHT im öffentlichen Repo.
Dieses Skript holt sie bei Bedarf aus dem Marvel-Rivals-Wiki (wiki.gg) und setzt sie nur in die
Artifact-Datei ein. Ohne Bilder zeigt die App Initialen mit Rollenring.

  python3 app_build.py icons      # lädt die Heldenbilder nach hero_img.json (braucht Pillow)
  python3 app_build.py artifact   # schreibt artifact/rivals-coach.html (mit Bildern und deinen privaten Werten)
  python3 app_build.py friends    # schreibt artifact/rivals-coach-friends.html (ohne Bilder, ohne private Werte)

Die Ausgabedateien sind per .gitignore vom Repo ausgeschlossen. Private Werte (dein Artifact-Link, deine
Sync-Sitzung) stehen in private.json, die ebenfalls nicht ins Repo kommt:
  {"ONLINE_URL": "https://claude.ai/artifact/…", "SYNC_HELPER": "session_…"}
"""
import base64
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE / "app" / "index.html"
IMG = HERE / "hero_img.json"
PRIVATE = HERE / "private.json"
OUT = HERE / "artifact" / "rivals-coach.html"
OUT_FRIENDS = HERE / "artifact" / "rivals-coach-friends.html"
API = "https://marvelrivals.wiki.gg/api.php"
UA = {"User-Agent": "RivalsCoach/1.0 (persönliche Trainings-App; github.com/Jumagirl/bildung6)"}
# Wiki-Dateinamen, die vom Muster „<Name> Icon.png“ abweichen
ALT = {"Cyclops": "Cyclops.png", "Black Cat": "Black Cat.png", "Devil Dinosaur": "Devil Dinosaur.png", "Jeff the Land Shark": "Jeff The Landshark Icon.png"}


def api(**kw):
    kw["format"] = "json"
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(kw), headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def hero_names():
    s = APP.read_text(encoding="utf-8")
    a = s.index("const DEFAULT_HEROES")
    b = s.index("];", a)
    names = [re.sub(r" \(.*\)", "", n) for n in re.findall(r'\{ name: "([^"]+)"', s[a:b])]
    return list(dict.fromkeys(names))


def icons():
    from PIL import Image
    names = hero_names()
    files = {n: ALT.get(n, f"{n} Icon.png") for n in names}
    out, missing = {}, []
    items = list(files.items())
    for i in range(0, len(items), 20):
        chunk = items[i:i + 20]
        d = api(action="query", titles="|".join("File:" + f for _, f in chunk), prop="imageinfo", iiprop="url")
        info = {p["title"]: (p.get("imageinfo") or [None])[0] for p in d["query"]["pages"].values()}
        for name, f in chunk:
            ii = info.get("File:" + f)
            if not ii:
                missing.append(name)
                continue
            data = urllib.request.urlopen(urllib.request.Request(ii["url"], headers=UA), timeout=30).read()
            im = Image.open(io.BytesIO(data)).convert("RGBA")
            w, h = im.size
            m = min(w, h)
            im = im.crop(((w - m) // 2, (h - m) // 2, (w - m) // 2 + m, (h - m) // 2 + m)).resize((80, 80), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=82, method=6)
            out[name] = "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
            time.sleep(0.25)
    IMG.write_text(json.dumps(out), encoding="utf-8")
    print(f"{len(out)} Bilder gespeichert, ohne Bild: {', '.join(missing) or '–'}")


def strip_wrapper(s):
    a = s.index("<title>")
    b = s.rindex("</script>") + len("</script>")
    return s[a:b]


def artifact(friends=False):
    s = APP.read_text(encoding="utf-8")
    if not friends and IMG.exists():
        imgs = json.loads(IMG.read_text(encoding="utf-8"))
        a, b = s.index("/* HERO-IMG:BEGIN */"), s.index("/* HERO-IMG:END */")
        s = s[:a] + "/* HERO-IMG:BEGIN */\nconst HERO_IMG = " + json.dumps(imgs, separators=(",", ":")) + ";\n" + s[b:]
        print(f"{len(imgs)} Heldenbilder eingesetzt")
    else:
        print("Ohne Heldenbilder" + ("" if friends else " (erst `icons` ausführen)"))
    if not friends and PRIVATE.exists():
        for key, value in json.loads(PRIVATE.read_text(encoding="utf-8")).items():
            old = f'const {key} = ""; /* PRIVATE:{key} */'
            if old not in s:
                print(f"Platzhalter für {key} fehlt")
                continue
            s = s.replace(old, f"const {key} = {json.dumps(value)};")
        print("Private Werte eingesetzt")
    elif not friends:
        print("Keine private.json: Online-Link und Sync-Helfer bleiben leer")
    out = OUT_FRIENDS if friends else OUT
    out.parent.mkdir(exist_ok=True)
    out.write_text(strip_wrapper(s), encoding="utf-8")
    print(f"{out} geschrieben ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "icons":
        icons()
    elif cmd == "artifact":
        artifact()
    elif cmd == "friends":
        artifact(friends=True)
    else:
        print(__doc__)
