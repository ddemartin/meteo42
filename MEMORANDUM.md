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

## 2026-08-10 — ERA5-Land: 76 anni di rianalisi, in un database separato

Le osservazioni ARPAV per Mogliano partono dal 2010. ERA5-Land, la rianalisi
ECMWF, copre **dal 1950** su una griglia di `0,1°`: per la cella
`45,6 N, 12,3 E` — il nodo più vicino alla stazione, a circa 2,2 km — sono
671.303 ore di temperatura, dew point e precipitazione. È l'unico modo di
avere un fondale climatico lungo sotto una serie osservata corta.

**Database separato, `era5_land.sqlite`.** Provenienza, semantica e ciclo di
aggiornamento non hanno niente in comune con le osservazioni: tenerle nello
stesso file appesantirebbe backup, indici e scritture del DB operativo per
dati che cambiano una volta l'anno. I confronti si fanno con `ATTACH DATABASE`
o con un merge Pandas, che costano molto meno del contrario.

**Un parser GRIB scritto a mano** (`era5_grib.py`), invece di `cfgrib`/eccodes.
Il formato accettato è solo quello verificato nei download CDS correnti:
GRIB 1 ECMWF, griglia lat/lon regolare, scan mode `0`, packing semplice. Tutto
il resto solleva un errore. Il criterio è che un formato inatteso deve
*fermare* l'import, non produrre dati silenziosamente sbagliati.
**Prezzo:** se ECMWF cambia codifica il parser va aggiornato a mano.
**Alternativa scartata:** eccodes, che è una dipendenza nativa da compilare e
tenere allineata per leggere tre variabili su un punto solo.

Tre cose sono costate tempo, e nessuna è deducibile dalla documentazione CDS.

**Il CDS tariffa per numero di campi, e l'area non c'entra.** Una sola cella
per un anno intero viene rifiutata con `cost limits exceeded`. Misurato:
12 mesi (26.280 campi) rifiutato, 6 mesi (12.960) rifiutato, 4 mesi (8.640)
accettato. Da qui `CHUNK_MONTHS = 4`, che sta sotto la soglia ed è un terzo
esatto d'anno, quindi i blocchi cadono su confini di mese puliti. Il chunking
annuale progettato quando la variabile era una sola non ha mai funzionato con
tre: non era mai stato provato contro il CDS.

**Il 1950-01-01 ha 23 ore, non 24.** ERA5-Land nasce da previsioni lanciate
alle 00 UTC, quindi il valore valido a mezzanotte appartiene al run del giorno
prima. Il primo giorno del dataset quel run non ce l'ha, e mancano **tutte e
tre le variabili**, non solo la precipitazione. Senza questa correzione la
prima richiesta dello storico fallisce la validazione sul conteggio dei
messaggi — che è esattamente il comportamento voluto, ma per il motivo
sbagliato.

**L'intestazione GRIB della precipitazione mente.** Ogni messaggio dichiara
`P1 = N-1`, `P2 = N`, indicatore temporale `4` — cioè un intervallo di un'ora
— mentre i valori sono l'accumulo dall'inizio del run:

```
param  rif.(A M G H)  unità P1 P2 TRI
  228  15-10-03 00h       1 23 24   4     <- valido 15-10-04 00:00
  228  15-10-04 00h       1  0  1   4     <- reset
  228  15-10-04 00h       1  1  2   4
```

Il reset si riconosce quindi da `P2 == 1`, non dall'indicatore temporale, e il
valore orario si ottiene per differenza. Il DB conserva **entrambi**: accumulo
grezzo e valore orario, così la differenza resta verificabile a posteriori e
l'ora a cavallo di due file si ricostruisce leggendo l'accumulo precedente dal
database. **Prezzo:** se ECMWF passasse a valori davvero orari l'intestazione
resterebbe identica e il differenziamento produrrebbe spazzatura. L'unica
difesa è il controllo sull'accumulo decrescente, che solleva un errore invece
di correggere e scatterebbe alla prima ora asciutta dopo una piovosa.

**Confronto con ARPAV.** ERA5-Land è in UTC, il DB ARPAV in ora solare fissa
`UTC+1` tutto l'anno: per confrontare le serie il timestamp ERA5 va traslato di
`+1 ora`. E `TARIA2M` è una media oraria, mentre ERA5 è il valore modellato
all'istante di validità — differenza da ricordare leggendo gli scarti orari.
Verificato su ottobre 2015, 744 coppie: bias `+0,46 °C`, MAE `0,98 °C`, RMSE
`1,34 °C`, correlazione `0,950`, MAE sulle medie giornaliere `0,55 °C`. Il
valore ERA5 rappresenta un'area di circa 11 × 8 km, non la misura puntuale
della stazione: a questa scala quel bias è il livello di accordo che ci si
può aspettare, non un difetto da correggere.

