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

## 2026-08-17 — la retta di tendenza sull'andamento annuale, non pesata e con un minimo di anni

Terza casella sull'andamento annuale, spenta di default come le altre due del
2026-08-15: la **retta dei minimi quadrati** sulle medie annue, tratteggiata,
con la pendenza scritta in legenda e l'R² nell'hover. Sull'archivio ERA5 di
oggi (1950-2017) dice **+0,23 °C per decennio, R² 0,45**.

**Lineare e non altro.** Una curva — polinomio, LOESS — descriverebbe meglio i
punti e direbbe molto meno: la domanda è di quanto si sia scaldato, cioè un
numero solo, e quel numero è la pendenza. Il rischio della curva è l'opposto di
quello della retta: la retta si vede subito che è una semplificazione, mentre
la curva si legge come struttura misurata anche dove è solo rumore
interpolato.

**Non pesata sulle ore**, a differenza della media del periodo e delle medie
per decennio. Lì il peso serve perché si sommano ore disuguali dentro un unico
numero; qui ogni punto è un anno completo e vale quanto gli altri, e il giorno
in più dei bisestili sposta la pendenza di molto meno di quanto la sposti un
anno caldo qualunque. Pesare avrebbe dato un'aria di precisione che il dato non
ha.

**La pendenza per decennio, non per anno né per secolo.** All'anno sono
centesimi di grado che non si leggono, al secolo è una cifra che nessuno può
verificare sul grafico; il decennio è anche il passo con cui il resto della
scheda confronta i periodi.

**Sotto i dieci anni completi la casella è disabilitata**, non nascosta. Su una
serie corta la retta misura soprattutto quali anni sono capitati agli estremi,
e il testo d'aiuto lo dice: una casella grigia con la spiegazione insegna
qualcosa, una casella assente lascia credere a un guasto. Il limite di dieci è
convenzionale — vale il criterio, non il numero: sull'archivio ERA5 (68 anni)
non scatta mai, serve a chi ripuntasse la scheda su una serie osservata breve.

**L'R² sta nell'hover e non in legenda.** In legenda ci va ciò che si porta via
guardando il grafico una volta sola, e quello è la pendenza; l'R² serve a chi
si chiede quanto la retta stia stretta ai punti, cioè a chi sta già guardando.

---

## 2026-08-15 — due strati facoltativi sull'andamento annuale, e la finestra mobile che vale quanto un anno solare

Sull'andamento annuale si accendono a casella — **spente di default** — le
medie per decennio e la media degli ultimi 365 giorni. Il criterio della
casella è che il grafico di base risponde a una domanda sola: tre linee sempre
accese sarebbero due linee da scartare ogni volta che se ne guarda una.

**I decenni a scalini (`shape="hv"`), non uniti fra i centri.** Dentro un
decennio non c'è nessun andamento, c'è un unico numero: la spezzata che
congiunge i centri dei decenni disegnerebbe una pendenza che nei dati non
esiste, e in mezzo a una serie annua vera sarebbe indistinguibile da un
andamento misurato. Lo scalino, che salta di netto al cambio di decennio, dice
esattamente ciò che il numero è.

**La media dei decenni è pesata sulle ore**, non è la media delle medie annue:
i bisestili portano un giorno in più e i decenni di bordo sono fatti di meno
anni — il 1990 ne ha sei, e l'hover lo dice invece di lasciarlo credere pieno.

**La finestra di 365 giorni è l'unica media della scheda che non passa dagli
anni completi, e non contraddice la regola del 2026-08-10 — la conferma.** Quel
divieto esiste perché un anno solare tronco ha dentro solo certe stagioni, e
mediarci sopra dà un numero che parla del pezzo di calendario, non del clima.
Una finestra **lunga un anno per costruzione** contiene ogni stagione una volta
sola: lo squilibrio che rendeva falsa l'altra media qui non c'è. Sotto le 8.000
ore la funzione non restituisce niente e la casella resta disabilitata, perché
lì la finestra tornerebbe a essere una stagione.

**Un secondo tolto alla data di fine.** L'ultimo record copre l'ora che
comincia alle 23:00 UTC del 31 dicembre, che in ora locale è il 1° gennaio: la
finestra si sarebbe detta chiusa in un anno di cui non esiste nemmeno un
giorno. È lo stesso spostamento di UTC+1 già annotato il 2026-08-10, che
ricompare ogni volta che si stampa un estremo dell'archivio.

---

## 2026-08-15 — i giorni oltre soglia contati anno per anno, in sei ricette

