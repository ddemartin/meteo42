# ARPAV Meteo 42

Scraper e dashboard per i dati meteorologici della rete ARPAV (Agenzia Regionale per la Prevenzione e Protezione dell'Ambiente Veneto).


## Avvio

launchctl kickstart -k gui/$(id -u)/com.meteo42.dashboard

## Setup

```bash
# Richiede Python 3.10 o successivo. Sul Mac mini è installato Python 3.13
# tramite Homebrew; non usare il python3 Apple (3.9).
python3.13 -m venv .venv

# Attiva su macOS:
source .venv/bin/activate

# Installa dipendenze
python -m pip install -r requirements.txt
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
# --raw-directory raw            Directory per JSON grezzi (default)
# --request-delay 0.5            Delay tra richieste in secondi (default)
```

### 4. Avvia la dashboard

```bash
streamlit run dashboard.py
```

La dashboard sarà disponibile su `http://localhost:8501`

In produzione sul Mac mini non si lancia a mano: gira come servizio launchd e si
raggiunge da <https://meteo42.tail1a68b4.ts.net/> — dentro la tailnet, anche da
fuori casa, senza nulla esposto su Internet.

### 5. Rianalisi ERA5-Land (opzionale)

Storico orario dal 1950 — temperatura, dew point e precipitazione — per la
cella ERA5-Land più vicina a una stazione, in un database separato. Richiede un
account CDS configurato in `~/.cdsapirc` e l'accettazione della licenza del
dataset.

```bash
.venv/bin/python download_era5_land.py \
  --from 1950-01-01 --to 2026-07-31 \
  --lat 45.5807425 --lon 12.30779083 \
  --database era5_land.sqlite
```

Le coordinate vengono arrotondate alla griglia di 0,1°. Il comando divide il
periodo in blocchi di quattro mesi, verifica il numero di ore ricevute e salta
i file già scaricati e validi: è riprendibile, basta rilanciarlo. La taglia dei
blocchi non è arbitraria — il CDS rifiuta per costo una richiesta di sei mesi
su tre variabili, anche per una singola cella.

`--dry-run` mostra il piano senza interrogare il CDS, `--chunk-size month`
forza file mensili, `--overwrite` sostituisce i download esistenti.

Per validare e importare GRIB già scaricati, senza rete:

```bash
.venv/bin/python import_era5_land.py \
  raw/era5-land --database era5_land.sqlite
```

L'import è idempotente: ogni file è identificato da percorso e checksum
SHA-256, un file invariato viene saltato.

## Scheduling su macOS

Vedi [SCHEDULER_SETUP.md](SCHEDULER_SETUP.md) per installare i due servizi
`launchd` (scraper e dashboard), e [CLAUDE.md](CLAUDE.md) per l'accesso
Tailscale e la relativa diagnostica.

Il **perché** delle scelte — a partire da quella di girare in `launchd` e non in
Docker come gli altri progetti — sta in [MEMORANDUM.md](MEMORANDUM.md).

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

Chiave primaria `(station_id, observation_at, variable_type)`. Non si conserva
la risposta grezza dell'API: vedi [MEMORANDUM.md](MEMORANDUM.md) (2026-08-07).

Indici:
- `idx_observations_time`: su `observation_at`
- `idx_observations_variable_time`: su `(variable_type, observation_at)`

Un indice su `(station_id, observation_at)` **non va aggiunto**: è un prefisso
della chiave primaria, che serve già quegli accessi.

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

### `daily_weather_bulletins`
Bollettino narrativo quotidiano usato dal diario meteorologico:
- `weather_date`: giorno descritto
- `issued_at`: emissione in ora italiana
- `general_evolution`: evoluzione generale del bollettino Meteo Veneto
- `source_xml`: copia XML del bollettino originale

### `cloud_type_images`
Indice delle analisi orarie della tipologia delle nubi:
- `observed_at_utc`: timestamp originale UTC
- `source_id`: identificativo dell'asset sorgente
- `file_path`: immagine conservata in `cloud_type/`
- `mime_type`, `size_bytes`: formato e dimensione del file

### `era5_land.sqlite` — rianalisi, database separato

Perché sia un file a parte sta in [MEMORANDUM.md](MEMORANDUM.md) (2026-08-10).

- `grid_points`: una riga per coordinate di griglia
- `weather_hourly`: una riga per punto e ora — Unix time UTC, temperatura, dew
  point, umidità relativa derivata, accumulo grezzo di precipitazione e valore
  orario ricavato per differenza; chiave `(grid_point_id, valid_at_utc)`,
  tabella `WITHOUT ROWID`
- `imports`: percorso, checksum SHA-256, intervallo e conteggi di ogni GRIB

I timestamp sono in **UTC**, mentre le osservazioni ARPAV sono in ora solare
fissa `UTC+1`: per confrontarle il timestamp ERA5 va traslato di `+1 ora`.

## Dashboard

Nove tab, una per argomento, nell'ordine in cui si usano. Il *perché* di questa
divisione — e del fatto che il radar stia con le previsioni e non con le
osservazioni — sta in [MEMORANDUM.md](MEMORANDUM.md) (2026-08-07).

**📍 Adesso**
- Condizioni correnti della stazione di casa: temperatura, percepito, umidità,
  vento, pioggia del giorno
- Report testuale della settimana, con riassunto AI opzionale (Ollama locale)
- Grafici delle ultime 72 ore: temperatura, umidità, bulbo umido, indice di calore
- Temperature dei sette capoluoghi veneti

**🔭 Previsioni**
- Mosaico radar ARPAV del Nord-Est, aggiornato ogni 5 minuti
- Bollettino Meteo Veneto giorno per giorno, con le mappe ufficiali

**🌌 Cielo**
- Sole: alba, culmine con altezza massima, tramonto, ore di luce e differenza
  rispetto a ieri
- Luna: fase, illuminazione, sorgere e tramontare
- Percorsi di Sole, Luna e pianeti sull'orizzonte nell'arco della giornata
- Pianeti visibili a occhio nudo nella notte corrente
- Il giorno è scegliibile: le effemeridi si calcolano per qualsiasi data

**🕰️ Che tempo fece**
- Diario giornaliero: bollettino archiviato, osservazioni di Mogliano,
  animazione oraria della tipologia delle nubi
- Il giorno si sceglie da calendario, limitato agli estremi realmente in
  archivio; sui giorni vuoti dentro l'intervallo lo dice

**📊 Dati**
- Visualizza osservazioni con filtri per stazione, variabile e periodo
- Scarica in CSV **la selezione filtrata** (`;` e BOM, per Excel italiano).
  Non esiste più un export automatico dell'intero database: per quello si
  copia `arpav_meteo.sqlite`, che è già un file solo. Vedi
  [MEMORANDUM.md](MEMORANDUM.md) (2026-08-07)

**📈 Grafici**
- Trend temporali per variabile
- Confronta più stazioni
- Grafici giornalieri e mensili con minimo, media e massimo
- Visualizzazione interattiva con Plotly

**📅 Storico Annuale**
- Confronto pluriennale, precipitazioni cumulate per anno

**🌡️ Clima**
- Rianalisi ERA5-Land dal 1950 (`era5_land.sqlite`, database separato): il
  fondale climatico lungo sotto una serie osservata corta
- Temperatura media e precipitazione annua, ciclo annuale con la banda tra
  l'anno più freddo e il più caldo, ciclo annuale per decennio (dal blu del
  decennio più vecchio al rosso del più recente)
