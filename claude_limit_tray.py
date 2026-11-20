"""Claude Limit Tray - okienko na pasku zadan obok zasobnika: ludek + ile zostalo limitu Claude'a (jak bateria).

Nieoficjalne narzedzie, niezwiazane z Anthropic. Token Claude Code jest tylko odczytywany lokalnie
i wysylany wylacznie do api.anthropic.com przez HTTPS.
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
SETTINGS = Path(os.environ["APPDATA"]) / APP / "settings.json"
STARTUP_LNK = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup" / f"{APP}.lnk"

POLL_OK, POLL_ERR, MAX_BACKOFF = 180, 30, 900
LIMITS = {"five_hour": "5 godzin", "seven_day": "Tydzień"}
DAYS = ["pon", "wt", "śr", "czw", "pt", "sob", "nd"]
NO_WINDOW = 0x08000000
GAP = 8  # odstep od zasobnika w px
# ---------- dane ----------

def find_claude_exe():
    """claude.exe tylko z absolutnych katalogow PATH - bez szukania w biezacym folderze i bez powloki."""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = Path(d) / "claude.exe"
        if d and Path(d).is_absolute() and p.is_file():
            return p
    return None


def claude_version():
    exe = find_claude_exe()
    if exe:
        try:
            out = subprocess.run([str(exe), "--version"], capture_output=True, text=True,
                                 timeout=15, creationflags=NO_WINDOW).stdout.split()
            if out and all(c.isdigit() or c == "." for c in out[0]):
                return out[0]
        except Exception:
            pass
    return "2.1.0"


UA = f"claude-code/{claude_version()}"


def fetch_usage():
    """Zwraca (dane, blad, retry_after)."""
    try:
        token = json.loads(CREDS.read_text(encoding="utf-8"))["claudeAiOauth"]["accessToken"]
    except Exception:
        return None, "Brak logowania Claude Code", None
    try:
        r = requests.get(USAGE_URL, timeout=10, headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": UA,
        })
    except requests.RequestException:
        return None, "Brak połączenia", None
    if r.status_code == 401:
        return None, "Otwórz Claude Code, żeby odświeżyć logowanie", None
    if r.status_code == 429:
        ra = r.headers.get("Retry-After", "")
        return None, "Za dużo zapytań, czekam", int(ra) if ra.isdigit() else None
    if not r.ok:
        return None, f"Błąd serwera {r.status_code}", None
    try:
        data = r.json()
    except ValueError:
        return None, "Niepoprawna odpowiedź serwera", None
    return (data, None, None) if isinstance(data, dict) else (None, "Niepoprawna odpowiedź serwera", None)


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
        return "reset teraz"
    if secs < 86400:
        return f"reset za {secs // 3600}h {secs % 3600 // 60}m"
    lt = t.astimezone()
    return f"reset {DAYS[lt.weekday()]} {lt:%H:%M}"

# ---------- wyglad ----------

# Pikselowy ludek: szeroki, oczy-szczeliny, raczki, 4 nozki.
# 20x12 px - tyle co ikonka baterii na pasku (rysowane 1:1, bez skalowania).
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


def level_color(pct):
    if pct is None:
        return (140, 140, 140)
    if pct < 10:
        return (217, 69, 59)
    if pct < 30:
        return (232, 176, 74)
    return (217, 119, 87)  # pomaranczowy Claude


def taskbar_color(tray_left, top):
    """Prawdziwy kolor paska (jest przezroczysty, wiec zalezy od tapety) - probka z ekranu obok widgetu."""
    from PIL import ImageGrab
    try:
        strip = ImageGrab.grab(bbox=(tray_left - 460, top + 2, tray_left - 360, top + 4)).convert("RGB")
        px = sorted(strip.getdata(), key=sum)
        return px[len(px) // 2]
    except Exception:
        return (32, 32, 32)


def is_light(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b > 140


def font(size):
    """Segoe UI Variable - ta sama czcionka co procent baterii w Windows 11."""
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


def render(text, pct, height, bg):
    """Jak bateria: ikonka 20x12 rysowana 1:1, odstep 4 px, procent czcionka 12 px; wysrodkowane w pionie."""
    scale = max(1, round(height / 48))  # przy skali Windows 200% wszystko x2
    mw, mh = 20 * scale, 12 * scale
    f = font(12 * scale)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tl, _, tr, _ = probe.textbbox((0, 0), text, font=f, anchor="ls")
    tx = mw + 4 * scale
    img = Image.new("RGB", (tx + (tr - tl) + 1, height), bg)
    d = ImageDraw.Draw(img)
    oy = height // 2 - 6 * scale  # jak ikonka baterii: wiersze 17-28 przy pasku 48 px
    color = level_color(pct)
    for y, row in enumerate(MASCOT):
        for x, ch in enumerate(row):
            if ch == "#":
                d.rectangle([x * scale, oy + y * scale, (x + 1) * scale - 1, oy + (y + 1) * scale - 1], fill=color)
    d.text((tx - tl, height // 2 + 4 * scale), text, font=f, fill=(255, 255, 255), anchor="ls")
    return img

# ---------- ustawienia / autostart ----------

def load_settings():
    try:
        s = json.loads(SETTINGS.read_text(encoding="utf-8"))
        if s.get("limit") in LIMITS:
            return s
    except Exception:
        pass
    return {"limit": "five_hour"}


def save_settings(s):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s), encoding="utf-8")


def set_autostart(on):
    if not on:
        STARTUP_LNK.unlink(missing_ok=True)
        return
    pyw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve()
    # sciezki ida przez zmienne srodowiskowe, nie sa wklejane w tekst polecenia (brak wstrzykniecia)
    env = dict(os.environ, CLT_LNK=str(STARTUP_LNK), CLT_PYW=str(pyw),
               CLT_ARGS=f'"{script}"', CLT_DIR=str(script.parent))
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:CLT_LNK);"
          "$s.TargetPath=$env:CLT_PYW;$s.Arguments=$env:CLT_ARGS;"
          "$s.WorkingDirectory=$env:CLT_DIR;$s.Save()")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                   env=env, creationflags=NO_WINDOW)

# ---------- pasek zadan (Win32) ----------

user32 = ctypes.windll.user32


def win_rect(h):
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def tray_geometry():
    """(lewa krawedz zasobnika, gora paska, wysokosc paska) albo None."""
    tb = user32.FindWindowW("Shell_TrayWnd", None)
    if not tb:
        return None
    l, t, r, b = win_rect(tb)
    tn = user32.FindWindowExW(tb, None, "TrayNotifyWnd", None)
    left = win_rect(tn)[0] if tn else r - 300
    return left, t, b - t


def fullscreen_app_active():
    """Nie rysuj nad grami / filmami na pelnym ekranie."""
    h = user32.GetForegroundWindow()
    if not h:
        return False
    cls = ctypes.create_unicode_buffer(64)
    user32.GetClassNameW(h, cls, 64)
    if cls.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
        return False
    l, t, r, b = win_rect(h)
    return l <= 0 and t <= 0 and r >= user32.GetSystemMetrics(0) and b >= user32.GetSystemMetrics(1)

# ---------- aplikacja ----------

class App:
    def __init__(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        self.settings = load_settings()
        self.data, self.error = None, None
        self.wake = threading.Event()

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.bg = (32, 32, 32)  # aktualizowane probka z ekranu
        self.key = "#010203"  # kolor przezroczysty
        self.root.configure(bg=self.key)
        self.root.attributes("-transparentcolor", self.key)
        self.label = tk.Label(self.root, bg=self.key, bd=0)
        self.label.pack()
        self.photo = None

        self.limit_var = tk.StringVar(value=self.settings["limit"])
        self.auto_var = tk.BooleanVar(value=STARTUP_LNK.exists())
        self.menu = tk.Menu(self.root, tearoff=0)
        for k, name in LIMITS.items():
            self.menu.add_radiobutton(label=name, value=k, variable=self.limit_var, command=self.pick)
        self.menu.add_separator()
        self.menu.add_command(label="Odśwież teraz", command=self.wake.set)
        self.menu.add_checkbutton(label="Uruchamiaj z Windowsem", variable=self.auto_var,
                                  command=lambda: set_autostart(self.auto_var.get()))
        self.menu.add_command(label="Zamknij", command=self.root.destroy)

        self.tip = None
        self.label.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        self.label.bind("<Button-1>", lambda e: self.wake.set())
        self.label.bind("<Enter>", self.show_tip)
        self.label.bind("<Leave>", self.hide_tip)

    # --- UI ---
    def pick(self):
        self.settings["limit"] = self.limit_var.get()
        save_settings(self.settings)
        self.redraw()

    def tip_text(self):
        lines = []
        for k, name in LIMITS.items():
            r = remaining(self.data, k)
            if r is not None:
                lines.append(f"{name}: zostało {r}%  ·  {reset_text(self.data, k)}")
        if self.error:
            lines.append(self.error)
        return "Claude\n" + "\n".join(lines or ["Ładowanie…"])

    def show_tip(self, _e=None):
        self.hide_tip()
        self.tip = tk.Toplevel(self.root)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        tk.Label(self.tip, text=self.tip_text(), justify="left", bg="#2b2b2b", fg="white",
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
        geo = tray_geometry()
        left, top, height = geo if geo else (self.root.winfo_screenwidth() - 300,
                                             self.root.winfo_screenheight() - 48, 48)
        pct = remaining(self.data, self.settings["limit"])
        if self.data is None:
            text = "?" if self.error else "…"
        else:
            text = f"{pct}%" if pct is not None else "–"
        self.bg = taskbar_color(left, top)
        img = render(text, pct, height, self.bg)
        # tlo (kolor paska) -> przezroczyste; krawedzie tekstu zostaja wygladzone na kolor paska
        rgba = img.convert("RGBA")
        key_rgb = tuple(int(self.key[i:i + 2], 16) for i in (1, 3, 5))
        rgba.putdata([key_rgb + (255,) if p[:3] == self.bg else p for p in rgba.getdata()])
        self.photo = ImageTk.PhotoImage(rgba)
        self.label.configure(image=self.photo)
        self.root.geometry(f"{img.width}x{height}+{left - img.width - GAP}+{top}")

    def keep_on_taskbar(self):
        """Co sekunde: pozycja przy zasobniku, na wierzchu paska, schowany przy pelnym ekranie."""
        if fullscreen_app_active():
            self.root.withdraw()
        else:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.root.lift()
            geo = tray_geometry()
            self._ticks = getattr(self, "_ticks", 0) + 1
            moved = geo and geo != getattr(self, "_geo", None)
            if moved or (geo and self._ticks % 5 == 0 and
                         sum(abs(a - b) for a, b in zip(taskbar_color(geo[0], geo[1]), self.bg)) > 24):
                self._geo = geo
                self.redraw()  # przesuniety zasobnik albo zmieniona tapeta
        self.root.after(1000, self.keep_on_taskbar)

    # --- dane ---
    def poll_loop(self):
        backoff = POLL_ERR
        while True:
            data, err, retry = fetch_usage()
            if data is not None:
                self.data, self.error, backoff, wait = data, None, POLL_ERR, POLL_OK
            else:
                self.error = err
                wait = retry or backoff
                backoff = min(backoff * 2, MAX_BACKOFF)
            self.root.after(0, self.redraw)
            self.wake.wait(min(wait, MAX_BACKOFF))
            self.wake.clear()

    def run(self):
        self.redraw()
        threading.Thread(target=self.poll_loop, daemon=True).start()
        self.keep_on_taskbar()
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