La libreria contava i giorni oltre una soglia **dentro un anno** o **per
decennio**: mancava la forma che serve per vedere lo spostamento, cioè un
conteggio per ogni anno dell'archivio. Sei ricette nuove — massima, minima,
media giornaliera, ciascuna sopra e sotto soglia.

**Sei e non una con la colonna a scelta.** Il patto di questo file è che il
modello riempie *valori*, mai frammenti di SQL: né `tmax`/`tmin`/`tmedia` né il
verso del confronto possono essere parametri legati. Scartata anche la via di
mezzo — un parametro `verso` con un `CASE` dentro il `FILTER` — perché
complica la query per risparmiare cinque voci in un elenco che il modello
legge, e leggere sei titoli espliciti è proprio il compito facile che lo fa
sbagliare meno.

**Il conteggio in `FILTER`, non in `WHERE`.** Stessa ragione già scritta per i
decenni, ma qui pesa di più: filtrando prima del raggruppamento un anno senza
nemmeno un giorno oltre soglia sparirebbe dal risultato, e in una serie nel
tempo un anno mancante non si legge come lo zero che è — si legge come un dato
che non c'è. Il caso è reale e non teorico: con la soglia a 30 °C il **1951 vale
zero**, perché la massima oraria di tutto l'anno è 29,8 °C.

**Quel 1951 non è un guasto ed è un promemoria su cosa sono questi numeri.**
ERA5-Land è una media su una cella di 9 km: gli estremi sono smorzati, e le
massime di questa serie stanno sotto quelle che avrebbe misurato un termometro
in loco. Le soglie classiche (30 °C, 0 °C, notti tropicali a 20 °C) restano
utili per **confrontare un anno con l'altro**, che è ciò a cui servono queste
ricette, non per dire quanti giorni sopra i 30 ha fatto davvero a Mogliano.

**Solo anni completi**, con `COMPLETE_YEARS_CTE` già in uso per le medie: un
conteggio su un anno tronco crolla senza dirlo, e su una serie di conteggi il
crollo finale si legge come un fatto climatico. Costo misurato: **0,2-0,4 s** a
query sull'archivio attuale, ben dentro il limite dei 15 secondi.

---

## 2026-08-15 — una classifica non è una serie: il grafico lo riconosce dalle righe

`Lo stesso mese confrontato in tutti gli anni` disegnava un intrico
illeggibile: quattro segmenti che scendevano da sinistra a destra
attraversandosi, senza che nessuno dei due assi dicesse più niente. La query
finisce con `ORDER BY media DESC LIMIT 15`, quindi le righe arrivano
**1950, 1994, 1983, 1952, 1995…**: unendole con una linea si tracciavano
segmenti fra anni che nel tempo non si toccano, e i sessant'anni rimasti fuori
dalla classifica sparivano senza dirlo. Non era un difetto di stile ma un
grafico **falso**: la pendenza di quei segmenti si legge come un andamento, e
lì dentro di andamento non ce n'è.

**Il criterio è la monotonia dell'asse X, non il testo dell'SQL.** Se i valori
di X non salgono (o scendono) riga dopo riga, il risultato è un elenco
ordinato per valore e non una serie nel tempo: asse di categorie nell'ordine
del risultato e niente linee. Scartato l'etichettare a mano le ricette come
"classifica": sarebbe stato un campo in più da ricordare per ognuna delle
trenta, e soprattutto non avrebbe coperto l'SQL libero, dove la classifica la
scrive chi guarda. Delle ricette della libreria ne cadono in questo caso **sei**
(`stesso_mese_tra_anni`, `anni_piu_caldi`, `anni_piu_freddi`,
`giorni_piu_caldi`, `giorni_piu_freddi`, `giorni_piu_piovosi`), e infatti il
difetto era stato notato su più di una query.

**Punti per i gradi, barre solo per ciò che ha uno zero vero.** Prima cura
scritta e subito corretta: mettere *tutto* a barre. Una barra dice "quanto", e
0 °C non è un'assenza di temperatura ma una convenzione — la classifica dei
luglio sta fra 23 e 26 °C, e da zero sarebbero state quindici barre tutte
uguali, cioè un altro modo di non far vedere il dato. I millimetri, che uno
zero vero ce l'hanno, restano barre da zero sull'asse destro.

**Il titolo dei grafici diceva `undefined`.** `stile_clima` impostava
`title=dict(x=…, font=…)` senza `text`: le figure fisse lo scrivevano da sé e
il difetto non si vedeva, quella dei risultati di query no, e plotly.js
stampava la stringa `undefined` in grassetto dove sarebbe andato il titolo.
Ora `text` viene ripetuto sempre, vuoto quando non c'è. Non è un caso che sia
saltato fuori con l'unica figura senza titolo: un default assente si vede solo
dove nessuno lo copre.

