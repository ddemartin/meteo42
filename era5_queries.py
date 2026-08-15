"""Ricette SQL pronte per la rianalisi ERA5-Land.

Il modello locale non scrive SQL: **sceglie** una ricetta da questo elenco e ne
riempie i parametri. Un 9B che genera SQL libero sbaglia in modi che SQLite
rifiuta (funzioni finestra nel WHERE, `AVG(SUM(...))`) o — peggio — in modi che
SQLite accetta, restituendo un numero plausibile e falso. Scegliere fra venti
opzioni e compilare due campi è un compito di un altro ordine di difficoltà.

Le query stanno qui e non in `dashboard.py` per poterle eseguire tutte in un
test senza tirarsi dietro Streamlit.

I parametri sono **sempre** legati con named parameters, mai interpolati nella
stringa: il modello riempie valori, non frammenti di SQL.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path


# A mano come ITALIAN_WEEKDAYS in dashboard.py, e per lo stesso motivo: `%B`
# segue la locale del processo e il servizio launchd gira senza `LANG`.
ITALIAN_MONTHS_SHORT = (
    "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
    "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
)

ITALIAN_MONTHS = (
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
)

# ERA5 è orario e in UTC; tutto qui dentro ragiona in ora solare fissa UTC+1
# come il resto della dashboard.
LOCAL_OFFSET = "+ 3600"

# Il giorno si costruisce dalle ore e si tengono solo i giorni interi: il primo
# e l'ultimo giorno dell'archivio sono tronchi, e una massima giornaliera
# calcolata su mezza giornata sarebbe più bassa del vero senza dirlo.
DAILY_CTE = f"""\
WITH giorni AS (
    SELECT date(valid_at_utc {LOCAL_OFFSET}, 'unixepoch') AS giorno,
           MAX(temperature_c)    AS tmax,
           MIN(temperature_c)    AS tmin,
           AVG(temperature_c)    AS tmedia,
           AVG(relative_humidity_pct) AS umidita,
           SUM(precipitation_mm) AS mm,
           COUNT(*)              AS ore
    FROM weather_hourly
    GROUP BY giorno
    HAVING ore = 24
)"""

# Un anno "completo" ha tutte le sue ore meno le due che mancano al primo mese
# dell'archivio (la corsa di mezzanotte del 1950-01-01 non esiste, e lo scarto
# in ora locale ne sposta fuori un'altra). Serve perché durante lo scaricamento
# l'ultimo anno è tronco: mediarci sopra dà un anno caldissimo mai esistito.
COMPLETE_YEARS_CTE = f"""\
anni_completi AS (
    SELECT CAST(strftime('%Y', valid_at_utc {LOCAL_OFFSET}, 'unixepoch') AS INTEGER)
               AS anno,
           COUNT(*) AS ore
    FROM weather_hourly
    GROUP BY anno
    HAVING ore >= 8758
)"""


def _anno(default: int = 1960) -> dict:
    return {
        "nome": "anno",
        "etichetta": "Anno",
        "tipo": "intero",
        "default": default,
        "minimo": 1950,
        "massimo": 2026,
    }


def _mese(default: int = 7) -> dict:
    return {
        "nome": "mese",
        "etichetta": "Mese",
        "tipo": "mese",
        "default": default,
        "minimo": 1,
        "massimo": 12,
    }


def _giorno(default: int = 1) -> dict:
    return {
        "nome": "giorno",
        "etichetta": "Giorno",
        "tipo": "intero",
        "default": default,
        "minimo": 1,
        "massimo": 31,
    }


def _soglia(etichetta: str, default: float) -> dict:
    return {
        "nome": "soglia",
        "etichetta": etichetta,
        "tipo": "decimale",
        "default": default,
        "minimo": -40.0,
        "massimo": 50.0,
    }


def _limite(default: int = 10) -> dict:
    return {
        "nome": "limite",
        "etichetta": "Quante righe",
        "tipo": "intero",
        "default": default,
        "minimo": 1,
        "massimo": 100,
    }


QUERIES: list[dict] = [
    # --- temperatura: conteggi di giorni oltre una soglia -------------------
    {
        "id": "giorni_caldi_anno",
        "titolo": "Giorni con massima ≥ soglia, in un anno",
        "esempio": "Nel 1960 quanti giorni hanno avuto massima ≥ 30 °C?",
        "parametri": [_anno(), _soglia("Soglia della massima (°C)", 30.0)],
        "sql": f"""{DAILY_CTE}
