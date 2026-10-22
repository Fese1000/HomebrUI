# Security Policy

## Supported versions

Only the latest [release](https://github.com/Fese1000/HomebrUI/releases/latest) is supported.

## Reporting a vulnerability

Please do not open a public issue. Report it privately with GitHub's [private vulnerability reporting](https://github.com/Fese1000/HomebrUI/security/advisories/new) ("Security" tab → "Report a vulnerability").

Include what you found, how to reproduce it and which version you tested. You will get an answer as soon as possible; this is a hobby project, so please allow a few days.

## What is in scope

HomebrUI runs a local server on `127.0.0.1` that can run a fixed set of `brew` commands and, if you enter it, passes your `sudo` password straight to `sudo` without storing it. Interesting reports include: access from other websites or other hosts, running commands outside the allowed set, and leaking the password or the request token. How this is protected is described under "Security" in the [README](README.md#security).