---

## 2026-08-13 — la cella ERA5-Land è tutta terraferma: misurato, non dedotto

La domanda era legittima e non aveva ancora una risposta: la cella
`45,6 N / 12,3 E` sta a una decina di chilometri dalla laguna, e una cella che
ne prendesse dentro un pezzo darebbe temperature smorzate dall'acqua — un
difetto che non si vede, perché i numeri restano plausibili.

Il nodo è il centro di un rettangolo di `0,1°`: **45,55–45,65 N / 12,25–12,35 E**,
11,1 × 7,8 km, 87 km². Quattro misure indipendenti, tutte concordi:

| controllo | risultato |
|---|---|
| linea di costa (OSM `natural=coastline`) dentro la cella | **0 elementi** |
| acqua di marea più vicina (barene, `tidalflat`, coastline) | **3,66 km** dal bordo (45,5209 N 12,3719 E), ~10 km dal centro |
| costa aperta (laguna navigabile / mare) | 14,1 km dal bordo, 20,6 km dal centro |
| quote del terreno (Copernicus DEM, griglia 9×9 nella cella) | min 0 m, media 6,4 m, max 16 m |

**L'angolo sud-est ha rischiato di far dire di no.** Due punti della griglia
davano quota `0,0 m`, che su un DEM è anche il valore dell'acqua. Infittendo il
campionamento (36 punti su ~3 km) e interrogando l'OSM entro 300 m si vede che
è **bonifica agricola**: campi, strade, fossi e canali di scolo, con un punto a
−2 m che è terra sotto il livello del mare, normale da quelle parti. Nessun
poligono d'acqua li contiene. La lezione è che la quota da sola non separa
l'acqua dalla terra bassa, e infatti da sola non è stata creduta.

Dentro la cella l'acqua mappata è **2,08 km², il 2,4%**: lo Zero, il Dese,
qualche bacino e i fossi. È l'acqua interna di qualsiasi cella di pianura
veneta, non un pezzo di laguna.

**Riscontro dal dato stesso:** ERA5-Land è prodotto solo sui punti di terra, e
sul mare i valori sono mascherati. Il nodo ha 242.519 ore senza buchi, quindi
anche ECMWF lo classifica come terra — non è solo la geometria dell'OSM a dirlo.

**Il margine è più stretto di quanto sembri.** Il nodo immediatamente a sud,
`45,5 / 12,3`, ha il bordo del suo rettangolo a `45,45` e la laguna se la
prende dentro. Quello scelto — che resta il più vicino alla stazione, 2,2 km —
sta dalla parte giusta per un solo passo di griglia: se un domani si cambiasse
stazione o si arrotondasse diversamente, questa verifica va rifatta, non
ereditata.

**Come si rifà**, senza dipendenze nuove: Overpass API per costa, acque e
barene nel riquadro della cella (`way["natural"="coastline"](45.55,12.25,45.65,12.35)`
e la stessa cosa per `natural=water|wetland`), e l'API di elevazione di
Open-Meteo per le quote su una griglia di punti. **Scartata** l'idea di
scaricare la maschera terra/mare dal CDS: quella di ERA5 sta a `0,25°`, cioè
più grossa della cella che deve giudicare, e avrebbe risposto a una domanda
diversa da quella posta.

---

## 2026-08-13 — i grafici della scheda Clima hanno uno stile solo, e gli assi smettono di decidere da soli

Quattro difetti visti guardando la scheda, non leggendo il codice. Si curano in
un posto solo — `stile_clima`, chiamata per ultima da ogni figura della scheda —
perché quattro `update_layout` copiati sono quattro posti dove il quinto grafico
dimenticherà qualcosa.

**Via i pallini dalle serie continue.** Su 76 punti annuali o su dodici mesi il
marcatore non aggiunge un'informazione: ingrossa la linea e le fa perdere la
forma, che è l'unica cosa che si va a cercare in un ciclo annuale. Il valore
puntuale resta a un tocco di distanza nel tooltip, che c'era già.

**Le tacche dell'asse Y le decide `passo_gradevole`, non Plotly.** Sulle
temperature di luglio — che stanno in nove gradi — la scelta automatica dava
**15 / 20 / 25**: tre tacche, e una serie che si muove tutta dentro il primo
intervallo. Ora il passo è il numero tondo (1, 2 o 5 × 10ⁿ) che divide
l'intervallo dei dati in circa dieci, quindi luglio si legge di grado in grado.
**Scartato il 2,5** che pure sarebbe "tondo": una scala di temperature che sale
di 2,5 °C alla volta si legge peggio di una che ne salta 5, e sarebbe stato
spostare il difetto invece di toglierlo.