SELECT COUNT(*) AS giorni
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
  AND tmax >= :soglia""",
    },
    {
        "id": "giorni_freddi_anno",
        "titolo": "Giorni con minima ≤ soglia (gelo), in un anno",
        "esempio": "Quanti giorni di gelo ci sono stati nel 1956?",
        "parametri": [_anno(1956), _soglia("Soglia della minima (°C)", 0.0)],
        "sql": f"""{DAILY_CTE}
SELECT COUNT(*) AS giorni
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
  AND tmin <= :soglia""",
    },
    {
        "id": "giorni_caldi_decennio",
        "titolo": "Giorni con massima ≥ soglia, per decennio",
        "esempio": "Quanti giorni sopra i 30 °C ci sono stati nei vari decenni?",
        "parametri": [_soglia("Soglia della massima (°C)", 30.0)],
        # La soglia sta in FILTER e non in WHERE: filtrando prima del
        # raggruppamento, un decennio senza nemmeno un giorno sopra soglia
        # sparirebbe dalla tabella, e «anni coperti» conterebbe solo gli anni
        # che un giorno caldo ce l'hanno — un denominatore falso proprio nel
        # confronto fra decenni, dove il decennio in corso ha meno anni.
        "sql": f"""{DAILY_CTE}
SELECT (CAST(strftime('%Y', giorno) AS INTEGER) / 10) * 10 AS decennio,
       COUNT(*) FILTER (WHERE tmax >= :soglia) AS giorni,
       COUNT(DISTINCT strftime('%Y', giorno)) AS anni_coperti
FROM giorni
GROUP BY decennio
ORDER BY decennio""",
    },
    {
        "id": "giorni_freddi_decennio",
        "titolo": "Giorni con minima ≤ soglia, per decennio",
        "esempio": "Come cambiano i giorni di gelo tra un decennio e l'altro?",
        "parametri": [_soglia("Soglia della minima (°C)", 0.0)],
        "sql": f"""{DAILY_CTE}
SELECT (CAST(strftime('%Y', giorno) AS INTEGER) / 10) * 10 AS decennio,
       COUNT(*) FILTER (WHERE tmin <= :soglia) AS giorni,
       COUNT(DISTINCT strftime('%Y', giorno)) AS anni_coperti
FROM giorni
GROUP BY decennio
ORDER BY decennio""",
    },
    {
        "id": "notti_tropicali_anno",
        "titolo": "Notti tropicali (minima ≥ soglia), in un anno",
        "esempio": "Quante notti tropicali nel 1959?",
        "parametri": [_anno(1959), _soglia("Soglia della minima (°C)", 20.0)],
        "sql": f"""{DAILY_CTE}
SELECT COUNT(*) AS notti
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
  AND tmin >= :soglia""",
    },
    # --- gli stessi conteggi, ma anno per anno su tutto l'archivio ----------
    # Sei ricette e non una con la colonna a scelta: il modello riempie
    # valori, mai frammenti di SQL, quindi né la colonna (`tmax`/`tmin`/
    # `tmedia`) né il verso del confronto possono essere parametri. Scegliere
    # fra sei titoli espliciti è per lui più facile che comporre la query
    # giusta, ed è il motivo per cui questo file esiste.
    #
    # Il conteggio sta in FILTER e non in WHERE per la ragione già vista sui
    # decenni: filtrando prima del raggruppamento, un anno senza nemmeno un
    # giorno oltre soglia sparirebbe invece di valere zero — e in una serie
    # nel tempo un anno mancante si legge come una linea che salta, cioè come
    # un dato che non c'è, non come lo zero che è.
    #
    # Solo anni completi: l'ultimo anno dell'archivio è tronco finché lo
    # scaricamento non l'ha finito, e un conteggio su mezzo anno crolla senza
    # dirlo, che su una serie di conteggi è il difetto peggiore possibile.
    {
        "id": "giorni_massima_sopra_per_anno",
        "titolo": "Giorni con massima ≥ soglia, anno per anno",
        "esempio": "Come cambiano negli anni i giorni con massima ≥ 30 °C?",
        "parametri": [_soglia("Soglia della massima (°C)", 30.0)],
        "sql": f"""{DAILY_CTE},
{COMPLETE_YEARS_CTE}
SELECT CAST(strftime('%Y', giorno) AS INTEGER) AS anno,
       COUNT(*) FILTER (WHERE tmax >= :soglia) AS giorni
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER)
      IN (SELECT anno FROM anni_completi)
