"""Antigravity Limit Tray - the same taskbar widget, for Google Antigravity.

Reads the Antigravity sign-in token (read-only) from Windows Credential Manager and asks Google's
Cloud Code server - the same one Antigravity itself uses - for the remaining quota per model pool.
The token lives only ~1 hour and only Antigravity refreshes it, so between uses the widget shows
the last known values (saved to disk) - once a pool's reset time passes it shows 100% again.

Data-source logic originally drafted by the Antigravity agent (agy).
"""
import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

import requests

import claude_limit_tray as clt

APP = "AntigravityLimitTray"
API = "https://daily-cloudcode-pa.googleapis.com/v1internal"
CRED_TARGET = "gemini:antigravity"
CACHE = Path(os.environ["APPDATA"]) / APP / "last.json"
UA = "antigravity-limit-tray/1.0 (+https://github.com/jakmot12/claude-limit-tray)"

LIMITS = {
    "lowest": "Lowest",
    "gemini-5h": "Gemini (5h)",
    "gemini-weekly": "Gemini (Week)",
    "3p-5h": "Claude & GPT (5h)",
    "3p-weekly": "Claude & GPT (Week)",
}

# Multicolor pixel "A" (12x10). Letters map to PALETTE colors; the whole logo turns yellow/red when low.
MASCOT = [
    ".....ab.....",
    "....cadb....",
    "...efgdbb...",
    "...higdjj...",
    "..iklmnopq..",
    "..hlr..rsp..",
    "..tu....rr..",
    ".tvv....wwr.",
    ".xy......ww.",
    "yy........ww",
]
PALETTE = {
    "a": (255, 135, 0), "b": (255, 95, 95), "c": (215, 175, 95), "d": (255, 135, 95), "e": (175, 215, 95),
    "f": (175, 175, 95), "g": (215, 135, 95), "h": (135, 215, 95), "i": (135, 175, 95), "j": (215, 95, 95),
    "k": (95, 175, 95), "l": (95, 175, 135), "m": (95, 135, 175), "n": (135, 135, 175), "o": (135, 95, 215),
    "p": (135, 95, 175), "q": (175, 95, 135), "r": (95, 135, 215), "s": (95, 95, 215), "t": (95, 215, 135),
    "u": (95, 175, 175), "v": (95, 175, 215), "w": (95, 135, 255), "x": (95, 215, 175), "y": (95, 175, 255),
}
BLUE = (95, 135, 255)  # base color (only used to detect the normal state)

# ---------- token (read-only) ----------


