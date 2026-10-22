#!/usr/bin/env python3
"""HomebrUI – Homebrew im Browser verwalten. Läuft nur lokal, nur Standardbibliothek."""
import hashlib
import json
import os
import secrets
import stat
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import brewlib
import catalog
import updater
from brewlib import valid_name
from jobs import JobManager

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
CFG = brewlib.load_config()
PORT = int(os.environ.get("PORT", CFG["port"]))
TOKEN = secrets.token_hex(16)
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8")}

SERVER = {}


def code_version():
    """Hash des eigenen Codes: erkennt, ob im Hintergrund noch eine ältere Version läuft."""
    h = hashlib.sha1()
    for p in sorted([*HERE.glob("*.py"), *WEB.glob("*")]):
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


VERSION = code_version()
_cache = {"data": None}
_cache_lock = threading.Lock()


def get_data(refresh=False):
    with _cache_lock:
        if refresh or _cache["data"] is None:
            _cache["data"] = brewlib.collect(brewlib.load_config())
        return _cache["data"]


def public(data):
    return {k: v for k, v in data.items() if k != "deps_map"}


def make_askpass():
    """Kleines Wrapper-Skript, das sudo als Passwort-Abfrage benutzt (Port und Token stecken darin)."""
    brewlib.CONF_DIR.mkdir(exist_ok=True)
    path = brewlib.CONF_DIR / f"askpass-{PORT}.sh"
    path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "askpass.py"}" {PORT} {TOKEN} "$@"\n')
    path.chmod(stat.S_IRWXU)
    (brewlib.CONF_DIR / "location").write_text(str(HERE))
    return str(path)


def record_history(cmd):
    for r in cmd.get("record", []):
        brewlib.add_history(r)


JOBS = JobManager(brewlib.BREW_CMD, brewlib.ENV, make_askpass(), record_history)


