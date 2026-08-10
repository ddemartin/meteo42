from __future__ import annotations

import argparse
import hashlib
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from era5_grib import iter_weather_fields


SCHEMA = """
CREATE TABLE IF NOT EXISTS grid_points (
    grid_point_id INTEGER PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    UNIQUE (latitude, longitude)
);

CREATE TABLE IF NOT EXISTS imports (
    import_id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL,
    first_valid_at_utc INTEGER NOT NULL,
    last_valid_at_utc INTEGER NOT NULL,
    message_count INTEGER NOT NULL,
    value_count INTEGER NOT NULL,
    imported_at_utc INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS weather_hourly (
    grid_point_id INTEGER NOT NULL,
    valid_at_utc INTEGER NOT NULL,
    temperature_c REAL,
    dewpoint_c REAL,
    relative_humidity_pct REAL,
    precipitation_accumulated_mm REAL,
    precipitation_mm REAL,
    import_id INTEGER NOT NULL,
    PRIMARY KEY (grid_point_id, valid_at_utc),
    FOREIGN KEY (grid_point_id) REFERENCES grid_points(grid_point_id),
    FOREIGN KEY (import_id) REFERENCES imports(import_id)
) WITHOUT ROWID;
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def discover_files(inputs: list[Path]) -> list[Path]:
    files = []
    for item in inputs:
        if item.is_dir():
            files.extend(sorted(item.rglob("*.grib")))
        elif item.is_file():
            files.append(item)
        else:
            raise SystemExit(f"file o directory inesistente: {item}")
    unique = {path.resolve(): path for path in files}
    return [unique[key] for key in sorted(unique)]


def connect_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.executescript(SCHEMA)
    weather_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(weather_hourly)")
    }
    if "precipitation_accumulated_mm" not in weather_columns:
        connection.execute(
            "ALTER TABLE weather_hourly "
            "ADD COLUMN precipitation_accumulated_mm REAL"
        )
    old_table = connection.execute(
        """
        SELECT 1 FROM sqlite_schema
        WHERE type = 'table' AND name = 'temperature_hourly'
        """
    ).fetchone()
    if old_table is not None:
        with connection:
            connection.execute(
                """
                INSERT INTO weather_hourly (
                    grid_point_id, valid_at_utc, temperature_c, import_id
                )
                SELECT grid_point_id, valid_at_utc, temperature_c, import_id
                FROM temperature_hourly
                WHERE 1
                ON CONFLICT (grid_point_id, valid_at_utc) DO UPDATE SET
                    temperature_c = excluded.temperature_c,
                    import_id = excluded.import_id
                """
            )
            connection.execute("DROP TABLE temperature_hourly")
    return connection


def load_file(path: Path) -> tuple[list, str]:
    fields = list(iter_weather_fields(path))
    if not fields:
        raise ValueError("il file non contiene messaggi GRIB")
    return fields, sha256_file(path)


def import_file(
    connection: sqlite3.Connection,
    path: Path,
    *,
    dry_run: bool = False,
) -> dict:
    fields, checksum = load_file(path)
    source_path = display_path(path)
    value_count = sum(len(field.values) for field in fields)
    if value_count == 0:
        raise ValueError(
            "il GRIB non contiene valori terrestri; la cella potrebbe essere "
            "mascherata come mare"
        )
    coordinates = sorted(
        {
            (value.latitude, value.longitude)
            for field in fields
            for value in field.values
        }
    )
    variables = sorted({field.variable for field in fields})
    summary = {
        "source_path": source_path,
        "sha256": checksum,
        "first_valid_at_utc": fields[0].valid_at_utc,
        "last_valid_at_utc": fields[-1].valid_at_utc,
        "message_count": len(fields),
        "hour_count": len({field.valid_at_utc for field in fields}),
        "value_count": value_count,
        "grid_point_count": len(coordinates),
        "variables": variables,
        "skipped": False,
    }
    if dry_run:
        return summary

    previous = connection.execute(
        "SELECT sha256 FROM imports WHERE source_path = ?", (source_path,)
    ).fetchone()
    if previous is not None and previous[0] == checksum:
        summary["skipped"] = True
        return summary

    with connection:
        connection.executemany(
            """
            INSERT INTO grid_points (latitude, longitude)
            VALUES (?, ?)
            ON CONFLICT (latitude, longitude) DO NOTHING
            """,
            coordinates,
        )
        grid_point_ids = {
            (latitude, longitude): grid_point_id
            for grid_point_id, latitude, longitude in connection.execute(
                "SELECT grid_point_id, latitude, longitude FROM grid_points"
            )
        }

        now = int(datetime.now(timezone.utc).timestamp())
        connection.execute(
            """
            INSERT INTO imports (
                source_path, sha256, first_valid_at_utc, last_valid_at_utc,
                message_count, value_count, imported_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_path) DO UPDATE SET
                sha256 = excluded.sha256,
                first_valid_at_utc = excluded.first_valid_at_utc,
                last_valid_at_utc = excluded.last_valid_at_utc,
                message_count = excluded.message_count,
                value_count = excluded.value_count,
                imported_at_utc = excluded.imported_at_utc
            """,
            (
                source_path,
                checksum,
                fields[0].valid_at_utc,
                fields[-1].valid_at_utc,
                len(fields),
                value_count,
                now,
            ),
        )
        import_id = connection.execute(
            "SELECT import_id FROM imports WHERE source_path = ?", (source_path,)
        ).fetchone()[0]
        connection.execute(
            "DELETE FROM weather_hourly WHERE import_id = ?", (import_id,)
        )
        weather = {}
        for field in fields:
            for value in field.values:
                key = (value.latitude, value.longitude, field.valid_at_utc)
                values = weather.setdefault(key, {})
                values[field.variable] = value.value
                if field.variable == "precipitation_mm":
                    values["precipitation_step"] = field.forecast_step

        rows = []
        previous_accumulation = {}
        for (latitude, longitude, timestamp), values in sorted(weather.items()):
            temperature = values.get("temperature_c")
            dewpoint = values.get("dewpoint_c")
            humidity = (
                relative_humidity(temperature, dewpoint)
                if temperature is not None and dewpoint is not None
                else None
            )
            accumulation = values.get("precipitation_mm")
            precipitation = None
            if accumulation is not None:
                step = values["precipitation_step"]
                coordinate = (latitude, longitude)
                if step == 1:
                    precipitation = accumulation
                else:
                    previous = previous_accumulation.get(coordinate)
                    if previous is None:
                        previous_row = connection.execute(
                            """
                            SELECT w.precipitation_accumulated_mm
                            FROM weather_hourly w
                            JOIN grid_points g USING (grid_point_id)
                            WHERE g.latitude = ? AND g.longitude = ?
                              AND w.valid_at_utc = ?
                            """,
                            (latitude, longitude, timestamp - 3600),
                        ).fetchone()
                        previous = previous_row[0] if previous_row else None
                    if previous is not None:
                        precipitation = accumulation - previous
                        if precipitation < -1e-4:
                            raise ValueError(
                                "accumulo di precipitazione decrescente senza "
                                f"reset a {timestamp}: {precipitation} mm"
                            )
                        precipitation = max(0.0, precipitation)
                previous_accumulation[coordinate] = accumulation
            rows.append(
                (
                    grid_point_ids[(latitude, longitude)],
                    timestamp,
                    temperature,
                    dewpoint,
                    humidity,
                    accumulation,
                    precipitation,
                    import_id,
                )
            )
        connection.executemany(
            """
            INSERT INTO weather_hourly (
                grid_point_id, valid_at_utc, temperature_c, dewpoint_c,
                relative_humidity_pct, precipitation_accumulated_mm,
                precipitation_mm, import_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (grid_point_id, valid_at_utc) DO UPDATE SET
                temperature_c = COALESCE(
                    excluded.temperature_c, weather_hourly.temperature_c
                ),
                dewpoint_c = COALESCE(
                    excluded.dewpoint_c, weather_hourly.dewpoint_c
                ),
                relative_humidity_pct = COALESCE(
                    excluded.relative_humidity_pct,
                    weather_hourly.relative_humidity_pct
                ),
                precipitation_accumulated_mm = COALESCE(
                    excluded.precipitation_accumulated_mm,
                    weather_hourly.precipitation_accumulated_mm
                ),
                precipitation_mm = COALESCE(
                    excluded.precipitation_mm, weather_hourly.precipitation_mm
                ),
                import_id = excluded.import_id
            """,
            rows,
        )
    return summary


def timestamp_text(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def relative_humidity(temperature_c: float, dewpoint_c: float) -> float:
    """Magnus formula, suitable for ordinary near-surface temperatures."""
    numerator = math.exp(17.625 * dewpoint_c / (243.04 + dewpoint_c))
    denominator = math.exp(17.625 * temperature_c / (243.04 + temperature_c))
    return min(100.0, max(0.0, 100.0 * numerator / denominator))


def print_summary(summary: dict, dry_run: bool) -> None:
    action = "DRY-RUN" if dry_run else "già importato" if summary["skipped"] else "importato"
    print(
        f"{action}: {summary['source_path']} | "
        f"{summary['hour_count']} ore, {summary['message_count']} messaggi, "
        f"{summary['value_count']} valori, "
        f"{summary['grid_point_count']} punti, "
        f"{','.join(summary['variables'])} | "
        f"{timestamp_text(summary['first_valid_at_utc'])} -> "
        f"{timestamp_text(summary['last_valid_at_utc'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida e importa file GRIB ERA5-Land in un database SQLite."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="file GRIB o directory")
    parser.add_argument(
        "--database", type=Path, default=Path("era5_land.sqlite")
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="valida senza modificare il database"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    files = discover_files(args.inputs)
    if not files:
        raise SystemExit("nessun file .grib trovato")

    connection = None if args.dry_run else connect_database(args.database)
    try:
        for path in files:
            summary = import_file(connection, path, dry_run=args.dry_run)
            print_summary(summary, args.dry_run)
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