GROUP BY anno
ORDER BY anno""",
    },
    {
        "id": "giorni_massima_sotto_per_anno",
        "titolo": "Giorni con massima ≤ soglia (di ghiaccio), anno per anno",
        "esempio": "Quanti giorni di ghiaccio, con la massima sotto zero, ogni anno?",
        "parametri": [_soglia("Soglia della massima (°C)", 0.0)],
        "sql": f"""{DAILY_CTE},
{COMPLETE_YEARS_CTE}
SELECT CAST(strftime('%Y', giorno) AS INTEGER) AS anno,
       COUNT(*) FILTER (WHERE tmax <= :soglia) AS giorni
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER)
      IN (SELECT anno FROM anni_completi)
GROUP BY anno
ORDER BY anno""",
    },
    {
        "id": "giorni_minima_sopra_per_anno",
        "titolo": "Notti con minima ≥ soglia (tropicali), anno per anno",
        "esempio": "Le notti tropicali sono aumentate nel tempo?",
        "parametri": [_soglia("Soglia della minima (°C)", 20.0)],
        "sql": f"""{DAILY_CTE},
{COMPLETE_YEARS_CTE}
SELECT CAST(strftime('%Y', giorno) AS INTEGER) AS anno,
       COUNT(*) FILTER (WHERE tmin >= :soglia) AS notti
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER)
      IN (SELECT anno FROM anni_completi)
GROUP BY anno
ORDER BY anno""",
    },
    {
        "id": "giorni_minima_sotto_per_anno",
        "titolo": "Giorni con minima ≤ soglia (gelo), anno per anno",
        "esempio": "I giorni di gelo sono diminuiti dal 1950 a oggi?",
        "parametri": [_soglia("Soglia della minima (°C)", 0.0)],
        "sql": f"""{DAILY_CTE},
{COMPLETE_YEARS_CTE}
SELECT CAST(strftime('%Y', giorno) AS INTEGER) AS anno,
       COUNT(*) FILTER (WHERE tmin <= :soglia) AS giorni
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER)
      IN (SELECT anno FROM anni_completi)
GROUP BY anno
ORDER BY anno""",
    },
    {
        "id": "giorni_media_sopra_per_anno",
        "titolo": "Giorni con media giornaliera ≥ soglia, anno per anno",
        "esempio": "Quanti giorni all'anno hanno una media di almeno 25 °C?",
        "parametri": [_soglia("Soglia della media (°C)", 25.0)],
        "sql": f"""{DAILY_CTE},
{COMPLETE_YEARS_CTE}
SELECT CAST(strftime('%Y', giorno) AS INTEGER) AS anno,
       COUNT(*) FILTER (WHERE tmedia >= :soglia) AS giorni
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER)
      IN (SELECT anno FROM anni_completi)
GROUP BY anno
ORDER BY anno""",
    },
    {
        "id": "giorni_media_sotto_per_anno",
        "titolo": "Giorni con media giornaliera ≤ soglia, anno per anno",
        "esempio": "Quanti giorni all'anno restano in media sotto zero?",
        "parametri": [_soglia("Soglia della media (°C)", 0.0)],
        "sql": f"""{DAILY_CTE},
{COMPLETE_YEARS_CTE}
SELECT CAST(strftime('%Y', giorno) AS INTEGER) AS anno,
       COUNT(*) FILTER (WHERE tmedia <= :soglia) AS giorni
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER)
      IN (SELECT anno FROM anni_completi)
GROUP BY anno
ORDER BY anno""",
    },
    # --- temperatura: medie -------------------------------------------------
    {
        "id": "media_massime_mese",
        "titolo": "Media delle massime di un mese, in un anno",
        "esempio": "Qual è stata la media delle massime di luglio 1960?",
        "parametri": [_anno(), _mese()],
        "sql": f"""{DAILY_CTE}
SELECT ROUND(AVG(tmax), 2) AS media_massime,
       ROUND(MAX(tmax), 2) AS massima_del_mese,
       COUNT(*) AS giorni
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
  AND CAST(strftime('%m', giorno) AS INTEGER) = :mese""",
    },
    {
        "id": "media_minime_mese",
        "titolo": "Media delle minime di un mese, in un anno",
        "esempio": "Qual è stata la media delle minime di gennaio 1956?",
        "parametri": [_anno(1956), _mese(1)],
        "sql": f"""{DAILY_CTE}
SELECT ROUND(AVG(tmin), 2) AS media_minime,
       ROUND(MIN(tmin), 2) AS minima_del_mese,
       COUNT(*) AS giorni
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
  AND CAST(strftime('%m', giorno) AS INTEGER) = :mese""",
    },
    {
        "id": "andamento_giornaliero_mese",
        "titolo": "Andamento giorno per giorno di un mese",
        "esempio": "Mostra il grafico delle precipitazioni di novembre 1966",
        "parametri": [_anno(1966), _mese(11)],
        # Una riga per giorno, non un aggregato: è la forma che serve per
        # disegnare un grafico, e nessuna delle altre ricette la produce.
        "sql": f"""{DAILY_CTE}
