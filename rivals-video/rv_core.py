"""Rivals Video: Kern (Video lesen, Funde erkennen, lernen, Daten speichern).

Alles läuft auf dem PC. Das Programm misst nur Farben an festen Stellen im Bild
(Grundlage: Notiz «Video-Erkennung» im Gehirn, Screenshots vom 08.11.2026):

- gelbe Zahl oben links = Zeit bis zum Wiedereinstieg; ihr Start ist der Tod.
  Solange sie läuft, zeigt das Spiel die Sicht eines Gegners oder Teammates,
  deren Anzeigen zählen nicht.
- heller Balken in der Kill-Anzeige oben rechts = eigener Kill.
- goldenes Ult-Feld unten rechts, das verschwindet = eigene Ult.

Lernen: Jede Antwort («stimmt», «stimmt nicht», «Tod ist hier», selbst markiert)
wird mit den Messwerten gespeichert. Daraus stellt das Programm die Schwellen und
die Zeitverschiebung des Todes nach. Die Messreihe jedes Videos liegt im Cache,
so lässt sich ein Video mit neuem Wissen ohne neues Dekodieren auswerten.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np

VERSION = "0.1.0"
FPS = 4                      # Bilder pro Sekunde für die Messung (Browser-Version: 1)
W, H = 480, 270              # Messbild (Bereiche sind relativ, das Seitenverhältnis spielt kaum eine Rolle)
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}
DATA_NAME = "rivals-video-daten.json"
CACHE_DIR = ".rivals-video-cache"
SUB_NEW, SUB_DONE = "Neu", "Ausgewertet"

REGIONS = {
    "cnt": (0.00, 0.02, 0.10, 0.13),
    "feed": (0.70, 0.02, 0.99, 0.14),
    "ult": (0.89, 0.84, 0.98, 0.97),
}
DEFAULT_THR = {"dead": 0.05, "kill": 0.012, "killQuiet": 0.005, "ultOn": 0.012, "ultOff": 0.004}
DEFAULT_LEAD = 1.0           # Tod: so viele Sekunden vor dem Auftauchen der gelben Zahl (Schätzung)
DEAD_MIN_S = 3.0             # die Zahl muss mindestens so lange bleiben
DEAD_GAP_S = 3.0             # Lücken bis so lange gehören zur selben Zeit bis zum Wiedereinstieg
AFTER_S = 1.5                # nach dem Wiedereinstieg so lange nichts werten
ULT_READY_S = 1.5            # Ult-Feld muss so lange golden sein
KILL_REFRACT_S = 1.0         # zwei Kills frühestens so weit auseinander

DEATH_CAUSES = ["Position", "Fluchtweg/Cooldown", "Gegnerische Ult", "Zu gierig", "Vom Team getrennt", "Sonstiges"]
KINDS = {"death": "Tod", "kill": "Kill", "ult": "Meine Ult", "eult": "Gegner-Ult", "win": "Fight gewonnen",
         "loss": "Fight verloren", "good": "Gut gemacht", "note": "Notiz"}


# ---------------------------------------------------------------- ffmpeg
def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg  # im Windows-Programm eingebaut
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        if found:
            return found
        raise RuntimeError("ffmpeg fehlt")


def _popen_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": 0x08000000}   # CREATE_NO_WINDOW
    return {}


def probe_duration(path: Path) -> float:
    """Länge in Sekunden aus der Ausgabe von «ffmpeg -i»."""
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       errors="replace", **_popen_kwargs())
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def iter_frames(path: Path, fps: int = FPS, stop: threading.Event | None = None):
    """Liefert (Zeit, Bild HxWx3 uint8). ffmpeg dekodiert und verkleinert."""
    cmd = [ffmpeg_exe(), "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={W}:{H}",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_popen_kwargs())
    n, i = W * H * 3, 0
    try:
        while True:
            if stop is not None and stop.is_set():
                break
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            yield i / fps, np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            i += 1
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        proc.wait()


# ---------------------------------------------------------------- Messen
def _crop(a: np.ndarray, r) -> np.ndarray:
    h, w = a.shape[:2]
    x0, y0, x1, y1 = r
    return a[int(y0 * h):max(int(y0 * h) + 1, int(y1 * h)), int(x0 * w):max(int(x0 * w) + 1, int(x1 * w))].astype(np.int16)


def features(a: np.ndarray) -> tuple[float, float, float]:
    """(cnt, feed, ug): Anteil gelber Pixel oben links, Anteil heller grauer Zeilen in der Kill-Anzeige,
    Anteil goldener Pixel im Ult-Feld. Gleiche Formeln wie in Rivals Coach (vidFeat)."""
    c = _crop(a, REGIONS["cnt"])
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    cnt = float(((r > 200) & (g > 170) & (b < 110) & (r - b > 110)).mean())
    c = _crop(a, REGIONS["feed"])
    mx, mn = c.max(axis=2), c.min(axis=2)
    feed = float((((mn > 175) & (mx - mn < 45)).mean(axis=1) > 0.45).mean())
    c = _crop(a, REGIONS["ult"])
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    ug = float(((r > 140) & (g > 100) & (b < 90) & (r - b > 80) & (r >= g)).mean())
    return round(cnt, 4), round(feed, 4), round(ug, 4)


def measure(path: Path, progress=None, stop: threading.Event | None = None) -> dict:
    """Messreihe eines Videos: {fps, t: [...], cnt: [...], feed: [...], ug: [...]}."""
    dur = probe_duration(path)
    ser = {"fps": FPS, "dur": dur, "t": [], "cnt": [], "feed": [], "ug": []}
    last = 0.0
    for t, frame in iter_frames(path, stop=stop):
        cnt, feed, ug = features(frame)
        ser["t"].append(round(t, 2)); ser["cnt"].append(cnt); ser["feed"].append(feed); ser["ug"].append(ug)
        if progress and dur and t - last >= 2:
            last = t
            progress(min(0.99, t / dur))
    if not ser["dur"] and ser["t"]:
        ser["dur"] = ser["t"][-1]
    return ser


# ---------------------------------------------------------------- Erkennen
def detect(ser: dict, thr: dict | None = None, lead: float | None = None) -> list[dict]:
    """Funde aus einer Messreihe. Gleiche Regeln wie in Rivals Coach (vidScanEvents), aber feiner (4 Bilder pro Sekunde)."""
    T = dict(DEFAULT_THR, **(thr or {}))
    lead = DEFAULT_LEAD if lead is None else lead
    fps = ser.get("fps", FPS)
    ts, cnt, feed, ug = ser["t"], ser["cnt"], ser["feed"], ser["ug"]
    out: list[dict] = []
    # Strecken mit gelber Zahl (Zeit bis zum Wiedereinstieg)
    runs, cur = [], None
    for i, t in enumerate(ts):
        if cnt[i] > T["dead"]:
            if cur and t - cur["end"] <= DEAD_GAP_S:
                cur["end"] = t; cur["n"] += 1
            else:
                cur = {"start": t, "end": t, "n": 1, "i": i}
                runs.append(cur)
    min_n = max(2, int(round(DEAD_MIN_S * fps)) - 1)
    starts = {r["i"] for r in runs if r["n"] >= min_n}
    last_dead, prev_feed, ready, last_kill = -1e9, 0.0, 0.0, -1e9
    step = 1.0 / fps
    for i, t in enumerate(ts):
        f = {"cnt": cnt[i], "feed": feed[i], "ug": ug[i]}
        if cnt[i] > T["dead"]:
            if i in starts:
                out.append({"t": round(max(0.0, t - lead), 2), "k": "death", "f": f, "raw": t})
            last_dead, ready, prev_feed = t, 0.0, feed[i]
            continue
        after = t - last_dead <= AFTER_S
        if (not after and feed[i] > T["kill"] and t - last_kill >= KILL_REFRACT_S
                and (prev_feed < T["killQuiet"] or feed[i] > prev_feed * 1.6 + 0.01)):
            out.append({"t": round(t, 2), "k": "kill", "f": f})
            last_kill = t
        prev_feed = feed[i]
        if ug[i] > T["ultOn"]:
            ready += step
        elif ug[i] < T["ultOff"]:
            if ready >= ULT_READY_S and not after:
                out.append({"t": round(t, 2), "k": "ult", "f": f})
            ready = 0.0
    return out


# ---------------------------------------------------------------- Dateiname → Aufnahmezeit
_TIME_RE = re.compile(r"(?:^|\D)(20\d\d)[.\-_]?(\d\d)[.\-_]?(\d\d)[ _\-T.]*(\d\d)[.\-_:h]?(\d\d)[.\-_:m]?(\d\d)(?!\d)")


def name_time(name: str) -> int:
    """Aufnahmezeit (ms seit 1970, Ortszeit) aus dem Dateinamen, sonst 0. Gleiche Regel wie vidNameTime."""
    m = _TIME_RE.search(name or "")
    if not m:
        return 0
    y, mo, d, hh, mi, ss = (int(x) for x in m.groups())
    if not (1 <= mo <= 12 and 1 <= d <= 31 and hh <= 23 and mi <= 59 and ss <= 59):
        return 0
    try:
        return int(datetime(y, mo, d, hh, mi, ss).timestamp() * 1000)
    except ValueError:
        return 0


def done_name(rec: dict) -> str:
    """Name für eine abgeschlossene Aufnahme: «Ausgewertet JJJJ-MM-TT HH-MM-SS.ext» (Zeit bleibt lesbar)."""
    ext = Path(rec["name"]).suffix or ".mp4"
    base = re.sub(r"^Ausgewertet\s+", "", Path(rec["name"]).stem, flags=re.I)
    if rec.get("start"):
        when = datetime.fromtimestamp(rec["start"] / 1000).strftime("%Y-%m-%d %H-%M-%S")
        core = when
    else:
        core = base
    core = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", core).strip()
    return f"Ausgewertet {core}{ext}"


# ---------------------------------------------------------------- Lernen
def learned(learn: dict) -> tuple[dict, float, dict]:
    """Schwellen und Zeitverschiebung aus den Beispielen. Gibt (Schwellen, lead, Bericht) zurück."""
    thr = dict(DEFAULT_THR)
    rep = {}
    ex = learn.get("examples", {})
    keymap = {"death": ("dead", "cnt"), "kill": ("kill", "feed"), "ult": ("ultOn", "ug")}
    for kind, (tk, fk) in keymap.items():
        pos = [e["v"] for e in ex.get(kind, []) if e.get("ok") and isinstance(e.get("v"), (int, float))]
        neg = [e["v"] for e in ex.get(kind, []) if e.get("ok") is False and isinstance(e.get("v"), (int, float))]
        r = {"stimmt": len(pos), "falsch": len(neg), "schwelle": thr[tk], "angepasst": False}
        if len(pos) >= 3 and neg:
            lo, hi = max(neg), min(pos)
            if lo < hi:
                thr[tk] = round((lo + hi) / 2, 4)
                r.update(schwelle=thr[tk], angepasst=True)
            else:
                r["hinweis"] = "Richtige und falsche Funde überschneiden sich, die Schwelle bleibt."
        elif len(pos) >= 3 and min(pos) > thr[tk] * 3:
            # nur richtige Funde, alle weit über der Schwelle: vorsichtig anheben gegen Fehlalarme
            thr[tk] = round(min(pos) / 2, 4)
            r.update(schwelle=thr[tk], angepasst=True)
        rep[kind] = r
    if thr["ultOn"] != DEFAULT_THR["ultOn"]:
        thr["ultOff"] = round(min(DEFAULT_THR["ultOff"], thr["ultOn"] / 3), 4)
    corr = [c["d"] if isinstance(c, dict) else c for c in learn.get("corrections", [])]
    corr = [c for c in corr if isinstance(c, (int, float))][-20:]
    lead = DEFAULT_LEAD
    if len(corr) >= 2:
        lead = round(max(-1.0, min(6.0, statistics.median(corr))), 2)
    rep["tod_zeit"] = {"korrekturen": len(corr), "sekunden_vor_der_zahl": lead}
    return thr, lead, rep


# ---------------------------------------------------------------- Daten
def vid_key(name: str, size: int) -> str:
    return f"{name}|{size}"


def vid_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def new_id() -> str:
    return uuid.uuid4().hex[:10]


class Store:
    """Daten im Ordner: rivals-video-daten.json (das liest auch Rivals Coach) und Messreihen im Cache-Ordner."""

    def __init__(self, base: Path):
        self.base = Path(base)
        self.lock = threading.RLock()
        (self.base / SUB_NEW).mkdir(parents=True, exist_ok=True)
        (self.base / SUB_DONE).mkdir(parents=True, exist_ok=True)
        self.cache = self.base / CACHE_DIR
        self.cache.mkdir(exist_ok=True)
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(str(self.cache), 0x02)   # versteckt
            except Exception:
                pass
        self.data = self._load()

    def _load(self) -> dict:
        p = self.base / DATA_NAME
        d = {}
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                bak = p.with_suffix(".kaputt.json")
                shutil.copyfile(p, bak)
                d = {}
        d.setdefault("format", "rivals-video")
        d["version"] = 1
        d.setdefault("videos", {})
        d.setdefault("learn", {"examples": {}, "corrections": []})
        d["learn"].setdefault("examples", {})
        d["learn"].setdefault("corrections", [])
        for k, v in list(d["videos"].items()):
            if not isinstance(v, dict):
                del d["videos"][k]
                continue
            v.setdefault("events", []); v.setdefault("marks", [])
            if v.get("status") == "läuft":
                v["status"] = "wartet"
        return d

    def save(self):
        with self.lock:
            self.data["updated"] = datetime.now().isoformat(timespec="seconds")
            self.data["program"] = VERSION
            p = self.base / DATA_NAME
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, p)

    # Dateien im Ordner
    def files(self) -> list[tuple[Path, str]]:
        out = []
        for sub in (SUB_NEW, SUB_DONE):
            for p in sorted((self.base / sub).rglob("*")):
                if p.is_file() and p.suffix.lower() in VIDEO_EXT and CACHE_DIR not in p.parts:
                    out.append((p, sub))
        return out

    def sync_files(self) -> list[str]:
        """Neue Dateien aufnehmen, umbenannte an der Grösse wiedererkennen. Gibt Schlüssel zurück, die eine Auswertung brauchen."""
        with self.lock:
            V = self.data["videos"]
            seen, todo = set(), []
            for p, sub in self.files():
                size = p.stat().st_size
                key = vid_key(p.name, size)
                if key not in V:
                    old = next((k for k, v in V.items() if v.get("size") == size and k not in seen
                                and not (self.base / v.get("path", "")).exists()), None)
                    if old:
                        V[key] = V.pop(old)
                        V[key].setdefault("names", []).append(V[key]["name"])
                        V[key]["name"] = p.name
                        oc, nc = self.cache / (vid_id(old) + ".json"), self.cache / (vid_id(key) + ".json")
                        if oc.exists() and not nc.exists():
                            os.replace(oc, nc)
                    else:
                        V[key] = {"name": p.name, "size": size, "start": name_time(p.name), "dur": 0,
                                  "mtime": int(p.stat().st_mtime * 1000), "status": "wartet", "events": [], "marks": [],
                                  "added": datetime.now().isoformat(timespec="seconds")}
                rec = V[key]
                rec["path"] = str(p.relative_to(self.base))
                rec["folder"] = sub
                rec["id"] = vid_id(key)
                seen.add(key)
                if rec.get("status") in ("wartet", None) and sub == SUB_NEW:
                    todo.append(key)
            for k, v in V.items():
                v["missing"] = k not in seen
            return todo

    def by_id(self, vid: str):
        with self.lock:
            for k, v in self.data["videos"].items():
                if v.get("id") == vid:
                    return k, v
        return None, None

    def series(self, key: str) -> dict | None:
        p = self.cache / (vid_id(key) + ".json")
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def save_series(self, key: str, ser: dict):
        (self.cache / (vid_id(key) + ".json")).write_text(json.dumps(ser, separators=(",", ":")), encoding="utf-8")

    # Erkennung anwenden, Antworten behalten
    def apply_detect(self, key: str, ser: dict):
        with self.lock:
            rec = self.data["videos"][key]
            thr, lead, _ = learned(self.data["learn"])
            old = rec.get("events", [])
            evs = []
            for e in detect(ser, thr, lead):
                o = next((x for x in old if x["k"] == e["k"] and abs(x["t"] - e["t"]) <= 2.0 and isinstance(x.get("ok"), bool)), None)
                evs.append({"id": o["id"] if o else new_id(), "t": e["t"], "k": e["k"], "f": e["f"], "raw": e.get("raw", e["t"]),
                            "ok": o["ok"] if o else None, "mk": o.get("mk", "") if o else ""})
            # bestätigte Funde, die jetzt nicht mehr gefunden werden, bleiben als Markierung erhalten (mk)
            rec["events"] = evs
            rec["dur"] = round(ser.get("dur") or 0, 1)
            if not rec.get("start") and rec.get("mtime") and rec["dur"]:
                rec["start"] = int(rec["mtime"] - rec["dur"] * 1000)   # Ende der Aufnahme minus Länge
            rec["status"] = "fertig"
            rec["analyzed"] = datetime.now().isoformat(timespec="seconds")
            rec["learnedWith"] = {"thr": thr, "lead": lead}

    # Antworten
    def _example(self, kind: str, f: dict, ok: bool):
        k = {"death": "cnt", "kill": "feed", "ult": "ug"}.get(kind)
        if not k or not f:
            return
        lst = self.data["learn"]["examples"].setdefault(kind, [])
        lst.append({"v": f.get(k), "ok": ok, "at": int(time.time())})
        del lst[:-200]

    def answer(self, key: str, eid: str, ok: bool | None) -> dict:
        with self.lock:
            rec = self.data["videos"][key]
            e = next(x for x in rec["events"] if x["id"] == eid)
            prev = e.get("ok")
            e["ok"] = ok
            if ok is True and prev is not True:
                near = next((m for m in rec["marks"] if m["k"] == e["k"] and abs(m["t"] - e["t"]) <= 4), None)
                mk = near or {"id": new_id(), "t": e["t"], "k": e["k"], "auto": 1}
                if not near:
                    rec["marks"].append(mk)
                e["mk"] = mk["id"]
            if ok is False and e.get("mk"):
                rec["marks"] = [m for m in rec["marks"] if not (m["id"] == e["mk"] and m.get("auto"))]
                e["mk"] = ""
            if isinstance(ok, bool):
                self._example(e["k"], e.get("f"), ok)
            self.save()
            return rec

    def add_mark(self, key: str, t: float, kind: str) -> dict:
        with self.lock:
            rec = self.data["videos"][key]
            mk = {"id": new_id(), "t": round(float(t), 2), "k": kind}
            rec["marks"].append(mk)
            # übersehen? Messwert an dieser Stelle als richtiges Beispiel lernen
            ser = self.series(key)
            if ser and kind in ("death", "kill", "ult") and not any(e["k"] == kind and abs(e["t"] - mk["t"]) <= 4 for e in rec["events"]):
                fk = {"death": "cnt", "kill": "feed", "ult": "ug"}[kind]
                lo, hi = (mk["t"], mk["t"] + 4) if kind == "death" else (mk["t"] - 1, mk["t"] + 2)
                vals = [ser[fk][i] for i, t in enumerate(ser["t"]) if lo <= t <= hi]
                if vals:
                    self._example(kind, {fk: max(vals)}, True)
                    mk["missed"] = 1
            self.save()
            return mk

    def update_mark(self, key: str, mid: str, fields: dict) -> dict:
        with self.lock:
            rec = self.data["videos"][key]
            mk = next(m for m in rec["marks"] if m["id"] == mid)
            for f in ("c", "v", "h", "n"):
                if f in fields:
                    if fields[f]:
                        mk[f] = str(fields[f])[:300]
                    else:
                        mk.pop(f, None)
            if "t" in fields:
                nt = round(float(fields["t"]), 2)
                e = next((x for x in rec["events"] if x.get("mk") == mid and x["k"] == "death"), None)
                if e is not None:
                    # «Tod ist hier»: wie viele Sekunden lag der Tod vor dem Auftauchen der gelben Zahl?
                    cl = [c for c in self.data["learn"]["corrections"] if not (isinstance(c, dict) and c.get("e") == e["id"])]
                    cl.append({"e": e["id"], "d": round(e.get("raw", e["t"]) - nt, 2)})   # pro Tod zählt die letzte Korrektur
                    self.data["learn"]["corrections"] = cl[-50:]
                mk["t"] = nt
            self.save()
            return mk

    def delete_mark(self, key: str, mid: str):
        with self.lock:
            rec = self.data["videos"][key]
            rec["marks"] = [m for m in rec["marks"] if m["id"] != mid]
            for e in rec["events"]:
                if e.get("mk") == mid:
                    e["mk"] = ""
                    e["ok"] = None
            self.save()

    def finish(self, key: str) -> str:
        """Abschliessen: nach «Ausgewertet» verschieben und umbenennen. Gibt den neuen Schlüssel zurück."""
        with self.lock:
            rec = self.data["videos"][key]
            src = self.base / rec["path"]
            name = done_name(rec)
            dst = self.base / SUB_DONE / name
            i = 2
            while dst.exists() and dst.resolve() != src.resolve():
                dst = self.base / SUB_DONE / f"{Path(name).stem} ({i}){Path(name).suffix}"
                i += 1
            if src.exists() and dst.resolve() != src.resolve():
                os.replace(src, dst)
            new_key = vid_key(dst.name, rec["size"])
            if new_key != key:
                self.data["videos"][new_key] = self.data["videos"].pop(key)
                oc, nc = self.cache / (vid_id(key) + ".json"), self.cache / (vid_id(new_key) + ".json")
                if oc.exists():
                    os.replace(oc, nc)
            rec = self.data["videos"][new_key]
            rec.setdefault("names", []).append(rec["name"])
            rec.update(name=dst.name, path=str(dst.relative_to(self.base)), folder=SUB_DONE, id=vid_id(new_key),
                       done=int(time.time() * 1000))
            self.save()
            return new_key

    def reopen(self, key: str):
        with self.lock:
            self.data["videos"][key].pop("done", None)
            self.save()


# ---------------------------------------------------------------- Selbsttest (ohne private Bilder)
def selftest(tmp: Path) -> int:
    """Erzeugt ein Testvideo mit gelbem Feld oben links (3–7 s) und prüft, dass genau ein Tod gefunden wird."""
    tmp.mkdir(parents=True, exist_ok=True)
    vid = tmp / "selbsttest.mp4"
    cmd = [ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x101828:s=1280x720:d=10:r=30",
           "-vf", "drawbox=x=10:y=20:w=110:h=70:color=0xF5D232@1:t=fill:enable='between(t,3,7)'",
           "-pix_fmt", "yuv420p", str(vid)]
    subprocess.run(cmd, check=True, **_popen_kwargs())
    ser = measure(vid)
    evs = detect(ser)
    deaths = [e for e in evs if e["k"] == "death"]
    ok = len(deaths) == 1 and 1.5 <= deaths[0]["t"] <= 3.0 and abs(ser["dur"] - 10) < 0.6
    print(f"Selbsttest: {len(ser['t'])} Bilder, Länge {ser['dur']:.1f} s, Funde {evs}")
    print("Selbsttest OK" if ok else "Selbsttest FEHLER")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(selftest(Path(sys.argv[1] if len(sys.argv) > 1 else "selbsttest")))
