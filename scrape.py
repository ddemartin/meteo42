from __future__ import annotations

import argparse
import csv
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API_URL = (
    "https://api.arpa.veneto.it/REST/v1/"
    "meteo_meteogrammi_tabella"
)

DEFAULT_CONFIG = Path("stations.json")
DEFAULT_DATABASE = Path("arpav_meteo.sqlite")
DEFAULT_CSV = Path("arpav_meteo.csv")
DEFAULT_RAW_DIRECTORY = Path("raw")

LOG = logging.getLogger("arpav_collector")


def create_session() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )

    session.mount("https://", HTTPAdapter(max_retries=retry))

    session.headers.update(
        {
            "User-Agent": "ARPAV-multi-station-archiver/1.0",
            "Accept": "application/json",
        }
    )

    return session


def load_stations(config_path: Path) -> list[dict[str, Any]]:
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}"
        )

    config = json.loads(config_path.read_text(encoding="utf-8"))
    stations = config.get("stations")

    if not isinstance(stations, list):
        raise ValueError(
            "The configuration file must contain a 'stations' list."
        )

    enabled_stations = []

    for station in stations:
        if not isinstance(station, dict):
            continue

        station_id = str(station.get("id", "")).strip()

        if not station_id:
            LOG.warning("Skipped station without id: %r", station)
            continue

        if not station.get("enabled", True):
            continue

        enabled_stations.append(
            {
                "id": station_id,
                "name": station.get("name"),
            }
        )

    if not enabled_stations:
        raise ValueError("No enabled stations found.")

    return enabled_stations


def download_station(
    session: requests.Session,
    station_id: str,
) -> dict[str, Any]:
    response = session.get(
        API_URL,
        params={
            "codseqst": station_id,

            # Cache-buster; not a date parameter.
            "_": int(time.time() * 1000),
        },
        timeout=(10, 60),
    )

    response.raise_for_status()

    try:
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise RuntimeError(
            f"Station {station_id}: invalid JSON response"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Station {station_id}: unexpected JSON structure"
        )

    if not isinstance(payload.get("data"), list):
        raise RuntimeError(
            f"Station {station_id}: missing 'data' list"
        )

    return payload


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS stations (
            station_id          TEXT PRIMARY KEY,
            configured_name     TEXT,
            api_name            TEXT,
            first_seen_at       TEXT NOT NULL,
            last_seen_at        TEXT NOT NULL,
            last_download_at    TEXT,
            last_record_at      TEXT,
            enabled             INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            station_id          TEXT NOT NULL,
            observation_at      TEXT NOT NULL,
            variable_type       TEXT NOT NULL,

            station_name        TEXT,
            value_text          TEXT,
            value_numeric       REAL,
            unit                TEXT,

            downloaded_at       TEXT NOT NULL,
            raw_json            TEXT NOT NULL,

            PRIMARY KEY (
                station_id,
                observation_at,
                variable_type
            ),

            FOREIGN KEY (station_id)
                REFERENCES stations(station_id)
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_observations_time
        ON observations(observation_at)
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_observations_station_time
        ON observations(station_id, observation_at)
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_observations_variable_time
        ON observations(variable_type, observation_at)
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS downloads (
            download_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id          TEXT NOT NULL,
            requested_at        TEXT NOT NULL,
            completed_at        TEXT,
            success             INTEGER NOT NULL,
            records_received    INTEGER,
            records_inserted    INTEGER,
            error_message       TEXT
        )
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS station_metadata (
            station_id          TEXT PRIMARY KEY,
            codice_stazione     INTEGER,
            nome_stazione       TEXT NOT NULL,
            latitudine          REAL,
            longitudine         REAL,
            quota               REAL,
            provincia           TEXT,
            gestore             TEXT,
            updated_at          TEXT NOT NULL
        )
        """
    )

    connection.commit()


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def extract_api_station_name(
    records: list[dict[str, Any]],
) -> str | None:
    for record in records:
        name = record.get("nome_stazione")

        if name:
            return str(name)

    return None


def update_station_registry(
    connection: sqlite3.Connection,
    station_id: str,
    configured_name: str | None,
    api_name: str | None,
    downloaded_at: str,
    last_record_at: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO stations (
            station_id,
            configured_name,
            api_name,
            first_seen_at,
            last_seen_at,
            last_download_at,
            last_record_at,
            enabled
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)

        ON CONFLICT(station_id) DO UPDATE SET
            configured_name = COALESCE(
                excluded.configured_name,
                stations.configured_name
            ),
            api_name = COALESCE(
                excluded.api_name,
                stations.api_name
            ),
            last_seen_at = excluded.last_seen_at,
            last_download_at = excluded.last_download_at,
            last_record_at = excluded.last_record_at,
            enabled = 1
        """,
        (
            station_id,
            configured_name,
            api_name,
            downloaded_at,
            downloaded_at,
            downloaded_at,
            last_record_at,
        ),
    )