SELECT giorno,
       ROUND(tmin, 2)    AS minima,
       ROUND(tmedia, 2)  AS media,
       ROUND(tmax, 2)    AS massima,
       ROUND(mm, 1)      AS pioggia_mm
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
  AND CAST(strftime('%m', giorno) AS INTEGER) = :mese
ORDER BY giorno""",
    },
    {
        "id": "andamento_orario_giorno",
        "titolo": "Andamento ora per ora di un giorno",
        "esempio": "Come è andata la temperatura ora per ora il 17 febbraio 1956?",
        "parametri": [_anno(1956), _mese(2), _giorno(17)],
        "sql": """SELECT strftime('%H:%M', valid_at_utc + 3600, 'unixepoch') AS ora,
       ROUND(temperature_c, 2)          AS temperatura,
       ROUND(dewpoint_c, 2)             AS dew_point,
       ROUND(relative_humidity_pct, 1)  AS umidita_pct,
       ROUND(precipitation_mm, 2)       AS pioggia_mm
FROM weather_hourly
WHERE date(valid_at_utc + 3600, 'unixepoch') =
      printf('%04d-%02d-%02d', :anno, :mese, :giorno)
ORDER BY valid_at_utc""",
    },
    {
        "id": "medie_mensili_anno",
        "titolo": "Medie di tutti i mesi di un anno",
        "esempio": "Com'è andato il 1960, mese per mese?",
        "parametri": [_anno()],
        "sql": f"""{DAILY_CTE}
SELECT CAST(strftime('%m', giorno) AS INTEGER) AS mese,
       ROUND(AVG(tmedia), 2) AS media,
       ROUND(AVG(tmin), 2)   AS media_minime,
       ROUND(AVG(tmax), 2)   AS media_massime,
       ROUND(SUM(mm), 1)     AS pioggia_mm
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
GROUP BY mese
ORDER BY mese""",
    },
    {
        "id": "stesso_mese_tra_anni",
        "titolo": "Lo stesso mese confrontato in tutti gli anni",
        "esempio": "Tutti i mesi di luglio a confronto: quale il più caldo?",
        "parametri": [_mese(), _limite(15)],
        "sql": f"""{DAILY_CTE}
SELECT CAST(strftime('%Y', giorno) AS INTEGER) AS anno,
       ROUND(AVG(tmedia), 2) AS media,
       ROUND(AVG(tmax), 2)   AS media_massime,
       ROUND(SUM(mm), 1)     AS pioggia_mm
FROM giorni
WHERE CAST(strftime('%m', giorno) AS INTEGER) = :mese
GROUP BY anno
ORDER BY media DESC
LIMIT :limite""",
    },
    {
        "id": "escursione_mensile_anno",
        "titolo": "Escursione termica media, mese per mese",
        "esempio": "In quale mese del 1960 l'escursione giorno-notte era maggiore?",
        "parametri": [_anno()],
        "sql": f"""{DAILY_CTE}
SELECT CAST(strftime('%m', giorno) AS INTEGER) AS mese,
       ROUND(AVG(tmax - tmin), 2) AS escursione_media
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
GROUP BY mese
ORDER BY mese""",
    },
    # --- classifiche fra anni (solo anni completi) --------------------------
    {
        "id": "anni_piu_caldi",
        "titolo": "Classifica degli anni più caldi",
        "esempio": "Quali sono stati gli anni più caldi?",
        "parametri": [_limite()],
        "sql": f"""WITH {COMPLETE_YEARS_CTE}
SELECT CAST(strftime('%Y', valid_at_utc {LOCAL_OFFSET}, 'unixepoch') AS INTEGER)
           AS anno,
       ROUND(AVG(temperature_c), 2) AS media
FROM weather_hourly
WHERE anno IN (SELECT anno FROM anni_completi)
GROUP BY anno
ORDER BY media DESC
LIMIT :limite""",
    },
    {
        "id": "anni_piu_freddi",
        "titolo": "Classifica degli anni più freddi",
        "esempio": "Quali sono stati gli anni più freddi?",
        "parametri": [_limite()],
        "sql": f"""WITH {COMPLETE_YEARS_CTE}
SELECT CAST(strftime('%Y', valid_at_utc {LOCAL_OFFSET}, 'unixepoch') AS INTEGER)
           AS anno,
       ROUND(AVG(temperature_c), 2) AS media
