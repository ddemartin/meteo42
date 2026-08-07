# Memorandum meteo42 — il "perché" delle decisioni

README dice **cosa** c'è, CLAUDE.md dice **come** si lavora e come si rimette in
piedi la produzione. Qui sta il **perché**: ogni scelta con la sua data, il
criterio che l'ha decisa e l'alternativa scartata.

Una decisione senza il suo motivo, dopo tre mesi, è indistinguibile da un
capriccio: si rifà il giro, si cambia, e si riscopre il problema che l'aveva
motivata. L'alternativa scartata si annota perché è quella che tornerà a
sembrare buona.

Questo documento è nato il **2026-08-07**, a progetto avviato. Le voci fino a
quella data sono ricostruite dai commit e dal codice: dove il commit non
portava già il suo motivo, la voce lo dice.

---

## 2026-08-07 — launchd + venv, non Docker (⚠️ ricostruita a posteriori)

**Voce ricostruita**, non registrata al momento della scelta: nasce dalla
domanda «perché meteo42 non è in Docker come stock42 e brain42?». Se il motivo
vero fosse un altro — per esempio che il progetto è semplicemente nato prima e
non ci si è più tornati — va corretta qui.

Il dato di meteo42 vive **sull'host**: `arpav_meteo.sqlite` è oltre 1 GB, il
CSV ~200 MB, più `raw/` e `cloud_type/`. Su quel file SQLite scrivono lo scraper
e legge la dashboard, due processi launchd distinti. È esattamente il punto su
cui stock42 ha sbattuto (`stock42/CLAUDE.md`): su macOS i bind mount passano da
virtiofs e il file locking di SQLite lì non è affidabile. La soluzione adottata
là — il DB in **volume nominato** — costa la visibilità del file nel Finder, e
infatti stock42 ha dovuto aggiungere una cartella `export/` per rivederlo. Qui
quel prezzo non ha contropartita: il DB deve restare dov'è, ispezionabile con
`sqlite3` e copiabile a mano.

E non c'è nulla da orchestrare. stock42 mette in piedi IB Gateway (immagine di
terzi, IBC, login e riavvio giornaliero) *accanto* all'app: due container,
healthcheck, `depends_on` — lì Docker risolve un problema che esiste. meteo42 è
un processo `streamlit` più uno scraper periodico, che launchd copre nativamente
e senza il vincolo che Docker Desktop su macOS si porta dietro (sessione utente
aperta, accesso automatico, `pmset`; vedi la testa di `stock42/docker-compose.yml`).

**Alternativa scartata:** containerizzare per uniformità con gli altri due
progetti. Avrebbe aggiunto il problema del locking senza togliere nulla.

## 2026-07-19 — Streamlit, non un frontend proprio

brain42 e stock42 hanno una UI scritta a mano (`web/`, `gui/`) servita da un
loro server. Qui la dashboard è **esplorazione di dati** su pandas e Plotly:
filtri, tab, tabelle. Streamlit dà tutto questo senza scrivere un'app web, e il
costo — un solo processo, niente API, niente stato client — è accettabile
finché il consumo resta la lettura di serie storiche.

Il limite si vede quando serve interattività fine: vedi la voce del 2026-08-02
sui grafici touch, dove l'unica leva è la configurazione di Plotly.

## 2026-07-19 → fine luglio — da tutte le 223 stazioni a 15

Si è partiti abilitandole tutte: `generate_stations_config.py` scopre l'elenco
dall'API invece di curarlo a mano, e il criterio era che i dati non raccolti non
si recuperano mentre una richiesta per stazione ogni ora non costa nulla.

**Dopo alcuni giorni di raccolta su tutte e 223 si è scelto di ridurre a 15**, e
i dati delle abbandonate sono stati rimossi: al 2026-08-07 `observations`,
`stations`, `station_metadata` e `downloads` conoscono gli stessi 15
`station_id`, senza traccia degli altri.

Il criterio implicito è che il valore non sta nella copertura della rete ARPAV —
che ARPAV pubblica già — ma nella **profondità storica di poche stazioni
interessanti**. Il che è coerente con la voce qui sotto: si stanno importando le
storie orarie delle 15, non si sta allargando l'elenco.

