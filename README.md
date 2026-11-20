<div align="center">

# Limit Tray for Claude & Codex

**Your remaining Claude Code and OpenAI Codex usage limits right on the Windows taskbar — just like the battery percentage.**

<p>
  <img src="taskbar.png" alt="Codex and Claude widgets on the Windows 11 taskbar next to the system tray" />
  <br />
  <sub>Codex (blue) and Claude (orange) on the Windows 11 taskbar, right next to the system tray.</sub>
</p>

<table>
  <tr>
    <th>Claude</th>
    <th>Codex</th>
  </tr>
  <tr>
    <td><img src="preview.png" alt="Claude widget states: 87%, 25%, 5% and offline" /></td>
    <td><img src="preview-codex.png" alt="Codex widget states: 87%, 25%, 5% and offline" /></td>
  </tr>
</table>
<sub>All states at actual taskbar size (rendered directly by the app).</sub>

<p>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4?style=flat-square" alt="Windows 10/11" />
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License" />
</p>

</div>

---

A tiny Windows taskbar widget that shows a pixel-art mascot and how much of your usage limit is **left**, right next to the system tray. No Electron, no background bloat, just plain Python. Run the Claude widget, the Codex widget, or both: they line up next to each other automatically.

## Install

You need **Windows 10/11**, **[Python 3.10+](https://www.python.org/downloads/)** and **[Git](https://git-scm.com/download/win)**. Paste one command into **PowerShell**:

### Claude

Requires [Claude Code](https://claude.com/claude-code) installed and signed in (Pro or Max plan).

```powershell
git clone https://github.com/jakmot12/claude-limit-tray.git; cd claude-limit-tray; python -m pip install -r requirements.txt; pythonw claude_limit_tray.py
```

### Codex

Requires [Codex](https://openai.com/codex) (CLI or app) used at least once with a ChatGPT plan.

```powershell
git clone https://github.com/jakmot12/claude-limit-tray.git; cd claude-limit-tray; python -m pip install -r requirements.txt; pythonw codex_limit_tray.py
```

### Both

```powershell
git clone https://github.com/jakmot12/claude-limit-tray.git; cd claude-limit-tray; python -m pip install -r requirements.txt; pythonw claude_limit_tray.py; pythonw codex_limit_tray.py
```

> [!TIP]
> To launch it automatically, **right-click the mascot → Start with Windows**. Each widget has its own toggle.

**Update:** `cd claude-limit-tray; git pull`, then restart the widget (right-click → **Quit**, run it again).
**Uninstall:** turn off **Start with Windows**, **Quit**, and delete the folder.

## Features

- **Battery-style taskbar indicator** — crisp pixel-art mascot + remaining percentage in `Segoe UI Variable` (plain `Segoe UI` on Windows 10), sized like the battery icon (tested at 100% display scaling; other scales are approximated).
- **5-hour & weekly limits** — pick which one the taskbar shows in the right-click menu; hover to see **both** with exact reset countdowns.
- **At-a-glance color coding** — brand color (`≥ 30%`) → yellow (`< 30%`) → red (`< 10%`); gray with `?` when there is no data.
- **Stays out of your way** — hides during fullscreen games/videos, when an auto-hidden taskbar collapses, or when the taskbar isn't at the bottom of the primary monitor.
- **Single instance** — launching it twice never creates duplicates.

## Controls

| Action | Behavior |
| :--- | :--- |
| **Hover** | Show both 5-hour and weekly remaining limits with reset times |
| **Left-click** | Refresh immediately |
| **Right-click** | Switch limit (**5 hours** / **Week**), **Refresh now**, toggle **Start with Windows**, or **Quit** |

## How it gets the data

| | Claude | Codex |
| :--- | :--- | :--- |
| **Source** | Claude Code's usage endpoint (`api.anthropic.com/api/oauth/usage`), polled every 3 minutes | The rate limits Codex writes into its own session logs (`%USERPROFILE%\.codex\sessions`) after every turn |
| **Network** | HTTPS to `api.anthropic.com` only | None, fully offline |
| **Credentials** | Reads the Claude Code token from `%USERPROFILE%\.claude\.credentials.json` (read-only, never refreshed or logged) | None, never touches `.codex\auth.json` |
| **Freshness** | Live | As of your **last Codex use** (shown in the tooltip); after a reset time passes it shows 100% |
| **Custom folder** | `CLAUDE_CONFIG_DIR` | `CODEX_HOME` |

## Privacy & Security

- **No telemetry, no third-party servers.** The Claude widget talks only to Anthropic, with an honest `User-Agent` (`claude-limit-tray`); the Codex widget makes no requests at all.
- **Does not consume usage** — it only reads your quota counters; it never sends prompts or calls a model.
- **Local-only color sampling** — it samples a 2 px strip of your taskbar in memory to blend text edges with your wallpaper. Nothing is saved or sent.
- **Minimal footprint** — stores only `%APPDATA%\ClaudeLimitTray\settings.json` / `%APPDATA%\CodexLimitTray\settings.json` (selected limit) and, if enabled, a Startup shortcut. Two small readable files: [`claude_limit_tray.py`](claude_limit_tray.py) and [`codex_limit_tray.py`](codex_limit_tray.py).

> [!WARNING]
> **Never share your `.credentials.json` or `.codex\auth.json`** — they grant full access to your accounts.

> [!NOTE]
> Unofficial tool, not affiliated with Anthropic or OpenAI. It relies on an undocumented Claude endpoint and on Codex's log format, either of which may change without notice.

## License

[MIT](LICENSE)