FROM weather_hourly
WHERE anno IN (SELECT anno FROM anni_completi)
GROUP BY anno
ORDER BY media ASC
LIMIT :limite""",
    },
    {
        "id": "media_per_decennio",
        "titolo": "Temperatura media e pioggia per decennio",
        "esempio": "Come cambia la media da un decennio all'altro?",
        "parametri": [],
        "sql": f"""WITH {COMPLETE_YEARS_CTE},
per_anno AS (
    SELECT CAST(strftime('%Y', valid_at_utc {LOCAL_OFFSET}, 'unixepoch') AS INTEGER)
               AS anno,
           AVG(temperature_c)    AS media,
           SUM(precipitation_mm) AS mm
    FROM weather_hourly
    GROUP BY anno
)
SELECT (anno / 10) * 10 AS decennio,
       COUNT(*)                AS anni,
       ROUND(AVG(media), 2)    AS temperatura_media,
       ROUND(AVG(mm), 0)       AS pioggia_media_annua
FROM per_anno
WHERE anno IN (SELECT anno FROM anni_completi)
GROUP BY decennio
ORDER BY decennio""",
    },
    {
        "id": "climatologia_mese_decennio",
        "titolo": "Media di un mese, decennio per decennio",
        "esempio": "Il mese di gennaio si è scaldato tra i decenni?",
        "parametri": [_mese(1)],
        "sql": f"""{DAILY_CTE}
SELECT (CAST(strftime('%Y', giorno) AS INTEGER) / 10) * 10 AS decennio,
       ROUND(AVG(tmedia), 2) AS media,
       COUNT(DISTINCT strftime('%Y', giorno)) AS anni
FROM giorni
WHERE CAST(strftime('%m', giorno) AS INTEGER) = :mese
GROUP BY decennio
ORDER BY decennio""",
    },
    # --- estremi ------------------------------------------------------------
    {
        "id": "giorni_piu_caldi",
        "titolo": "I giorni più caldi dell'archivio",
        "esempio": "Qual è stato il giorno più caldo di sempre?",
        "parametri": [_limite()],
        "sql": f"""{DAILY_CTE}
SELECT giorno, ROUND(tmax, 2) AS massima, ROUND(tmin, 2) AS minima
FROM giorni
ORDER BY tmax DESC
LIMIT :limite""",
    },
    {
        "id": "giorni_piu_freddi",
        "titolo": "I giorni più freddi dell'archivio",
        "esempio": "Qual è stato il giorno più freddo di sempre?",
        "parametri": [_limite()],
        "sql": f"""{DAILY_CTE}
SELECT giorno, ROUND(tmin, 2) AS minima, ROUND(tmax, 2) AS massima
FROM giorni
ORDER BY tmin ASC
LIMIT :limite""",
    },
    {
        "id": "media_giorni_piu_caldi_anno",
        "titolo": "Media dei N giorni più caldi, anno per anno",
        "esempio": "Qual è la media dei 10 giorni più caldi di ogni anno?",
        "parametri": [_limite(10)],
        # La coda calda di ogni anno, misurata su giorni **distinti**: è la
        # domanda che di solito si intende con «le temperature più alte».
        "sql": f"""{DAILY_CTE},
classifica AS (
    SELECT CAST(strftime('%Y', giorno) AS INTEGER) AS anno, tmax,
           ROW_NUMBER() OVER (
               PARTITION BY strftime('%Y', giorno) ORDER BY tmax DESC
           ) AS posizione
    FROM giorni
)
SELECT anno,
       ROUND(AVG(tmax), 2) AS media_giorni_piu_caldi,
       COUNT(*) AS giorni_usati
FROM classifica
WHERE posizione <= :limite
GROUP BY anno
ORDER BY anno""",
    },
    {
        "id": "media_ore_piu_calde_anno",
        "titolo": "Media delle N ore più calde, anno per anno",
        "esempio": "Qual è la media delle 10 temperature orarie più alte per anno?",
        "parametri": [_limite(10)],
        # ⚠️ Le ore più calde di un anno cadono quasi tutte nello stesso
        # pomeriggio: nel 1952 le prime dieci stanno in **due sole giornate**.
        # Misura l'intensità del picco, non quanti giorni caldi ci sono stati.
        # Per quello serve la ricetta sui giorni, qui sopra. `giornate_distinte`
        # rende la cosa visibile invece di lasciarla supporre.
        "sql": """WITH classifica AS (
    SELECT CAST(strftime('%Y', valid_at_utc + 3600, 'unixepoch') AS INTEGER)
               AS anno,
           date(valid_at_utc + 3600, 'unixepoch') AS giorno,
           temperature_c,
           ROW_NUMBER() OVER (
               PARTITION BY strftime('%Y', valid_at_utc + 3600, 'unixepoch')
               ORDER BY temperature_c DESC
           ) AS posizione
    FROM weather_hourly
)
SELECT anno,
       ROUND(AVG(temperature_c), 2) AS media_ore_piu_calde,
       COUNT(DISTINCT giorno) AS giornate_distinte
