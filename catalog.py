"""Katalog aller Homebrew-Pakete zum Stöbern. Quelle: formulae.brew.sh (öffentlich), 24 h lokal zwischengespeichert.

Homebrew selbst kennt keine Kategorien; sie werden hier aus Name und Beschreibung geschätzt.
"""
import gzip
import json
import re
import threading
import time
import urllib.request

from brewlib import CONF_DIR

BASE = "https://formulae.brew.sh/api/"
TTL = 24 * 3600
FILE = CONF_DIR / "catalog.json"
PAGE = 60

# Reihenfolge = Priorität: die erste passende Kategorie gewinnt.
CATEGORIES = [
    ("languages", r"\b(programming language|language runtime|compiler for|interpreter for|javascript runtime|jdk|openjdk|golang|rustc|nodejs|node\.js|lua|php|kotlin|haskell|ocaml|julia|zig|erlang|elixir|scala|clojure|typescript|dotnet|swift)\b|^(python|ruby|node|go|rust|perl|java|deno|bun)(@[\d.]+)? "),
    ("databases", r"\b(database|databases|sql|sqlite|postgres\w*|mysql|mariadb|redis|mongodb|key-value|elasticsearch|cassandra|dbms|datastore)\b"),
    ("security", r"\b(security|secure|encrypt\w*|crypto\w*|password|gpg|pgp|vulnerabilit\w*|firewall|authenticat\w*|certificate|malware|pentest\w*|forensic\w*|antivirus|keychain|secrets?|2fa|otp)\b"),
    ("media", r"\b(audio|video|videos|photo|photos|music|ffmpeg|media player|codec|pdf|fonts?|svg|jpeg|png|camera|podcast|screenshots?|subtitles?|epub|ebook|drawing|painting|illustration|image (editor|viewer|processing|manipulation|converter|library)|graphics (editor|software)|3d (modeling|printing|model)|streaming (app|client|service))\b"),
    ("science", r"\b(bioinformatics|genom\w*|sequenc\w*|scientific|science|statistic\w*|math\w*|plot\w*|chemistry|chemical|machine learning|neural|llm|ai|numerical|simulation|jupyter|dna|rna|protein\w*|molecul\w*|data analysis|dataset\w*|csv|tensor\w*|physics|astronomy|geospatial|gis|bio\w*)\b"),
    ("games", r"\b(game|games|gaming|game emulator|console emulator|retro|chess|puzzle|arcade|minecraft|steam)\b"),
    ("network", r"\b(http|https|network\w*|dns|proxy|vpn|ssh|ftp|web server|curl|wget|nginx|apache|download\w*|torrent|packet|wifi|wi-fi|tcp|udp|ssl|tls|websocket|api gateway|load balanc\w*|cdn|tunnel\w*|bandwidth|port scanner|email server)\b"),
    ("comms", r"\b(browser|chat|messag\w*|email|e-mail|video conferenc\w*|slack|discord|telegram|whatsapp|matrix|irc|mastodon|twitter|social|voip|meeting|webcam)\b"),
    ("dev", r"\b(build|debugger|linter|formatter|ide|editor|git|version control|ci|code|sdk|test\w*|lsp|package manager|docker|container\w*|kubernetes|terraform|devops|cloud|aws|azure|gcp|framework|developer|development|api|diff|merge|profiler|logging|deploy\w*|cmake|make|compile\w*|parser|regex)\b"),
    ("shell", r"\b(shell|terminal|command-line|command line|cli|tui|zsh|bash|fish|prompt|tmux|multiplexer|fuzzy|grep|find|json|yaml|xml|text|utility|utilities|unix|coreutils|pager|cat|ls|sed|awk|rename|calculator|benchmark\w*)\b"),
    ("system", r"\b(system|monitor\w*|disk|backup|file|files|archive|compress\w*|window manager|menu bar|menubar|clipboard|launcher|keyboard|hardware|driver|usb|battery|cleaner|uninstall\w*|storage|sync|mount|filesystem|cpu|memory|process\w*|task manager|automation|macos)\b"),
    ("office", r"\b(note|notes|todo|calendar|office|document\w*|markdown|productivity|task|tasks|writing|spreadsheet|presentation|bookmark\w*|reader|rss|journal|time tracking|planner|wiki|knowledge)\b"),
    ("libs", r"\b(library|libraries|bindings|lib|headers|sdk)\b"),
]
_RX = [(c, re.compile(p, re.I)) for c, p in CATEGORIES]
OTHER = "other"

_lock = threading.Lock()
_mem = {"items": None, "time": 0, "error": None, "thread": None}


