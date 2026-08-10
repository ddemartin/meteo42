from __future__ import annotations

import argparse
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from era5_grib import count_grib1_messages


DATASET = "reanalysis-era5-land"
VARIABLES = (
    "2m_temperature",
    "2m_dewpoint_temperature",
    "total_precipitation",
)
GRID_STEP = Decimal("0.1")
CELL_HALF_BOX = 0.04
# CDS prices a request by the number of fields it produces. With three
# variables, six months (about 13000 fields) is refused as "cost limits
# exceeded" while four months (about 8800) is accepted; four months is also an
# exact third of a year, so the blocks land on clean month boundaries. Must
# divide 12, otherwise a block would straddle two years.
CHUNK_MONTHS = 4
# ERA5-Land comes from forecasts started at 00 UTC, so the value valid at
# midnight belongs to the previous day's run. The first day of the dataset has
# no previous run, and CDS simply omits that hour for every variable.
DATASET_FIRST_DATE = date(1950, 1, 1)


@dataclass(frozen=True)
class DownloadChunk:
    start: date
    end: date

    @property
    def expected_hours(self) -> int:
        hours = (self.end - self.start).days * 24 + 24
        if self.start <= DATASET_FIRST_DATE <= self.end:
            hours -= 1
        return hours

    @property
    def expected_messages(self) -> int:
        return self.expected_hours * len(VARIABLES)

    @property
    def label(self) -> str:
        if self.start == date(self.start.year, 1, 1) and self.end == date(
            self.start.year, 12, 31
        ):
            return str(self.start.year)
        if (
            self.start.day == 1
            and self.end.year == self.start.year
            and self.end.month == self.start.month
            and self.end.day
            == calendar.monthrange(self.start.year, self.start.month)[1]
        ):
            return self.start.strftime("%Y-%m")
        return f"{self.start.isoformat()}_{self.end.isoformat()}"


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"data non valida: {value!r}; usa YYYY-MM-DD"
        ) from error


def snap_to_grid(value: float) -> float:
    return float(
        Decimal(str(value)).quantize(GRID_STEP, rounding=ROUND_HALF_UP)
    )


def coordinate_label(value: float, positive: str, negative: str) -> str:
    hemisphere = positive if value >= 0 else negative
    return f"{abs(value):07.3f}{hemisphere}"