**Nota per le stazioni costiere:** ERA5-Land maschera il mare, e il nodo
geometricamente più vicino può non contenere valori. Va verificato prima di
dare per scontato che una cella esista.

## 2026-08-09 — sorgere e tramontare della luna calcolati sul giorno locale

La sezione cielo è andata in `TypeError` sul sorgere della luna del 9 agosto.
Due difetti sovrapposti, e il primo nascondeva il secondo.

`astral.moon.NoTransit` **non è un'eccezione**: è una `dataclass` che
`riseset()` usa internamente per dire «in quest'ora la luna non attraversa
l'orizzonte». Scriverla in `except (ValueError, moon.NoTransit)` compila, ma il
giorno in cui il ramo serve davvero Python rifiuta la tupla — *catching classes
that do not inherit from BaseException is not allowed* — e l'errore che si
vede non è quello vero. Un `except` scritto per un caso raro va provocato
almeno una volta, altrimenti è codice mai eseguito che aspetta il suo giorno.

Il caso raro, però, non era affatto quello previsto. `moon.moonrise` ragiona a
**giorni UTC**: a est di Greenwich un sorgere subito dopo la mezzanotte locale
cade nella finestra del giorno UTC precedente, e la funzione solleva
`ValueError("Moon never rises on this date")` mentre la luna sorge eccome — il
9 agosto alle 01:41. Catturare e mostrare «—» avrebbe tolto il crash lasciando
un dato **falso**, una volta al mese e sempre di notte, cioè quando la scheda
serve. Si chiama quindi `riseset()` direttamente sulle tre finestre `-1, 0, +1`
e si tiene l'evento la cui **data locale** è quella richiesta. Su 60 giorni
provati restano quattro «—», e sono veri: capita davvero, circa una volta al
mese per il sorgere e una per il tramontare, che l'evento salti un giorno di
calendario perché slitta di ~50 minuti al giorno.

**Prezzo:** `riseset` non è in `__all__` di `astral.moon`, è API interna e un
aggiornamento del pacchetto può cambiarla. È un rischio accettato consapevolmente:
l'API pubblica non espone il giorno locale, e la sola alternativa era calcolare
le effemeridi della luna con `ephem` — che c'è già per i pianeti, ma è
opzionale (vedi il `try/import` in testa a `dashboard.py`) e avrebbe reso la
luna indisponibile proprio quando lo si scarta. Se `astral` romperà `riseset`,
la strada è quella.

**Alternativa scartata:** correggere solo l'`except` in `except ValueError`.
Un carattere, nessun crash, e un dato sbagliato al mese che nessuno avrebbe più
messo in dubbio.

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

## 2026-08-07 — l'export CSV automatico sparisce, si esporta la selezione

`export_csv` riscriveva **l'intero database** in fondo a ogni scrape: 208 MB
rigenerati da zero, 4,85 s su un giro il cui lavoro utile ne dura ~17, cioè
~5 GB di scritture SSD al giorno. Con le storie orarie in arrivo sarebbero
diventati ~2,8 GB all'ora, **67 GB al giorno**.

E non lo leggeva nessuno: né la dashboard, né l'importatore. Era la copia
testuale di un database che sta già in Time Machine.

**L'incrementale è la strada peggiore**, e vale la pena scriverlo perché è la
prima che viene in mente: il file è ordinato per `(station_id, observation_at,
variable_type)` e gli import storici inseriscono righe *in mezzo*: un append
lascerebbe il file disordinato, oppure costringerebbe a riscriverlo comunque.

Al suo posto, in fondo al tab Dati, un `st.download_button` che esporta **la
selezione filtrata** — le stesse colonne di prima, `;` e BOM perché il consumo
è Excel in locale italiano. In cache 60 s: `download_button` vuole i byte
pronti a ogni rerun, quindi senza cache ogni interazione con la pagina
rigenererebbe l'export.

**⚠️ Quello che si è scoperto facendolo:** l'esportazione dalla dashboard **non
esisteva**, benché il README la promettesse ("Esporta risultati") da luglio. Il
bottone "Scarica dati ora" lancia lo scrape, non scarica niente. Togliere
`export_csv` senza guardare avrebbe lasciato il progetto **senza alcuna via
d'uscita dei dati** — il README l'avrebbe coperto, essendo già falso.