FROM classifica
WHERE posizione <= :limite
GROUP BY anno
ORDER BY anno""",
    },
    {
        "id": "onda_calore_piu_lunga",
        "titolo": "La sequenza più lunga di giorni sopra soglia, in un anno",
        "esempio": "Qual è stata l'ondata di caldo più lunga del 1960?",
        "parametri": [_anno(), _soglia("Soglia della massima (°C)", 28.0)],
        # Gaps and islands: la differenza tra due numerazioni progressive resta
        # costante finché i giorni sopra soglia sono consecutivi, e cambia al
        # primo giorno sotto soglia. È il modo standard di trovare le sequenze
        # in SQL, senza cursori.
        "sql": f"""{DAILY_CTE},
caldi AS (
    SELECT giorno,
           ROW_NUMBER() OVER (ORDER BY giorno) -
           ROW_NUMBER() OVER (
               PARTITION BY CASE WHEN tmax >= :soglia THEN 1 ELSE 0 END
               ORDER BY giorno
           ) AS blocco,
           tmax
    FROM giorni
    WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
)
SELECT COUNT(*) AS giorni_consecutivi,
       MIN(giorno) AS inizio,
       MAX(giorno) AS fine,
       ROUND(MAX(tmax), 2) AS punta
FROM caldi
WHERE tmax >= :soglia
GROUP BY blocco
ORDER BY giorni_consecutivi DESC
LIMIT 1""",
    },
    # --- precipitazione -----------------------------------------------------
    {
        "id": "pioggia_per_anno",
        "titolo": "Pioggia totale, anno per anno",
        "esempio": "Quanta pioggia è caduta in ciascun anno?",
        "parametri": [_limite(20)],
        "sql": f"""WITH {COMPLETE_YEARS_CTE}
SELECT CAST(strftime('%Y', valid_at_utc {LOCAL_OFFSET}, 'unixepoch') AS INTEGER)
           AS anno,
       ROUND(SUM(precipitation_mm), 0) AS pioggia_mm
FROM weather_hourly
WHERE anno IN (SELECT anno FROM anni_completi)
GROUP BY anno
ORDER BY anno
LIMIT :limite""",
    },
    {
        "id": "giorni_piovosi_anno",
        "titolo": "Giorni di pioggia (≥ soglia mm), in un anno",
        "esempio": "Quanti giorni di pioggia nel 1960?",
        "parametri": [
            _anno(),
            {
                "nome": "soglia",
                "etichetta": "Soglia giornaliera (mm)",
                "tipo": "decimale",
                "default": 1.0,
                "minimo": 0.0,
                "massimo": 200.0,
            },
        ],
        "sql": f"""{DAILY_CTE}
SELECT COUNT(*) AS giorni_piovosi,
       ROUND(SUM(mm), 1) AS pioggia_totale_mm
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
  AND mm >= :soglia""",
    },
    {
        "id": "giorni_piu_piovosi",
        "titolo": "I giorni di pioggia più intensi dell'archivio",
        "esempio": "Qual è stato il giorno più piovoso?",
        "parametri": [_limite()],
        "sql": f"""{DAILY_CTE}
SELECT giorno, ROUND(mm, 1) AS pioggia_mm
FROM giorni
ORDER BY mm DESC
LIMIT :limite""",
    },
    {
        "id": "mesi_piu_piovosi_anno",
        "titolo": "Pioggia mese per mese, in un anno",
        "esempio": "Qual è stato il mese più piovoso del 1960?",
        "parametri": [_anno()],
        "sql": f"""{DAILY_CTE}
SELECT CAST(strftime('%m', giorno) AS INTEGER) AS mese,
       ROUND(SUM(mm), 1) AS pioggia_mm,
       COUNT(*) FILTER (WHERE mm >= 1.0) AS giorni_piovosi
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
GROUP BY mese
ORDER BY mese""",
    },
    {
        "id": "siccita_piu_lunga_anno",
        "titolo": "Il periodo asciutto più lungo, in un anno",
        "esempio": "Qual è stato il periodo senza pioggia più lungo del 1960?",
        "parametri": [
            _anno(),
            {
                "nome": "soglia",
                "etichetta": "Sotto quanti mm il giorno è asciutto",
                "tipo": "decimale",
                "default": 1.0,
                "minimo": 0.0,
                "massimo": 50.0,
            },
        ],
        "sql": f"""{DAILY_CTE},