**Le tacche dell'asse X partono dal primo valore.** Una serie di mesi cominciava
da **3**, perché la prima tacca automatica cadeva lì: sembrava che i dati
partissero da marzo. Con `tick0` sul minimo, gennaio è gennaio e il primo del
mese è il primo. Nei risultati delle query una colonna `mese` di interi fra 1 e
12 porta direttamente i nomi dei mesi, e sugli assi di categorie le etichette
sono tutte forzate con `tickvals`: Plotly ne salta una sì e una no appena il
riquadro si stringe, ed è lo stesso difetto visto da un'altra parte.

**La legenda non tocca più il titolo dell'asse X.** Erano appiccicati perché
occupavano la stessa fascia sotto al riquadro. Invece di allontanarli di
qualche pixel — cura che il primo schermo stretto avrebbe disfatto — sono
spariti i titoli degli assi dove non dicevano niente ("Mese" sotto Gen-Dic,
"Anno" sotto gli anni) e l'unità di misura è passata nel titolo del grafico
(«Temperatura media annua · °C»). Sotto al riquadro resta solo la legenda,
quindi non ha più niente da toccare, e il margine inferiore cresce con il
numero di voci invece di essere il valore fisso di `MOBILE_CHART_MARGIN`.

**I decenni passano da tinte qualitative a una scala fredda→calda.** I decenni
sono ordinati: `year_qualitative_color` — che resta giusta dove un anno deve
avere sempre lo stesso colore a prescindere dal filtro — li dipingeva di colori
non confrontabili tra loro, e lo spostamento del clima si vedeva solo leggendo
la legenda. Ora il blu è il decennio più vecchio, il rosso il più recente, e
l'ultimo è anche più spesso perché è quello che si va a guardare.

**Cambiata solo la scheda Clima.** `MOBILE_LEGEND` e `MOBILE_CHART_MARGIN`
restano come sono per le altre schede: se questo stile regge all'uso, sarà da
estendere lì, ma cambiare nove schede per un difetto visto su una avrebbe
mescolato la cura con l'esperimento.

---

## 2026-08-11 — la scheda "Clima", e un'LLM che propone l'SQL invece di eseguirlo

La rianalisi entra nella dashboard con una scheda sua, la nona.

**Si chiama "Clima", per funzione e non per fornitore.** Scartati due nomi:
*Sentinel*, che è la costellazione di satelliti di Copernicus e non ha niente a
che vedere con una rianalisi ECMWF — avrebbe promesso dati che non ci sono; e
*ERA5-Land*, corretto ma che lega il nome della scheda a una sorgente che un
giorno potrebbe cambiare. "Clima" dice cosa ci si trova, e sta accanto a
"Storico Annuale" che sono invece le osservazioni.

**Nelle medie entrano solo gli anni con dodici mesi completi.** Lo scaricamento
dura giorni e per tutto quel tempo l'ultimo anno è tronco: la media del 1961
sui soli gennaio-agosto dava **14,04 °C** contro i 12,7 °C del periodo, cioè un
anno eccezionalmente caldo che non è mai esistito. Un errore che non si vede,
perché il numero è plausibile. I mesi incompleti restano elencati sotto le
tessere, così l'esclusione è visibile invece che silenziosa.

**⚠️ Scoperto facendolo:** con la tolleranza a un'ora il 1950 spariva dai
confronti. Ne mancano **due**, non una: quella che ERA5 non ha (a mezzanotte
del primo giorno manca la corsa che la produce) e quella che porta via il
raggruppamento in ora locale `UTC+1`, che fa cominciare gennaio alle 02:00.
Buttare un anno intero per due ore su 8760 è peggio del difetto che la soglia
doveva evitare. La tolleranza non può nascondere un buco vero: il download
valida ogni blocco sul numero di messaggi, quindi i mesi interni sono interi.

**L'aggregazione è in ora locale, non in UTC**, coerente con il resto della
dashboard (2026-08-02): altrimenti ogni mese si porterebbe dietro un'ora di
quello prima. Le medie non sono pesate esplicitamente perché le ore ERA5 durano
tutte uguale — la media semplice *è già* pesata sulla durata (2026-07-30).

### L'interrogazione in linguaggio naturale

**Il modello propone l'SQL, la dashboard lo esegue solo su conferma.** Scartate
le due alternative. *Query predefinite con l'LLM che si limita a narrare*:
sicuro ma risponde solo alle domande già previste, e il punto di avere 76 anni
di dati è farci le domande che non si erano previste. *Text-to-SQL diretto*:
una query sbagliata non dà un errore, dà **un numero plausibile e falso** — lo
stesso difetto che il 2026-07-31 aveva già portato a vietare al riassunto AI di
inventare. Mostrare la query, lasciarla correggere e chiedere conferma costa un
clic e rende l'errore visibile prima che diventi una risposta.

