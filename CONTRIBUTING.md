# Contributing to HomebrUI

Thanks for helping! Bug reports, ideas and pull requests are welcome. Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting bugs and ideas

Open an [issue](https://github.com/Fese1000/HomebrUI/issues/new/choose) and use the template. For a bug, include your macOS version, chip (Apple silicon or Intel), how you run HomebrUI (app or `python3 server.py`) and the end of `~/.brew-aufraeumer/server.log`. Security problems: see [SECURITY.md](SECURITY.md), not a public issue.

## Development

HomebrUI needs only Python 3 and no extra packages.

```bash
python3 server.py                     # run from source
python3 -m unittest discover tests    # tests
./make-app.sh arm64                   # build the app (needs Xcode Command Line Tools)
```

Layout and what each file does: see the table in the [README](README.md#layout).

## Pull requests

- Keep a change focused; one topic per pull request.
- Run the tests and try the change in the UI. Add a test in `tests/` when you touch logic in `brewlib.py`.
- Keep the dependencies at zero: standard library only, no frontend build step.
- New or changed UI text needs an entry in every language in `web/i18n.js` (en, de, fr, zh, es, pt, ar, ru). If you cannot translate all of them, say so in the pull request.
- Anything that changes a package must stay behind the existing checks in `server.py`: custom header, name validation and the fixed list of `brew` commands.
- Describe what you changed and why. Screenshots help for UI changes.
