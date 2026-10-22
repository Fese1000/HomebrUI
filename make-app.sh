#!/bin/bash
# Baut HomebrUI.app mit eingebettetem Python und eigenem Fenster (Swift/WKWebView) und packt sie als DMG.
# Aufruf: ./make-app.sh [arm64|x86_64|all]   (Standard: Architektur dieses Macs)
# Ergebnis: dist/HomebrUI-AppleSilicon.dmg und/oder dist/HomebrUI-Intel.dmg
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
DIST="$SRC/dist"; CACHE="$SRC/build/cache"
PYVER="3.13"
mkdir -p "$DIST" "$CACHE"

fetch_python() {  # $1 = arm64|x86_64 -> Pfad der Archivdatei
  local triple; [ "$1" = arm64 ] && triple=aarch64-apple-darwin || triple=x86_64-apple-darwin
  local f; f="$(ls "$CACHE"/cpython-$PYVER.*-$triple-install_only_stripped.tar.gz 2>/dev/null | tail -1 || true)"
  if [ -z "$f" ]; then
    local url
    url="$(curl -fsSL https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest |
      python3 -c "import sys,json;print(next(a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if a['name'].startswith('cpython-$PYVER.') and a['name'].endswith('-$triple-install_only_stripped.tar.gz')))")"
    f="$CACHE/$(basename "$url")"
    echo "Lade $(basename "$url") ..." >&2
    curl -fL --progress-bar -o "$f" "$url"
  fi
  echo "$f"
}

build() {  # $1 = arm64|x86_64
  local arch="$1" label; [ "$arch" = arm64 ] && label=AppleSilicon || label=Intel
  local stage="$SRC/build/$label" app="$SRC/build/$label/HomebrUI.app"
  rm -rf "$stage"; mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  cp -R "$SRC"/{server.py,brewlib.py,catalog.py,jobs.py,askpass.py,web} "$app/Contents/Resources/"
  tar -xzf "$(fetch_python "$arch")" -C "$app/Contents/Resources"   # ergibt Resources/python
  cp "$SRC/app/AppIcon.icns" "$app/Contents/Resources/AppIcon.icns"
  swiftc -O -target "$arch-apple-macos13" "$SRC/app/HomebrUI.swift" -o "$app/Contents/MacOS/HomebrUI"
  cat > "$app/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>HomebrUI</string>
<key>CFBundleDisplayName</key><string>HomebrUI</string>
<key>CFBundleIdentifier</key><string>de.felix.homebrui</string>
<key>CFBundleExecutable</key><string>HomebrUI</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1.0</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PL
  # Ad-hoc-Signatur (nötig, damit Apple-Silicon-Macs die App starten); echte Signatur: CODESIGN_ID="Developer ID Application: ..."
  codesign --force --deep --sign "${CODESIGN_ID:--}" "$app"
  ln -s /Applications "$stage/Programme"
  rm -f "$DIST/HomebrUI-$label.dmg"
  hdiutil create -quiet -volname HomebrUI -srcfolder "$stage" -ov -format UDZO "$DIST/HomebrUI-$label.dmg"
  echo "Fertig: $DIST/HomebrUI-$label.dmg"
}

case "${1:-$(uname -m)}" in
  arm64)  build arm64 ;;
  x86_64) build x86_64 ;;
  all)    build arm64; build x86_64 ;;
  *) echo "Aufruf: $0 [arm64|x86_64|all]"; exit 1 ;;
esac