**Sola lettura, tre difese sovrapposte:** `mode=ro` nell'URI, `PRAGMA
query_only`, e il database delle osservazioni allegato anch'esso in `mode=ro`.
Verificato che un `CREATE TABLE` sull'allegato fallisce con *attempt to write a
readonly database*. In più la query viene rifiutata **prima** di partire se non
comincia per `SELECT`/`WITH`, se contiene più istruzioni o parole chiave di
scrittura: le difese di SQLite basterebbero, ma darebbero un errore oscuro a
metà esecuzione invece di un motivo leggibile.

**Il tetto di 2000 righe si applica leggendo il cursore, non riscrivendo
l'SQL.** Aggiungere un `LIMIT` alla query di qualcun altro ne cambia il senso
senza dirlo. E un `progress handler` la interrompe dopo 15 secondi, perché una
scansione delle 671.000 ore senza indice bloccherebbe la pagina.

**⚠️ Misurato, non supposto: senza esempi svolti nel prompt il modello da 9B
sbaglia sistematicamente.** Due proposte su due non eseguibili — un `ORDER BY`
prima di `UNION ALL`, e `AVG(SUM(...))` che SQLite rifiuta. Con tre esempi nel
prompt (anno più caldo, media annua di pioggia con `WITH`, ciclo mensile),
due su due corrette, e i numeri **coincidono con quelli delle tessere**,
calcolati da un percorso di codice indipendente: 1124,66 mm/anno contro
1125 mm/anno, 1950 a 13,54 °C in entrambi. Serve anche dire al modello quali
anni sono completi: senza, calcolava la media annua includendo l'anno tronco.
**Prezzo:** il prompt contiene anni concreti (1950-1960) che vanno letti come
esempi, e l'elenco degli anni completi va rigenerato a ogni import.

**Fallback:** se Ollama non risponde la casella dell'SQL resta scrivibile a
mano e i grafici non se ne accorgono. Vale qui la regola del riassunto AI: la
narrazione è un ornamento, non può portarsi via lo strumento.

### La libreria di ricette: il modello sceglie, non scrive

**Gli esempi nel prompt non sono bastati.** Alla prima domanda vera — «nel 1960
quanti giorni con massima ≥ 35 gradi?» — il modello ha prodotto una funzione
finestra dentro il `WHERE`, che SQLite rifiuta (*misuse of window function
MAX()*). Terzo fallimento su una domanda che un utente pone davvero: il
few-shot alza la percentuale di successo, non cambia il fatto che generare SQL
sia il compito sbagliato per un 9B.

**Da qui `era5_queries.py`: 23 ricette scritte e verificate a mano.** Il
modello non scrive più SQL, **sceglie** un identificativo dall'elenco e riempie
due campi numerici — un compito di un altro ordine di difficoltà. L'unico
errore che gli resta possibile è scegliere la ricetta sbagliata, e si vede,
perché il titolo scelto è scritto a schermo prima di eseguire. I parametri sono
sempre *named parameters* legati da SQLite: il modello riempie valori, mai
frammenti di SQL. Misurato dopo il cambio: le quattro domande di prova — giorni
sopra soglia in un anno, medie delle minime di un mese, conteggi per decennio,
periodo asciutto più lungo — tutte corrette, con i parametri estratti giusti
(anche «febbraio 1956» → mese 2, e i 29 giorni dell'anno bisestile).

**L'SQL libero resta**, in una modalità a parte: la libreria copre le domande
prevedibili, e il punto di avere 76 anni di dati è anche fare quelle che non si
erano previste. Ma non è più la strada principale.

**Le query stanno in un modulo separato** e non in `dashboard.py` per poterle
eseguire tutte in un test senza tirarsi dietro Streamlit — cosa che ha trovato
subito il difetto del denominatore qui sotto.

**⚠️ Scoperto facendolo, due volte.** *Primo:* nelle ricette per decennio la
soglia stava nel `WHERE`, quindi filtrava **prima** del raggruppamento e la
colonna «anni coperti» contava solo gli anni con almeno un giorno oltre soglia
— il decennio 1950 risultava di 5 anni. Spostata in `FILTER`, il denominatore
torna onesto (10 anni nel 1950, 2 nel 1960 ancora in corso). *Secondo, peggiore:*
la chiave del widget di un parametro era il solo nome, così `soglia` si
trascinava da una ricetta all'altra. Passando da «giorni con massima ≥ 30 °C» a
«periodo asciutto più lungo» la soglia restava 30, ma lì si misura in
millimetri: risultato, 161 giorni consecutivi di siccità in mezzo a 60 giorni
di pioggia. Nessuno dei due numeri è assurdo di per sé, ed è proprio questo che
lo rendeva invisibile. La chiave ora contiene l'identificativo della ricetta.

### «Le 10 temperature più alte» sono due pomeriggi, non dieci giorni

Domanda posta davvero: *media delle 10 temperature più alte per anno*. Il
modello locale ha prodotto una CTE che seleziona anno e numero di riga ma
**non** `temperature_c`, e poi la cerca fuori: `no such column`. Quarto modo
diverso di sbagliare la stessa cosa, e conferma che l'SQL nuovo è il compito da
lasciare a un modello più capace o a una ricetta.

**Ma il difetto interessante è nella domanda, non nella query.** Su dati orari
le dieci temperature più alte di un anno cadono quasi tutte nello stesso
pomeriggio: misurato, nel 1952 stanno in **due sole giornate**, nel 1950 in
quattro. Quel numero descrive l'intensità di un picco, non i dieci giorni più
caldi dell'anno — che è quasi sempre ciò che si intende chiedendolo.

Quindi **due ricette invece di una**: `media_ore_piu_calde_anno`, che risponde
alla lettera e porta in tabella una colonna `giornate_distinte` perché
l'ambiguità si veda nel risultato invece di doverla sospettare; e
`media_giorni_piu_caldi_anno`, che classifica le **massime giornaliere** e
quindi usa dieci giorni distinti. Sul 1952: 33,81 °C la prima, 32,87 °C la
seconda. Verificato che il modello le distingue — «le 10 temperature più alte»
sceglie la prima, «i 10 giorni più caldi» la seconda.

La libreria sale a **25 ricette**.

### I risultati si possono guardare come grafico, e le unità non si mescolano

Richiesta: «mostra il **grafico** delle precipitazioni di novembre 1966».
Mancava il pezzo a monte, non il disegno: **nessuna ricetta restituiva una
serie**, erano tutte aggregati, e un grafico vuole una riga per punto. Da qui
`andamento_giornaliero_mese` (una riga per giorno, con minima/media/massima e
pioggia) e `andamento_orario_giorno`. La libreria sale a **27 ricette**.

Il disegno è generico e vale per qualunque risultato, anche di una query
scritta a mano: si scelgono asse orizzontale e colonne, e la vista parte da
*Grafico* quando il risultato ha almeno tre righe e una colonna numerica —
una serie si guarda meglio disegnata, un conteggio no.

**⚠️ Il primo grafico era sbagliato, e in modo elegante.** Metteva le tre
temperature e la pioggia sullo stesso asse: gradi fra −20 e 35, millimetri fra
0 e 80. Leggibile a fatica e suggerisce confronti che non esistono. Ora
pioggia a barre sull'asse destro e temperature a linee su quello sinistro —
il meteogramma di sempre, che qui viene da sé perché i due gruppi si
riconoscono dal nome della colonna. La pioggia va **a barre** e non a linea per
una ragione sua: è una quantità caduta in un intervallo, e unire due giorni
piovosi con una linea direbbe che è piovuto anche nel mezzo.

Le percentuali (umidità) restano fuori dalla selezione iniziale quando c'è
dell'altro: uno 0-100 sullo stesso asse di temperature invernali le schiaccia
contro il fondo. Si aggiungono a mano, e da sole si disegnano benissimo.

**⚠️ E di nuovo il difetto delle chiavi appiccicate**, terza volta: scegliendo
la sola pioggia il grafico restava a linee, perché il tipo scelto prima
sopravviveva al cambio di selezione. La chiave del widget ora dipende dalla
famiglia di colonne. È lo stesso errore dei parametri delle ricette (soglia in
gradi che diventava soglia in millimetri): in Streamlit **una chiave di widget
è uno stato globale**, e va legata a tutto ciò da cui il valore dipende.

**Verifica storica gradita:** la serie giornaliera di novembre 1966 mostra
52 mm il giorno 3 e 78 mm il giorno 4. È l'alluvione del 1966, nel posto e nei
giorni giusti — una conferma che i dati sono quelli che dicono di essere.

### Il ricettario cresce: una query verificata si salva

**Una query scritta a mano e vista funzionare vale quanto una di serie**, e
riscriverla la volta dopo significa rischiare di risbagliarla. Da *SQL libero*
si salva con un titolo e una domanda d'esempio, e da quel momento è nella
libreria come le altre: compare nel menù e **il modello può sceglierla da sé**.
Verificato: salvata «Giorni caldi tra due anni», alla domanda «quanti giorni
sopra 30 gradi tra il 1950 e il 1955?» il modello ha scelto proprio quella.

**I parametri si leggono dall'SQL**, cercando i `:nome`, invece di farli
dichiarare a parte: così non possono andare fuori sincrono con la query che
devono riempire. I nomi noti alla libreria (`anno`, `mese`, `soglia`,
`limite`) portano con sé etichetta, tipo e intervallo giusti, e il
riconoscimento è per sottostringa — `:anno_fine` è un anno fra 1950 e 2026, non
un decimale generico con default 0.

**⚠️ Scoperto facendolo:** in *SQL libero* una query con parametri non era
eseguibile — mancavano i valori da legare — e quindi non era **verificabile**,
che è l'unica condizione a cui ha senso salvarla. Da qui i campi dei parametri
anche lì. Il difetto non si vedeva finché la modalità serviva solo a eseguire
query con valori scritti dentro.

**Il file sta fuori dal versionamento** (`era5_ricette.json`, accanto al
database), come `stations.json` per la ragione del 2026-07-30: è contenuto di
questa installazione, non del progetto. Un file rovinato non porta via la
scheda — si legge quel che si può e si tira dritto con le ricette di serie.

### Via il «commenta il risultato»: era un ornamento senza funzione

Il bottone che faceva riscrivere la tabella in prosa **è stato tolto**. Le
risposte di questa scheda sono un numero o una manciata di righe — «0 giorni»,
«−7,59 °C» — e una parafrasi non aggiunge niente a un numero che si legge da
sé: allunga la pagina, costa una chiamata e introduce un punto in cui il
modello può sbagliare, dove prima non ce n'erano. Diverso dal riassunto AI
della scheda «Adesso» (2026-07-31), che riscrive **un report lungo** e lì il
guadagno c'è.

**Smentisce in parte la voce di stamattina**, che dava il commento per parte
della forma ibrida: la parte che conta è mostrare la query e chiedere conferma,
non far parlare il modello dopo.

### `gpt-5.6-luna` come seconda opzione, mai come ricaduta

Stessi nomi di variabili di brain42 — `LLM_EXTERNAL_BASE_URL`,
`LLM_EXTERNAL_MODEL`, `LLM_EXTERNAL_API_KEY` — e stesso dialetto
OpenAI-compatibile, così la configurazione è **una sola cosa da ricordare** per
due progetti invece di due convenzioni divergenti.

**Niente ricaduta automatica**, che è la regola già scritta in brain42
(2026-08-03) e qui vale identica: chi chiede l'esterno lo chiede perché il
locale non gli basta. Una dashboard che chiama da sola un'API a consumo quando
il modello di casa incespica fa crescere un conto che nessuno ha deciso. Il
selettore è a mano; quando il locale non trova nessuna ricetta, l'avviso
*ricorda* che luna esiste, non ci passa sopra da solo.

**⚠️ Corretto in giornata: luna vive solo in «SQL libero».** All'inizio il
selettore del modello valeva per tutta la scheda. Ma la scelta della ricetta il
9B locale la azzecca, e il commento del risultato non esiste più: l'unico
compito rimasto in cui il locale sbaglia davvero è **scrivere SQL nuovo**, ed è
lì che il modello esterno serve. Un selettore dove non serve non è neutro,
suggerisce che l'esterno migliori qualcosa anche altrove.

**Lo schema vincolato resta** per la scelta della ricetta sull'esterno, se un
giorno tornerà a servire: `response_format: json_schema` con l'`enum` degli
identificativi generato dalla libreria — una ricetta inesistente non è proprio
rappresentabile, e i parametri non possono uscire come stringhe. È la
differenza tra validare una risposta e non poterla sbagliare. Sul locale resta
il parsing tollerante del JSON, perché lì lo schema non è garantito.
`reasoning_effort: "none"`, come in brain42: scegliere da un elenco è un lavoro
meccanico, e i livelli più alti si alzeranno **se e quando** un compito
sbaglierà per aver pensato troppo poco.

**Provato senza chiave**, puntando `LLM_EXTERNAL_BASE_URL` all'endpoint
OpenAI-compatibile di Ollama (`http://localhost:11434/v1`): lo stesso codice —
`/chat/completions`, schema vincolato, `reasoning_effort` — sceglie la ricetta
ed esegue. Il percorso è verificato; quel che resta da misurare sull'endpoint
vero è solo la qualità delle scelte, non il trasporto.