def build_job(body):
    """Übersetzt eine UI-Aktion in brew-Befehle. Nur diese Whitelist ist erlaubbar."""
    a = body.get("action")
    name, kind = body.get("name", ""), body.get("kind")
    dry = bool(body.get("dry_run"))
    if a in ("install", "pin", "unpin", "mark_request", "tap", "untap", "services") and not valid_name(name):
        raise ValueError("Invalid name")
    if a == "install":
        if kind not in ("formula", "cask"):
            raise ValueError("Invalid type")
        return f"{name} installieren", [{"args": ["install", f"--{kind}", name]}]
    if a == "mark_request":
        return f"{name} als selbst installiert markieren", [{"args": ["install", "--formula", name]}]
    if a in ("pin", "unpin"):
        return f"{name}: {a}", [{"args": [a, name]}]
    if a in ("tap", "untap"):
        return f"{a} {name}", [{"args": [a, name]}]
    if a == "services":
        op = body.get("op")
        if op not in ("start", "stop", "restart"):
            raise ValueError("Invalid action")
        return f"Dienst {name}: {op}", [{"args": ["services", op, name]}]
    if a == "update":
        return "brew update", [{"args": ["update"]}]
    if a == "upgrade":
        items = body.get("items") or []
        if not all(valid_name(i.get("name")) and i.get("kind") in ("formula", "cask") for i in items):
            raise ValueError("Invalid packages")
        base = ["upgrade"] + (["--dry-run"] if dry else [])
        if not items:
            return ("Vorschau: alle Upgrades" if dry else "Alles upgraden"), [{"args": base}]
        return ("Vorschau: " if dry else "Upgrade: ") + ", ".join(i["name"] for i in items), \
            [{"args": base + [f"--{i['kind']}", i["name"]]} for i in items]
    if a == "cleanup":
        args = ["cleanup"] + (["--prune=all"] if body.get("prune_all") else []) + (["-n"] if dry else [])
        return ("Vorschau: " if dry else "") + "Cleanup", [{"args": args}]
    if a == "autoremove":
        return ("Vorschau: " if dry else "") + "Autoremove", [{"args": ["autoremove"] + (["-n"] if dry else [])}]
    if a == "doctor":
        return "brew doctor", [{"args": ["doctor"]}]
    if a == "bundle_install":
        text = body.get("text", "")
        if not isinstance(text, str) or len(text) > 200_000:
            raise ValueError("Invalid Brewfile")
        brewlib.CONF_DIR.mkdir(exist_ok=True)
        path = brewlib.CONF_DIR / "Brewfile.import"
        path.write_text(text)
        return "Brewfile installieren", [{"args": ["bundle", "install", f"--file={path}", "--no-upgrade"]}]
    if a == "uninstall":
        items = body.get("items") or []
        also = body.get("also") or []
        if not all(valid_name(i.get("name")) and i.get("kind") in ("formula", "cask") for i in items) \
                or not all(valid_name(n) for n in also):
            raise ValueError("Invalid packages")
        versions = {(i["kind"], i["name"]): i["version"] for i in get_data()["items"]}
        rec = lambda k, n: {"name": n, "kind": k, "version": versions.get((k, n), "")}
        cmds = [{"args": ["uninstall", f"--{i['kind']}", i["name"]], "record": [rec(i["kind"], i["name"])]}
                for i in items]
        if also:
            cmds.append({"args": ["uninstall", "--formula", *also], "record": [rec("formula", n) for n in also]})
        return "Deinstallieren: " + ", ".join(i["name"] for i in items), cmds
    raise ValueError("Unknown action")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Browser hat die Verbindung schon geschlossen (z. B. beim Neuladen)

    def host_ok(self):
        return self.headers.get("Host") in HOSTS

    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "Host nicht erlaubt"})
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        p = url.path
        try:
            if p in STATIC:
                f, ctype = STATIC[p]
                body = (WEB / f).read_bytes()
                if p == "/":  # Theme/Sprache schon im HTML setzen, damit beim Laden nichts umspringt
                    cfg = brewlib.load_config()
                    if cfg["theme"] not in brewlib.THEMES or cfg["lang"] not in brewlib.LANGS:
                        cfg = brewlib.DEFAULT_CONFIG  # handgeschriebene Config nie ungeprüft ins HTML
                    body = body.replace(b'<html lang="en">', f'<html lang="{cfg["lang"]}" dir="{"rtl" if cfg["lang"] == "ar" else "ltr"}" data-theme="{cfg["theme"]}">'.encode(), 1)
                return self.send(200, body, ctype)
            if p == "/api/data":
                return self.send(200, {**public(get_data("refresh" in qs)), "config": brewlib.load_config()})
            if p == "/api/version":
                return self.send(200, {"version": VERSION})
            if p == "/api/update/status":
                return self.send(200, updater.status())
            if p == "/api/jobs":
                return self.send(200, JOBS.listing())
            if p.startswith("/api/jobs/"):
                job = JOBS.get(int(p.rsplit("/", 1)[1]))
                if not job:
                    return self.send(404, {"error": "Job nicht gefunden"})
                since = int(qs.get("since", ["0"])[0])
                return self.send(200, {**job.summary(), "log": job.lines[since:]})
            if p == "/api/catalog":
                g = lambda k, d="": qs.get(k, [d])[0]
                inst = {(i["kind"], i["name"]) for i in get_data()["items"]}
                return self.send(200, catalog.query(
                    inst, kind=g("kind", "all"), cat=g("cat"), q=g("q"), sort=g("sort", "pop"),
                    page=max(0, int(g("page", "0"))), only_new=g("new") == "1", refresh="refresh" in qs))
            if p == "/api/services":
                return self.send(200, {"services": brewlib.services()})
            if p == "/api/taps":
                return self.send(200, {"taps": brewlib.installed_taps()})
            if p == "/api/maintenance":
                return self.send(200, brewlib.cache_info())
            if p == "/api/history":
                return self.send(200, {"history": list(reversed(brewlib.load_history()))})
            if p == "/api/brewfile":
                text = brewlib.make_brewfile(get_data()["items"], [t for t in brewlib.installed_taps()
                                                                    if not t.startswith("homebrew/")])
                return self.send(200, text.encode(), "text/plain; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="Brewfile"'})
            self.send(404, {"error": "nicht gefunden"})
        except Exception as e:
            self.send(500, {"error": str(e)})

    def do_POST(self):
        if not self.host_ok():
            return self.send(403, {"error": "Host nicht erlaubt"})
        p = urlparse(self.path).path
        if p == "/api/askpass":  # vom sudo-Helfer, per Token abgesichert
            if self.headers.get("X-Askpass-Token") != TOKEN:
                return self.send(403, {"error": "Token"})
            prompt = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode(errors="replace")
            pw = JOBS.ask_password(prompt)
            return self.send(200 if pw is not None else 408, (pw or "").encode(), "text/plain")
        if self.headers.get("X-BrewUI") != "1" or self.headers.get("Origin") not in (None, *(f"http://{h}" for h in HOSTS)):
            return self.send(403, {"error": "Anfrage nicht erlaubt"})
        try:
            body = self.body()
            if p == "/api/action":
                _, cmds = build_job(body)
                title = "brew " + " ".join(cmds[0]["args"])[:60] + (f" (+{len(cmds) - 1})" if len(cmds) > 1 else "")
                return self.send(200, {"job": JOBS.submit(title, cmds).id})
            if p == "/api/preview-uninstall":
                d = get_data()
                names = [i["name"] for i in body.get("items", []) if i.get("kind") == "formula"]
                on_req = {i["name"] for i in d["items"] if i["kind"] == "formula" and i["on_request"]}
                return self.send(200, brewlib.removal_closure(names, d["deps_map"], on_req))
            if p == "/api/quit":
                self.send(200, {"ok": True})
                threading.Thread(target=SERVER["srv"].shutdown, daemon=True).start()
                return
            if p == "/api/update/check":
                return self.send(200, updater.check())
            if p == "/api/update/install":
                if any(j["status"] in ("queued", "running") for j in JOBS.listing()["jobs"]):
                    raise ValueError("Es läuft noch eine Aufgabe")
                info = updater.check()
                if not info["available"]:
                    raise ValueError("Kein Update verfügbar")
                def restart():
                    import time
                    time.sleep(1.5)  # die Oberfläche soll den Status noch abholen können
                    SERVER["srv"].shutdown()
                return self.send(200, {"ok": updater.install(info["asset"], restart)})
            if p == "/api/cancel":
                return self.send(200, {"ok": JOBS.cancel(int(body.get("id", 0)))})
            if p == "/api/askpass/answer":
                pw = None if body.get("cancel") else str(body.get("password", ""))
                return self.send(200, {"ok": JOBS.answer(pw)})
            if p == "/api/config":
                return self.send(200, brewlib.save_config(body))
            if p == "/api/brewfile/diff":
                d = get_data()["items"]
                formulae = {i["full_name"] for i in d if i["kind"] == "formula"} | {i["name"] for i in d if i["kind"] == "formula"}
                requested = {i["name"] for i in d if i["kind"] == "formula" and i["on_request"]}
                casks = {i["name"] for i in d if i["kind"] == "cask"}
                taps = set(brewlib.installed_taps())
                return self.send(200, brewlib.diff_brewfile(brewlib.parse_brewfile(body.get("text", "")),
                                                           formulae, casks, taps, requested))
            self.send(404, {"error": "nicht gefunden"})
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": str(e)})


def _local(path, body=None):
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-BrewUI": "1"}, method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read())


def already_running():
    """True, wenn auf dem Port schon eine *aktuelle* HomebrUI läuft. Eine ältere Version wird beendet und ersetzt."""
    import socket
    import time
    with socket.socket() as sk:
        sk.settimeout(0.5)
        if sk.connect_ex(("127.0.0.1", PORT)) != 0:
            return False
    try:
        if _local("/api/version").get("version") == VERSION:
            return True
    except Exception:
        pass  # sehr alte Version ohne /api/version
    try:
        if any(j["status"] in ("queued", "running") for j in _local("/api/jobs")["jobs"]):
            return True  # läuft gerade etwas: nicht unterbrechen
        _local("/api/quit", {})
    except Exception:
        return True  # nicht erreichbar/fremder Dienst: in Ruhe lassen
    for _ in range(30):
        time.sleep(0.2)
        with socket.socket() as sk:
            sk.settimeout(0.3)
            if sk.connect_ex(("127.0.0.1", PORT)) != 0:
                return False
    return True


def main():
    catalog.ensure()  # Katalog schon beim Start im Hintergrund laden
    url = f"http://127.0.0.1:{PORT}"
    if already_running():  # läuft schon (z. B. im Hintergrund): nur den Browser öffnen
        print("HomebrUI läuft schon auf", url)
        if "--no-open" not in sys.argv:
            webbrowser.open(url)
        return
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    SERVER["srv"] = srv
    print("HomebrUI läuft auf", url, "(Strg+C zum Beenden)")
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
