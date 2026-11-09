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
import struct
import threading
import zlib
import time
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np

VERSION = "0.3.0"
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
SER_V = 2                    # Version der Messreihe: ältere werden neu gemessen (0.2.0: HDR umgerechnet, Kill-Feed-Farben)
NPL = 203                    # HDR: so viele Nits gelten als Weiss (Bezugsweiss nach ITU-R BT.2408); normale Farben bleiben so fast gleich
FIGHT_GAP_S = 8.0            # Ereignisse bis so weit auseinander gehören zum selben Fight
STABLE_S = 8.0               # eine Datei gilt als fertig kopiert, wenn sie sich so lange nicht ändert
RETRY_S = [60, 300, 1800]    # nach einem Fehler: so viele Sekunden bis zum nächsten Versuch

DEATH_CAUSES = ["Position", "Fluchtweg/Cooldown", "Gegnerische Ult", "Zu gierig", "Vom Team getrennt", "Sonstiges"]


def _load_data() -> dict:
    """Genaue Todesursachen pro Rolle und Helden: aus Rivals Coach erzeugt (tools/make_rv_data.js), damit beide dieselben Wörter nutzen."""
    for base in (getattr(sys, "_MEIPASS", None), Path(__file__).resolve().parent):
        f = Path(base or ".") / "rv_data.json"
        if base and f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {"groups": DEATH_CAUSES, "ultGroup": "Gegnerische Ult", "roles": {}, "heroes": []}


RV_DATA = _load_data()


def cause_group(label: str) -> str:
    """Gruppe einer Ursache (die Gruppe selbst oder eine genaue Ursache darin)."""
    if label in RV_DATA["groups"]:
        return label
    for gs in RV_DATA.get("roles", {}).values():
        for g in gs:
            if label in g["causes"]:
                return g["group"]
    return ""
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


def probe(path: Path) -> dict:
    """Länge und Farbraum aus der Ausgabe von «ffmpeg -i». trc: "pq" (HDR10, so nimmt die PS5 mit HDR auf), "hlg" oder ""."""
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       errors="replace", **_popen_kwargs())
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    vs = next((ln for ln in p.stderr.splitlines() if "Video:" in ln), "")
    trc = "pq" if "smpte2084" in vs else "hlg" if "arib-std-b67" in vs else ""
    return {"dur": dur, "trc": trc, "bt2020": "bt2020" in vs, "stream": vs.strip()[:200]}


def probe_duration(path: Path) -> float:
    return probe(path)["dur"]


_FILTERS: dict[str, bool] = {}


def has_filter(name: str) -> bool:
    """Kann das mitgelieferte ffmpeg diesen Filter? (zscale/tonemap für HDR fehlen in manchen Builds)"""
    if not _FILTERS:
        p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-filters"], capture_output=True, text=True, errors="replace", **_popen_kwargs())
        for ln in p.stdout.splitlines():
            parts = ln.split()
            if len(parts) >= 2:
                _FILTERS[parts[1]] = True
        _FILTERS["_"] = True
    return bool(_FILTERS.get(name))


def color_mode(info: dict) -> str:
    """"sdr" normal, "zscale" HDR mit ffmpeg umrechnen, "lut" HDR (PQ) selbst umrechnen, "hlg" HLG ohne passende Filter (ungenau)."""
    if not info.get("trc"):
        return "sdr"
    if has_filter("zscale") and has_filter("tonemap"):
        return "zscale"
    return "lut" if info["trc"] == "pq" else "hlg"


def _vf(info: dict, fps: int | None) -> tuple[str, str]:
    """Filterkette und Pixelformat. HDR wird auf normale Farben gebracht, damit Gelb wieder Gelb ist:
    linear mit NPL Nits als Weiss, Primärfarben BT.709, sanft gekappt (mobius), dann BT.709. Normale Videos bleiben wie bisher."""
    mode = color_mode(info)
    pre = f"fps={fps}," if fps else ""
    if mode == "zscale":
        tin = "smpte2084" if info["trc"] == "pq" else "arib-std-b67"
        return (pre + f"zscale=w={W}:h={H}:tin={tin}:min=bt2020nc:pin=bt2020:rin=tv:t=linear:npl={NPL},format=gbrpf32le,"
                "zscale=p=bt709,tonemap=tonemap=mobius:desat=0,zscale=t=bt709:m=bt709:r=pc,format=rgb24"), "rgb24"
    if mode == "lut":
        return pre + f"scale={W}:{H}:in_color_matrix=bt2020:in_range=tv:out_range=full", "rgb48le"
    return pre + f"scale={W}:{H}", "rgb24"


# PQ selbst umrechnen (wenn ffmpeg kein zscale hat): PQ → Nits → linear (NPL = 1) → BT.2020 nach BT.709 → sanft kappen → BT.709
_M1, _M2, _C1, _C2, _C3 = 2610 / 16384, 2523 / 4096 * 128, 3424 / 4096, 2413 / 4096 * 32, 2392 / 4096 * 32
_P2020_709 = np.array([[1.6605, -0.5876, -0.0728], [-0.1246, 1.1329, -0.0083], [-0.0182, -0.1006, 1.1187]], dtype=np.float32)


def pq_to_sdr(a16: np.ndarray) -> np.ndarray:
    e = np.clip(a16.astype(np.float32) / 65535.0, 0, 1)
    ep = np.power(e, 1 / _M2)
    lin = np.power(np.maximum(ep - _C1, 0) / (_C2 - _C3 * ep), 1 / _M1) * (10000.0 / NPL)
    lin = np.clip(lin @ _P2020_709.T, 0, None)
    j = 0.8   # bis hier unverändert, darüber sanft gegen 1 (wie mobius)
    lin = np.where(lin <= j, lin, j + (1 - j) * (lin - j) / ((lin - j) + (1 - j)))
    v = np.where(lin < 0.018, 4.5 * lin, 1.099 * np.power(lin, 0.45) - 0.099)
    return np.clip(v * 255 + 0.5, 0, 255).astype(np.uint8)