**Il servizio launchd non eredita l'ambiente della shell**: le tre variabili
vanno nel plist, e dopo averlo toccato serve `bootout` + `bootstrap`, non
`kickstart`. Sta in CLAUDE.md, con il resto di ciò che serve sotto mano.

**Approssimazione accettata, e dichiarata a schermo.** Le massime e minime
giornaliere sono ricavate dai campioni orari, e ogni valore è la media di una
cella di circa 11 × 8 km: gli estremi risultano **più smorzati** di quelli di
un termometro. In tutto l'archivio 1950-1961 non c'è un solo giorno a 35 °C, e
non significa che non abbia mai fatto così caldo. Contare i giorni oltre una
soglia su ERA5 non dà lo stesso numero che darebbe la stazione, e la scheda lo
dice sopra la libreria invece di lasciarlo scoprire. Il giorno si costruisce
solo dalle giornate con tutte e 24 le ore: il primo e l'ultimo dell'archivio
sono tronchi, e una massima calcolata su mezza giornata sarebbe più bassa del
vero senza dirlo.

**Il confronto con ARPAV non è ancora possibile e la scheda lo dice.** ERA5 è
arrivato al 1961, le osservazioni partono dal 2010: zero ore in comune, quindi
nessun grafico di scarto. Il messaggio si calcola dai dati, non è scritto a
mano, e sparirà da solo quando lo scaricamento avrà superato il 2010.

