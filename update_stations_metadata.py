import os
import sqlite3
import requests
import logging
from datetime import datetime
from pathlib import Path

DATABASE_PATH = Path(
    os.environ.get("ARPAV_DATABASE_PATH", "arpav_meteo.sqlite")
)
API_URL = "https://api.arpa.veneto.it/REST/v1/meteo_meteogrammi"

LOG = logging.getLogger("meteo_metadata")


def fetch_stations_metadata() -> list[dict]:
    """Scarica i metadata delle stazioni dall'API MGRAMMI"""
    response = requests.get(
        API_URL,
        params={
            "rete": "MGRAMMI",
            "coordcd": 18,
            "orario": 0,
        },
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()

    if not data.get("success"):
        raise RuntimeError(
            f"API error: {data.get('error', 'Unknown error')}"
        )

    # Raggruppa per stazione (una per codseqst)
    stations = {}
    for record in data.get("data", []):
        codseqst = str(record.get("codseqst"))

        if codseqst not in stations:
            stations[codseqst] = {
                "station_id": codseqst,
                "codice_stazione": record.get("codice_stazione"),
                "nome_stazione": record.get("nome_stazione"),
                "latitudine": record.get("latitudine"),
                "longitudine": record.get("longitudine"),
                "quota": record.get("quota"),
                "provincia": record.get("provincia"),
                "gestore": record.get("gestore"),
            }

    return list(stations.values())


def update_database(stations: list[dict]) -> None:
    """Aggiorna la tabella station_metadata nel database"""
    conn = sqlite3.connect(DATABASE_PATH)
    updated_at = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    for station in stations:
        conn.execute(
            """
            INSERT OR REPLACE INTO station_metadata (
                station_id,
                codice_stazione,
                nome_stazione,
                latitudine,
                longitudine,
                quota,
                provincia,
                gestore,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                station["station_id"],
                station["codice_stazione"],
                station["nome_stazione"],
                station["latitudine"],
                station["longitudine"],
                station["quota"],
                station["provincia"],
                station["gestore"],
                updated_at,
            ),
        )

    conn.commit()
    conn.close()

    LOG.info(f"Updated {len(stations)} station metadata records")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    try:
        LOG.info("Fetching station metadata from MGRAMMI API...")
        stations = fetch_stations_metadata()
        LOG.info(f"Found {len(stations)} stations")

        update_database(stations)
        LOG.info("Database updated successfully")

    except Exception as exc:
        LOG.exception("Failed to update station metadata")
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