def iter_frames(path: Path, fps: int = FPS, stop: threading.Event | None = None, info: dict | None = None):
    """Liefert (Zeit, Bild HxWx3 uint8). ffmpeg dekodiert, verkleinert und rechnet HDR auf normale Farben um."""
    info = info if info is not None else probe(path)
    vf, pix = _vf(info, fps)
    cmd = [ffmpeg_exe(), "-v", "error", "-i", str(path), "-vf", vf,
           "-f", "rawvideo", "-pix_fmt", pix, "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_popen_kwargs())
    errs: list[str] = []

    def drain():
        for line in iter(proc.stderr.readline, b""):
            errs.append(line.decode("utf-8", "replace").strip())
            del errs[:-8]
    threading.Thread(target=drain, daemon=True).start()
    iter_frames.last_errors = errs
    wide = pix == "rgb48le"
    n, i = W * H * 3 * (2 if wide else 1), 0
    try:
        while True:
            if stop is not None and stop.is_set():
                break
            buf = proc.stdout.read(n)
            if len(buf) < n:
                break
            yield i / fps, (pq_to_sdr(np.frombuffer(buf, "<u2").reshape(H, W, 3)) if wide else np.frombuffer(buf, np.uint8).reshape(H, W, 3))
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


def feed_colors(a: np.ndarray, prev: np.ndarray | None) -> tuple[float, float, float, np.ndarray]:
    """Kill-Feed (für Fights): Anteil rötlicher und bläulicher Pixel und wie stark sich der Bereich seit dem letzten Bild geändert hat
    (eine neue Zeile). Welche Farbe zu welchem Team gehört, steht nirgends fest: Das lernt das Programm aus deinen Antworten."""
    c = _crop(a, REGIONS["feed"])
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    fr = float(((r > 150) & (r - g > 60) & (r - b > 50)).mean())
    fb = float(((b > 140) & (b - r > 50) & (b - g > 0)).mean())
    fa = float(np.abs(c - prev).mean() / 255.0) if prev is not None and prev.shape == c.shape else 0.0
    return round(fr, 4), round(fb, 4), round(fa, 4), c


def series_summary(ser: dict, thr: dict | None = None) -> dict:
    """Kurzfassung für die Diagnose: höchster Wert und wie oft die Schwelle erreicht wird."""
    T = dict(DEFAULT_THR, **(thr or {}))
    out = {}
    for k, tk in (("cnt", "dead"), ("feed", "kill"), ("ug", "ultOn")):
        v = ser.get(k) or []
        if v:
            srt = sorted(v)
            out[k] = {"max": round(srt[-1], 4), "p99": round(srt[int(len(srt) * 0.99) - 1 if len(srt) > 1 else 0], 4),
                      "over": round(sum(1 for x in v if x > T[tk]) / len(v), 4), "thr": T[tk]}
    return out


def measure(path: Path, progress=None, stop: threading.Event | None = None) -> dict:
    """Messreihe eines Videos: {v, fps, dur, hdr, tm, t: [...], cnt, feed, ug, fr, fb, fa}."""
    info = probe(path)
    dur = info["dur"]
    ser = {"v": SER_V, "fps": FPS, "dur": dur, "hdr": info["trc"], "tm": color_mode(info),
           "t": [], "cnt": [], "feed": [], "ug": [], "fr": [], "fb": [], "fa": []}
    last, prev = 0.0, None
    for t, frame in iter_frames(path, stop=stop, info=info):
        cnt, feed, ug = features(frame)
        fr, fb, fa, prev = feed_colors(frame, prev)
        ser["t"].append(round(t, 2)); ser["cnt"].append(cnt); ser["feed"].append(feed); ser["ug"].append(ug)
        ser["fr"].append(fr); ser["fb"].append(fb); ser["fa"].append(fa)
        if progress and dur and t - last >= 2:
            last = t
            progress(min(0.99, t / dur))
    if stop is not None and stop.is_set():
        return ser
    errs = [e for e in getattr(iter_frames, "last_errors", []) if e]
    if not ser["t"]:
        raise RuntimeError("Das Video liess sich nicht lesen." + (" ffmpeg: " + " | ".join(errs[-3:]) if errs else ""))
    if dur and ser["t"][-1] < dur - 5:
        raise RuntimeError(f"Nur {ser['t'][-1]:.0f} von {dur:.0f} Sekunden gelesen. Die Datei ist vielleicht noch nicht fertig kopiert oder beschädigt."
                           + (" ffmpeg: " + " | ".join(errs[-3:]) if errs else ""))
    if not ser["dur"]:
        ser["dur"] = ser["t"][-1]
    ser["sum"] = series_summary(ser)
    return ser


def grab_frame(path: Path, t: float) -> tuple[np.ndarray, dict]:
    """Ein Bild an der Stelle t, so wie das Programm es misst (gleiche Umrechnung)."""
    info = probe(path)
    vf, pix = _vf(info, None)
    cmd = [ffmpeg_exe(), "-v", "error", "-ss", f"{max(0.0, float(t)):.2f}", "-i", str(path), "-frames:v", "1", "-vf", vf,
           "-f", "rawvideo", "-pix_fmt", pix, "-"]
    r = subprocess.run(cmd, capture_output=True, **_popen_kwargs())
    n = W * H * 3 * (2 if pix == "rgb48le" else 1)
    if len(r.stdout) < n:
        raise RuntimeError("Das Bild liess sich nicht lesen. " + r.stderr.decode("utf-8", "replace").strip()[-200:])
    buf = r.stdout[:n]
    a = pq_to_sdr(np.frombuffer(buf, "<u2").reshape(H, W, 3)) if pix == "rgb48le" else np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    return a, {"trc": info["trc"], "tm": color_mode(info)}


def png_bytes(a: np.ndarray) -> bytes:
    """Kleiner PNG-Schreiber (ohne Zusatzpakete)."""
    h, w = a.shape[:2]
    raw = b"".join(b"\x00" + a[y].astype(np.uint8).tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def diag_image(a: np.ndarray) -> np.ndarray:
    """Bild mit den drei Messbereichen als Rahmen: gelb (Respawn-Zahl), weiss (Kill-Anzeige), gold (Ult-Feld)."""
    out = a.copy()
    cols = {"cnt": (255, 230, 0), "feed": (255, 255, 255), "ult": (255, 160, 0)}
    h, w = out.shape[:2]
    for k, (x0, y0, x1, y1) in REGIONS.items():
        X0, Y0, X1, Y1 = int(x0 * w), int(y0 * h), min(w - 1, int(x1 * w)), min(h - 1, int(y1 * h))
        c = cols[k]
        out[Y0:Y0 + 2, X0:X1] = c; out[Y1 - 1:Y1 + 1, X0:X1] = c; out[Y0:Y1, X0:X0 + 2] = c; out[Y0:Y1, X1 - 1:X1 + 1] = c
    return out


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


# ---------------------------------------------------------------- Fights (Versuch)
def fights(ser: dict, events: list[dict]) -> list[dict]:
    """Fight-Vorschläge: mindestens zwei deiner Ereignisse (Kill, Tod, deine Ult) höchstens FIGHT_GAP_S Sekunden auseinander.
    Die Bildänderung im Kill-Feed-Bereich (fa) taugt dafür nicht: Der Bereich liegt über der Spielwelt, die sich mit der Kamera ständig bewegt.
    score: Anteil bläulicher minus rötlicher Pixel im Kill-Feed während des Fights (−1 bis 1). Ob und wie das mit «gewonnen» zusammenhängt,
    lernt das Programm erst aus deinen Antworten (learned_fights). Fights ohne eigenen Kill, Tod oder Ult findet es nicht (Versuch)."""
    if not ser.get("fr"):
        return []
    ts = ser["t"]
    pts = sorted(e["t"] for e in events if e["k"] in ("death", "kill", "ult"))
    groups: list[list[float]] = []
    for t in pts:
        if groups and t - groups[-1][-1] <= FIGHT_GAP_S:
            groups[-1].append(t)
        else:
            groups.append([t])
    out = []
    for g in groups:
        if len(g) < 2:
            continue
        s0, s1 = max(0.0, g[0] - 3), g[-1] + 3
        idx = [i for i, t in enumerate(ts) if s0 <= t <= s1]
        R, B = sum(ser["fr"][i] for i in idx), sum(ser["fb"][i] for i in idx)
        out.append({"t": round(s0, 2), "e": round(s1, 2), "n": len(g), "score": round((B - R) / (B + R), 3) if B + R > 0 else 0.0})
    return out


def learned_fights(ex: list[dict]) -> dict:
    """Aus deinen Antworten (gewonnen/verloren mit score) eine Regel: ab mindestens 3 von beiden, wenn sie sich klar trennen."""
    W = [e["s"] for e in ex if e.get("res") == "win" and isinstance(e.get("s"), (int, float))]
    L = [e["s"] for e in ex if e.get("res") == "loss" and isinstance(e.get("s"), (int, float))]
    r = {"gewonnen": len(W), "verloren": len(L), "gelernt": False}
    if len(W) >= 3 and len(L) >= 3:
        mw, ml = statistics.median(W), statistics.median(L)
        if abs(mw - ml) >= 0.15:
            thr, d = (mw + ml) / 2, 1 if mw > ml else -1
            hit = sum(1 for x in W if d * (x - thr) > 0) + sum(1 for x in L if d * (x - thr) <= 0)
            acc = hit / (len(W) + len(L))
            r.update(treffer=round(acc, 2))
            if acc >= 0.7:
                r.update(gelernt=True, thr=round(thr, 3), dir=d)
        else:
            r["hinweis"] = "Gewonnene und verlorene Fights sehen im Kill-Feed noch gleich aus."
    return r


def ult_score(ser: dict, t: float, events: list[dict]) -> float:
    """Ult-Wirkung (Versuch): Wie ändert sich der Kill-Feed nach deiner Ult (bläulich minus rötlich, 8 s danach gegen 8 s davor),
    dazu deine Kills in den 10 s danach. Die Wirkung selbst (Heilung, Rettung) sieht das Programm nicht; ob der Wert dazu passt,
    zeigt erst der Vergleich mit deinen Bewertungen (learned_ulteff)."""
    if not ser.get("fr"):
        return 0.0
    ts = ser["t"]
    def bal(a, b):
        idx = [i for i, x in enumerate(ts) if a <= x < b]
        return sum(ser["fb"][i] - ser["fr"][i] for i in idx) / len(idx) if idx else 0.0
    kills = sum(1 for e in events if e["k"] == "kill" and t < e["t"] <= t + 10)
    return round(bal(t, t + 8) - bal(t - 8, t) + 0.1 * min(kills, 3), 4)


def learned_ulteff(ex: list[dict]) -> dict:
    """Aus deinen Bewertungen «mit Wirkung» und «ohne Wirkung» eine Regel: ab je 4, wenn sie sich klar trennen und mindestens 70 % stimmen."""
    J = [e["s"] for e in ex if e.get("v") == "ja" and isinstance(e.get("s"), (int, float))]
    N = [e["s"] for e in ex if e.get("v") == "nein" and isinstance(e.get("s"), (int, float))]
    r = {"mit": len(J), "ohne": len(N), "gelernt": False}
    if len(J) >= 4 and len(N) >= 4:
        mj, mn = statistics.median(J), statistics.median(N)
        if abs(mj - mn) >= 0.02:
            thr, d = (mj + mn) / 2, 1 if mj > mn else -1
            hit = sum(1 for x in J if d * (x - thr) > 0) + sum(1 for x in N if d * (x - thr) <= 0)
            acc = hit / (len(J) + len(N))
            r.update(treffer=round(acc, 2))
            if acc >= 0.7:
                r.update(gelernt=True, thr=round(thr, 4), dir=d)
        else:
            r["hinweis"] = "Ults mit und ohne Wirkung sehen im Kill-Feed noch gleich aus."
    return r


def ulteff_pred(score: float, ul: dict) -> str:
    if not ul.get("gelernt"):
        return ""
    return "ja" if ul["dir"] * (score - ul["thr"]) > 0 else "nein"


def fight_pred(score: float, fl: dict) -> str:
    if not fl.get("gelernt"):
        return ""
    return "win" if fl["dir"] * (score - fl["thr"]) > 0 else "loss"


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


# ---------------------------------------------------------------- Für die Cloud (0.3.0)
# Kleine Dateien für Rivals Coach: Die App nimmt höchstens 20 MiB pro Datei. Das Programm macht deshalb Stücke:
# Highlights (die Stellen aus dem Kurz-Review) und das ganze Video. H.264 in MP4, 960 Pixel breit, ohne Ton
# (im Ton können Stimmen von Teammates sein), HDR wie beim Messen auf normale Farben umgerechnet.
CLOUD_DIR = "Für die Cloud"
CLOUD_V = 1
CLOUD_W, CLOUD_FPS = 960, 30
CLOUD_MAX = 19 * 1024 * 1024        # darüber wird ein Stück mit weniger Datenrate neu gemacht
CLOUD_TARGET = 17 * 1024 * 1024     # so gross soll ein Stück im Mittel höchstens werden
HL_KBPS, FULL_KBPS = 1200, 900      # Datenrate Bild (kbit/s): Highlights etwas schärfer


def piece_seconds(kbps: int) -> int:
    """Länge eines Stücks, damit es bei dieser Datenrate unter CLOUD_TARGET bleibt (1200 kbit/s: 118 s, 900 kbit/s: 158 s)."""
    return int(CLOUD_TARGET * 8 / (kbps * 1000))


_ENCODERS: dict[str, bool] = {}


def has_encoder(name: str) -> bool:
    if not _ENCODERS:
        p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-encoders"], capture_output=True, text=True, errors="replace", **_popen_kwargs())
        for ln in p.stdout.splitlines():
            parts = ln.split()
            if len(parts) >= 2:
                _ENCODERS[parts[1]] = True
        _ENCODERS["_"] = True
    return bool(_ENCODERS.get(name))


def cloud_codec() -> str:
    """H.264 spielt jeder Browser ab, auch am Handy. Ohne H.264-Encoder gibt es keine Cloud-Dateien."""
    for c in ("libx264", "libopenh264"):
        if has_encoder(c):
            return c
    return ""


def _enc_args(codec: str, kbps: int) -> list[str]:
    a = ["-c:v", codec, "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.25)}k", "-bufsize", f"{kbps * 2}k"]
    if codec == "libx264":
        a += ["-preset", "veryfast", "-profile:v", "high"]
    return a + ["-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart"]


def _size_of(info: dict) -> tuple[int, int]:
    m = re.search(r"\b(\d{3,5})x(\d{3,5})\b", info.get("stream", ""))
    return (int(m.group(1)), int(m.group(2))) if m else (1920, 1080)


def _cube(path: Path):
    """3D-LUT für ffmpeg (lut3d) aus pq_to_sdr: nötig, wenn dem ffmpeg zscale fehlt."""
    n = 33
    g = np.linspace(0, 1, n)
    bb, gg, rr = np.meshgrid(g, g, g, indexing="ij")   # Rot ändert sich am schnellsten
    rgb = np.stack([rr, gg, bb], axis=-1).reshape(-1, 3)
    out = pq_to_sdr((rgb * 65535 + 0.5).astype(np.uint16)).astype(np.float32) / 255
    lines = [f"LUT_3D_SIZE {n}"] + [f"{r:.5f} {g_:.5f} {b:.5f}" for r, g_, b in out]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def cloud_vf(info: dict) -> tuple[str, bool]:
    """Filterkette für die Cloud-Stücke: (Filter, braucht die LUT-Datei im Arbeitsordner). Nach der HDR-Umrechnung die Kennzeichnung
    auf normale Farben (BT.709) setzen, sonst behandeln Browser das Stück weiter als HDR und die Farben stimmen nicht."""
    w, h = _size_of(info)
    oh = max(2, int(round(CLOUD_W * h / w / 2)) * 2)
    mode = color_mode(info)
    if mode == "zscale":
        tin = "smpte2084" if info["trc"] == "pq" else "arib-std-b67"
        return (f"zscale=w={CLOUD_W}:h={oh}:tin={tin}:min=bt2020nc:pin=bt2020:rin=tv:t=linear:npl={NPL},format=gbrpf32le,"
                f"zscale=p=bt709,tonemap=tonemap=mobius:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709,fps={CLOUD_FPS}"), False
    if mode == "lut":
        return (f"scale={CLOUD_W}:{oh}:in_color_matrix=bt2020:in_range=tv:out_range=full,format=rgb48le,lut3d=file=pq2sdr.cube,"
                f"scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709,fps={CLOUD_FPS}"), True
    return f"scale={CLOUD_W}:{oh},format=yuv420p,fps={CLOUD_FPS}", False


def _ffrun(args: list[str], total: float, progress=None, stop: threading.Event | None = None, cwd: Path | None = None):
    """ffmpeg mit Fortschritt (0 bis 1). Bricht ab, wenn stop gesetzt ist."""
    cmd = [ffmpeg_exe(), "-v", "error", "-y", "-nostats", "-progress", "pipe:1"] + args
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(cwd) if cwd else None, **_popen_kwargs())
    err: list[str] = []
    threading.Thread(target=lambda: err.extend(x.decode("utf-8", "replace") for x in p.stderr), daemon=True).start()
    for ln in iter(p.stdout.readline, b""):
        if stop is not None and stop.is_set():
            p.kill()
            p.wait()
            raise InterruptedError("abgebrochen")
        s = ln.decode("ascii", "replace").strip()
        if progress and s.startswith("out_time_us=") and total > 0:
            try:
                progress(min(1.0, int(s.split("=")[1]) / 1e6 / total))
            except ValueError:
                pass
    p.wait()
    if p.returncode != 0:
        raise RuntimeError("ffmpeg: " + "".join(err).strip()[-300:])


def highlight_segments(rec: dict) -> list[dict]:
    """Die Stellen aus dem Kurz-Review (wie segments() in der Oberfläche): Tod mit 10 s davor, Kill, deine Ult, Fights, eigene Markierungen.
    Funde mit «Stimmt nicht» fallen weg. Überlappende Stellen werden zusammengefasst."""
    dur = float(rec.get("dur") or 0)
    win = {"death": (10, 2), "kill": (4, 2), "ult": (2, 6)}
    raw = []
    evs = rec.get("events", [])
    for e in evs:
        if e.get("ok") is False:
            continue
        if e["k"] == "fight":
            raw.append((e["t"], e.get("e", e["t"] + 5)))
        else:
            a, b = win.get(e["k"], (5, 3))
            raw.append((e["t"] - a, e["t"] + b))
    linked = {e.get("mk") for e in evs if e.get("mk")}
    for m in rec.get("marks", []):
        if m["id"] in linked:
            continue
        a, b = win.get(m["k"], (5, 3))
        raw.append((m["t"] - a, m["t"] + b))
    out: list[dict] = []
    for s, e in sorted((max(0.0, s), min(dur, e) if dur else e) for s, e in raw):
        if e - s < 0.5:
            continue
        if out and s <= out[-1]["e"] + 1:
            out[-1]["e"] = max(out[-1]["e"], e)
        else:
            out.append({"s": s, "e": e})
    return [{"s": round(x["s"], 2), "e": round(x["e"], 2)} for x in out]


def group_pieces(segs: list[dict], max_s: float) -> list[list[dict]]:
    """Stellen der Reihe nach in Stücke packen, jedes höchstens max_s Sekunden. Eine zu lange Stelle wird geteilt."""
    parts = []
    for g in segs:
        s = g["s"]
        while g["e"] - s > max_s:
            parts.append({"s": s, "e": s + max_s})
            s += max_s
        parts.append({"s": s, "e": g["e"]})
    groups: list[list[dict]] = []
    cur: list[dict] = []
    tot = 0.0
    for p in parts:
        d = p["e"] - p["s"]
        if cur and tot + d > max_s:
            groups.append(cur)
            cur, tot = [], 0.0
        cur.append(p)
        tot += d
    if cur:
        groups.append(cur)
    return groups


def build_highlights(src: Path, info: dict, segs: list[dict], out_dir: Path, codec: str, progress=None, stop=None) -> list[dict]:
    """Highlights als Stücke hl-01.mp4, … Jedes Stück hat eine Karte: welche Stelle im Video (s bis e) ab welcher Sekunde im Stück (at) läuft."""
    out_dir.mkdir(parents=True, exist_ok=True)
    vf, need_cube = cloud_vf(info)
    if need_cube and not (out_dir.parent / "pq2sdr.cube").exists():
        _cube(out_dir.parent / "pq2sdr.cube")
    groups = group_pieces(segs, piece_seconds(HL_KBPS))
    total = sum(p["e"] - p["s"] for g in groups for p in g) or 1.0
    done, pieces = 0.0, []
    for i, g in enumerate(groups, 1):
        f = f"hl-{i:02d}.mp4"
        dst = out_dir / f
        d = sum(p["e"] - p["s"] for p in g)
        kbps = HL_KBPS
        for _ in range(3):
            args = []
            for p in g:
                args += ["-ss", f"{p['s']:.2f}", "-t", f"{p['e'] - p['s']:.2f}", "-i", str(src)]
            chain = "".join(f"[{k}:v]" for k in range(len(g))) + f"concat=n={len(g)}:v=1:a=0,{vf}[out]"
            args += ["-filter_complex", chain, "-map", "[out]"] + _enc_args(codec, kbps) + [str(dst)]
            _ffrun(args, d, (lambda x, base=done: progress((base + x * d) / total)) if progress else None, stop, cwd=out_dir.parent)
            if dst.stat().st_size <= CLOUD_MAX:
                break
            kbps = int(kbps * 0.7)
        at, segmap = 0.0, []
        for p in g:
            segmap.append({"s": p["s"], "e": p["e"], "at": round(at, 2)})
            at += p["e"] - p["s"]
        pieces.append({"f": f, "size": dst.stat().st_size, "d": round(at, 2), "segs": segmap})
        done += d
    return pieces


def build_full(src: Path, info: dict, dur: float, out_dir: Path, codec: str, progress=None, stop=None) -> list[dict]:
    """Das ganze Video in Stücken ganz-01.mp4, … zu je piece_seconds(FULL_KBPS) Sekunden (ein Durchgang, Schnitt genau an den Grenzen)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    vf, need_cube = cloud_vf(info)
    if need_cube and not (out_dir.parent / "pq2sdr.cube").exists():
        _cube(out_dir.parent / "pq2sdr.cube")
    P = piece_seconds(FULL_KBPS)
    for old in out_dir.glob("ganz-*.mp4"):
        old.unlink()
    args = ["-i", str(src), "-vf", vf] + _enc_args(codec, FULL_KBPS)[:-2] + [
        "-force_key_frames", f"expr:gte(t,n_forced*{P})", "-f", "segment", "-segment_time", str(P), "-segment_start_number", "1",
        "-reset_timestamps", "1", "-segment_format", "mp4", "-segment_format_options", "movflags=+faststart", str(out_dir / "ganz-%02d.mp4")]
    _ffrun(args, dur, progress, stop, cwd=out_dir.parent)
    pieces = []
    for i, dst in enumerate(sorted(out_dir.glob("ganz-*.mp4"))):
        s, e = i * P, (min((i + 1) * P, dur) if dur else (i + 1) * P)
        if dst.stat().st_size > CLOUD_MAX:   # selten: sehr unruhige Stelle, dann mit weniger Datenrate neu
            _ffrun(["-ss", f"{s:.2f}", "-t", f"{e - s:.2f}", "-i", str(src), "-vf", vf] + _enc_args(codec, int(FULL_KBPS * 0.6)) + [str(dst)],
                   e - s, None, stop, cwd=out_dir.parent)
        pieces.append({"f": dst.name, "size": dst.stat().st_size, "s": round(s, 2), "e": round(e, 2)})
    return pieces


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
        elif len(pos) >= 3 and not neg and max(pos) < thr[tk]:
            # deine markierten Stellen liegen alle unter der Schwelle (zum Beispiel andere Farben im Video): senken, mit Untergrenze gegen Rauschen
            floor = {"dead": 0.01, "kill": 0.004, "ultOn": 0.004}[tk]
            thr[tk] = round(max(floor, min(pos) * 0.8), 4)
            r.update(schwelle=thr[tk], angepasst=True, hinweis="Gesenkt: Deine markierten Stellen lagen alle unter der Schwelle.")
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
    rep["fight"] = learned_fights(learn.get("fights", []))
    rep["ultEff"] = learned_ulteff(learn.get("ults", []))
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
        self.seen: dict[str, tuple] = {}   # Pfad → (Grösse, Änderungszeit, seit wann so)

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
        d["learn"].setdefault("fights", [])
        d["learn"].setdefault("ults", [])
        d.setdefault("prefs", {})
        for k, v in list(d["videos"].items()):
            if not isinstance(v, dict):
                del d["videos"][k]
                continue
            v.setdefault("events", []); v.setdefault("marks", [])
            v.setdefault("cid", new_id())   # bleibt beim Umbenennen gleich: Ordner in «Für die Cloud»
            if v.get("status") == "läuft":
                v["status"] = "wartet"
        return d

    def save(self):
        with self.lock:
            self.data["updated"] = datetime.now().isoformat(timespec="seconds")
            self.data["program"] = VERSION
            # Für Rivals Coach: Wie oft lag das Programm bei deinen Antworten richtig? Erst dann zählen ungeprüfte Funde in der Statistik.
            _, _, rep = learned(self.data["learn"])
            self.data["quality"] = {k: {"stimmt": rep[k]["stimmt"], "falsch": rep[k]["falsch"]} for k in ("death", "kill", "ult")}
            self.data["quality"]["fight"] = rep["fight"]
            self.data["quality"]["ultEff"] = rep["ultEff"]
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
                        V[key] = {"name": p.name, "size": size, "start": name_time(p.name), "dur": 0, "cid": new_id(),
                                  "mtime": int(p.stat().st_mtime * 1000), "status": "wartet", "events": [], "marks": [],
                                  "added": datetime.now().isoformat(timespec="seconds")}
                rec = V[key]
                rec["path"] = str(p.relative_to(self.base))
                rec["folder"] = sub
                rec["id"] = vid_id(key)
                seen.add(key)
                now = time.time()
                st = p.stat()
                sig = (st.st_size, st.st_mtime)
                prev = self.seen.get(str(p))
                since = prev[2] if prev and prev[:2] == sig else now
                self.seen[str(p)] = (sig[0], sig[1], since)
                stable = now - since >= STABLE_S
                if rec.get("status") == "fehler" and now >= rec.get("retryAt", 0) and rec.get("tries", 0) < len(RETRY_S):
                    rec["status"] = "wartet"
                if rec.get("status") in ("wartet", None) and sub == SUB_NEW:
                    if stable:
                        todo.append(key)
                    else:
                        rec["copying"] = 1
                elif rec.get("copying"):
                    rec.pop("copying", None)
            for k in list(V):
                v = V[k]
                v["missing"] = k not in seen
                # halbe Kopien (andere Grösse, nie beantwortet) verschwinden
                if v["missing"] and not v.get("done") and not v.get("marks") and not any(isinstance(e.get("ok"), bool) for e in v.get("events", [])):
                    c = self.cache / (vid_id(k) + ".json")
                    if c.exists():
                        c.unlink()
                    del V[k]
            return todo

    def failed(self, key: str, msg: str):
        with self.lock:
            rec = self.data["videos"].get(key)
            if not rec:
                return
            rec["tries"] = rec.get("tries", 0) + 1
            rec["status"], rec["error"] = "fehler", msg[:400]
            if rec["tries"] <= len(RETRY_S):
                rec["retryAt"] = time.time() + RETRY_S[rec["tries"] - 1]
            c = self.cache / (vid_id(key) + ".json")
            if c.exists():
                c.unlink()

    def retry(self, key: str):
        with self.lock:
            rec = self.data["videos"][key]
            for f in ("error", "tries", "retryAt"):
                rec.pop(f, None)
            rec["status"] = "wartet"
            c = self.cache / (vid_id(key) + ".json")
            if c.exists():
                c.unlink()
            self.seen.clear()
            self.save()

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

    def upgrade_series(self) -> int:
        """Videos in «Neu», deren Messreihe älter ist (vor 0.2.0: ohne HDR-Umrechnung), neu messen. Antworten und Markierungen bleiben."""
        n = 0
        with self.lock:
            for k, v in self.data["videos"].items():
                if v.get("done") or v.get("folder") != SUB_NEW or v.get("status") != "fertig":
                    continue
                ser = self.series(k)
                if ser is not None and ser.get("v") != SER_V:
                    (self.cache / (vid_id(k) + ".json")).unlink(missing_ok=True)
                    v["status"] = "wartet"
                    n += 1
            if n:
                self.save()
        return n

    def save_series(self, key: str, ser: dict):
        (self.cache / (vid_id(key) + ".json")).write_text(json.dumps(ser, separators=(",", ":")), encoding="utf-8")

    # Erkennung anwenden, Antworten behalten
    def apply_detect(self, key: str, ser: dict):
        with self.lock:
            rec = self.data["videos"][key]
            thr, lead, _ = learned(self.data["learn"])
            old = rec.get("events", [])
            evs = []
            fl = learned_fights(self.data["learn"].get("fights", []))
            for g in fights(ser, detect(ser, thr, lead)):
                o = next((x for x in old if x["k"] == "fight" and abs(x["t"] - g["t"]) <= 4), None)
                evs.append({"id": o["id"] if o else new_id(), "t": g["t"], "e": g["e"], "k": "fight", "n": g["n"], "score": g["score"],
                            "pred": fight_pred(g["score"], fl), "res": o.get("res", "") if o else "", "ok": o.get("ok") if o else None, "mk": o.get("mk", "") if o else ""})
            ul = learned_ulteff(self.data["learn"].get("ults", []))
            found = detect(ser, thr, lead)
            for e in found:
                o = next((x for x in old if x["k"] == e["k"] and abs(x["t"] - e["t"]) <= 2.0 and isinstance(x.get("ok"), bool)), None)
                ne = {"id": o["id"] if o else new_id(), "t": e["t"], "k": e["k"], "f": e["f"], "raw": e.get("raw", e["t"]),
                      "ok": o["ok"] if o else None, "mk": o.get("mk", "") if o else ""}
                if e["k"] == "ult":
                    ne["us"] = ult_score(ser, e["t"], found)
                    ne["est"] = ulteff_pred(ne["us"], ul)
                evs.append(ne)
            # bestätigte Funde, die jetzt nicht mehr gefunden werden, bleiben als Markierung erhalten (mk)
            rec["events"] = evs
            rec["dur"] = round(ser.get("dur") or 0, 1)
            if not rec.get("start") and rec.get("mtime") and rec["dur"]:
                rec["start"] = int(rec["mtime"] - rec["dur"] * 1000)   # Ende der Aufnahme minus Länge
            rec["status"] = "fertig"
            for f in ("error", "tries", "retryAt"):
                rec.pop(f, None)
            rec["analyzed"] = datetime.now().isoformat(timespec="seconds")
            rec["learnedWith"] = {"thr": thr, "lead": lead}
            rec["diag"] = {"hdr": ser.get("hdr", ""), "tm": ser.get("tm", ""), "sum": series_summary(ser, thr)}

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
            if e["k"] == "fight":
                raise ValueError("Fights mit gewonnen/verloren beantworten")
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

    def fight_answer(self, key: str, eid: str, res: str) -> dict:
        """Fight-Vorschlag beantworten: «win», «loss» oder «none» (kein Fight). Gewonnen/verloren wird als Markierung übernommen
        (zählt im Coach als Fight) und ist ein Beispiel zum Lernen."""
        with self.lock:
            rec = self.data["videos"][key]
            e = next(x for x in rec["events"] if x["id"] == eid and x["k"] == "fight")
            if e.get("mk"):
                rec["marks"] = [m for m in rec["marks"] if not (m["id"] == e["mk"] and m.get("auto"))]
                e["mk"] = ""
            e["res"] = res if res in ("win", "loss", "none") else ""
            e["ok"] = None if not e["res"] else e["res"] != "none"
            if e["res"] in ("win", "loss"):
                mk = {"id": new_id(), "t": e["t"], "k": e["res"], "auto": 1}
                rec["marks"].append(mk)
                e["mk"] = mk["id"]
            fl = [x for x in self.data["learn"]["fights"] if x.get("e") != eid]
            if e["res"] in ("win", "loss"):
                fl.append({"e": eid, "s": e.get("score", 0.0), "res": e["res"]})
            self.data["learn"]["fights"] = fl[-200:]
            self.save()
            return rec

    def set_pref(self, k: str, v: str):
        with self.lock:
            prefs = self.data.setdefault("prefs", {})
            if k == "role" and v in RV_DATA.get("roles", {}):
                prefs["role"] = v
            if k == "cloudFull":
                prefs["cloudFull"] = v in ("1", "true", True)
            self.save()

    def add_mark(self, key: str, t: float, kind: str) -> dict:
        with self.lock:
            rec = self.data["videos"][key]
            mk = {"id": new_id(), "t": round(float(t), 2), "k": kind}
            rec["marks"].append(mk)
            # «Fight gewonnen/verloren» von Hand in einem vorgeschlagenen Fight: gilt als Antwort und Beispiel
            if kind in ("win", "loss"):
                e = next((x for x in rec["events"] if x["k"] == "fight" and x["t"] - 2 <= mk["t"] <= x.get("e", x["t"]) + 2 and not x.get("res")), None)
                if e is not None:
                    e.update(res=kind, ok=True, mk=mk["id"])
                    self.data["learn"]["fights"] = [x for x in self.data["learn"]["fights"] if x.get("e") != e["id"]] + [{"e": e["id"], "s": e.get("score", 0.0), "res": kind}]
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
            if fields.get("h"):
                prefs = self.data.setdefault("prefs", {})
                prefs["recentUlt"] = ([str(fields["h"])[:40]] + [x for x in prefs.get("recentUlt", []) if x != fields["h"]])[:8]
            if "v" in fields and mk.get("k") == "ult":
                e = next((x for x in rec["events"] if x.get("mk") == mid and x["k"] == "ult" and "us" in x), None)
                if e is not None:
                    ul = [x for x in self.data["learn"]["ults"] if x.get("e") != e["id"]]
                    if mk.get("v") in ("ja", "nein"):
                        ul.append({"e": e["id"], "s": e["us"], "v": mk["v"]})
                    self.data["learn"]["ults"] = ul[-200:]
            if "c" in fields and cause_group(mk.get("c", "")) != RV_DATA.get("ultGroup") and mk.get("k") == "death":
                mk.pop("h", None)   # Ult-Held gehört nur zu einem Tod durch eine Ult
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
        """Abschliessen: als ausgewertet markieren, nach «Ausgewertet» verschieben und umbenennen. Gibt den Schlüssel zurück.
        Ist die Datei noch offen (Windows: «von einem anderen Prozess verwendet», etwa weil der Browser sie gerade abspielt),
        bleibt sie vorerst liegen; das Programm verschiebt sie später (pending_moves)."""
        with self.lock:
            rec = self.data["videos"][key]
            rec["done"] = int(time.time() * 1000)
            name = done_name(rec)
            dst = self.base / SUB_DONE / name
            src = self.base / rec["path"]
            i = 2
            while dst.exists() and dst.resolve() != src.resolve():
                dst = self.base / SUB_DONE / f"{Path(name).stem} ({i}){Path(name).suffix}"
                i += 1
            rec["moveTo"] = str(dst.relative_to(self.base))
            self.save()
        for _ in range(12):   # ohne Sperre warten, damit der Browser die Datei loslassen kann
            nk = self.try_move(key)
            if nk:
                return nk
            time.sleep(0.5)
        return key

    def try_move(self, key: str) -> str:
        """Verschiebt eine abgeschlossene Aufnahme, falls noch nicht geschehen. Gibt den neuen Schlüssel zurück oder ""."""
        with self.lock:
            rec = self.data["videos"].get(key)
            if not rec or not rec.get("moveTo"):
                return key if rec else ""
            src, dst = self.base / rec["path"], self.base / rec["moveTo"]
            try:
                if src.exists() and dst.resolve() != src.resolve():
                    os.replace(src, dst)
            except OSError:
                return ""
            new_key = vid_key(dst.name, rec["size"])
            if new_key != key:
                self.data["videos"][new_key] = self.data["videos"].pop(key)
                oc, nc = self.cache / (vid_id(key) + ".json"), self.cache / (vid_id(new_key) + ".json")
                if oc.exists():
                    os.replace(oc, nc)
            rec = self.data["videos"][new_key]
            if rec["name"] != dst.name:
                rec.setdefault("names", []).append(rec["name"])
            rec.update(name=dst.name, path=str(dst.relative_to(self.base)), folder=SUB_DONE, id=vid_id(new_key))
            rec.pop("moveTo", None)
            self.save()
            return new_key

    def pending_moves(self):
        with self.lock:
            keys = [k for k, v in self.data["videos"].items() if v.get("moveTo") and v.get("done")]
        for k in keys:
            self.try_move(k)

    # Für die Cloud
    def cloud_next(self) -> tuple[str, str] | None:
        """Nächste Arbeit für die Cloud: (Schlüssel, "hl" oder "full"). Neueste Aufnahmen zuerst, Highlights vor ganzen Videos."""
        if not cloud_codec():
            return None
        full_on = self.data.get("prefs", {}).get("cloudFull", True)
        now = time.time()
        with self.lock:
            cands = []
            for k, v in self.data["videos"].items():
                if v.get("missing") or v.get("status") != "fertig" or not (self.base / v.get("path", "")).exists():
                    continue
                c = v.get("cloud") or {}
                if c.get("errAt") and now - c["errAt"] < 3600 or c.get("tries", 0) >= 3:
                    continue
                d = self.base / CLOUD_DIR / v["cid"]
                hl = c.get("hl") or {}
                if hl.get("sig") != f"{v.get('analyzed')}|{CLOUD_V}" or not all((d / p["f"]).exists() for p in hl.get("pieces", [])):
                    cands.append((0, -(v.get("start") or 0), k, "hl"))
                elif full_on:
                    fu = c.get("full") or {}
                    if fu.get("sig") != f"{v.get('size')}|{CLOUD_V}" or not all((d / p["f"]).exists() for p in fu.get("pieces", [])):
                        cands.append((1, -(v.get("start") or 0), k, "full"))
            cands.sort()
            return (cands[0][2], cands[0][3]) if cands else None

    def build_cloud(self, key: str, what: str, progress=None, stop=None):
        with self.lock:
            v = self.data["videos"][key]
            cid, src, dur = v["cid"], self.base / v["path"], float(v.get("dur") or 0)
            segs = highlight_segments(v)
            sig = f"{v.get('analyzed')}|{CLOUD_V}" if what == "hl" else f"{v.get('size')}|{CLOUD_V}"
        out = self.base / CLOUD_DIR / cid
        codec = cloud_codec()
        info = probe(src)
        try:
            if what == "hl":
                for old in out.glob("hl-*.mp4"):
                    old.unlink()
                pieces = build_highlights(src, info, segs, out, codec, progress, stop) if segs else []
                part = {"sig": sig, "at": datetime.now().isoformat(timespec="seconds"), "pieces": pieces}
            else:
                pieces = build_full(src, info, dur, out, codec, progress, stop)
                part = {"sig": sig, "at": datetime.now().isoformat(timespec="seconds"), "piece": piece_seconds(FULL_KBPS), "pieces": pieces}
        except InterruptedError:
            return
        except Exception as e:
            with self.lock:
                k2, v2 = next(((k, x) for k, x in self.data["videos"].items() if x.get("cid") == cid), (None, None))
                if v2 is not None:
                    c = v2.setdefault("cloud", {})
                    c.update(err=str(e)[:300], errAt=time.time(), tries=c.get("tries", 0) + 1)
                    self.save()
            raise
        with self.lock:
            k2, v2 = next(((k, x) for k, x in self.data["videos"].items() if x.get("cid") == cid), (None, None))
            if v2 is None:
                return
            c = v2.setdefault("cloud", {})
            c.update({"v": CLOUD_V, "dir": f"{CLOUD_DIR}/{cid}", what: part})
            for f in ("err", "errAt", "tries"):
                c.pop(f, None)
            self.save()

    def reopen(self, key: str):
        with self.lock:
            self.data["videos"][key].pop("done", None)
            self.data["videos"][key].pop("moveTo", None)
            self.save()


# ---------------------------------------------------------------- Selbsttest (ohne private Bilder)
def selftest(tmp: Path) -> int:
    """Erzeugt Testvideos mit gelbem Feld oben links (3–7 s) und prüft, dass genau ein Tod gefunden wird.
    Geprüft werden MP4 (H.264) und WebM (VP9, wie die PS5), wenn möglich auch VP9 mit 10 Bit, und eine HDR-Aufnahme (PQ, wie die PS5 mit HDR)."""
    tmp.mkdir(parents=True, exist_ok=True)
    src = "color=c=0x101828:s=1280x720:d=10:r=30"
    box = "drawbox=x=10:y=20:w=110:h=70:color=0xF5D232@1:t=fill:enable='between(t,3,7)'"
    cases = [("MP4 (H.264)", "selbsttest.mp4", ["-pix_fmt", "yuv420p"], True),
             ("WebM (VP9)", "selbsttest.webm", ["-c:v", "libvpx-vp9", "-b:v", "1M", "-deadline", "realtime", "-cpu-used", "8", "-pix_fmt", "yuv420p"], True),
             ("WebM (VP9, 10 Bit)", "selbsttest10.webm", ["-c:v", "libvpx-vp9", "-b:v", "1M", "-deadline", "realtime", "-cpu-used", "8", "-pix_fmt", "yuv420p10le"], False)]
    result = 0
    for label, name, enc, must in cases:
        vid = tmp / name
        r = subprocess.run([ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", src, "-vf", box, *enc, str(vid)],
                           capture_output=True, text=True, errors="replace", **_popen_kwargs())
        if r.returncode != 0 or not vid.exists():
            print(f"Selbsttest {label}: Testvideo liess sich nicht erzeugen ({r.stderr.strip()[-200:]}), übersprungen")
            if must and label.startswith("MP4"):
                result = 1
            continue
        try:
            ser = measure(vid)
            deaths = [e for e in detect(ser) if e["k"] == "death"]
            ok = len(deaths) == 1 and 1.5 <= deaths[0]["t"] <= 3.0 and abs(ser["dur"] - 10) < 0.6
            print(f"Selbsttest {label}: {len(ser['t'])} Bilder, Länge {ser['dur']:.1f} s, Tod bei {[d['t'] for d in deaths]} → {'OK' if ok else 'FEHLER'}")
        except Exception as e:
            ok = False
            print(f"Selbsttest {label}: FEHLER {e}")
        if not ok and must:
            result = 1
    nh = len(RV_DATA.get("heroes", []))
    print(f"Ursachen und Helden aus Rivals Coach: {len(RV_DATA.get('roles', {}))} Rollen, {nh} Helden → {'OK' if nh else 'FEHLER (rv_data.json fehlt)'}")
    if not nh:
        result = 1
    hdr = _selftest_hdr(tmp)
    if hdr:
        result = 1
    # Cloud-Stücke: H.264 muss gehen, sonst kann Rivals Coach die Videos nicht abspielen
    codec = cloud_codec()
    mp4 = tmp / "selbsttest.mp4"
    if not codec:
        print("Cloud-Stücke: kein H.264-Encoder im ffmpeg → FEHLER")
        result = 1
    elif mp4.exists():
        try:
            info = probe(mp4)
            pieces = build_highlights(mp4, info, [{"s": 2.0, "e": 5.0}, {"s": 7.5, "e": 9.0}], tmp / "cloud" / "test", codec)
            p0 = probe(tmp / "cloud" / "test" / pieces[0]["f"])
            ok = len(pieces) == 1 and abs(p0["dur"] - 4.5) < 0.3 and "h264" in p0["stream"] and pieces[0]["segs"][1]["at"] == 3.0
            print(f"Cloud-Stücke ({codec}): {pieces[0]['size']} Bytes, {p0['dur']:.1f} s → {'OK' if ok else 'FEHLER'}")
        except Exception as e:
            ok = False
            print(f"Cloud-Stücke: FEHLER {e}")
        if not ok:
            result = 1
    print("Selbsttest OK" if result == 0 else "Selbsttest FEHLER")
    return result


def _sdr_to_pq(rgb8: tuple[int, int, int]) -> np.ndarray:
    """Umkehrung von pq_to_sdr für eine Farbe (ohne Knie, Farben im Test liegen darunter): so sähe sie in einer HDR-Aufnahme aus."""
    v = np.array(rgb8, dtype=np.float64) / 255
    lin = np.where(v < 0.081, v / 4.5, np.power((v + 0.099) / 1.099, 1 / 0.45))
    lin2020 = np.clip(np.linalg.inv(_P2020_709.astype(np.float64)) @ lin, 0, None) * (NPL / 10000.0)
    yp = np.power(lin2020, _M1)
    e = np.power((_C1 + _C2 * yp) / (1 + _C3 * yp), _M2)
    return np.clip(e * 65535 + 0.5, 0, 65535).astype("<u2")


def _selftest_hdr(tmp: Path) -> int:
    """HDR10-Testvideo (PQ, BT.2020, 10 Bit) aus numpy, damit es auch ohne zscale entsteht. Geprüft wird der Weg, den
    dieses ffmpeg nimmt, und zusätzlich immer die eigene Umrechnung (lut), weil sie der Ersatz ist, wenn zscale fehlt."""
    print(f"HDR-Umrechnung mit ffmpeg (zscale und tonemap): {'ja' if has_filter('zscale') and has_filter('tonemap') else 'nein, eigene Umrechnung'}")
    w, h, fps, dur = 640, 360, 10, 10
    bg = np.empty((h, w, 3), dtype="<u2"); bg[:] = _sdr_to_pq((0x10, 0x18, 0x28))
    box = bg.copy(); box[10:45, 5:60] = _sdr_to_pq((0xF5, 0xD2, 0x32))
    vid = tmp / "selbsttest-hdr.mkv"
    cmd = [ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb48le", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           "-vf", "scale=out_color_matrix=bt2020:out_range=tv,format=yuv420p10le", "-c:v", "ffv1",
           "-color_primaries", "bt2020", "-color_trc", "smpte2084", "-colorspace", "bt2020nc", "-color_range", "tv", str(vid)]
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, **_popen_kwargs())
        for i in range(fps * dur):
            p.stdin.write((box if 3 <= i / fps < 7 else bg).tobytes())
        p.stdin.close()
        err = p.stderr.read().decode("utf-8", "replace"); p.wait()
    except Exception as e:
        err, p = str(e), None
    if p is None or p.returncode != 0 or not vid.exists():
        print(f"Selbsttest HDR: Testvideo liess sich nicht erzeugen ({err.strip()[-200:]}), übersprungen")
        return 0
    info = probe(vid)
    modes = [color_mode(info)]
    if modes[0] != "lut":
        modes.append("lut")
    bad = 0
    saved = dict(_FILTERS)
    for mode in modes:
        try:
            if mode == "lut" and color_mode(info) != "lut":
                _FILTERS.clear(); _FILTERS.update({"_": True})   # zscale vorübergehend «ausblenden»
            ser = measure(vid)
            deaths = [e for e in detect(ser) if e["k"] == "death"]
            ok = info["trc"] == "pq" and len(deaths) == 1 and 1.5 <= deaths[0]["t"] <= 3.0
            print(f"Selbsttest HDR (PQ, {mode}): erkannt als {info['trc'] or 'normal'}, Tod bei {[d['t'] for d in deaths]}, "
                  f"stärkster Wert {max(ser['cnt']):.2f} → {'OK' if ok else 'FEHLER'}")
        except Exception as e:
            ok = False
            print(f"Selbsttest HDR ({mode}): FEHLER {e}")
        finally:
            _FILTERS.clear(); _FILTERS.update(saved)
        bad |= 0 if ok else 1
    return bad

if __name__ == "__main__":
    sys.exit(selftest(Path(sys.argv[1] if len(sys.argv) > 1 else "selbsttest")))
