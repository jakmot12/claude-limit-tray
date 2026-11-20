"""Claude Limit Tray - a tiny widget on the Windows taskbar next to the system tray:
a pixel mascot + how much of your Claude usage limit is left (like the battery percentage).

Unofficial tool, not affiliated with Anthropic. The Claude Code token is only read locally
and sent exclusively to api.anthropic.com over HTTPS.
"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageTk

APP = "ClaudeLimitTray"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
CREDS = CLAUDE_DIR / ".credentials.json"


def settings_path(app):
    return Path(os.environ["APPDATA"]) / app / "settings.json"


def startup_lnk(app):
    return Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup" / f"{app}.lnk"


POLL_OK, POLL_ERR, MAX_BACKOFF = 180, 30, 900
LIMITS = {"five_hour": "5 hours", "seven_day": "Week"}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
NO_WINDOW = 0x08000000
GAP = 8  # gap between the widget and the system tray, in px
# ---------- data ----------

# Identify honestly with our own name (do not impersonate Claude Code).
UA = "claude-limit-tray/1.2 (+https://github.com/jakmot12/claude-limit-tray)"


def fetch_usage():
    """Returns (data, error, retry_after)."""
    try:
        token = json.loads(CREDS.read_text(encoding="utf-8"))["claudeAiOauth"]["accessToken"]
    except Exception:
        return None, "Not signed in to Claude Code", None
    try:
        r = requests.get(USAGE_URL, timeout=10, headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": UA,
        })
    except requests.RequestException:
        return None, "No connection", None
    if r.status_code == 401:
        return None, "Open Claude Code to refresh your sign-in", None
    if r.status_code == 429:
        ra = r.headers.get("Retry-After", "")
        return None, "Too many requests, waiting", int(ra) if ra.isdigit() else None
    if not r.ok:
        return None, f"Server error {r.status_code}", None
    try:
        data = r.json()
    except ValueError:
        return None, "Invalid server response", None
    return (data, None, None) if isinstance(data, dict) else (None, "Invalid server response", None)


def remaining(data, key):
    w = (data or {}).get(key)
    u = w.get("utilization") if isinstance(w, dict) else None
    return max(0, min(100, round(100 - u))) if isinstance(u, (int, float)) else None


def reset_text(data, key):
    w = (data or {}).get(key)
    s = w.get("resets_at") if isinstance(w, dict) else None
    if not isinstance(s, str):
        return ""
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return ""
    secs = int((t - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "resets now"
    if secs < 60:
        return "resets in <1m"
    if secs < 3600:
        return f"resets in {secs // 60}m"
    if secs < 86400:
        return f"resets in {secs // 3600}h {secs % 3600 // 60}m"
    lt = t.astimezone()
    return f"resets {DAYS[lt.weekday()]} {lt:%H:%M}"

# ---------- look ----------

# Pixel mascot: wide body, slit eyes, little arms, 4 legs.
# 20x12 px - the size of the battery icon on the taskbar (drawn 1:1, no scaling).
MASCOT = [
    "..################..",
    "..################..",
    "..###.########.###..",
    "..###.########.###..",
    "..###.########.###..",
    "####################",
    "####################",
    "..################..",
    "..################..",
    "..################..",
    "...#.#........#.#...",
    "...#.#........#.#...",
]


CLAUDE_ORANGE = (217, 119, 87)


def level_color(pct, base=CLAUDE_ORANGE):
    if pct is None:
        return (140, 140, 140)
    if pct < 10:
        return (217, 69, 59)
    if pct < 30:
        return (232, 176, 74)
    return base


def taskbar_color(tray_left, top):
    """Real taskbar color (it is translucent, so it depends on the wallpaper) - sampled from the
    top edge of the taskbar above the widget."""
    from PIL import ImageGrab
    try:
        x2 = max(20, tray_left - GAP)
        x1 = max(0, x2 - 100)
        strip = ImageGrab.grab(bbox=(x1, top + 2, x2, top + 4)).convert("RGB")
        px = sorted(strip.getdata(), key=sum)
        return px[len(px) // 2]
    except Exception:
        return (32, 32, 32)


def is_light(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b > 140


def font(size):
    """Segoe UI Variable - the same font Windows 11 uses for the battery percentage."""
    try:
        f = ImageFont.truetype("SegUIVar.ttf", size)
        axes = f.get_variation_axes()
        f.set_variation_by_axes([400 if a["name"] in (b"Weight", "Weight") else a["default"] for a in axes])
        return f
    except Exception:
        try:
            return ImageFont.truetype("segoeuib.ttf", size)
        except OSError:
            return ImageFont.load_default()


def render(text, pct, height, bg, base=CLAUDE_ORANGE, rows=MASCOT, palette=None, tint_all=False):
    """Like the battery: 20x12 icon scaled to DPI, 4 px gap, 12 px percentage text; vertically centered.
    In `rows`, '#' is drawn in the level color and other letters come from `palette` (char -> RGB)."""
    dpi = max(1.0, height / 48)  # smooth scaling (also for 125% and 150% DPI)
    w0, h0 = len(rows[0]), len(rows)
    mw, mh = round(w0 * dpi), round(h0 * dpi)
    f = font(max(10, round(12 * dpi)))
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tl, _, tr, _ = probe.textbbox((0, 0), text, font=f, anchor="ls")
    tx = mw + round(4 * dpi)
    img = Image.new("RGB", (tx + (tr - tl) + 1, height), bg)
    d = ImageDraw.Draw(img)
    oy = (height - mh) // 2  # like the battery icon: rows 18-29 on a 48 px taskbar
    color = level_color(pct, base)
    colors = dict(palette or {}, **{"#": color})
    if tint_all and color != base:  # low / offline: the whole multicolor logo takes the warning color
        colors = dict.fromkeys(colors, color)
    mascot = Image.new("RGBA", (w0, h0), (0, 0, 0, 0))
    md = ImageDraw.Draw(mascot)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in colors:
                md.point((x, y), fill=colors[ch] + (255,))
    if (mw, mh) != (w0, h0):
        mascot = mascot.resize((mw, mh), Image.Resampling.NEAREST)
    img.paste(mascot, (0, oy), mascot)
    # always white, like the battery percentage (intentional design choice, independent of taskbar brightness)
    d.text((tx - tl, height // 2 + round(4 * dpi)), text, font=f, fill=(255, 255, 255), anchor="ls")
    return img

# ---------- settings / autostart ----------

def load_settings(app, limits=LIMITS):
    try:
        s = json.loads(settings_path(app).read_text(encoding="utf-8"))
        if s.get("limit") in limits:
            return s
    except Exception:
        pass
    return {"limit": next(iter(limits))}


def save_settings(app, s):
    settings_path(app).parent.mkdir(parents=True, exist_ok=True)
    settings_path(app).write_text(json.dumps(s), encoding="utf-8")


def set_autostart(on, app=APP, script=None):
    if not on:
        startup_lnk(app).unlink(missing_ok=True)
        return
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.exists():
        pyw = Path(sys.executable)
    script = Path(script or __file__).resolve()
    # paths are passed via environment variables, never pasted into the command text (no injection)
    env = dict(os.environ, CLT_LNK=str(startup_lnk(app)), CLT_PYW=str(pyw),
               CLT_ARGS=f'"{script}"', CLT_DIR=str(script.parent))
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:CLT_LNK);"
          "$s.TargetPath=$env:CLT_PYW;$s.Arguments=$env:CLT_ARGS;"
          "$s.WorkingDirectory=$env:CLT_DIR;$s.Save()")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                   env=env, creationflags=NO_WINDOW)

# ---------- taskbar (Win32) ----------

user32 = ctypes.windll.user32
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
ERROR_ALREADY_EXISTS = 183


def acquire_single_instance(app=APP):
    """Returns a mutex handle, or None if another copy of the app is already running."""
    h = kernel32.CreateMutexW(None, False, f"Local\\{app}_SingleInstance")
    if not h:
        return None
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(h)
        return None
    return h


def win_rect(h):
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT), ("rc", wintypes.RECT), ("lParam", wintypes.LPARAM)]


ABM_GETTASKBARPOS, ABE_BOTTOM = 5, 3


def window_title(app):
    """Every widget titles its window like this, so sibling widgets can line up next to each other."""
    return f"LimitTray:{app}"


def tray_geometry(anchors=()):
    """(left edge to stand next to, taskbar top, taskbar height), or None when the widget should hide:
    the taskbar is not at the bottom (side/top), or an auto-hidden taskbar is currently collapsed.
    The left edge is the first visible sibling widget from `anchors`, else the system tray."""
    tb = user32.FindWindowW("Shell_TrayWnd", None)
    if not tb:
        return None
    abd = APPBARDATA(cbSize=ctypes.sizeof(APPBARDATA))
    if ctypes.windll.shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(abd)) and abd.uEdge != ABE_BOTTOM:
        return None
    l, t, r, b = win_rect(tb)
    if b - t <= 0 or t > user32.GetSystemMetrics(1) - (b - t) // 2:
        return None  # auto-hide: the taskbar slid down off the screen
    tn = user32.FindWindowExW(tb, None, "TrayNotifyWnd", None)
    left = win_rect(tn)[0] if tn else r - 300
    for a in anchors:
        h = user32.FindWindowW(None, window_title(a))
        if h and user32.IsWindowVisible(h):
            left = win_rect(h)[0]
            break
    return left, t, b - t


def fullscreen_app_active():
    """Do not draw over fullscreen games / videos."""
    h = user32.GetForegroundWindow()
    if not h:
        return False
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(h, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
        return False
    l, t, r, b = win_rect(h)
    return l <= 0 and t <= 0 and r >= user32.GetSystemMetrics(0) and b >= user32.GetSystemMetrics(1)

# ---------- app ----------

class App:
    def __init__(self, name="Claude", app=APP, fetch=None, color=CLAUDE_ORANGE, anchors=(), script=None,
                 mascot=MASCOT, palette=None, limits=LIMITS, tint_all=False):
        self.limits, self.tint_all = limits, tint_all
        self.mascot, self.palette = mascot, palette
        self.name, self.app, self.color, self.anchors = name, app, color, tuple(anchors)
        self.fetch, self.script = fetch or fetch_usage, script
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        self.settings = load_settings(app, limits)
        self.data, self.error = None, None
        self.wake = threading.Event()
        self.closing = False
        self._visible = True

        self.root = tk.Tk()
        self.root.title(window_title(app))
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.bg = (32, 32, 32)  # updated from a screen sample
        self.key = "#010203"  # transparent color key
        self.root.configure(bg=self.key)
        self.root.attributes("-transparentcolor", self.key)
        self.label = tk.Label(self.root, bg=self.key, bd=0)
        self.label.pack()
        self.photo = None

        self.limit_var = tk.StringVar(value=self.settings["limit"])
        self.auto_var = tk.BooleanVar(value=startup_lnk(app).exists())
        self.menu = tk.Menu(self.root, tearoff=0)
        for k, name in self.limits.items():
            self.menu.add_radiobutton(label=name, value=k, variable=self.limit_var, command=self.pick)
        self.menu.add_separator()
        self.menu.add_command(label="Refresh now", command=self.wake.set)
        self.menu.add_checkbutton(label="Start with Windows", variable=self.auto_var,
                                  command=lambda: set_autostart(self.auto_var.get(), self.app, self.script))
        self.menu.add_command(label="Quit", command=self.close)

        self.tip = None
        self.label.bind("<Button-3>", self.show_menu)
        self.label.bind("<Button-1>", lambda e: self.wake.set())
        self.label.bind("<Enter>", self.show_tip)
        self.label.bind("<Leave>", self.hide_tip)

    # --- UI ---
    def show_menu(self, e):
        self.hide_tip()
        self.root.focus_force()
        self.menu.tk_popup(e.x_root, e.y_root)

    def close(self):
        self.closing = True
        self.wake.set()
        self.hide_tip()
        self.root.destroy()

    def pick(self):
        self.settings["limit"] = self.limit_var.get()
        save_settings(self.app, self.settings)
        self.redraw()

    def tip_text(self):
        lines = []
        for k, name in self.limits.items():
            r = remaining(self.data, k)
            if r is not None:
                lines.append(f"{name}: {r}% left  ·  {reset_text(self.data, k)}")
        if (self.data or {}).get("note"):
            lines.append(self.data["note"])
        if self.error:
            lines.append(self.error)
        return f"{self.name}\n" +"\n".join(lines or ["Loading…"])

    def show_tip(self, _e=None):
        self.hide_tip()
        self.tip = tk.Toplevel(self.root)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        light = is_light(self.bg)
        tip_bg, tip_fg, tip_bd = ("#f3f3f3", "#181818", "#d0d0d0") if light else ("#2b2b2b", "white", "#454545")
        tk.Label(self.tip, text=self.tip_text(), justify="left", bg=tip_bg, fg=tip_fg,
                 highlightthickness=1, highlightbackground=tip_bd,
                 font=("Segoe UI", 10), padx=10, pady=6).pack()
        self.tip.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() - self.tip.winfo_width()
        y = self.root.winfo_y() - self.tip.winfo_height() - 8
        self.tip.geometry(f"+{x}+{y}")

    def hide_tip(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None

    def redraw(self):
        geo = tray_geometry(self.anchors)
        if not geo:
            return  # taskbar hidden / not at the bottom - keep_on_taskbar hides the widget
        left, top, height = geo
        pct = remaining(self.data, self.settings["limit"])
        if self.data is None:
            text = "?" if self.error else "…"
        else:
            text = f"{pct}%" if pct is not None else "–"
        self.bg = taskbar_color(left, top)
        img = render(text, pct, height, self.bg, self.color, self.mascot, self.palette, self.tint_all)
        # background (taskbar color) -> transparent; text edges stay anti-aliased against the taskbar color
        rgba = img.convert("RGBA")
        key_rgb = tuple(int(self.key[i:i + 2], 16) for i in (1, 3, 5))
        rgba.putdata([key_rgb + (255,) if p[:3] == self.bg else p for p in rgba.getdata()])
        self.photo = ImageTk.PhotoImage(rgba)
        self.label.configure(image=self.photo)
        self.root.geometry(f"{img.width}x{height}+{left - img.width - GAP}+{top}")

    def keep_on_taskbar(self):
        """Every second: stick to the system tray and stay on top of the taskbar; hide over fullscreen apps,
        a collapsed (auto-hidden) taskbar, or a side/top taskbar - never float over the screen."""
        if self.closing:
            return
        geo = tray_geometry(self.anchors)
        if fullscreen_app_active() or not geo:
            if self._visible:
                self.hide_tip()
                self.root.withdraw()
                self._visible = False
        else:
            if not self._visible:
                self.root.deiconify()
                self._visible = True
            self.root.attributes("-topmost", True)
            self.root.lift()
            self._ticks = getattr(self, "_ticks", 0) + 1
            moved = geo != getattr(self, "_geo", None)
            if moved or (self._ticks % 5 == 0 and
                         sum(abs(a - b) for a, b in zip(taskbar_color(geo[0], geo[1]), self.bg)) > 24):
                self._geo = geo
                self.redraw()  # system tray moved or wallpaper changed
        self.root.after(1000, self.keep_on_taskbar)

    # --- data ---
    def apply_result(self, data, err):
        if self.closing:
            return
        if data is not None:
            self.data, self.error = data, None
        else:
            self.error = err
        self.redraw()
        if self.tip:
            self.show_tip()

    def poll_loop(self):
        backoff = POLL_ERR
        while not self.closing:
            data, err, retry = self.fetch()
            if data is not None:
                backoff, wait = POLL_ERR, POLL_OK
            else:
                wait = retry or backoff
                backoff = min(backoff * 2, MAX_BACKOFF)
            if self.closing:
                return
            try:
                self.root.after(0, self.apply_result, data, err)
            except (RuntimeError, tk.TclError):
                return
            self.wake.wait(min(wait, MAX_BACKOFF))
            self.wake.clear()

    def run(self):
        self.redraw()
        threading.Thread(target=self.poll_loop, daemon=True).start()
        self.keep_on_taskbar()
        self.root.mainloop()


if __name__ == "__main__":
    _mutex = acquire_single_instance()
    if _mutex is None:
        sys.exit(0)
    try:
        App().run()
    finally:
        kernel32.CloseHandle(_mutex)
