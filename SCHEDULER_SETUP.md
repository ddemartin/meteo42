# Setup dei servizi launchd su Mac mini

Due servizi, due file: `com.meteo42.scraper.plist` scarica i dati,
`com.meteo42.dashboard.plist` tiene su la dashboard. Entrambi contengono il
segnaposto `/path/to/project`, da sostituire al momento dell'installazione.

## Passo 1: Sostituire i percorsi

```bash
sed -i '' "s|/path/to/project|$PWD|g" com.meteo42.scraper.plist com.meteo42.dashboard.plist
```

I plist puntano a `.venv/bin/python` e `.venv/bin/streamlit`, non al Python di
sistema: le dipendenze di `requirements.txt` stanno nel venv.

## Passo 2: Creare la cartella dei log

```bash
mkdir -p logs
```

## Passo 3: Installare e caricare

```bash
cp com.meteo42.scraper.plist com.meteo42.dashboard.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.meteo42.scraper.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.meteo42.dashboard.plist
```

## Comandi utili

**Verificare se sono caricati:**
```bash
launchctl list | grep meteo42
```

**Visualizzare i log:**
```bash
tail -f logs/scraper.log logs/scraper_error.log
tail -f logs/dashboard.log logs/dashboard_error.log
```

**Riavviare dopo una modifica al codice:**
```bash
launchctl kickstart -k gui/$(id -u)/com.meteo42.dashboard
```

**Riavviare dopo una modifica al plist** — qui `kickstart` non basta, rilegge la
copia che launchd tiene in cache:
```bash
launchctl bootout    gui/$(id -u)/com.meteo42.dashboard
launchctl bootstrap  gui/$(id -u) ~/Library/LaunchAgents/com.meteo42.dashboard.plist
```

**Fermare un servizio:**
```bash
launchctl bootout gui/$(id -u)/com.meteo42.scraper
```

## Cadenza dello scraper

Lo scraper gira **una volta all'ora**, al minuto zero:

```xml
<key>StartCalendarInterval</key>
<dict>
	<key>Minute</key>
	<integer>0</integer>
</dict>
```

È la cadenza con cui ARPAV pubblica le misure: interrogarla più spesso
scaricherebbe le stesse righe. Per un intervallo fisso invece che un orario si
usa `StartInterval` con i secondi (`<integer>300</integer>` per cinque minuti),
ma le due chiavi non vanno messe insieme.

`KeepAlive` è `false` perché è un lavoro periodico che finisce, non un server —
al contrario della dashboard, che ha `true` e viene rilanciata se muore.

## Accesso alla dashboard

La dashboard ascolta su `127.0.0.1:8501` e **non è raggiungibile dalla rete
locale in chiaro**: si arriva da <https://meteo42.tail1a68b4.ts.net/>, che è un
servizio Tailscale. Configurazione, diagnostica e comandi stanno in
[CLAUDE.md](CLAUDE.md).

Per riaprirla sulla rete di casa, `--server.address=0.0.0.0` nel plist, seguito
dal ciclo `bootout` + `bootstrap` qui sopra.