class CREDENTIALW(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", wintypes.LPVOID),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
advapi32.CredReadW.restype = wintypes.BOOL
advapi32.CredFree.argtypes = [wintypes.LPVOID]


def read_token():
    """(access_token, expired) from Credential Manager, or (None, False). Never writes or refreshes."""
    ptr = ctypes.POINTER(CREDENTIALW)()
    if not advapi32.CredReadW(CRED_TARGET, 1, 0, ctypes.byref(ptr)):  # 1 = CRED_TYPE_GENERIC
        return None, False
    try:
        c = ptr.contents
        raw = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize) if c.CredentialBlob else b""
    finally:
        advapi32.CredFree(ptr)
    try:
        text = raw.decode("utf-8").strip()
        if text.startswith("go-keyring-base64:"):
            text = base64.b64decode(text[len("go-keyring-base64:"):]).decode("utf-8")
        obj = json.loads(text)
        tok = obj.get("token", obj)
        at, exp = tok.get("access_token"), tok.get("expiry")
    except (ValueError, AttributeError):
        return None, False
    expired = False
    if isinstance(exp, str):
        try:
            expired = datetime.fromisoformat(exp.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
        except ValueError:
            pass
    return (at, expired) if isinstance(at, str) and at else (None, False)

# ---------- data ----------


def _used(obj):
    """remainingFraction (0..1) -> used % (proto3 JSON omits 0.0, so resetTime alone means 0% left)."""
    rf = obj.get("remainingFraction")
    if isinstance(rf, (int, float)):
        return max(0, min(100, round(100 - rf * 100)))
    return 100 if obj.get("resetTime") else None


def parse(models, summary):
    """Pools -> {key: {"utilization", "resets_at"}} (the shape the shared widget code expects)."""
    out = {}
    pools = {"gemini-5h": [], "3p-5h": []}
    for mid, info in ((models or {}).get("models") or {}).items():
        qi = info.get("quotaInfo") if isinstance(info, dict) else None
        if not isinstance(qi, dict) or mid.lower().startswith("tab_"):
            continue
        used = _used(qi)
        key = "gemini-5h" if mid.lower().startswith("gemini") else \
              "3p-5h" if mid.lower().startswith(("claude", "gpt")) else None
        if key and used is not None:
            pools[key].append((used, qi.get("resetTime")))
    for key, items in pools.items():
        if items:
            used, rt = max(items, key=lambda x: (x[0], bool(x[1])))  # most used model in the pool
            out[key] = {"utilization": used, "resets_at": rt}
    for grp in (summary or {}).get("groups") or []:
        for b in (grp.get("buckets") or []) if isinstance(grp, dict) else []:
            used = _used(b) if isinstance(b, dict) else None
            if b.get("bucketId") in LIMITS and used is not None:
                out[b["bucketId"]] = {"utilization": used, "resets_at": b.get("resetTime")}
    return out


def fetch_live():
    """(pools, error). Skips the network entirely when the token is already expired."""
    token, expired = read_token()
    if not token:
        return None, "Not signed in to Antigravity"
    if expired:
        return None, "Open Antigravity to refresh"
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA}
    try:
        with requests.Session() as s:
            rm = s.post(f"{API}:fetchAvailableModels", json={}, timeout=10, headers=h)
            if rm.status_code in (401, 403):
                return None, "Open Antigravity to refresh"
            if rm.status_code == 429:
                return None, "Too many requests"
            rs = s.post(f"{API}:retrieveUserQuotaSummary", json={}, timeout=10, headers=h)
            pools = parse(rm.json() if rm.ok else None, rs.json() if rs.ok else None)
    except requests.RequestException:
        return None, "No connection"
    except ValueError:
        return None, "Invalid server response"
    return (pools, None) if pools else (None, f"Server error {rm.status_code}")


def fetch_antigravity():
    """Live data when possible, otherwise the last saved values. Pools whose reset time has passed
    are shown as full again - so the cached numbers stay true until you use Antigravity again."""
    pools, err = fetch_live()
    now = datetime.now(timezone.utc)
    if pools:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"at": now.isoformat(), "pools": pools}), encoding="utf-8")
        at = now
    else:
        try:
            c = json.loads(CACHE.read_text(encoding="utf-8"))
            pools, at = c["pools"], datetime.fromisoformat(c["at"])
        except (OSError, ValueError, KeyError, TypeError):
            return None, err, None
    data = {}
    for k, p in pools.items():
        try:
            if p.get("resets_at") and datetime.fromisoformat(p["resets_at"].replace("Z", "+00:00")) <= now:
                p = {"utilization": 0, "resets_at": None}
        except (ValueError, AttributeError):
            pass
        data[k] = p
    used = [p["utilization"] for p in data.values() if isinstance(p.get("utilization"), (int, float))]
    if used:
        worst = max(data.values(), key=lambda p: p.get("utilization") or 0)
        data["lowest"] = {"utilization": max(used), "resets_at": worst.get("resets_at")}
    if err:
        t = at.astimezone()
        data["note"] = f"As of {clt.DAYS[t.weekday()]} {t:%H:%M} - {err}"
    return data, None, None


if __name__ == "__main__":
    _mutex = clt.acquire_single_instance(APP)
    if _mutex is None:
        sys.exit(0)
    try:
        clt.App(name="Antigravity", app=APP, fetch=fetch_antigravity, color=BLUE,
                anchors=["CodexLimitTray", clt.APP], script=__file__,
                mascot=MASCOT, palette=PALETTE, limits=LIMITS, tint_all=True).run()
    finally:
        clt.kernel32.CloseHandle(_mutex)
