#!/usr/bin/env python3
# <xbar.title>HomebrUI</xbar.title>
# <xbar.desc>Zeigt Updates und Löschkandidaten in der Menüleiste (SwiftBar/xbar).</xbar.desc>
import sys
from pathlib import Path

loc = Path.home() / ".brew-aufraeumer" / "location"
if not loc.exists():
    print("🍺 ?\n---\nHomebrUI einmal starten (start.command)")
    sys.exit()
sys.path.insert(0, loc.read_text().strip())
import brewlib

cfg = brewlib.load_config()
items = brewlib.collect(cfg)["items"]
out = [i for i in items if i["outdated"]]
cand = [i for i in items if i["reasons"]]
print(f"🍺 {len(out)}↑ {len(cand)}🗑" if out or cand else "🍺")
print("---")
print(f"{len(out)} Updates | color=orange" if out else "Alles aktuell")
for i in out[:10]:
    print(f"--{i['name']} {i['version']} → {i['new_version']}")
print(f"{len(cand)} Löschkandidaten" if cand else "Keine Löschkandidaten")
for i in cand[:10]:
    print(f"--{i['name']}: {i['reasons'][0][1]}")
print("---")
print(f"HomebrUI öffnen | href=http://127.0.0.1:{cfg['port']}")
