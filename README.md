# Claude Limit Tray

Pokazuje na pasku zadań Windows, obok zasobnika, **ile zostało limitu Claude'a**: tak jak procent baterii. Mały pikselowy ludek i obok procent.

![Claude Limit Tray na pasku zadań](preview.png)

- Do wyboru limit **5-godzinny** albo **tygodniowy** (prawy przycisk → menu)
- Najechanie myszką: oba limity i czas do resetu
- Kolor ludka: pomarańczowy → żółty (< 30%) → czerwony (< 10%)
- Chowa się, gdy gra albo film jest na pełnym ekranie, gdy automatycznie ukrywany pasek jest schowany oraz gdy pasek jest z boku lub u góry ekranu (obsługiwany jest tylko pasek na dole głównego monitora)
- Opcja „Uruchamiaj z Windowsem”

## Wymagania

- Windows 10/11
- Python 3.10+
- Zainstalowany i zalogowany [Claude Code](https://claude.com/claude-code) (plan Pro/Max), bo aplikacja korzysta z jego logowania

## Instalacja

```powershell
git clone https://github.com/jakmot12/claude-limit-tray.git
cd claude-limit-tray
python -m pip install -r requirements.txt
pythonw claude_limit_tray.py
```

## Bezpieczeństwo i prywatność

- Aplikacja **tylko odczytuje** token z `%USERPROFILE%\.claude\.credentials.json` (plik Claude Code). Nie zapisuje go, nie loguje i nie odświeża.
- Aplikacja przedstawia się serwerowi własną nazwą (`claude-limit-tray`), nie podszywa się pod Claude Code, i nie uruchamia żadnych zewnętrznych programów (poza PowerShellem przy włączaniu autostartu).
- Sprawdzanie limitu **nie zużywa** Twojego limitu Claude'a. To tylko odczyt licznika, a nie rozmowa z modelem.
- Token jest wysyłany **wyłącznie** do `https://api.anthropic.com/api/oauth/usage` (HTTPS z weryfikacją certyfikatu). Żadnych innych serwerów, żadnej telemetrii.
- Żeby dobrać kolor do paska zadań, aplikacja co kilka sekund odczytuje kolor paska kilku pikseli tuż obok siebie. Ten fragment ekranu nie jest nigdzie zapisywany ani wysyłany.
- Lokalnie zapisuje tylko `%APPDATA%\ClaudeLimitTray\settings.json` (wybrany limit) i, jeśli włączysz autostart, skrót w folderze Autostart.
- Cały kod to jeden plik: `claude_limit_tray.py`. Przeczytaj go przed uruchomieniem.

**Nigdy nikomu nie wysyłaj swojego pliku `.credentials.json`**: daje pełny dostęp do Twojego konta Claude.

## Uwaga

To nieoficjalne narzędzie, niezwiązane z Anthropic. Korzysta z nieudokumentowanego endpointu, tego samego co komenda `/usage` w Claude Code, więc może przestać działać, gdy Anthropic go zmieni.

## Licencja

MIT