- Sull'andamento annuale due strati si accendono con una casella, spenti di
  default: le **medie per decennio**, disegnate a scalini perché dentro il
  decennio c'è un numero solo e non un andamento, e la **media degli ultimi
  365 giorni** come linea di riferimento accanto a quella del periodo. La
  finestra dei 365 giorni è lunga un anno per costruzione, quindi si confronta
  con le medie annue anche quando non coincide con un anno solare
- I grafici della scheda hanno uno stile comune: linee senza marcatori, tacche
  dell'asse Y su un passo tondo scelto sull'intervallo dei dati invece che
  lasciato all'automatismo, asse X che parte dal primo valore e mesi scritti
  per nome, unità di misura nel titolo e legenda sotto al riquadro
- Solo gli anni con dodici mesi completi entrano in medie e confronti: durante
  lo scaricamento — che dura giorni — l'ultimo anno è tronco, e una media
  calcolata su mezzo anno sarebbe falsa senza sembrarlo. I mesi ancora
  incompleti sono elencati sotto le tessere
- Nella libreria ci sono anche i **giorni oltre una soglia contati anno per
  anno** — massima, minima o media giornaliera, sopra o sotto la soglia: sei
  ricette che mostrano come si sposta il clima invece di fotografare un anno
  solo. Contano solo gli anni completi, e un anno senza nemmeno un giorno oltre
  soglia vale zero invece di sparire dalla serie
