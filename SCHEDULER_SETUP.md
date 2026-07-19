# Setup Scheduler su Mac Mini

## Passo 1: Configurare il file plist

Modifica `com.meteo42.scraper.plist` e sostituisci `/path/to/project` con il percorso effettivo del progetto.

Ad esempio, se il progetto è in `/Users/davide/Projects/meteo42`:

```bash
sed -i '' 's|/path/to/project|/Users/davide/Projects/meteo42|g' com.meteo42.scraper.plist
```

## Passo 2: Creare cartella log

```bash
mkdir -p ~/Projects/meteo42/logs
```

## Passo 3: Installare il launchd agent

```bash
cp com.meteo42.scraper.plist ~/Library/LaunchAgents/
```

## Passo 4: Carica il servizio

```bash
launchctl load ~/Library/LaunchAgents/com.meteo42.scraper.plist
```

## Comandi utili

**Verificare se è caricato:**
```bash
launchctl list | grep meteo42
```

**Visualizzare i log:**
```bash
tail -f ~/Projects/meteo42/logs/scraper.log
tail -f ~/Projects/meteo42/logs/scraper_error.log
```

**Fermare il servizio:**
```bash
launchctl unload ~/Library/LaunchAgents/com.meteo42.scraper.plist
```

**Riavviare il servizio:**
```bash
launchctl unload ~/Library/LaunchAgents/com.meteo42.scraper.plist
launchctl load ~/Library/LaunchAgents/com.meteo42.scraper.plist
```

## Configurare l'intervallo di esecuzione

Nel file `com.meteo42.scraper.plist`, modifica la sezione:

```xml
<key>StartInterval</key>
<integer>300</integer>  <!-- 300 secondi = 5 minuti -->
```

Opzioni comuni:
- `60` = 1 minuto
- `300` = 5 minuti
- `600` = 10 minuti
- `1800` = 30 minuti
- `3600` = 1 ora

## Eseguire lo scraper con l'ambiente virtuale

Se usi il venv, modifica le `ProgramArguments` nel plist:

```xml
<key>ProgramArguments</key>
<array>
    <string>/Users/davide/Projects/meteo42/.venv/bin/python</string>
    <string>/Users/davide/Projects/meteo42/scrape.py</string>
</array>
```

## Eseguire la dashboard Streamlit in background

Crea un altro file `com.meteo42.dashboard.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.meteo42.dashboard</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/davide/Projects/meteo42/.venv/bin/streamlit</string>
        <string>run</string>
        <string>/Users/davide/Projects/meteo42/dashboard.py</string>
        <string>--server.port=8501</string>
        <string>--server.address=0.0.0.0</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/davide/Projects/meteo42</string>

    <key>StandardOutPath</key>
    <string>/Users/davide/Projects/meteo42/logs/dashboard.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/davide/Projects/meteo42/logs/dashboard_error.log</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Installa con:
```bash
cp com.meteo42.dashboard.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.meteo42.dashboard.plist
```

Accedi dalla rete a `http://[IP_MAC]:8501`
