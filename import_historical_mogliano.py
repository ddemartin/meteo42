from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

STATION_ID = "300000150"
STATION_NAME = "Mogliano Veneto"
DATABASE_PATH = Path("arpav_meteo.sqlite")
RAW_DIRECTORY = Path("raw")

RAW_FILES = sorted(RAW_DIRECTORY.glob("moglianoveneto_227_*.txt"))

# column_name -> (variable_type, unit, is_numeric, conversion_factor)
#
# RADSOL in the historical hourly bulletin is the average irradiance over the
# hour in W/m2, while the live scraper (meteo_meteogrammi_tabella API) reports
# RADSOL as an energy-equivalent in MJ/m2 per hour, sampled every 10 minutes.
# W/m2 -> MJ/m2/h is *3600/1e6 = *0.0036 (confirmed by comparing overlapping
# hours between the historical file and the live DB: e.g. 917 W/m2 historical
# vs. 3.308 MJ/m2 live at 2026-07-17T12:00, 917*0.0036 = 3.30).
RADSOL_WM2_TO_MJM2 = 0.0036

COLUMN_MAP = {
    "TEMP_MED": ("TARIA2M", "°C", True, 1.0),
    "PREC": ("PREC", "mm", True, 1.0),
    "UMID_MIN": ("UMID2M_MIN", "%", True, 1.0),
    "UMID_MAX": ("UMID2M_MAX", "%", True, 1.0),
    "RADSOL": ("RADSOL", "MJ/m2", True, RADSOL_WM2_TO_MJM2),
    "VVENTOMEDIO": ("VVENTO10M", "m/s", True, 1.0),
    "DVENTOPREV": ("DVENTO10M", "gradi", True, 1.0),
    "DVENTOPREV_SETTORE": ("DVENTOPREV_SETTORE", None, False, 1.0),
    "TSUOLO_0": ("TSUOLO", "°C", True, 1.0),
    "TSUOLO_10": ("TSUOLO-10", "°C", True, 1.0),
    "TSUOLO_20": ("TSUOLO-20", "°C", True, 1.0),
    "TSUOLO_30": ("TSUOLO-30", "°C", True, 1.0),
}


def to_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def parse_file(path: Path, downloaded_at: str) -> list[tuple]:
    rows: list[tuple] = []

    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, delimiter=";")

        for record in reader:
            timestamp = datetime(
                int(record["ANNO"]),
                int(record["MESE"]),
                int(record["GIORNO"]),
                int(record["ORA"]),
            )
            observation_at = timestamp.isoformat(timespec="seconds")

            for column, (
                variable_type,
                unit,
                is_numeric,
                conversion_factor,
            ) in COLUMN_MAP.items():
                raw_value = record[column]

                if is_numeric:
                    value_numeric = to_float(raw_value)
                    if value_numeric is not None and conversion_factor != 1.0:
                        value_numeric = round(
                            value_numeric * conversion_factor, 4
                        )
                    value_text = (
                        raw_value
                        if value_numeric is None or conversion_factor == 1.0
                        else str(value_numeric)
                    )
                else:
                    value_numeric = None
                    value_text = raw_value

                rows.append(
                    (
                        STATION_ID,
                        observation_at,
                        variable_type,
                        STATION_NAME,
                        value_text,
                        value_numeric,
                        unit,
                        downloaded_at,
                    )
                )

            # The historical bulletin only has hourly UMID_MIN/UMID_MAX, no
            # average. The live scraper reports an instant UMID2M reading, so
            # to make historical humidity usable in the same UMID2M charts
            # and overlays (e.g. heat index) we derive it as the midpoint of
            # min/max for that hour.
            umid_min = to_float(record["UMID_MIN"])
            umid_max = to_float(record["UMID_MAX"])
            if umid_min is not None and umid_max is not None:
                umid_avg = round((umid_min + umid_max) / 2, 1)
                rows.append(
                    (
                        STATION_ID,
                        observation_at,
                        "UMID2M",
                        STATION_NAME,
                        str(umid_avg),
                        umid_avg,
                        "%",
                        downloaded_at,
                    )
                )

    return rows


def main() -> None:
    downloaded_at = datetime.now().astimezone().isoformat(timespec="seconds")

    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute("PRAGMA foreign_keys = ON")

    total_rows = 0
    total_inserted = 0

    for path in RAW_FILES:
        rows = parse_file(path, downloaded_at)
        total_rows += len(rows)

        changes_before = connection.total_changes

        connection.executemany(
            """
            INSERT OR IGNORE INTO observations (
                station_id,
                observation_at,
                variable_type,
                station_name,
                value_text,
                value_numeric,
                unit,
                downloaded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

        inserted = connection.total_changes - changes_before
        total_inserted += inserted

        print(f"{path}: {len(rows)} candidate rows, {inserted} newly inserted")

    connection.commit()
    connection.close()

    print(f"Done. Candidate observation rows: {total_rows}, newly inserted: {total_inserted}")


if __name__ == "__main__":
    main()