asciutti AS (
    SELECT giorno, mm,
           ROW_NUMBER() OVER (ORDER BY giorno) -
           ROW_NUMBER() OVER (
               PARTITION BY CASE WHEN mm < :soglia THEN 1 ELSE 0 END
               ORDER BY giorno
           ) AS blocco
    FROM giorni
    WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
)
SELECT COUNT(*) AS giorni_consecutivi,
       MIN(giorno) AS inizio,
       MAX(giorno) AS fine
FROM asciutti
WHERE mm < :soglia
GROUP BY blocco
ORDER BY giorni_consecutivi DESC
LIMIT 1""",
    },
    # --- umidità ------------------------------------------------------------
    {
        "id": "umidita_mensile_anno",
        "titolo": "Umidità relativa media, mese per mese",
        "esempio": "Com'è l'umidità nei mesi del 1960?",
        "parametri": [_anno()],
        "sql": f"""{DAILY_CTE}
SELECT CAST(strftime('%m', giorno) AS INTEGER) AS mese,
       ROUND(AVG(umidita), 1) AS umidita_media_pct
FROM giorni
WHERE CAST(strftime('%Y', giorno) AS INTEGER) = :anno
GROUP BY mese
ORDER BY mese""",
    },
]

QUERIES_BY_ID = {ricetta["id"]: ricetta for ricetta in QUERIES}


# --- ricette aggiunte dall'utente -------------------------------------------
#
# Una query scritta a mano (o da un modello) e **verificata funzionante** vale
# quanto una di quelle scritte qui: si salva e diventa disponibile alle volte
# successive, anche per la scelta automatica. Il file sta accanto al database e
# fuori dal versionamento, come `stations.json` (MEMORANDUM 2026-07-30): è
# contenuto di questa installazione, non del progetto.
RICETTE_UTENTE_PATH = Path("era5_ricette.json")

# I nomi già noti alla libreria portano con sé etichetta, tipo e limiti giusti.
# Un nome nuovo diventa un decimale con un intervallo largo: meglio un campo
# generico che rifiutare la query.
_COSTRUTTORI_PARAMETRI = {
    "anno": lambda: _anno(),
    "mese": lambda: _mese(),
    "giorno": lambda: _giorno(),
    "soglia": lambda: _soglia("Soglia", 0.0),
    "limite": lambda: _limite(),
}


def parametri_da_sql(sql: str) -> list[dict]:
    """I parametri nominati `:nome` presenti nella query, nell'ordine d'uso.

    Si leggono dall'SQL invece di farli dichiarare a parte: così non possono
    andare fuori sincrono con la query che devono riempire.
    """
    visti: list[str] = []
    for nome in re.findall(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)", sql):
        if nome not in visti:
            visti.append(nome)
    parametri = []
    for nome in visti:
        # Prima il nome esatto, poi il nome contenuto: `:anno_fine` è un anno,
        # e trattarlo come decimale generico darebbe un campo con default 0 e
        # intervallo ±100000 dove serve un anno fra 1950 e 2026.
        costruttore = _COSTRUTTORI_PARAMETRI.get(nome) or next(
            (
                funzione
                for chiave, funzione in _COSTRUTTORI_PARAMETRI.items()
                if chiave in nome
            ),
            None,
        )
        if costruttore is not None:
            parametro = costruttore()
            parametro["nome"] = nome
            parametro["etichetta"] = nome.replace("_", " ").capitalize()
            parametri.append(parametro)
        else:
            parametri.append(
                {
                    "nome": nome,
                    "etichetta": nome.replace("_", " ").capitalize(),
                    "tipo": "decimale",
                    "default": 0.0,
                    "minimo": -100000.0,
                    "massimo": 100000.0,
                }
            )
    return parametri


def _identificativo(titolo: str, occupati: set[str]) -> str:
    base = unicodedata.normalize("NFKD", titolo).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower() or "ricetta"
    identificativo = base
    contatore = 2
    while identificativo in occupati:
        identificativo = f"{base}_{contatore}"
        contatore += 1
    return identificativo


def carica_ricette_utente(path: Path | None = None) -> list[dict]:
    """Le ricette salvate, o una lista vuota se il file manca o è illeggibile.

    Un file rovinato non deve portarsi via la scheda: le ricette di serie
    bastano a farla funzionare, quindi qui si tace e si prosegue.
    """
    percorso = path or RICETTE_UTENTE_PATH
    if not percorso.exists():
        return []
    try:
        contenuto = json.loads(percorso.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(contenuto, list):
        return []
    ricette = []
    for voce in contenuto:
        if not isinstance(voce, dict):
            continue
        if not {"id", "titolo", "sql"} <= voce.keys():
            continue
        ricette.append(
            {
                "id": voce["id"],
                "titolo": voce["titolo"],
                "esempio": voce.get("esempio", ""),
                "parametri": voce.get("parametri") or [],
                "sql": voce["sql"],
                "utente": True,
            }
        )
    return ricette


def salva_ricetta_utente(
    titolo: str,
    esempio: str,
    sql: str,
    path: Path | None = None,
) -> dict:
    """Aggiunge una ricetta al file dell'utente e la restituisce."""
    titolo = titolo.strip()
    if not titolo:
        raise ValueError("il titolo non può essere vuoto")
    percorso = path or RICETTE_UTENTE_PATH
    esistenti = carica_ricette_utente(percorso)
    occupati = {r["id"] for r in esistenti} | set(QUERIES_BY_ID)
    ricetta = {
        "id": _identificativo(titolo, occupati),
        "titolo": titolo,
        "esempio": esempio.strip(),
        "parametri": parametri_da_sql(sql),
        "sql": sql.strip(),
    }
    percorso.write_text(
        json.dumps(esistenti + [ricetta], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {**ricetta, "utente": True}


def elimina_ricetta_utente(identificativo: str, path: Path | None = None) -> bool:
    percorso = path or RICETTE_UTENTE_PATH
    esistenti = carica_ricette_utente(percorso)
    rimaste = [r for r in esistenti if r["id"] != identificativo]
    if len(rimaste) == len(esistenti):
        return False
    percorso.write_text(
        json.dumps(
            [
                {k: v for k, v in r.items() if k != "utente"}
                for r in rimaste
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return True


def tutte_le_ricette(path: Path | None = None) -> list[dict]:
    return QUERIES + carica_ricette_utente(path)


def catalogo_per_prompt(ricette: list[dict] | None = None) -> str:
    """L'elenco compatto che finisce nel prompt del modello."""
    righe = []
    for ricetta in ricette if ricette is not None else QUERIES:
        parametri = ", ".join(
            f"{parametro['nome']} ({parametro['tipo']})"
            for parametro in ricetta["parametri"]
        )
        righe.append(
            f"- {ricetta['id']}: {ricetta['titolo']}"
            + (f" | parametri: {parametri}" if parametri else " | nessun parametro")
            + f" | es. \"{ricetta['esempio']}\""
        )
    return "\n".join(righe)


def schema_scelta(ricette: list[dict] | None = None) -> dict:
    """Schema JSON per il decoding vincolato sull'endpoint esterno.

    Con l'`enum` degli identificativi il modello **non può** inventare una
    ricetta che non esiste, e i parametri non possono essere stringhe: è la
    differenza tra validare una risposta e non poterla sbagliare. I nomi si
    ricavano dalla libreria, così aggiungere una ricetta non richiede di
    ricordarsi di aggiornare anche questo.
    """
    elenco = ricette if ricette is not None else QUERIES
    nomi = sorted({p["nome"] for q in elenco for p in q["parametri"]})
    return {
        "type": "object",
        "properties": {
            "id": {
                "type": ["string", "null"],
                "enum": [q["id"] for q in elenco] + [None],
            },
            "parametri": {
                "type": "object",
                "properties": {
                    nome: {"type": ["number", "null"]} for nome in nomi
                },
                "required": nomi,
                "additionalProperties": False,
            },
        },
        "required": ["id", "parametri"],
        "additionalProperties": False,
    }


def normalizza_parametri(ricetta: dict, valori: dict) -> dict:
    """Converte e verifica i valori, o solleva ValueError con il motivo.

    I valori arrivano da un modello, quindi possono essere stringhe, mancanti o
    fuori scala: qui diventano numeri dentro i limiti, oppure non passano.
    """
    puliti = {}
    for parametro in ricetta["parametri"]:
        nome = parametro["nome"]
        if nome not in valori or valori[nome] is None:
            raise ValueError(f"manca il parametro «{nome}»")
        grezzo = valori[nome]
        try:
            if parametro["tipo"] == "decimale":
                valore = float(grezzo)
            else:
                valore = int(float(grezzo))
        except (TypeError, ValueError):
            raise ValueError(
                f"il parametro «{nome}» non è un numero: {grezzo!r}"
            ) from None
        if not parametro["minimo"] <= valore <= parametro["massimo"]:
            raise ValueError(
                f"il parametro «{nome}» vale {valore}, fuori dall'intervallo "
                f"{parametro['minimo']}–{parametro['massimo']}"
            )
        puliti[nome] = valore
    return puliti
