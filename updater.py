"""Selbst-Update der App: neueste Version bei GitHub suchen, das passende DMG laden, prüfen und die App ersetzen."""
import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
from pathlib import Path

import brewlib

REPO = "Fese1000/HomebrUI"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
DL_PREFIX = f"https://github.com/{REPO}/releases/download/"
BUNDLE_ID = "de.felix.homebrui"
HERE = Path(__file__).resolve().parent
STATE = {"stage": "idle", "pct": 0, "error": None}
_lock = threading.Lock()


def parse_version(v):
    """'v1.2.3' -> (1, 2, 3); None, wenn es keine Versionsnummer ist."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+){0,3})", str(v).strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def current_version():
    try:
        return (HERE / "VERSION").read_text().strip() or None
    except OSError:
        return None


def app_bundle():
    """Pfad der laufenden .app, None beim Start aus dem Quellcode."""
    b = HERE.parent.parent
    return b if HERE.name == "Resources" and b.suffix == ".app" else None


def can_install():
    """(ok, Grund): ersetzt sich die App selbst nur, wenn sie als .app läuft und beschreibbar ist."""
    b = app_bundle()
    if not b:
        return False, "source"
    if not (os.access(b, os.W_OK) and os.access(b.parent, os.W_OK)):
        return False, "permission"
    return True, None


def asset_name():
    return "HomebrUI-%s.dmg" % ("AppleSilicon" if platform.machine() == "arm64" else "Intel")


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "HomebrUI", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def status():
    ok, why = can_install()
    return {"current": current_version(), "can_install": ok, "reason": why, **STATE}


def check():
    """Fragt GitHub nach der neuesten Version (nur auf Knopfdruck, es wird nichts gesendet außer der Anfrage selbst)."""
    cur = current_version()
    rel = _get_json(API)
    latest = parse_version(rel.get("tag_name", ""))
    if latest is None:
        raise ValueError("Unerwartete Antwort von GitHub")
    asset = next((a for a in rel.get("assets", []) if a.get("name") == asset_name()), None)
    available = bool(asset) and cur is not None and latest > (parse_version(cur) or (0,))
    return {**status(), "latest": rel["tag_name"].lstrip("v"), "available": available,
            "asset": asset and {"url": asset["browser_download_url"], "size": asset["size"], "digest": asset.get("digest")}}


def _set(stage, pct=0, error=None):
    STATE.update(stage=stage, pct=pct, error=error)


def _download(asset, dest):
    url = asset["url"]
    if not url.startswith(DL_PREFIX) or not (asset.get("digest") or "").startswith("sha256:"):
        raise ValueError("Download nicht vertrauenswürdig")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "HomebrUI"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or asset["size"] or 1)
        got = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            h.update(chunk)
            got += len(chunk)
            _set("download", min(99, got * 100 // total))
    if "sha256:" + h.hexdigest() != asset["digest"]:
        raise ValueError("Prüfsumme stimmt nicht")


def _run(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300] or f"{cmd[0]} fehlgeschlagen")


def _prepare(asset, work):
    """DMG laden, prüfen und die neue App nach work/new/HomebrUI.app kopieren."""
    dmg, mnt, new = work / "update.dmg", work / "mnt", work / "new"
    _download(asset, dmg)
    _set("install")
    mnt.mkdir()
    new.mkdir()
    _run("hdiutil", "attach", "-nobrowse", "-readonly", "-noverify", "-mountpoint", str(mnt), str(dmg))
    try:
        _run("ditto", str(mnt / "HomebrUI.app"), str(new / "HomebrUI.app"))
    finally:
        subprocess.run(["hdiutil", "detach", "-force", str(mnt)], capture_output=True)
    app = new / "HomebrUI.app"
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != BUNDLE_ID:
        raise ValueError("Unerwartete App im Update")
    if (parse_version(info.get("CFBundleShortVersionString", "")) or (0,)) <= (parse_version(current_version()) or (0,)):
        raise ValueError("Update ist nicht neuer")
    _run("codesign", "--verify", "--deep", "--strict", str(app))
    return app


def _helper(work, old, new, pids):
    """Kleines Skript, das wartet bis die App beendet ist, sie austauscht und neu startet."""
    script = work / "swap.sh"
    script.write_text(f"""#!/bin/sh
for p in {' '.join(str(p) for p in pids)}; do while kill -0 "$p" 2>/dev/null; do sleep 0.3; done; done
OLD='{old}'; NEW='{new}'
mv "$OLD" "$OLD.old" && {{ mv "$NEW" "$OLD" && rm -rf "$OLD.old" || mv "$OLD.old" "$OLD"; }}
open "$OLD"
rm -rf '{work}'
""")
    script.chmod(0o755)
    log = open(brewlib.CONF_DIR / "update.log", "w")
    subprocess.Popen(["/bin/sh", str(script)], stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)


def install(asset, on_restart):
    """Läuft im Hintergrund: laden, prüfen, Austausch-Skript starten, dann on_restart() (Server beenden)."""
    ok, _ = can_install()
    with _lock:
        if not ok or STATE["stage"] in ("download", "install", "restart"):
            return False
        _set("download")
    def run():
        work = None
        try:
            brewlib.CONF_DIR.mkdir(exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix="update-", dir=brewlib.CONF_DIR))
            new = _prepare(asset, work)
            _helper(work, app_bundle(), new, sorted({os.getpid(), os.getppid()} - {0, 1}))
            _set("restart")
            on_restart()
        except Exception as e:
            _set("error", error=str(e))
            if work:
                shutil.rmtree(work, ignore_errors=True)
    threading.Thread(target=run, daemon=True).start()
    return True