**Se un giorno si volesse tornare indietro**, il costo non è la banda ma lo
spazio: vedi la proiezione nelle domande aperte. Sul seguito di questa scelta —
la profondità storica al posto della copertura — vedi la voce del 2026-08-07.

## 2026-07-30 — dati e `stations.json` fuori dal versionamento

Il DB, il CSV e i JSON grezzi erano esclusi da `.gitignore` ma **ancora
tracciati** da prima che la regola esistesse, così ogni giro di scraping
produceva un diff enorme. Rimossi dall'indice, tenuti su disco.

Con loro è uscito anche `stations.json`: non è configurazione statica ma
**stato di runtime**, modificato dal tab "Gestione Stazioni" della dashboard.
Versionarlo significava trattare come sorgente una cosa che l'applicazione
riscrive da sola.

## 2026-07-30 — medie pesate sulla durata, mai la media aritmetica dei campioni

Le serie hanno campionamento disomogeneo: il live ARPAV è a 10 minuti, lo
storico importato è orario. Una media aritmetica dei valori grezzi darebbe alle
giornate campionate fitto un peso sei volte maggiore, e il confronto
storico/attuale — che è il punto del tab "Storico Annuale" — sarebbe falsato.
Tutte le aggregazioni (giornaliera, settimanale, mensile) pesano per la durata
dell'intervallo.

Vale anche per la media giornaliera della temperatura, che **non** è
`(max+min)/2`: quella è una convenzione climatologica comoda, non la media
della giornata.

## 2026-07-30 — Scattermap/MapLibre al posto di Scattermapbox

La mappa panoramica non si caricava su alcune connessioni mobili: Scattermapbox
è deprecato e tira giù Mapbox GL JS da un **CDN esterno**. Scattermap usa
MapLibre, che è dentro plotly.js. Nessuna dipendenza di rete a runtime oltre ai
dati.

Stessa occasione, stesso movente — la lettura da telefono: le legende sono
passate da colonna fissa a destra a riga orizzontale sotto il grafico, che su
schermo stretto non comprime più l'area utile.

## 2026-07-31 — l'umidità storica si deriva, non si lascia vuota

Il bollettino storico di Mogliano Veneto ha solo `UMID_MIN` e `UMID_MAX` orari,
nessuna media. `UMID2M` viene calcolata come punto medio dei due, così
l'umidità storica entra negli stessi grafici e nelle stesse sovrapposizioni
(indice di calore) delle letture live.

**È un'approssimazione dichiarata**, e la si accetta perché l'alternativa —
lasciare il buco — rendeva inutilizzabile l'indice di calore su tutto il periodo
2010-2024, cioè su quasi tutta la storia disponibile.

## 2026-07-31 — bande di range, non la linea min/max

I grafici annuali mostravano una singola linea di minimo e una di massimo per
periodo: **un solo giorno anomalo appiattiva l'intero periodo** e la forma
stagionale spariva. Ora si mostra il range dei massimi giornalieri e il range
dei minimi giornalieri, che è robusto all'outlier singolo.

Nel confronto delle precipitazioni, ogni anno ha un **colore fisso e distinto**
invece di un ciclo di tratteggi: i tratteggi si ripetevano e su dodici e più
anni di storia diventavano indistinguibili.

## 2026-07-31 — il riassunto AI gira in locale e non deve poter inventare

Il "Riassunto AI" riscrive il report templatizzato in linguaggio naturale con
un modello Ollama locale. Tre vincoli, tutti nati da difetti osservati:

- **Think mode disattivato e temperatura bassa.** Con il ragionamento acceso la
  latenza superava i 180 secondi contro i ~10 attuali, e il modello aggiungeva
  contesto non presente nei dati di partenza.
- **Un "record" solo se il precedente simile dista almeno 3 anni.** Senza la
  soglia, ogni settimana d'estate risultava eccezionale — un superlativo che si
  ripete ogni volta non informa più.
- **Fallback al testo templatizzato** se Ollama non risponde o va in timeout. La
  narrazione è un ornamento: non può portarsi via il report.

## 2026-08-02 — i timestamp ARPAV sono in ora solare, tutto l'anno

`utc_series_to_local()` interpretava i timestamp del DB come UTC. ARPAV li marca
invece in **ora solare (UTC+1) anche d'estate**: in luglio la dashboard mostrava
ogni osservazione un'ora avanti. Ora c'è `DB_TIMEZONE = UTC+1` esplicito, e le
query che confrontano con `now` (che è UTC) portano il `+1 hour` con il commento
che spiega perché.