Per l'intero database la via resta copiare `arpav_meteo.sqlite`, che è già un
file solo. Il vecchio `arpav_meteo.csv` è stato cancellato: era rigenerabile
byte per byte, e comunque non tornerà da solo.

## 2026-08-07 — un argomento per scheda: previsioni e cielo escono dalla panoramica

La panoramica faceva sei cose: condizioni di casa, report, grafici a 72 ore,
Sole/Luna/pianeti, radar, bollettino. Il bollettino stava **in fondo**, dopo
tutto il resto: la cosa che si consulta più spesso dopo «quanti gradi fa» era
la più lontana da leggere, e su un telefono voleva mezzo minuto di scorrimento.

Ora una scheda per argomento, e nell'ordine in cui si usano: **Adesso** (com'è
ora, a casa e nei capoluoghi), **Previsioni** (radar e bollettino), **Cielo**
(Sole, Luna, pianeti), poi diario, dati, grafici, storico, stazioni. Le
stazioni vanno in fondo: sono amministrazione, si aprono tre volte l'anno.

Il **radar sta con le previsioni e non con le osservazioni**, benché sia un
dato osservato: la domanda a cui risponde è «piove tra un'ora?», la stessa del
bollettino, e le due cose si leggono insieme.

Le **ore di luce erano finite sotto la Luna**, in una `st.caption` accanto a
sorgere e tramontare lunari, dove non c'entravano niente: la durata del giorno
la decide il Sole. Sono risalite nel gruppo del Sole, come quarta tessera dopo
alba, culmine e tramonto, e con l'occasione dicono anche quanto è cambiata
rispetto a ieri — che è l'informazione per cui uno guarda la durata del giorno.

**Alternativa scartata:** lasciare tutto in una scheda e riordinare soltanto.
Non risolveva: la panoramica restava lunga quanto prima, e su un telefono la
lunghezza è il problema.

## 2026-08-07 — le variabili di tema di Streamlit non esistono più

Le schede disegnate a mano (bollettino, diario) usavano `var(--primary-color)`,
`var(--background-color)` e `var(--text-color)` dentro `color-mix()`, dando per
scontato che Streamlit le esponesse. **Non le espone**, almeno dalla 1.60:
misurato in Chrome con `getComputedStyle(document.documentElement)`, tutte e
tre tornano stringa vuota, e nel foglio di stile della pagina non c'è nessuna
proprietà personalizzata a parte le proprie.

La conseguenza non era un errore ma qualcosa di peggio, perché silenzioso: una
`color-mix()` con dentro una variabile inesistente è invalida, la dichiarazione
cade, e le carte venivano disegnate **senza sfondo, senza bordo e con il
"cappello" del colore del testo invece che del colore primario**. Sembravano
semplicemente sciatte, e non c'era modo di accorgersi che era un guasto.

Al loro posto niente dipendenze dal tema: **grigio neutro a bassa opacità**
(`rgba(128,128,128,0.09)` per le superfici, `0.30` per i bordi) che su fondo
bianco e su fondo quasi nero rende allo stesso modo, e `currentColor` per il
testo secondario, che eredita il colore del tema qualunque esso sia. L'accento
resta `#FF4B4B`, il primario di Streamlit, scritto esplicitamente.

**Alternativa scartata:** leggere il tema da `st.context.theme` e generare il
foglio di stile lato Python. Funzionerebbe, ma lega il codice a un'altra API di
Streamlit per riottenere ciò che tre colori neutri danno senza legarsi a nulla.

**Regola che ne segue:** una regola CSS che dipende da un'API di terzi va
guardata **renderizzata**, non solo nel sorgente. Qui il codice era plausibile e
l'output no, e nessun test che guardi il codice se ne sarebbe accorto.

## 2026-08-07 — griglie CSS al posto di `st.columns`, per il telefono

`st.columns` **non manda a capo**: quattro colonne restano quattro colonne
anche a 390 px, e diventano quattro colonnine da una parola l'una. Le file di
`st.metric` della panoramica e del diario erano esattamente questo.

Le tessere sono ora HTML in una griglia `repeat(auto-fit, minmax(148px, 1fr))`,
che si impagina da sé: quattro colonne sul desktop, due sul telefono, senza una
media query. Stesso trattamento per i pianeti visibili, che erano un
`st.dataframe` a cinque colonne — su un telefono una striscia da scorrere in
orizzontale — e ora sono schede con il pallino del colore che hanno nel grafico
delle altezze.