def insert_observations(
    connection: sqlite3.Connection,
    station_id: str,
    configured_name: str | None,
    payload: dict[str, Any],
) -> tuple[int, int]:
    downloaded_at = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    records = payload["data"]
    inserted = 0
    valid_records = 0
    timestamps: list[str] = []

    api_name = extract_api_station_name(records)

    update_station_registry(
        connection=connection,
        station_id=station_id,
        configured_name=configured_name,
        api_name=api_name,
        downloaded_at=downloaded_at,
        last_record_at=None,
    )

    for record in records:
        if not isinstance(record, dict):
            continue

        observation_at = record.get("dataora")
        variable_type = record.get("tipo")

        if not observation_at or not variable_type:
            LOG.warning(
                "Station %s: skipped incomplete record: %r",
                station_id,
                record,
            )
            continue

        observation_at = str(observation_at)
        variable_type = str(variable_type)

        timestamps.append(observation_at)
        valid_records += 1

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO observations (
                station_id,
                observation_at,
                variable_type,
                station_name,
                value_text,
                value_numeric,
                unit,
                downloaded_at,
                raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                station_id,
                observation_at,
                variable_type,
                record.get("nome_stazione")
                or configured_name
                or api_name,
                None
                if record.get("valore") is None
                else str(record.get("valore")),
                to_float(record.get("valore")),
                record.get("unitnm"),
                downloaded_at,
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ),
        )

        if cursor.rowcount == 1:
            inserted += 1

    last_record_at = max(timestamps) if timestamps else None

    if last_record_at:
        connection.execute(
            """
            UPDATE stations
            SET last_record_at = ?
            WHERE station_id = ?
            """,
            (last_record_at, station_id),
        )

    connection.commit()

    return valid_records, inserted


def save_raw_json(
    station_id: str,
    payload: dict[str, Any],
    raw_directory: Path,
) -> None:
    raw_directory.mkdir(parents=True, exist_ok=True)

    latest_path = raw_directory / f"{station_id}_latest.json"
    temporary_path = raw_directory / f"{station_id}_latest.json.tmp"

    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    temporary_path.replace(latest_path)


def register_download_start(
    connection: sqlite3.Connection,
    station_id: str,
) -> tuple[int, str]:
    requested_at = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    cursor = connection.execute(
        """
        INSERT INTO downloads (
            station_id,
            requested_at,
            success
        )
        VALUES (?, ?, 0)
        """,
        (station_id, requested_at),
    )

    connection.commit()

    return int(cursor.lastrowid), requested_at


def register_download_success(
    connection: sqlite3.Connection,
    download_id: int,
    records_received: int,
    records_inserted: int,
) -> None:
    completed_at = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    connection.execute(
        """
        UPDATE downloads
        SET
            completed_at = ?,
            success = 1,
            records_received = ?,
            records_inserted = ?
        WHERE download_id = ?
        """,
        (
            completed_at,
            records_received,
            records_inserted,
            download_id,
        ),
    )

    connection.commit()


def register_download_failure(
    connection: sqlite3.Connection,
    download_id: int,
    error: Exception,
) -> None:
    completed_at = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    connection.execute(
        """
        UPDATE downloads
        SET
            completed_at = ?,
            success = 0,
            error_message = ?
        WHERE download_id = ?
        """,
        (
            completed_at,
            str(error),
            download_id,
        ),
    )

    connection.commit()


def export_csv(
    connection: sqlite3.Connection,
    destination: Path,
) -> None:
    rows = connection.execute(
        """
        SELECT
            o.station_id,
            COALESCE(
                o.station_name,
                s.api_name,
                s.configured_name
            ) AS station_name,
            o.observation_at,
            o.variable_type,
            o.value_numeric,
            o.value_text,
            o.unit,
            o.downloaded_at
        FROM observations AS o
        LEFT JOIN stations AS s
            ON s.station_id = o.station_id
        ORDER BY
            o.station_id,
            o.observation_at,
            o.variable_type
        """
    )

    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.writer(file, delimiter=";")

        writer.writerow(
            [
                "station_id",
                "station_name",
                "observation_at",
                "variable_type",
                "value_numeric",
                "value_text",
                "unit",
                "downloaded_at",
            ]
        )

        writer.writerows(rows)


def collect_all(
    config_path: Path,
    database_path: Path,
    csv_path: Path,
    raw_directory: Path,
    request_delay: float,
) -> None:
    stations = load_stations(config_path)
    session = create_session()

    database_path.parent.mkdir(parents=True, exist_ok=True)

    successes = 0
    failures = 0
    inserted_total = 0

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")

        initialize_database(connection)

        for index, station in enumerate(stations, start=1):
            station_id = station["id"]
            configured_name = station.get("name")

            LOG.info(
                "[%d/%d] Downloading station %s",
                index,
                len(stations),
                station_id,
            )

            download_id, _ = register_download_start(
                connection,
                station_id,
            )

            try:
                payload = download_station(
                    session=session,
                    station_id=station_id,
                )

                save_raw_json(
                    station_id=station_id,
                    payload=payload,
                    raw_directory=raw_directory,
                )

                received, inserted = insert_observations(
                    connection=connection,
                    station_id=station_id,
                    configured_name=configured_name,
                    payload=payload,
                )

                register_download_success(
                    connection=connection,
                    download_id=download_id,
                    records_received=received,
                    records_inserted=inserted,
                )

                LOG.info(
                    "Station %s: received %d, inserted %d",
                    station_id,
                    received,
                    inserted,
                )

                successes += 1
                inserted_total += inserted

            except Exception as exc:
                failures += 1

                register_download_failure(
                    connection=connection,
                    download_id=download_id,
                    error=exc,
                )

                LOG.exception(
                    "Station %s failed",
                    station_id,
                )

            if request_delay > 0 and index < len(stations):
                time.sleep(request_delay)

        export_csv(
            connection=connection,
            destination=csv_path,
        )

    LOG.info(
        "Completed: %d successful stations, %d failures, "
        "%d new observations",
        successes,
        failures,
        inserted_total,
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive data from multiple ARPAV stations."
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
    )

    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
    )

    parser.add_argument(
        "--raw-directory",
        type=Path,
        default=DEFAULT_RAW_DIRECTORY,
    )

    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.5,
        help="Delay between stations in seconds.",
    )

    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    args = parse_arguments()

    try:
        collect_all(
            config_path=args.config,
            database_path=args.database,
            csv_path=args.csv,
            raw_directory=args.raw_directory,
            request_delay=args.request_delay,
        )
    except Exception:
        LOG.exception("Collection failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())