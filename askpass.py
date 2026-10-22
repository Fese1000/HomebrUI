"""Von sudo aufgerufen (SUDO_ASKPASS): fragt das Passwort beim lokalen Brew-Aufräumer-Server ab.

Aufruf: askpass.py PORT TOKEN [PROMPT]. Das Passwort wird nur auf stdout an sudo gegeben, nie gespeichert.
"""
import sys
import urllib.request

port, token = sys.argv[1], sys.argv[2]
prompt = " ".join(sys.argv[3:]) or "Passwort"
req = urllib.request.Request(f"http://127.0.0.1:{port}/api/askpass", data=prompt.encode(),
                             headers={"X-Askpass-Token": token}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=200) as r:
        sys.stdout.write(r.read().decode())
except Exception:
    sys.exit(1)
