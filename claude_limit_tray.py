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

# Uczciwie przedstawiamy sie wlasna nazwa (nie podszywamy sie pod Claude Code).
UA = "claude-limit-tray/1.1 (+https://github.com/jakmot12/claude-limit-tray)"


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
    if secs < 60:
        return "reset za <1m"
    if secs < 3600:
        return f"reset za {secs // 60}m"
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
    """Prawdziwy kolor paska (jest przezroczysty, wiec zalezy od tapety) - probka z gornej krawedzi paska nad widgetem."""
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
    """Jak bateria: ikonka 20x12 skalowana do DPI, odstep 4 px, procent czcionka 12 px; wysrodkowane w pionie."""
    dpi = max(1.0, height / 48)  # plynne skalowanie (takze dla 125% i 150% DPI)
    mw, mh = round(20 * dpi), round(12 * dpi)
    f = font(max(10, round(12 * dpi)))
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    tl, _, tr, _ = probe.textbbox((0, 0), text, font=f, anchor="ls")
    tx = mw + round(4 * dpi)
    img = Image.new("RGB", (tx + (tr - tl) + 1, height), bg)
    d = ImageDraw.Draw(img)
    oy = (height - mh) // 2  # jak ikonka baterii: wiersze 18-29 przy pasku 48 px
    color = level_color(pct)
    mascot = Image.new("RGBA", (20, 12), (0, 0, 0, 0))
    md = ImageDraw.Draw(mascot)
    for y, row in enumerate(MASCOT):
        for x, ch in enumerate(row):
            if ch == "#":
                md.point((x, y), fill=color + (255,))
    if (mw, mh) != (20, 12):
        mascot = mascot.resize((mw, mh), Image.Resampling.NEAREST)
    img.paste(mascot, (0, oy), mascot)
    # zawsze bialy - tak jak procent baterii na pasku (swiadomy wybor autora, nie zalezy od jasnosci paska)
    d.text((tx - tl, height // 2 + round(4 * dpi)), text, font=f, fill=(255, 255, 255), anchor="ls")
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
    if not pyw.exists():
        pyw = Path(sys.executable)
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
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
ERROR_ALREADY_EXISTS = 183


def acquire_single_instance():
    """Zwraca uchwyt muteksu albo None, jesli druga kopia aplikacji juz dziala."""
    h = kernel32.CreateMutexW(None, False, f"Local\\{APP}_SingleInstance")
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


def tray_geometry():
    """(lewa krawedz zasobnika, gora paska, wysokosc paska) albo None, gdy widget ma byc schowany:
    pasek nie na dole ekranu (bok/gora) albo automatycznie ukryty pasek jest akurat schowany."""
    tb = user32.FindWindowW("Shell_TrayWnd", None)
    if not tb:
        return None
    abd = APPBARDATA(cbSize=ctypes.sizeof(APPBARDATA))
    if ctypes.windll.shell32.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(abd)) and abd.uEdge != ABE_BOTTOM:
        return None
    l, t, r, b = win_rect(tb)
    if b - t <= 0 or t > user32.GetSystemMetrics(1) - (b - t) // 2:
        return None  # auto-ukrywanie: pasek zjechal w dol poza ekran
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
        self.closing = False
        self._visible = True

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
        self.menu.add_command(label="Zamknij", command=self.close)

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
        geo = tray_geometry()
        if not geo:
            return  # pasek schowany / nie na dole - keep_on_taskbar ukrywa widget
        left, top, height = geo
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
        """Co sekunde: pozycja przy zasobniku, na wierzchu paska; schowany przy pelnym ekranie,
        schowanym (auto-ukrywanym) pasku albo pasku z boku / u gory - nigdy nie wisi nad ekranem."""
        if self.closing:
            return
        geo = tray_geometry()
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
                self.redraw()  # przesuniety zasobnik albo zmieniona tapeta
        self.root.after(1000, self.keep_on_taskbar)

    # --- dane ---
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
            data, err, retry = fetch_usage()
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
