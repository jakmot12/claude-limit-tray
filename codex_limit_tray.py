"""Codex Limit Tray - the same taskbar widget, for OpenAI Codex.

Codex records your rate limits in its own session logs (~/.codex/sessions/**/rollout-*.jsonl) after
every turn. This widget only reads those files - no network, no tokens - so it shows the state as of
your last Codex use. Once a window's reset time has passed, it shows 100% again.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import claude_limit_tray as clt

APP = "CodexLimitTray"
CODEX_DIR = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
WINDOWS = {300: "five_hour", 10080: "seven_day"}  # window_minutes -> limit key
TAIL = 4_000_000  # read only the end of big session files

# Cloud-headed terminal buddy: '#' = body (level color), 'd' = dark screen, 'c' = glowing ">_".
MASCOT = [
    "...##..##..##...",
    "..############..",
    ".##############.",
    ".##dddddddddd##.",
    "##dcdddddddddd##",
    "##ddcddddddddd##",
    "##dcdddcccdddd##",
    ".##dddddddddd##.",
    ".##############.",
    "..############..",
    "....########....",
    "...##########...",
    "....########....",
    ".....##..##.....",
    ".....##..##.....",
]
PALETTE = {"d": (24, 30, 62), "c": (150, 225, 255)}
BLUE = (70, 110, 240)


def last_rate_limits():
    """(rate_limits dict, ISO timestamp) from the newest session that has them, or (None, None)."""
    files = [p for d in ("sessions", "archived_sessions") if (CODEX_DIR / d).is_dir()
             for p in (CODEX_DIR / d).rglob("rollout-*.jsonl")]
    for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
        found = []
        with open(f, "rb") as fh:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - TAIL))
            for line in fh:
                if b'"rate_limits"' in line and b'"used_percent"' in line:
                    found = (found + [line])[-3:]
        # newest first; skip a line Codex is still writing (or one cut by the tail seek)
        for line in reversed(found):
            try:
                ev = json.loads(line)
                rl = ev["payload"]["rate_limits"]
                if isinstance(rl, dict):
                    return rl, ev.get("timestamp")
            except (ValueError, KeyError, TypeError):
                continue
    return None, None


def fetch_codex():
    """Same (data, error, retry_after) shape as the Claude fetcher."""
    try:
        rl, ts = last_rate_limits()
    except OSError:
        return None, "Cannot read Codex sessions", None
    if not rl:
        return None, "No Codex usage recorded yet", None
    now = datetime.now(timezone.utc)
    data = {}
    for w in (rl.get("primary"), rl.get("secondary")):
        if not isinstance(w, dict) or WINDOWS.get(w.get("window_minutes")) is None:
            continue
        used, reset = w.get("used_percent"), w.get("resets_at")
        reset_dt = datetime.fromtimestamp(reset, timezone.utc) if isinstance(reset, (int, float)) else None
        if reset_dt and reset_dt <= now:
            used, reset_dt = 0, None  # window already reset since the last Codex use
        data[WINDOWS[w["window_minutes"]]] = {
            "utilization": used, "resets_at": reset_dt.isoformat() if reset_dt else None}
    if ts:
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
            data["note"] = f"As of last Codex use: {clt.DAYS[t.weekday()]} {t:%H:%M}"
        except ValueError:
            pass
    return data, None, None


if __name__ == "__main__":
    _mutex = clt.acquire_single_instance(APP)
    if _mutex is None:
        sys.exit(0)
    try:
        clt.App(name="Codex", app=APP, fetch=fetch_codex, color=BLUE, anchors=[clt.APP],
                script=__file__, mascot=MASCOT, palette=PALETTE).run()
    finally:
        clt.kernel32.CloseHandle(_mutex)
