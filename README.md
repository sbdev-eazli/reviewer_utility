# reviewer_utility

View GitHub pull request review comments (inline, per-file/line), review summaries, general comments and the diff — in a local web UI or in the terminal. Also lists your repos' open PRs and lets you approve a PR.

## Requirements

- Python 3.8+ (standard library only, no pip installs)
- [GitHub CLI](https://cli.github.com/) (`gh`), authenticated: `gh auth login`

## Setup

```bash
git clone https://github.com/sbdev-eazli/reviewer_utility.git ~/reviewer_utility
cd ~/reviewer_utility
gh auth status   # make sure you're logged in
```

## Usage

### Web UI

```bash
python3 app.py            # serves on http://127.0.0.1:8765/ and opens your browser
python3 app.py --port 9000
```

The server listens on `127.0.0.1` only.

### Terminal

```bash
python3 reviewer_utility.py --pr https://github.com/<owner>/<repo>/pull/<number>
python3 reviewer_utility.py --pr <PR_URL> --repo /path/to/local/checkout   # also show the local line text
```

## Run as a systemd service

To keep the web UI running in the background and start it at login, run it as a **user** service. It then runs as you, with your `gh` login.

1. Create `~/.config/systemd/user/reviewer-utility.service`:

   ```ini
   [Unit]
   Description=GitHub PR reviewer utility (web UI)
   After=network-online.target

   [Service]
   Type=simple
   WorkingDirectory=%h/reviewer_utility
   ExecStart=/usr/bin/python3 -u %h/reviewer_utility/app.py --port 8765
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=default.target
   ```

   Change `WorkingDirectory`/`ExecStart` if you cloned it somewhere other than `~/reviewer_utility`. `%h` is your home directory.

2. Enable and start it:

   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now reviewer-utility.service
   ```

3. Open http://127.0.0.1:8765/ in your browser.

Useful commands:

```bash
systemctl --user status reviewer-utility     # is it running?
journalctl --user -u reviewer-utility -f     # follow logs
systemctl --user restart reviewer-utility    # after pulling updates
systemctl --user disable --now reviewer-utility
```

If `gh` isn't in `/usr/bin` or `/usr/local/bin` (for example Homebrew on Linux), add `Environment=PATH=/path/to/gh/dir:/usr/bin:/bin` under `[Service]`.

To keep the service running after you log out, run `loginctl enable-linger $USER` once.