---

## 2026-08-11 — lo scaricamento ERA5 rallenta di sei volte, e il database separato regge alla prova

Primo storico scaricato sul serio: **35 blocchi su 232** (1950-01-01 →
1961-08-31) in 18 ore, zero errori CDS.

**La coda CDS degrada, e la stima iniziale era sbagliata di un ordine di
grandezza.** Il tempo per blocco misurato sui `mtime` dei file: 20 min all'inizio,
24 → 51 → 86 → 91 → **113 min** dopo diciotto ore. I file sono sempre da 1 MB e
scendono in pochi secondi: il tempo se ne va tutto tra `accepted` e l'inizio del
trasferimento, cioè in coda, e la coda si allunga man mano che si consuma la
quota dell'utente. Conseguenza pratica: **lo storico completo non sono 3 giorni
ma 6-15**, e la stima va fatta sul ritmo recente, mai sulla prima ora. Da qui la
scelta di un ciclo di retry che si arrende dopo **5 fallimenti consecutivi senza
progresso** invece di riprovare all'infinito: gli ultimi blocchi del 2026
falliranno comunque, perché ERA5-Land esce con mesi di ritardo sul tempo reale,
e un ciclo cieco girerebbe a vuoto per giorni.

**Interrompere un download non costa niente.** Una richiesta già `accepted` viene
elaborata lato CDS anche se il client muore: al rilancio lo stesso blocco arriva
in secondi invece che in ore. Interrompere per rilanciare con `python -u` — senza
il buffering che rende illeggibile un log lungo tre giorni — è stato gratis.

