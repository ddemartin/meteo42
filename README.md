# ARPAV Meteo 42

Scraper e dashboard per i dati meteorologici della rete ARPAV (Agenzia Regionale per la Prevenzione e Protezione dell'Ambiente Veneto).


## Avvio

launchctl kickstart -k gui/$(id -u)/com.meteo42.dashboard

## Setup

```bash
# Crea ambiente virtuale
python -m venv .venv

# Attiva
# su macOS/Linux:
source .venv/bin/activate
# su Windows:
.venv\Scripts\activate

# Installa dipendenze
pip install -r requirements.txt
```

## Uso

### 1. Scarica i metadata delle stazioni

Esegui una volta per popolare il database con i nomi e le informazioni delle stazioni:

```bash
python update_stations_metadata.py
```

### 2. Configura le stazioni

Modifica `stations.json` oppure crea uno script di fetch automatico dalle stazioni disponibili.

### 3. Esegui lo scraper

```bash
python scrape.py

# Opzioni:
# --config stations.json          File di configurazione (default)
# --database arpav_meteo.sqlite  Database SQLite (default)
# --csv arpav_meteo.csv          Export CSV (default)
# --raw-directory raw            Directory per JSON grezzi (default)
# --request-delay 0.5            Delay tra richieste in secondi (default)
```

### 4. Avvia la dashboard

```bash
streamlit run dashboard.py
```

La dashboard sarà disponibile su `http://localhost:8501`

## Scheduling su macOS

Vedi [SCHEDULER_SETUP.md](SCHEDULER_SETUP.md) per configurare l'esecuzione automatica dello scraper con `launchd`.

## Database Schema

### `stations`
Metadati delle stazioni scaricate:
- `station_id`: ID della stazione (PRIMARY KEY)
- `configured_name`: Nome configurato
- `api_name`: Nome dall'API
- `first_seen_at`: Data primo download
- `last_seen_at`: Data ultimo accesso
- `last_download_at`: Data ultimo download
- `last_record_at`: Data ultimo record osservato
- `enabled`: Stazione abilitata (1/0)

### `station_metadata`
Informazioni dettagliate delle stazioni dalla MGRAMMI API:
- `station_id`: ID della stazione (PRIMARY KEY)
- `codice_stazione`: Codice numerico
- `nome_stazione`: Nome completo
- `latitudine`: Coordinate
- `longitudine`: Coordinate
- `quota`: Altitudine in metri
- `provincia`: Provincia Veneto
- `gestore`: Ente gestore (es. ARPAV)
- `updated_at`: Ultimo aggiornamento

### `observations`
Osservazioni meteorologiche:
- `station_id`: ID stazione (FOREIGN KEY)
- `observation_at`: Data/ora osservazione
- `variable_type`: Tipo variabile (es. TARIA2M)
- `station_name`: Nome stazione
- `value_text`: Valore testuale
- `value_numeric`: Valore numerico
- `unit`: Unità di misura
- `downloaded_at`: Data download
- `raw_json`: Dati JSON grezzi

Indici:
- `idx_observations_time`: su `observation_at`
- `idx_observations_station_time`: su `(station_id, observation_at)`
- `idx_observations_variable_time`: su `(variable_type, observation_at)`

### `downloads`
Log dei download:
- `download_id`: ID (PRIMARY KEY AUTOINCREMENT)
- `station_id`: ID stazione
- `requested_at`: Inizio download
- `completed_at`: Fine download
- `success`: Esito (1/0)
- `records_received`: Record ricevuti
- `records_inserted`: Record inseriti
- `error_message`: Messaggio errore (se fallito)

## Dashboard

La dashboard Streamlit offre 3 tab:

**📊 Dati**
- Visualizza osservazioni con filtri per stazione, variabile e periodo
- Esporta risultati

**⚙️ Stazioni**
- Gestisci `stations.json`
- Aggiungi/modifica/elimina stazioni
- Abilita/disabilita download

**📈 Grafici**
- Trend temporali per variabile
- Confronta più stazioni
- Grafici giornalieri e mensili con minimo, media e massimo
- Visualizzazione interattiva con Plotly

## API Endpoints

### MGRAMMI (Stazioni e metadata)
```
GET https://api.arpa.veneto.it/REST/v1/meteo_meteogrammi
?rete=MGRAMMI&coordcd=18&orario=0
```

Ritorna: Lista stazioni con nome, coordinate, provincia, dati recenti

### Osservazioni (Scraper)
```
GET https://api.arpa.veneto.it/REST/v1/meteo_meteogrammi_tabella
?codseqst=300000154
```

Ritorna: Storico osservazioni per stazione specifica

## Troubleshooting

**Errore FOREIGN KEY constraint failed**
- Esegui `update_stations_metadata.py` prima di fare lo scrape

**SQLite thread error in Streamlit**
- Risolto in versione recente (usa `check_same_thread=False`)

**La dashboard non carica dati**
- Verifica che il database esista: `arpav_meteo.sqlite`
- Verifica che i metadata siano stati scaricati

## Sviluppo

Dipendenze:
- `requests`: HTTP client
- `urllib3`: Retry logic
- `streamlit`: Dashboard web
- `pandas`: Data analysis
- `plotly`: Visualizzazione

## License

MIT
