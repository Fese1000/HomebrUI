# HomebrUI

A native Mac app for [Homebrew](https://brew.sh). See everything you have installed, find out what you can safely remove, browse and install from the full catalog, upgrade, manage services and taps, and back up your setup with a Brewfile.

Everything runs locally on your Mac (`127.0.0.1`); nothing is sent anywhere except the catalog download from Homebrew.

## Download

Get the app from the [latest release](https://github.com/Fese1000/HomebrUI/releases/latest), open the DMG and drag HomebrUI to Applications. Python is included, nothing else to install.

- **HomebrUI-AppleSilicon.dmg** for Macs with Apple silicon (M1 and later)
- **HomebrUI-Intel.dmg** for Intel Macs

The app is not notarized, so macOS asks once on the first start (see [As an app](#as-an-app-without-a-terminal) below).

> HomebrUI is an independent project and is not affiliated with Homebrew.

## Features

- **Packages** – every formula and cask with size, install date and estimated last use. Removal candidates are flagged: orphaned dependencies, casks whose app is gone, deprecated or disabled packages, and missing dependencies. Click a package to see what it needs and what needs it. Before uninstalling you see what would disappear with it. A history lets you reinstall anything you removed.
- **Install** – browse the whole catalog (~15,000 formulae and casks) by category, search, sort by popularity and install with one click. Categories are estimated from names and descriptions, because Homebrew itself has none.
- **Updates** – `brew update`, a preview of all upgrades, upgrade one or everything, pin packages.
- **Services, taps, maintenance** – start and stop services, add and remove taps, `cleanup`, `autoremove` and `doctor`, each with a preview where Homebrew supports it.
- **Brewfile** – export what you installed, import a Brewfile, compare it with this Mac and install only what is missing.
- **Live log** for every action. If a step needs `sudo`, the password is asked in the UI, passed straight to `sudo` and never stored.
- **8 languages** – English (default), German, French, Mandarin Chinese, Spanish, Portuguese, Arabic (right-to-left) and Russian.
- **12 color schemes** – default (light, dark or following the system), Solarized, Gruvbox, Nord, Dracula, Monokai, Tokyo Night, One Dark and Catppuccin.

Language, color scheme, the "long unused" threshold and a list of ignored packages are set in the settings (gear icon).

## Requirements

- macOS 13 or later with Homebrew installed
- To run from source: Python 3 (tested with 3.13 and 3.15), no extra packages
- Internet access for the catalog in the Install view (cached for 24 hours)

## Run from source

Double-click `start.command`, or:

```bash
python3 server.py
```

The server uses port 8765. To use a different one: `PORT=8766 python3 server.py`.

### As an app, without a terminal

```bash
./make-app.sh all     # or: arm64 | x86_64
```

Builds `dist/HomebrUI-AppleSilicon.dmg` and `dist/HomebrUI-Intel.dmg`. Each contains a native macOS app with its own window (WKWebView), the HomebrUI server and an embedded Python, so nothing else has to be installed: open the DMG and drag the app to Applications. The first build downloads the matching [python-build-standalone](https://github.com/astral-sh/python-build-standalone) once (cached in `build/cache`). Building needs the Xcode Command Line Tools (`swiftc`); the app needs macOS 13+.

The app is only ad-hoc signed, so macOS warns on the first start of a downloaded copy. On macOS 15 and later: try to open the app once, then go to System Settings → Privacy & Security and click "Open Anyway". On macOS 13/14: right-click the app, then Open. For a proper signature and notarization set `CODESIGN_ID="Developer ID Application: ..."` and notarize the DMG with `notarytool`. Quit with the power icon or by closing the window. Log: `~/.brew-aufraeumer/server.log`.

### Menu bar (optional)

With [SwiftBar](https://github.com/swiftbar/SwiftBar), copy `swiftbar/brew-aufraeumer.30m.py` into your plugin folder. It shows the number of updates and removal candidates. Start HomebrUI once first.

## Tests

```bash
python3 -m unittest discover tests
```

## Security

- Listens on `127.0.0.1` only; requests with an unexpected `Host` or `Origin` are rejected.
- Anything that changes something requires a custom header, so other websites cannot trigger actions.
- Package names are checked against a strict pattern, and only a fixed set of `brew` commands can be run.
- Settings and history are stored in `~/.brew-aufraeumer/`.

## Layout

| Path | Purpose |
| --- | --- |
| `server.py` | HTTP server and API |
| `brewlib.py` | Reads Homebrew, computes removal candidates, Brewfile logic |
| `catalog.py` | Catalog download, cache and categories |
| `jobs.py` | Background jobs, live output, `sudo` prompt |
| `askpass.py` | Helper that `sudo` calls to ask for the password |
| `web/` | User interface and translations (`i18n.js`) |
| `swiftbar/` | Optional menu bar plugin |

## License

[MIT](LICENSE)