Vincolo scoperto: **una griglia dev'essere una sola chiamata a `st.markdown`**.
Streamlit chiude ogni markdown in un contenitore suo, quindi tessere emesse una
per volta finiscono in griglie diverse, ognuna larga tutta la pagina. Da qui
`m42_render_tiles`, che prende la lista e la stampa in un colpo solo.

Per lo stesso motivo `get_visible_planets` restituisce ora **valori grezzi** e
non stringhe già formattate: serviva ordinare per altezza e formattare altezza
e magnitudine in modo diverso, cose che un DataFrame di stringhe non permette.

**Alternativa scartata:** `st.columns` con un numero di colonne diverso a
seconda della larghezza. Streamlit lato server la larghezza del browser non la
conosce, quindi non si può.

## 2026-08-07 — la carta di oggi è quella con meno mappe

**Difetto osservato subito dopo il riordino:** la carta di oggi, resa larga
tutta la riga perché è quella che si legge davvero, mostrava la mappa in mezzo
a un vuoto enorme. Misurato: carta 980 px, **una sola** figura, traccia unica
da 957 px, immagine sorgente 600×600 stirata a 957×990.

La causa non è la griglia ma il dato: il bollettino ARPAV pubblica due mappe al
giorno, mattino e pomeriggio, e **quella del mattino sparisce col passare della
giornata**. Nel pomeriggio la carta di oggi ha una mappa mentre i giorni
seguenti ne hanno due — cioè la carta più larga è proprio quella con meno da
mettere dentro. In `repeat(auto-fit, minmax(210px, 1fr))` le tracce vuote
collassano e l'unica rimasta si prende tutto.

Sopra gli 820 px la carta in evidenza diventa **mappe a sinistra (260–340 px) e
testo a destra**: la larghezza la usa il testo, che è la parte che si legge, e
la mappa resta della misura delle altre. Sotto quella soglia resta impilata
come prima. In più `max-width: 600px` sulle figure, la risoluzione nativa delle
mappe ARPAV: oltre si sgranerebbero e basta.

**Alternativa scartata:** togliere l'evidenza e rendere tutte le carte uguali.
Risolveva il vuoto ma buttava via la ragione dell'evidenza — il testo di oggi
finiva in una colonna da 317 px come quello di dopodomani.

**Regola che ne segue:** una carta "in evidenza" va guardata **con i dati del
momento peggiore**, non con quelli del momento in cui la si scrive. Al mattino
questo difetto non esisteva.

## 2026-08-07 — il diario si sfoglia col calendario, e i giorni sono in italiano

La tendina dei giorni cresce di una voce al giorno: a un anno di distanza
cercare «il 3 marzo» vuol dire scorrere trecento righe. Ora un `st.date_input`
con `min_value`/`max_value` presi dagli estremi realmente in archivio.

Dentro l'intervallo si può però cadere su un giorno **vuoto** — l'archivio non
è per forza di giorni consecutivi. In quel caso si dice («per questo giorno non c'è
niente in archivio»), non si nasconde: un calendario che accetta solo certi
giorni e tace sugli altri fa sembrare guasta l'applicazione.

**⚠️ Scoperto facendolo:** le date erano in inglese. `%A` segue la locale del
processo, e il servizio launchd gira **senza `LANG`**: in mezzo a una dashboard
tutta in italiano usciva «Friday 07/08/2026». Da qui `italian_date_label`, con
i nomi dei giorni scritti a mano — impostare la locale del processo avrebbe
toccato anche il parsing dei numeri, che qui non si vuole muovere.

**Limite accettato:** l'intestazione del calendario di Streamlit (mese e
iniziali dei giorni) resta in inglese e non è configurabile — verificato che
con browser in `it-IT` cambia solo il primo giorno della settimana, che passa
correttamente al lunedì. Sotto il campo c'è la data per esteso in italiano, che
è ciò che si legge davvero.

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
- ✅ **`export_csv` a ogni scrape** — chiusa il 2026-08-07, vedi la voce di quel
  giorno.
- **`station_name` ripetuto in ogni riga**, 32,5 MB prima del taglio, quando sta
  già in `stations`. E `downloaded_at` come testo ISO, 52 MB. Sono i due
  candidati successivi, ma valgono insieme meno di un decimo di ciò che si è
  appena recuperato: non si toccano finché non c'è un motivo migliore dello
  spazio.
- **Il fallback del riassunto AI non è mai stato provato sul serio.** Si sa che
  c'è, non si sa quanto spesso scatta. Un contatore nei log direbbe se il
  modello locale regge.