def monthly_chunks(start: date, end: date) -> list[DownloadChunk]:
    chunks = []
    cursor = start
    while cursor <= end:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, last_day)
        chunk_end = min(month_end, end)
        chunks.append(DownloadChunk(cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def automatic_chunks(start: date, end: date) -> list[DownloadChunk]:
    """Use one request per block of CHUNK_MONTHS and months at the boundaries."""
    chunks = []
    cursor = start
    while cursor <= end:
        block_start = ((cursor.month - 1) // CHUNK_MONTHS) * CHUNK_MONTHS + 1
        block_last = block_start + CHUNK_MONTHS - 1
        block_end = date(
            cursor.year,
            block_last,
            calendar.monthrange(cursor.year, block_last)[1],
        )
        if cursor == date(cursor.year, block_start, 1) and block_end <= end:
            chunks.append(DownloadChunk(cursor, block_end))
            cursor = block_end + timedelta(days=1)
            continue

        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        month_end = date(cursor.year, cursor.month, last_day)
        chunk_end = min(month_end, end)
        chunks.append(DownloadChunk(cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def values_for_chunk(chunk: DownloadChunk) -> tuple[list[str], list[str]]:
    if chunk.start.year != chunk.end.year:
        raise ValueError("un chunk non può attraversare più anni")

    # A span of whole months is requested as a month list crossed with every
    # day number; CDS ignores the day numbers a month does not have.
    last_day = calendar.monthrange(chunk.end.year, chunk.end.month)[1]
    if chunk.start.day == 1 and chunk.end.day == last_day:
        months = [
            f"{month:02d}"
            for month in range(chunk.start.month, chunk.end.month + 1)
        ]
        return months, [f"{day:02d}" for day in range(1, 32)]

    if chunk.start.month != chunk.end.month:
        raise ValueError("un chunk parziale non può attraversare più mesi")
    return [f"{chunk.start.month:02d}"], [
        f"{day:02d}" for day in range(chunk.start.day, chunk.end.day + 1)
    ]


def build_request(chunk: DownloadChunk, latitude: float, longitude: float) -> dict:
    months, days = values_for_chunk(chunk)
    return {
        "variable": list(VARIABLES),
        "year": str(chunk.start.year),
        "month": months,
        "day": days,
        "time": [f"{hour:02d}:00" for hour in range(24)],
        "data_format": "grib",
        "download_format": "unarchived",
        # CDS rejects a zero-area bounding box. A box narrower than the 0.1°
        # grid spacing selects only the requested grid node.
        "area": [
            round(latitude + CELL_HALF_BOX, 4),
            round(longitude - CELL_HALF_BOX, 4),
            round(latitude - CELL_HALF_BOX, 4),
            round(longitude + CELL_HALF_BOX, 4),
        ],
    }


def output_path(
    output_directory: Path,
    latitude: float,
    longitude: float,
    chunk: DownloadChunk,
) -> Path:
    lat = coordinate_label(latitude, "N", "S")
    lon = coordinate_label(longitude, "E", "W")
    return output_directory / (
        f"era5_land_2t_2d_tp_{lat}_{lon}_{chunk.label}.grib"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scarica temperatura, dew point e precipitazione ERA5-Land di una "
            "cella, dividendo automaticamente lo storico in richieste riprendibili."
        )
    )
    parser.add_argument("--from", dest="start", required=True, type=parse_iso_date)
    parser.add_argument("--to", dest="end", required=True, type=parse_iso_date)
    parser.add_argument("--lat", required=True, type=float)
    parser.add_argument("--lon", required=True, type=float)
    parser.add_argument(
        "--output-directory", type=Path, default=Path("raw/era5-land")
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="dopo il download importa i dati nel database SQLite indicato",
    )
    parser.add_argument(
        "--chunk-size",
        choices=("auto", "month"),
        default="auto",
        help="auto usa anni interi quando possibile; month forza file mensili",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="riscarica anche i file esistenti"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="mostra le richieste senza inviarle"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start > args.end:
        raise SystemExit("--from deve essere precedente o uguale a --to")
    if args.start < DATASET_FIRST_DATE:
        raise SystemExit(
            f"ERA5-Land inizia il {DATASET_FIRST_DATE.isoformat()}; "
            f"--from {args.start.isoformat()} è fuori dal dataset"
        )
    if not -90 <= args.lat <= 90 or not -180 <= args.lon <= 180:
        raise SystemExit("coordinate non valide")

    latitude = snap_to_grid(args.lat)
    longitude = snap_to_grid(args.lon)
    if (latitude, longitude) != (args.lat, args.lon):
        print(
            f"Coordinate richieste: {args.lat:.6f}, {args.lon:.6f}; "
            f"cella ERA5-Land: {latitude:.1f}, {longitude:.1f}"
        )
    else:
        print(f"Cella ERA5-Land: {latitude:.1f}, {longitude:.1f}")

    chunks = (
        monthly_chunks(args.start, args.end)
        if args.chunk_size == "month"
        else automatic_chunks(args.start, args.end)
    )
    total_hours = sum(chunk.expected_hours for chunk in chunks)
    print(
        f"Periodo inclusivo: {args.start} -> {args.end}; "
        f"{total_hours} ore in {len(chunks)} richieste"
    )

    if args.dry_run:
        for chunk in chunks:
            target = output_path(
                args.output_directory, latitude, longitude, chunk
            )
            print(
                f"DRY-RUN {chunk.start} -> {chunk.end}: "
                f"{chunk.expected_hours} ore, {chunk.expected_messages} "
                f"messaggi -> {target}"
            )
        if args.database is not None:
            print(f"DRY-RUN import nel database: {args.database}")
        return

    args.output_directory.mkdir(parents=True, exist_ok=True)
    pending = []
    targets = []
    for number, chunk in enumerate(chunks, start=1):
        target = output_path(args.output_directory, latitude, longitude, chunk)
        targets.append(target)
        if not target.exists() or args.overwrite:
            pending.append((number, chunk, target))
            continue
        try:
            messages = count_grib1_messages(target)
        except ValueError as error:
            raise SystemExit(
                f"file esistente non valido: {target} ({error}); "
                "usa --overwrite per sostituirlo"
            ) from error
        if messages != chunk.expected_messages:
            raise SystemExit(
                f"file esistente incompleto: {target} contiene {messages} "
                f"messaggi invece di {chunk.expected_messages}; usa --overwrite"
            )
        print(f"[{number}/{len(chunks)}] già presente e valido: {target}")

    if not pending:
        print("Tutti i file richiesti sono già presenti e validi.")

    if pending:
        try:
            import cdsapi
        except ImportError as error:
            raise SystemExit(
                "cdsapi non installato; esegui: "
                ".venv/bin/pip install -r requirements.txt"
            ) from error

        try:
            client = cdsapi.Client()
        except Exception as error:
            raise SystemExit(f"configurazione CDS non disponibile: {error}") from error

        for number, chunk, target in pending:
            temporary = target.with_suffix(target.suffix + ".part")
            if temporary.exists():
                temporary.unlink()
            print(f"[{number}/{len(chunks)}] scarico {chunk.start} -> {chunk.end}")
            try:
                client.retrieve(
                    DATASET,
                    build_request(chunk, latitude, longitude),
                    str(temporary),
                )
            except Exception as error:
                raise SystemExit(
                    f"download CDS fallito per {chunk.start} -> {chunk.end}: {error}"
                ) from None
            messages = count_grib1_messages(temporary)
            if messages != chunk.expected_messages:
                raise RuntimeError(
                    f"download incompleto: ricevuti {messages} messaggi, "
                    f"attesi {chunk.expected_messages}; file lasciato in {temporary}"
                )
            temporary.replace(target)
            print(
                f"[{number}/{len(chunks)}] completato: {target} "
                f"({chunk.expected_hours} ore, {messages} messaggi)"
            )

    if args.database is not None:
        from import_era5_land import connect_database, import_file, print_summary

        connection = connect_database(args.database)
        try:
            for target in targets:
                summary = import_file(connection, target)
                print_summary(summary, dry_run=False)
        finally:
            connection.close()


if __name__ == "__main__":
    main()
