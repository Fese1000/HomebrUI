"""Logik des Brew Aufräumers: liest Homebrew aus und rechnet. Keine UI, nur Standardbibliothek."""
import json
import os
import platform
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

BREW = next((p for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew") if os.path.exists(p)), "brew")


def _native_prefix():
    """Läuft Python unter Rosetta (x86_64) auf einem Apple-Silicon-Mac, würde brew sich als Intel melden.
    Dann brew erzwungen nativ (arm64) starten."""
    try:
        if platform.machine() == "x86_64" and subprocess.run(
                ["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True).stdout.strip() == "1":
            return ["/usr/bin/arch", "-arm64"]
    except OSError:
        pass
    return []


BREW_CMD = [*_native_prefix(), BREW]
ENV = {**os.environ, "HOMEBREW_NO_AUTO_UPDATE": "1", "HOMEBREW_NO_ANALYTICS": "1",
       "HOMEBREW_NO_COLOR": "1", "HOMEBREW_NO_EMOJI": "1"}
CONF_DIR = Path.home() / ".brew-aufraeumer"
DEFAULT_CONFIG = {"port": 8765, "theme": "auto", "lang": "en", "stale_days": 180, "ignore": []}
THEMES = ("auto", "light", "dark", "solarized-light", "solarized-dark", "gruvbox-light", "gruvbox-dark", "nord", "dracula",
          "monokai", "tokyo-night", "one-dark", "catppuccin-latte", "catppuccin-mocha")
LANGS = ("en", "de", "fr", "zh", "es", "pt", "ar", "ru")
_SEG = r"[A-Za-z0-9@_+][A-Za-z0-9@._+-]*"
NAME_RE = re.compile(rf"^{_SEG}(/{_SEG}){{0,2}}$")
BREWFILE_RE = re.compile(r'^\s*(brew|cask|tap|mas|vscode|whalebrew)\s+"([^"]+)"')


def valid_name(name):
    return isinstance(name, str) and bool(NAME_RE.match(name))


def run(*args, check=True, timeout=300):
    r = subprocess.run([*BREW_CMD, *args], capture_output=True, text=True, env=ENV,
                       stdin=subprocess.DEVNULL, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r


# ---------- Einstellungen & Verlauf ----------

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads((CONF_DIR / "config.json").read_text()))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(new):
    cfg = load_config()
    if new.get("theme") in THEMES:
        cfg["theme"] = new["theme"]
    if new.get("lang") in LANGS:
        cfg["lang"] = new["lang"]
    if isinstance(new.get("port"), int) and 1024 <= new["port"] <= 65535:
        cfg["port"] = new["port"]
    if isinstance(new.get("stale_days"), int) and 1 <= new["stale_days"] <= 3650:
        cfg["stale_days"] = new["stale_days"]
    if isinstance(new.get("ignore"), list):
        cfg["ignore"] = sorted({n for n in new["ignore"] if valid_name(n)})
    CONF_DIR.mkdir(exist_ok=True)
    (CONF_DIR / "config.json").write_text(json.dumps(cfg, indent=1))
    return cfg


def load_history():
    try:
        return json.loads((CONF_DIR / "history.json").read_text())
    except (OSError, ValueError):
        return []


def add_history(entry):
    hist = load_history()
    hist.append({**entry, "time": int(time.time())})
    CONF_DIR.mkdir(exist_ok=True)
    (CONF_DIR / "history.json").write_text(json.dumps(hist[-200:], indent=1))


# ---------- reine Rechenfunktionen (getestet) ----------

def removal_closure(selected, deps_map, on_request):
    """Was verschwindet zusätzlich, wenn `selected` deinstalliert wird, und was blockiert es?

    deps_map: Paket -> Liste seiner Laufzeit-Abhängigkeiten (nur installierte Formulae).
    on_request: Pakete, die der Nutzer selbst installiert hat (die bleiben immer).
    """
    selected = set(selected)
    dependents = {}
    for pkg, deps in deps_map.items():
        for d in deps:
            dependents.setdefault(d, set()).add(pkg)
    removed = set(selected)
    changed = True
    while changed:
        changed = False
        for r in list(removed):
            for d in deps_map.get(r, []):
                if d in removed or d in on_request or d not in deps_map:
                    continue
                if dependents.get(d, set()) <= removed:
                    removed.add(d)
                    changed = True
    blocked = {n: sorted(dependents[n] - removed) for n in selected if dependents.get(n, set()) - removed}
    return {"also": sorted(removed - selected), "blocked": blocked}


def parse_brewfile(text):
    out = {}
    for line in text.splitlines():
        m = BREWFILE_RE.match(line)
        if m:
            out.setdefault(m.group(1), []).append(m.group(2))
    return out


def diff_brewfile(parsed, formulae, casks, taps, requested=None):
    """Vergleicht ein Brewfile mit dem Ist-Zustand.

    formulae/casks/taps: Mengen aller installierten Namen; requested: nur die selbst installierten
    Formulae (nur diese zählen als "überzählig", Abhängigkeiten nicht).
    """
    short = lambda n: n.split("/")[-1]
    norm = {"brew": short, "cask": lambda n: n, "tap": lambda n: n}
    have = {"brew": set(formulae), "cask": set(casks), "tap": set(taps)}
    mine = {"brew": set(requested if requested is not None else formulae), "cask": set(casks), "tap": set(taps)}
    res = {"missing": {}, "extra": {}, "unsupported": 0}
    for kind in ("brew", "cask", "tap"):
        f = norm[kind]
        wanted = {f(w) for w in parsed.get(kind, [])}
        installed = {f(h) for h in have[kind]}
        res["missing"][kind] = [w for w in parsed.get(kind, []) if f(w) not in installed]
        res["extra"][kind] = sorted(h for h in mine[kind] if f(h) not in wanted)
    res["unsupported"] = sum(len(v) for k, v in parsed.items() if k not in norm)
    return res


def make_brewfile(items, taps):
    lines = [f'tap "{t}"' for t in sorted(taps)]
    lines += [f'brew "{i["full_name"]}"' for i in sorted(items, key=lambda x: x["name"])
              if i["kind"] == "formula" and i["on_request"]]
    lines += [f'cask "{i["name"]}"' for i in sorted(items, key=lambda x: x["name"]) if i["kind"] == "cask"]
    return "\n".join(lines) + "\n"


# ---------- Daten von Homebrew ----------

_size_cache = {}


def dir_size(path):
    try:
        key = (str(path), os.stat(path).st_mtime_ns)
    except OSError:
        return 0
    if key in _size_cache:
        return _size_cache[key]
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    _size_cache[key] = total
    return total


def formula_last_used(prefix, name):
    """Schätzung über den letzten Zugriff auf die Programmdateien (auf macOS nur ungefähr)."""
    newest = None
    for sub in ("bin", "sbin"):
        try:
            entries = list((Path(prefix) / "opt" / name / sub).iterdir())
        except OSError:
            continue
        for e in entries:
            try:
                newest = max(newest or 0, e.stat().st_atime)
            except OSError:
                pass
    return newest


def app_last_used(path):
    try:
        r = subprocess.run(["mdls", "-name", "kMDItemLastUsedDate", "-raw", path],
                           capture_output=True, text=True, timeout=10)
        out = r.stdout.strip()
        if out and out != "(null)":
            return datetime.strptime(out, "%Y-%m-%d %H:%M:%S %z").timestamp()
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def installed_taps():
    return [t for t in run("tap", check=False).stdout.split() if t]


def collect(cfg=None):
    cfg = cfg or load_config()
    ignore = set(cfg["ignore"])
    info = json.loads(run("info", "--json=v2", "--installed").stdout)
    cellar = Path(run("--cellar").stdout.strip())
    caskroom = Path(run("--caskroom").stdout.strip())
    prefix = run("--prefix").stdout.strip()
    leaves = set(run("leaves", check=False).stdout.split())
    orphans = set(re.findall(r"^(\S+)$", run("autoremove", "-n", check=False).stdout, re.M))
    missing = {}
    for line in run("missing", check=False).stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            missing[k.strip()] = v.split()

    full2name = {f["full_name"]: f["name"] for f in info["formulae"]}
    deps_map = {}
    for f in info["formulae"]:
        inst = (f.get("installed") or [{}])[-1]
        deps = [full2name.get(d["full_name"], d["full_name"]) for d in inst.get("runtime_dependencies") or []]
        deps_map[f["name"]] = [d for d in deps if d in full2name.values()]
    used_by = {n: [] for n in deps_map}
    for n, ds in deps_map.items():
        for d in ds:
            used_by[d].append(n)

    pool = ThreadPoolExecutor(8)
    items = []
    futures = []
    for f in info["formulae"]:
        n = f["name"]
        inst = (f.get("installed") or [{}])[-1]
        reasons = []
        if n in orphans:
            reasons.append(("orphan", ""))
        if n in missing:
            reasons.append(("missing", ", ".join(missing[n])))
        if f.get("disabled"):
            reasons.append(("disabled", ""))
        elif f.get("deprecated"):
            reasons.append(("deprecated", ""))
        new_ver = (f.get("versions") or {}).get("stable") or ""
        if new_ver and f.get("revision"):
            new_ver += f"_{f['revision']}"
        item = {
            "kind": "formula", "name": n, "full_name": f["full_name"], "desc": f.get("desc") or "",
            "version": inst.get("version", ""), "homepage": f.get("homepage"),
            "installed_at": inst.get("time"), "size": 0,
            "on_request": bool(inst.get("installed_on_request")),
            "is_leaf": n in leaves, "used_by": sorted(used_by[n]), "deps": sorted(deps_map[n]),
            "reasons": [] if n in ignore else reasons, "ignored": n in ignore,
            "outdated": bool(f.get("outdated")), "new_version": new_ver, "pinned": bool(f.get("pinned")),
            "last_used": None, "last_used_exact": False,
        }
        futures.append((item, pool.submit(dir_size, cellar / n), pool.submit(formula_last_used, prefix, n)))
        items.append(item)
    for c in info["casks"]:
        n = c["token"]
        apps = [a for art in c.get("artifacts", []) if isinstance(art, dict) for a in art.get("app", [])
                if isinstance(a, str)]
        found = [p for a in apps for p in (os.path.join("/Applications", a), os.path.expanduser(f"~/Applications/{a}"))
                 if os.path.exists(p)]
        reasons = []
        if apps and not found:
            reasons.append(("app-missing", ", ".join(apps)))
        if c.get("disabled"):
            reasons.append(("disabled", ""))
        elif c.get("deprecated"):
            reasons.append(("deprecated", ""))
        item = {
            "kind": "cask", "name": n, "full_name": n, "desc": c.get("desc") or "",
            "version": str(c.get("installed") or ""), "homepage": c.get("homepage"),
            "installed_at": c.get("installed_time"), "size": 0, "on_request": True, "is_leaf": True,
            "used_by": [], "deps": [], "apps": apps, "reasons": [] if n in ignore else reasons,
            "ignored": n in ignore, "outdated": bool(c.get("outdated")), "new_version": str(c.get("version") or ""),
            "pinned": bool(c.get("pinned")), "last_used": None, "last_used_exact": bool(found),
        }
        cask_dir = caskroom / n
        futures.append((item, pool.submit(dir_size, cask_dir) if cask_dir.exists() else None,
                        pool.submit(app_last_used, found[0]) if found else None))
        items.append(item)
    for item, size_f, used_f in futures:
        item["size"] = size_f.result() if size_f else 0
        item["last_used"] = used_f.result() if used_f else None
    pool.shutdown()
    return {"items": items, "generated": int(time.time()), "stale_days": cfg["stale_days"],
            "deps_map": deps_map}


def search(query):
    out = []
    for kind in ("formula", "cask"):
        r = run("search", f"--{kind}", query, check=False)
        names = [l.strip() for l in r.stdout.splitlines() if l.strip() and not l.startswith("==>")][:15]
        names = [n for n in names if valid_name(n)]
        if not names:
            continue
        data = json.loads(run("info", "--json=v2", f"--{kind}", *names, check=False).stdout or "{}")
        for e in data.get("formulae" if kind == "formula" else "casks", []):
            out.append({"kind": kind, "name": e["name"] if kind == "formula" else e["token"],
                        "desc": e.get("desc") or "", "homepage": e.get("homepage"),
                        "version": (e.get("versions") or {}).get("stable") if kind == "formula" else e.get("version"),
                        "installed": bool(e.get("installed"))})
    return out


def services():
    r = run("services", "list", "--json", check=False)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return []


def cache_info():
    cache = run("--cache", check=False).stdout.strip()
    return {"cache_path": cache, "cache_bytes": dir_size(cache) if cache else 0,
            "brew_version": run("--version", check=False).stdout.splitlines()[0]}