- **Interroga i dati**, in tre modi:
  - *Chiedi in italiano* — il modello Ollama locale **sceglie** una delle
    ricette pronte di `era5_queries.py` e ne riempie i parametri, che restano
    correggibili prima di eseguire. Non scrive SQL: sceglie e compila
  - *Scegli dalla libreria* — la stessa cosa senza modello, dal menù
  - *SQL libero* — il modello propone una query nuova, oppure la si scrive a
    mano. Serve per le domande che la libreria non copre. Se l'SQL contiene
    parametri `:anno`, `:mese`, `:soglia`… compaiono i campi per riempirli, e
    una query che funziona si **salva nel ricettario** con un titolo e una
    domanda d'esempio: da lì in poi è nella libreria come le altre, e il
    modello può sceglierla da sé. Le ricette salvate stanno in
    `era5_ricette.json`, fuori dal versionamento, e si eliminano dal menù

  In ogni caso la query è visibile prima di partire e si esegue solo su
  conferma. Il risultato si guarda come **tabella o come grafico**: si
  scelgono asse orizzontale e colonne, la pioggia va a barre sull'asse destro
  in millimetri e le temperature a linee su quello sinistro, perché unità
  diverse non stanno sulla stessa scala. Se le righe non procedono lungo
  l'asse orizzontale — una classifica come «i quindici luglio più caldi», che
  esce in ordine di temperatura — il grafico lo riconosce e non le unisce con
  una linea: valori a punti nell'ordine del risultato, su un asse di
  categorie. Vale per qualsiasi risultato, anche di una query scritta a mano Se sono configurate `LLM_EXTERNAL_BASE_URL` /
  `LLM_EXTERNAL_MODEL` / `LLM_EXTERNAL_API_KEY`, nella sola modalità *SQL
  libero* compare un selettore per usare `gpt-5.6-luna` al posto del modello
  locale — scelta manuale, mai automatica (vedi [CLAUDE.md](CLAUDE.md)) La connessione è in
  sola lettura (`mode=ro` + `PRAGMA query_only`), le query non-SELECT sono
  rifiutate prima di partire e quelle troppo lunghe interrotte dopo 15
  secondi. Il database delle osservazioni è allegato in sola lettura come
  `arpav.`, quindi si possono incrociare le due sorgenti. Senza Ollama restano
  la libreria e la casella SQL. Il perché di questa forma invece del
  text-to-SQL diretto è in [MEMORANDUM.md](MEMORANDUM.md) (2026-08-11)
- ⚠️ ERA5 è la media di una cella di ~11 × 8 km campionata ogni ora: gli
  estremi sono più smorzati di quelli di un termometro, e i conteggi di giorni
  oltre soglia non sono confrontabili con quelli di una stazione

**⚙️ Stazioni**
- Gestisci `stations.json`
- Aggiungi/modifica/elimina stazioni
- Abilita/disabilita download

### Aspetto

Le schede disegnate a mano condividono un foglio di stile unico
(`M42_STYLESHEET` in `dashboard.py`). I colori **non** usano le variabili di
tema di Streamlit, che dalla 1.60 non esistono più: grigio neutro a bassa
opacità e `currentColor`, che rendono uguale su tema chiaro e scuro. Le griglie
sono CSS `auto-fit` e non `st.columns`, che a 390 px non manda a capo. Il
motivo esteso è in [MEMORANDUM.md](MEMORANDUM.md) (2026-08-07).

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