**La de-accumulazione della precipitazione a cavallo di due file funziona, ed è
verificata sui dati, non solo sulla carta.** Al confine `1950-04-30 23:00` →
`1950-05-01 00:00` l'accumulo `0,002 mm` del primo record del file nuovo è stato
confrontato con l'ora precedente **letta dal database**, dando `0,0 mm` invece
di un falso scroscio; all'01:00 si vede il reset del run. Sulle 102.263 ore
importate: **zero NULL** su temperatura, dew point, umidità e precipitazione,
nessun buco (righe = ore attese), nessun `dew > temp`, e nessuno scatto del
controllo sull'accumulo decrescente. Medie annue 12,8-13,5 °C e 880-1365 mm/anno,
plausibili per la pianura veneta.

**⚠️ Smentita una scelta, poi rimessa a posto.** I dati erano stati importati in
`arpav_meteo.sqlite` con l'argomento che «altrimenti ogni confronto diventa un
`ATTACH`» — cioè esattamente il costo che la voce del 2026-08-10 aveva già pesato
e accettato, deciso senza rileggerla. L'import è stato annullato (`DROP` delle tre
tabelle, senza `VACUUM`: 6 MB su 497 tornano nella freelist e li riusa lo
scraper) e rifatto su `era5_land.sqlite`. La scelta del database separato **resta
valida**; quello che serviva era leggere il memorandum prima di contraddirlo.
Costo del giro: 6 MB di freelist e un `DROP` su un DB di produzione.

**Misura di dimensione, ora che c'è un campione vero:** 102.263 ore occupano
**6,0 MB**, cioè ~58 byte/ora. Le 671.303 ore dello storico completo staranno in
**~40 MB** — un trentesimo del DB operativo, e un motivo in meno per rimpiangere
il file separato.

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
