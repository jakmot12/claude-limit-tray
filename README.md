<div align="center">

# Claude Limit Tray

**Your remaining Claude Code and OpenAI Codex usage limits right on the Windows taskbar — just like the battery percentage.**

<p>
  <img src="taskbar.png" alt="Codex and Claude widgets on the Windows 11 taskbar next to the system tray" />
  <br />
  <sub>Codex (blue) and Claude (orange) on the Windows 11 taskbar, right next to the system tray.</sub>
</p>

<p>
  <img src="preview.png" alt="Claude Limit Tray states: 87%, 25%, 5% and offline" />
  <br />
  <sub>All 4 states at actual taskbar size (rendered directly by the app).</sub>
</p>

<p>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4?style=flat-square" alt="Windows 10/11" />
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License" />
</p>

</div>

---

A tiny Windows taskbar widget that displays a pixel-art mascot and your remaining usage percentage next to the system tray — no Electron, no background bloat, just plain Python scripts. One widget for **Claude Code**, an optional second one for **OpenAI Codex**; they line up next to each other automatically.

## Features

- **Battery-style taskbar indicator** — crisp pixel-art mascot + remaining percentage rendered with `Segoe UI Variable` (plain `Segoe UI` on Windows 10), sized like the battery icon (tested at 100% display scaling; other scales are approximated).
- **5-hour & 7-day limits** — switch which window is shown on the taskbar via the right-click menu; hover to see **both limits** and exact reset countdowns.
- **At-a-glance color coding** — Claude orange (`≥ 30%`) → yellow (`< 30%`) → red (`< 10%`); gray with `?` when there is no data (offline or sign-in expired: open Claude Code to refresh it).
- **Stays out of your way** — automatically hides during fullscreen games/videos, when an auto-hidden taskbar collapses, or when the taskbar isn't at the bottom of the primary monitor.
- **Start with Windows** — optional one-click Startup shortcut in the context menu, plus single-instance protection so you never launch duplicates.

## Controls

| Action | Behavior |
| :--- | :--- |
| **Hover** | Show both 5-hour and 7-day remaining limits with reset times |
| **Left-click** | Refresh usage immediately |
| **Right-click** | Switch limit (**5 hours** / **Week**), **Refresh now**, toggle **Start with Windows**, or **Quit** |

## Requirements

- **Windows 10 or 11** (bottom taskbar on primary monitor)
- **Python 3.10+**
- **[Claude Code](https://claude.com/claude-code)** installed and signed in (Pro or Max plan)
- *Optional:* **[Codex](https://openai.com/codex)** (CLI or app, ChatGPT plan) for the Codex widget

## Quick Start

```powershell
git clone https://github.com/jakmot12/claude-limit-tray.git
cd claude-limit-tray
python -m pip install -r requirements.txt
pythonw claude_limit_tray.py
pythonw codex_limit_tray.py   # optional: the Codex widget
```

Each widget has its own right-click menu, including its own **Start with Windows** toggle.

## Codex widget

[`codex_limit_tray.py`](codex_limit_tray.py) shows a blue cloud-terminal mascot with your remaining Codex 5-hour / weekly limit. It works fully **offline**: Codex itself records your rate limits in its session logs (`%USERPROFILE%\.codex\sessions\**ollout-*.jsonl`) after every turn, and the widget reads the latest entry.

- The value reflects your **last Codex use** — the tooltip says when that was. Once a window's reset time passes, it shows 100% again.
- It never touches `.codexuth.json` and makes **no network requests**.
- Respects `CODEX_HOME` if you moved the Codex folder.

## Privacy & Security

- **Read-only credentials** — reads your existing Claude Code OAuth token from `%USERPROFILE%\.claude\.credentials.json`. It never writes, logs, or refreshes the token.
- **Direct HTTPS only** — sends the token exclusively to `https://api.anthropic.com/api/oauth/usage` with certificate verification and an honest `User-Agent` (`claude-limit-tray`). Zero third-party servers, zero telemetry.
- **Does not consume usage** — polling only reads your quota counter; it does not send prompts or invoke any model.
- **Local-only color sampling** — periodically samples a tiny 2 px strip of your taskbar in memory to blend font edges cleanly with your wallpaper. Nothing is ever saved or transmitted.
- **Codex widget is local-only** — it only reads Codex's own session logs; no tokens, no network.
- **Minimal footprint** — stores only `%APPDATA%\ClaudeLimitTray\settings.json` / `%APPDATA%\CodexLimitTray\settings.json` (selected limit) and, if enabled, a Startup shortcut. Two small readable files: [`claude_limit_tray.py`](claude_limit_tray.py) and [`codex_limit_tray.py`](codex_limit_tray.py).

> [!WARNING]
> **Never share your `.credentials.json` file with anyone** — it grants full access to your Claude account.

> [!NOTE]
> This is an unofficial tool not affiliated with Anthropic or OpenAI. It uses the same undocumented OAuth usage endpoint as Claude Code's `/usage` command, which may change without notice.

## License

[MIT](LICENSE)