def categorize(name, desc):
    text = f"{name} {desc}"
    for cat, rx in _RX:
        if rx.search(text):
            return cat
    if name.startswith("lib"):
        return "libs"
    return OTHER


def _recat(items):
    """Kategorien beim Laden neu berechnen, damit Regel-Änderungen ohne neuen Download wirken."""
    for it in items:
        it["cat"] = categorize(f"{it['name']} {it.get('title', '')}", it["desc"])
    return items


def _get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "HomebrUI", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw)


def _count(entry):
    return int(str(entry.get("count", "0")).replace(",", "") or 0)


def build():
    formulae, casks = _get("formula.json"), _get("cask.json")
    pop_f = {e["formula"]: _count(e) for e in _get("analytics/install/30d.json")["items"]}
    pop_c = {e["cask"]: _count(e) for e in _get("analytics/cask-install/30d.json")["items"]}
    items = []
    for e in formulae:
        if e.get("disabled"):
            continue
        d = e.get("desc") or ""
        items.append({"kind": "formula", "name": e["name"], "desc": d, "homepage": e.get("homepage"),
                      "version": (e.get("versions") or {}).get("stable") or "", "pop": pop_f.get(e["name"], 0),
                      "deprecated": bool(e.get("deprecated")), "cat": categorize(e["name"], d)})
    for e in casks:
        if e.get("disabled"):
            continue
        d = e.get("desc") or ""
        title = (e.get("name") or [e["token"]])[0]
        items.append({"kind": "cask", "name": e["token"], "title": title, "desc": d, "homepage": e.get("homepage"),
                      "version": str(e.get("version") or ""), "pop": pop_c.get(e["token"], 0),
                      "deprecated": bool(e.get("deprecated")), "cat": categorize(f"{e['token']} {title}", d)})
    return items


def _load(refresh=False):
    now = time.time()
    if not refresh:
        try:
            saved = json.loads(FILE.read_text())
            if now - saved["time"] < TTL:
                _mem.update(items=_recat(saved["items"]), time=saved["time"])
                return
        except (OSError, ValueError, KeyError):
            pass
    try:
        items = build()
    except Exception:
        if _mem["items"]:
            return
        try:  # Offline: alten Stand weiterbenutzen
            saved = json.loads(FILE.read_text())
            _mem.update(items=_recat(saved["items"]), time=saved["time"])
            return
        except (OSError, ValueError, KeyError):
            raise RuntimeError("offline")
    CONF_DIR.mkdir(exist_ok=True)
    FILE.write_text(json.dumps({"time": now, "items": items}))
    _mem.update(items=items, time=now)


def _worker(refresh):
    try:
        _load(refresh)
    except Exception as e:
        _mem["error"] = str(e)


def ensure(refresh=False):
    """Startet das Laden im Hintergrund, falls der Katalog fehlt oder zu alt ist."""
    with _lock:
        fresh = _mem["items"] and not refresh and time.time() - _mem["time"] < TTL
        if fresh or (_mem["thread"] and _mem["thread"].is_alive()):
            return
        _mem["error"] = None
        _mem["thread"] = threading.Thread(target=_worker, args=(refresh,), daemon=True)
        _mem["thread"].start()


def query(installed, kind="all", cat="", q="", sort="pop", page=0, only_new=False, refresh=False):
    """installed: Menge von (kind, name). Gibt Seite, Gesamtzahl und Kategorien-Zähler zurück."""
    ensure(refresh)
    if not _mem["items"]:
        return {"error": _mem["error"]} if _mem["error"] else {"loading": True}
    q = q.lower().strip()
    pool = []
    for it in _mem["items"]:
        if kind != "all" and it["kind"] != kind:
            continue
        is_in = (it["kind"], it["name"]) in installed
        if only_new and is_in:
            continue
        if q and q not in (it["name"] + " " + it.get("title", "") + " " + it["desc"]).lower():
            continue
        pool.append((it, is_in))
    cats = {}
    for it, _ in pool:
        cats[it["cat"]] = cats.get(it["cat"], 0) + 1
    if cat:
        pool = [p for p in pool if p[0]["cat"] == cat]
    pool.sort(key=(lambda p: p[0]["name"]) if sort == "name" else (lambda p: (-p[0]["pop"], p[0]["name"])))
    chunk = pool[page * PAGE:(page + 1) * PAGE]
    return {"total": len(pool), "page": page, "size": PAGE, "cats": cats,
            "items": [{**it, "installed": is_in} for it, is_in in chunk]}