È il tipo di errore che non si nota — un'ora di sfasamento su una temperatura
resta plausibile — e per questo va scritto.

## 2026-08-02 — la dashboard è un servizio Tailscale, e ascolta solo su 127.0.0.1

L'indirizzo `https://meteo42.tail1a68b4.ts.net/` è quello di un **servizio**,
non di una macchina: se il dashboard traslocasse su un altro host, l'indirizzo
non cambierebbe. Streamlit ascolta solo su loopback, quindi dalla LAN in chiaro
non si raggiunge più: si passa dal nome, dentro la tailnet, senza niente esposto
su Internet.

Il grosso del tempo di configurazione è costato la confusione tra due permessi
distinti della ACL: il **grant** decide chi può *raggiungere* il servizio, gli
**autoApprovers** chi può *ospitarlo*. Senza i secondi l'host resta in attesa di
un'approvazione manuale che la console non offre in modo evidente, e il nome non
risolve pur essendo tutto configurato. La procedura completa, i sintomi e le
diagnosi che *non* sono probanti stanno in [CLAUDE.md](CLAUDE.md) — lì servono
sotto mano quando qualcosa non va.

## 2026-08-02 — i grafici sono in sola lettura

Su schermo touch lo scroll della pagina finiva dentro il grafico: si tentava di
scorrere e si otteneva uno zoom o un pan, con il grafico che restava in uno
stato da cui non si tornava indietro senza saperlo. Ora `dragmode=False`,
`scrollZoom`, `doubleClick` e la modebar disattivati: il grafico si guarda, e la
pagina scorre.

**Alternativa scartata:** interattività condizionata al dispositivo. Streamlit
non sa se il client è touch senza un giro di JavaScript, e un grafico che si
comporta in due modi diversi è peggio di uno che si comporta sempre allo stesso.

## 2026-08-05 — pianeti a occhio nudo sul grafico dell'altezza solare

Sul grafico del Sole ci sono anche Luna, Mercurio, Venere, Marte, Giove e
Saturno, con `ephem`. Due dettagli non ovvi:

- `observer.pressure = 0`: si vuole l'altezza **geometrica**, confrontabile tra
  tutti i corpi. Con la rifrazione attiva ogni corpo riceverebbe una correzione
  diversa vicino all'orizzonte, cioè proprio dove il grafico si legge.
- La scala verticale la fissa **l'arco notturno del Sole**, non il minimo di
  tutti i corpi. Un pianeta può avvicinarsi al nadir mentre è comunque
  inosservabile: includerlo comprimerebbe la parte visibile di ogni traiettoria
  per mostrare una porzione che non interessa a nessuno.

## 2026-08-05 — il diario meteorologico

Al numero si affianca il racconto: il bollettino narrativo Meteo Veneto
(`daily_weather_bulletins`) e le analisi orarie della tipologia delle nubi
(`cloud_type_images`), archiviate su disco in `cloud_type/`.

Le immagini si conservano perché la fonte non le tiene: senza copia locale il
diario funzionerebbe solo per il presente, che è il momento in cui serve meno.

## 2026-08-07 — la profondità storica si costruisce una stazione alla volta

Delle 15 stazioni, **solo Mogliano Veneto (`300000150`) ha dati anteriori a metà
luglio 2026**: 1.910.733 righe dal 2010, importate dai `.txt` in `raw/`. Le
altre 14 partono tutte dal 2026-07-17, che è la finestra che l'API restituisce a
ogni fetch — non una data scelta.

Lo scarico delle storie orarie delle altre 14 è **in corso** al momento di
questa nota. Chi legge un grafico pluriennale deve saperlo: finché non sono
tutte dentro, il confronto storico *tra* stazioni non è disponibile, e l'assenza
di una curva non significa che il dato non esista.

È il seguito della scelta di ridurre a 15 (voce del 2026-07-19): il valore sta
nella profondità, non nella copertura. Ed è la ragione per cui la proiezione di
crescita nelle domande aperte non è teorica — quei 6 GB stanno arrivando.

## 2026-08-07 — via `raw_json` e l'indice ridondante: il DB da 1189 a 457 MiB

