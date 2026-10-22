#!/bin/bash
# Baut "HomebrUI.app": Doppelklick startet den Server im Hintergrund (ohne Terminal) und öffnet den Browser.
# Aufruf: ./make-app.sh [Zielordner]   (Standard: aktueller Ordner)
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$SRC}/HomebrUI.app"
rm -rf "$OUT"
mkdir -p "$OUT/Contents/MacOS" "$OUT/Contents/Resources"
cp -R "$SRC"/{server.py,brewlib.py,catalog.py,jobs.py,askpass.py,web} "$OUT/Contents/Resources/"
cat > "$OUT/Contents/Info.plist" <<'PL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>HomebrUI</string>
<key>CFBundleDisplayName</key><string>HomebrUI</string>
<key>CFBundleIdentifier</key><string>de.felix.homebrui</string>
<key>CFBundleExecutable</key><string>start</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1.0</string>
<key>LSUIElement</key><true/>
</dict></plist>
PL
cat > "$OUT/Contents/MacOS/start" <<'SH'
#!/bin/bash
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
# Python so finden wie im Terminal (Finder hat nur einen minimalen PATH)
PY="$(/bin/zsh -lic 'command -v python3' 2>/dev/null | tail -1)"
[ -x "$PY" ] || PY=/usr/bin/python3
mkdir -p "$HOME/.brew-aufraeumer"
# Auf Apple Silicon immer nativ starten (sonst läuft brew unter Rosetta und meldet sich als Intel)
ARCH=""
[ "$(/usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && ARCH="/usr/bin/arch -arm64"
nohup $ARCH "$PY" "$DIR/server.py" >"$HOME/.brew-aufraeumer/server.log" 2>&1 &
disown
SH
chmod +x "$OUT/Contents/MacOS/start"
echo "Fertig: $OUT"
