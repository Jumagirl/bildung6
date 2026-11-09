"""Rivals Video: Programm für den PC.

Startet einen kleinen Server nur auf diesem PC (127.0.0.1) und öffnet die Oberfläche im Browser.
Im Hintergrund wertet es neue Videos im Ordner «Neu» aus. Nichts geht ins Internet.

Aufruf:  RivalsVideo.exe                (normal)
         RivalsVideo.exe --selftest     (prüft ffmpeg und Erkennung mit einem erzeugten Testvideo)
         RivalsVideo.exe --folder PFAD  (anderer Ordner)
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import rv_core as rc

APP = "Rivals Video"


def resource(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def config_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home()))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    p = root / "RivalsVideo"
    p.mkdir(parents=True, exist_ok=True)
    return p / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict):
    config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def default_folder() -> Path:
    vids = Path.home() / "Videos"
    return (vids if vids.exists() else Path.home()) / "Rivals Videos"


class App:
    def __init__(self, folder: Path):
        cfg = load_config()   # der Schlüssel bleibt über Neustarts gleich, damit offene Browser-Tabs weiter gehen
        self.token = cfg.get("token") or secrets.token_urlsafe(16)
        if cfg.get("token") != self.token:
            cfg["token"] = self.token; save_config(cfg)
        self.lock = threading.RLock()
        self.work = {"key": "", "name": "", "p": 0.0, "msg": ""}
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.redo_all = False
        self.set_folder(folder)

    def set_folder(self, folder: Path):
        with self.lock:
            self.store = rc.Store(Path(folder))
            self.folder = Path(folder)
            n = self.store.upgrade_series()   # 0.2.0: ältere Messungen (ohne HDR-Umrechnung) neu
            if n:
                print(f"{n} Video(s) werden mit der neuen Erkennung (HDR) neu ausgewertet. Deine Antworten bleiben.", flush=True)
            cfg = load_config(); cfg["folder"] = str(self.folder); save_config(cfg)
        self.wake.set()

    # Hintergrund-Auswertung
    def worker(self):
        while not self.stop.is_set():
            try:
                store = self.store
                store.pending_moves()
                todo = store.sync_files()
                if self.redo_all:
                    self.redo_all = False
                    for k in list(store.data["videos"]):
                        ser = store.series(k)
                        if ser:
                            store.apply_detect(k, ser)
                    store.save()
                for key in todo:
                    if self.stop.is_set() or store is not self.store:
                        break
                    rec = store.data["videos"].get(key)
                    if not rec or rec.get("missing"):
                        continue
                    rec["status"] = "läuft"
                    self.work.update(key=key, name=rec["name"], p=0.0, msg="")
                    try:
                        ser = store.series(key)
                        if not ser:
                            ser = rc.measure(store.base / rec["path"], progress=lambda p: self.work.update(p=p), stop=self.stop)
                            if self.stop.is_set():
                                rec["status"] = "wartet"
                                break
                            store.save_series(key, ser)
                        store.apply_detect(key, ser)
                    except Exception as e:   # ein kaputtes Video hält die anderen nicht auf
                        store.failed(key, str(e))
                        print(f"Fehler bei {rec['name']}: {e}", flush=True)
                    store.save()
                    self.work.update(key="", name="", p=0.0)
                store.save()
            except Exception:
                traceback.print_exc()
            self.wake.wait(5)
            self.wake.clear()

    def state(self) -> dict:
        store = self.store
        with store.lock:
            vids = []
            for k, v in store.data["videos"].items():
                if v.get("missing"):
                    continue
                open_n = sum(1 for e in v.get("events", []) if not isinstance(e.get("ok"), bool))
                vids.append({"id": v.get("id"), "name": v["name"], "folder": v.get("folder"), "status": v.get("status"),
                             "error": v.get("error", ""), "start": v.get("start", 0), "dur": v.get("dur", 0),
                             "done": v.get("done", 0), "open": open_n, "copying": v.get("copying", 0), "events": len(v.get("events", [])), "analyzed": v.get("analyzed", ""),
                             "marks": len(v.get("marks", []))})
            vids.sort(key=lambda x: (bool(x["done"]), -(x["start"] or 0)))
            thr, lead, rep = rc.learned(store.data["learn"])
            return {"app": APP, "version": rc.VERSION, "folder": str(self.folder), "videos": vids,
                    "work": dict(self.work), "learn": {"thr": thr, "lead": lead, "report": rep},
                    "kinds": rc.KINDS, "causes": rc.DEATH_CAUSES, "dataFile": rc.DATA_NAME, "prefs": store.data.get("prefs", {})}

    def video(self, vid: str) -> dict | None:
        k, v = self.store.by_id(vid)
        if not v:
            return None
        out = {x: v.get(x) for x in ("id", "name", "folder", "status", "error", "start", "dur", "done", "events", "marks", "moveTo", "diag")}
        out["doneName"] = rc.done_name(v)
        return out


def make_handler(app: App, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    ui = resource("rv_ui.html").read_text(encoding="utf-8")

    class H(BaseHTTPRequestHandler):
        server_version = "RivalsVideo"

        def log_message(self, fmt, *args):   # leise
            pass

        def _ok_host(self) -> bool:
            return self.headers.get("Host", "") in allowed_hosts

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _deny(self, code=403, msg="nicht erlaubt", why=""):
            self._json({"error": msg, "code": why}, code)

        def do_GET(self):
            if not self._ok_host():
                return self._deny()
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                body = ui.replace("__TOKEN__", app.token).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return self.wfile.write(body)
            if (q.get("token") or [""])[0] != app.token:
                return self._deny(why="token")
            if u.path == "/api/state":
                return self._json(app.state())
            if u.path == "/api/meta":
                return self._json(rc.RV_DATA)
            if u.path.startswith("/api/frame/"):
                return self._json(self._frame(u.path.rsplit("/", 1)[-1], float((q.get("t") or ["0"])[0] or 0)))
            if u.path.startswith("/api/video/"):
                v = app.video(u.path.rsplit("/", 1)[-1])
                return self._json(v) if v else self._deny(404, "unbekannt")
            if u.path.startswith("/media/"):
                return self._media(u.path.rsplit("/", 1)[-1])
            return self._deny(404, "unbekannt")

        def _frame(self, vid: str, t: float) -> dict:
            """Diagnose: das Bild an der Stelle t so, wie das Programm es misst, mit den Messbereichen und den Werten."""
            k, v = app.store.by_id(vid)
            if not v:
                return {"error": "unbekannt"}
            try:
                a, info = rc.grab_frame(app.store.base / v["path"], t)
            except Exception as e:
                return {"error": str(e)[:300]}
            cnt, feed, ug = rc.features(a)
            thr, lead, _ = rc.learned(app.store.data["learn"])
            img = "data:image/png;base64," + base64.b64encode(rc.png_bytes(rc.diag_image(a))).decode("ascii")
            return {"t": t, "img": img, "f": {"cnt": cnt, "feed": feed, "ug": ug}, "thr": thr, **info}

        def _media(self, vid: str):
            k, v = app.store.by_id(vid)
            if not v:
                return self._deny(404, "unbekannt")
            p = app.store.base / v["path"]
            if not p.exists():
                return self._deny(404, "Datei fehlt")
            size = p.stat().st_size
            ctype = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
                     ".mkv": "video/x-matroska"}.get(p.suffix.lower()) or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            rng = self.headers.get("Range", "")
            start, end = 0, size - 1
            code = 200
            if rng.startswith("bytes="):
                a, _, b = rng[6:].split(",")[0].partition("-")
                if a.strip():
                    start = int(a); end = int(b) if b.strip() else size - 1
                elif b.strip():
                    start = max(0, size - int(b))
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.end_headers(); return
                code = 206
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with open(p, "rb") as fh:
                    fh.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = fh.read(min(1 << 20, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_POST(self):
            if not self._ok_host():
                return self._deny()
            if self.headers.get("X-Token") != app.token:
                return self._deny(why="token")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                return self._json(self._post(urlparse(self.path).path, body))
            except Exception as e:
                traceback.print_exc()
                return self._json({"error": str(e)[:300]}, 400)

        def _post(self, path: str, b: dict):
            st = app.store
            if path == "/api/folder/set":
                p = Path(str(b.get("folder", "")).strip().strip('"'))
                if not str(p) or not p.is_absolute():
                    raise ValueError("Bitte einen vollständigen Ordnerpfad angeben, zum Beispiel C:\\Users\\…\\Videos\\Rivals Videos")
                app.set_folder(p)
                return {"ok": True, "folder": str(p)}
            if path == "/api/folder/choose":
                p = choose_folder(app.folder)
                if p:
                    app.set_folder(Path(p))
                return {"ok": bool(p), "folder": str(app.folder)}
            if path == "/api/folder/open":
                sub = b.get("sub") or ""
                target = app.folder / sub if sub in (rc.SUB_NEW, rc.SUB_DONE) else app.folder
                if os.name == "nt":
                    os.startfile(str(target))   # noqa: S606 (nur der eigene Ordner)
                return {"ok": True}
            if path == "/api/pref":
                st.set_pref(str(b.get("k", "")), str(b.get("v", "")))
                return {"ok": True, "prefs": st.data.get("prefs", {})}
            if path == "/api/reanalyze":
                app.redo_all = True
                app.wake.set()
                return {"ok": True}
            key, v = st.by_id(str(b.get("id", "")))
            if not v:
                raise ValueError("Video unbekannt")
            if path == "/api/answer":
                ok = b.get("ok")
                st.answer(key, str(b["eid"]), ok if isinstance(ok, bool) else None)
            elif path == "/api/fight":
                st.fight_answer(key, str(b["eid"]), str(b.get("res", "")))
            elif path == "/api/mark/add":
                if b.get("k") not in rc.KINDS:
                    raise ValueError("Art unbekannt")
                st.add_mark(key, float(b["t"]), b["k"])
            elif path == "/api/mark/update":
                st.update_mark(key, str(b["mid"]), b.get("fields") or {})
            elif path == "/api/mark/delete":
                st.delete_mark(key, str(b["mid"]))
            elif path == "/api/finish":
                key = st.finish(key)
            elif path == "/api/reopen":
                st.reopen(key)
            elif path == "/api/retry":
                st.retry(key)
                app.wake.set()
            elif path == "/api/redetect":
                ser = st.series(key)
                if ser:
                    st.apply_detect(key, ser); st.save()
            else:
                raise ValueError("unbekannte Aktion")
            return app.video(st.data["videos"][key]["id"]) or {"ok": True}

    return H


def choose_folder(current: Path) -> str:
    """Ordnerwahl mit dem Windows-Dialog (tkinter)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        p = filedialog.askdirectory(initialdir=str(current), title="Ordner für deine Rivals-Videos wählen")
        root.destroy()
        return p or ""
    except Exception:
        return ""


def free_port(start: int) -> int:
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if os.name != "nt":   # nach einem Neustart denselben Port nehmen (wie der Server selbst)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("Kein freier Port gefunden")


def main(argv=None) -> int:
    for st in (sys.stdout, sys.stderr):   # Windows-Konsole: Sonderzeichen nie als Absturzgrund
        try:
            st.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=APP)
    ap.add_argument("--folder")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return rc.selftest(Path(tempfile.mkdtemp(prefix="rivals-video-")))
    folder = Path(a.folder) if a.folder else Path(load_config().get("folder") or default_folder())
    app = App(folder)
    port = free_port(a.port)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, port))
    threading.Thread(target=app.worker, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"{APP} {rc.VERSION} läuft: {url}", flush=True)
    print(f"Ordner: {app.folder}  (neue Videos nach «{rc.SUB_NEW}» kopieren)", flush=True)
    print("Dieses Fenster offen lassen. Zum Beenden schliessen oder Strg+C drücken.", flush=True)
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop.set(); app.wake.set()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