Misurato perché la dimensione del file sorprendeva. `raw_json` pesava **582 MB,
il 49% del file**, e non veniva **mai letto**: solo scritto, da `scrape.py` e
dall'importatore. La dashboard non lo tocca.

Il grosso non era il campo ma come lo scriveva l'import storico: la stazione
`300000150` (Mogliano) fa 1.910.583 righe su 2.193.872, e ogni riga oraria del
CSV veniva salvata **per intero una volta per ciascuna variabile che se ne
deriva** — in media 11 copie, fino a 13. Su 520 MB, il contenuto unico era 45:
**475 MB di pura ripetizione, il 40% del file**.

Insieme è uscito `idx_observations_station_time` su `(station_id,
observation_at)`: un **prefisso della chiave primaria** `(station_id,
observation_at, variable_type)`, 90 MB. Il planner lo sceglieva — verificato con
`EXPLAIN QUERY PLAN`, quindi non era "morto" — ma solo perché più stretto;
tolto, ripiega sull'indice automatico della PK con lo stesso piano, stessi
risultati e nessun rallentamento misurabile.

Risultato: **1189 → 457 MiB, −62%**, con le 2.193.872 righe intatte e
`quick_check ok`.

**Perché si può buttare la risposta grezza:** il DB sta in Time Machine, e i
`.txt` storici che alimentano l'importatore restano in `raw/` (20 MB). La copia
in-riga non era un archivio, era un residuo.

**⚠️ Il codice ricreava ciò che si toglieva.** `scrape.py` fa `CREATE TABLE IF
NOT EXISTS` e `CREATE INDEX IF NOT EXISTS` a ogni avvio: senza toccarlo, il job
delle 13:00 avrebbe rimesso l'indice da 90 MB e la colonna sarebbe tornata al
primo schema nuovo. Lo si è scoperto solo perché dopo la migrazione si è
eseguito **subito** uno scrape di prova invece di fidarsi — il file era già
risalito di 84 MB. Regola che ne segue: **una migrazione dello schema non è
finita finché non si è visto girare lo scraper sul DB migrato.**

---

## Domande aperte

- ✅ **`raw_json`** — chiusa il 2026-08-07 con i numeri: 582 MB, mai letta, via.
  Vedi la voce di quel giorno.
- **La crescita del DB, con le 14 storie che stanno arrivando.** Oggi 457 MiB,
  costo misurato **218 byte per riga** tabella e indici compresi. La storia di
  Mogliano è 1,91 M di righe: se le altre 14 stazioni portano storie
  paragonabili, sono ~27 M di righe in più, cioè **nell'ordine dei 6 GB**
  (meno, per le stazioni con serie più corte o meno variabili). È un ordine di
  grandezza, non una previsione.

  Due conseguenze. La prima: il taglio di `raw_json` è arrivato appena in tempo
  — con la colonna, gli stessi import avrebbero aggiunto ~6,6 GB di sola
  ripetizione, e il DB sarebbe finito oltre i 13 GB. La seconda: **la soglia
  della politica di archiviazione la decidono quelle importazioni**, non il
  passare del tempo. Si fissa misurando i tempi di query della dashboard dopo
  la terza o quarta storia caricata; oggi le query di riferimento stanno sotto
  i 150 ms.
- **⚠️ `export_csv` riscrive l'intero database a ogni scrape.** Oggi sono 208 MB
  di CSV rigenerati da capo ogni ora, con una scansione completa di
  `observations`. Alla fine degli import diventerebbero **~2,8 GB riscritti ogni
  ora** su SSD, per un file che è la copia testuale di un DB già in Time
  Machine. Va deciso *prima* che gli import finiscano: export su richiesta dalla
  dashboard, oppure incrementale, oppure via del tutto.
- **`station_name` ripetuto in ogni riga**, 32,5 MB prima del taglio, quando sta
  già in `stations`. E `downloaded_at` come testo ISO, 52 MB. Sono i due
  candidati successivi, ma valgono insieme meno di un decimo di ciò che si è
  appena recuperato: non si toccano finché non c'è un motivo migliore dello
  spazio.
- **Il fallback del riassunto AI non è mai stato provato sul serio.** Si sa che
  c'è, non si sa quanto spesso scatta. Un contatore nei log direbbe se il
  modello locale regge.
