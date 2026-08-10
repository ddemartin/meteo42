from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator


ECMWF_CENTRE = 98
SURFACE_LEVEL_TYPE = 1


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    unit: str
    time_range_indicator: int
    convert: Callable[[float], float]


PARAMETERS = {
    167: ParameterSpec("temperature_c", "°C", 0, lambda value: value - 273.15),
    168: ParameterSpec("dewpoint_c", "°C", 0, lambda value: value - 273.15),
    228: ParameterSpec("precipitation_mm", "mm", 4, lambda value: value * 1000),
}


@dataclass(frozen=True)
class GribValue:
    latitude: float
    longitude: float
    value: float


@dataclass(frozen=True)
class GribField:
    valid_at_utc: int
    variable: str
    unit: str
    forecast_step: int | None
    values: tuple[GribValue, ...]


def unsigned(data: bytes) -> int:
    return int.from_bytes(data, "big")


def signed_magnitude(data: bytes) -> int:
    value = unsigned(data)
    sign_bit = 1 << (len(data) * 8 - 1)
    return -(value & (sign_bit - 1)) if value & sign_bit else value


def ibm_float(data: bytes) -> float:
    raw = unsigned(data)
    if raw == 0:
        return 0.0
    sign = -1 if raw >> 31 else 1
    exponent = ((raw >> 24) & 0x7F) - 64
    fraction = raw & 0xFFFFFF
    return sign * (16.0**exponent) * fraction / (1 << 24)


def bitmap_values(section: bytes, point_count: int) -> list[bool]:
    if unsigned(section[4:6]) != 0:
        raise ValueError("bitmap GRIB predefinita non supportata")
    bitmap = section[6:]
    if len(bitmap) * 8 < point_count:
        raise ValueError("bitmap GRIB troncata")
    return [
        bool(bitmap[index // 8] & (1 << (7 - index % 8)))
        for index in range(point_count)
    ]


def unpack_integers(data: bytes, width: int, count: int, unused_bits: int) -> list[int]:
    if width == 0:
        return [0] * count
    available_bits = len(data) * 8 - unused_bits
    if width * count > available_bits:
        raise ValueError("dati GRIB troncati")
    packed = int.from_bytes(data, "big")
    total_bits = len(data) * 8
    mask = (1 << width) - 1
    return [
        (packed >> (total_bits - (index + 1) * width)) & mask
        for index in range(count)
    ]


def forecast_delta(product: bytes, expected_indicator: int) -> timedelta:
    units = {
        0: timedelta(minutes=1),
        1: timedelta(hours=1),
        2: timedelta(days=1),
        10: timedelta(hours=3),
        11: timedelta(hours=6),
        12: timedelta(hours=12),
        13: timedelta(seconds=1),
    }
    if product[20] != expected_indicator:
        raise ValueError(
            f"indicatore temporale GRIB inatteso per il parametro {product[8]}: "
            f"{product[20]}"
        )
    try:
        unit = units[product[17]]
    except KeyError as error:
        raise ValueError(f"unità temporale GRIB non supportata: {product[17]}") from error
    if expected_indicator == 0:
        end_step = product[18]
    else:
        if product[19] - product[18] != 1:
            raise ValueError(
                "la precipitazione non rappresenta un intervallo di un'ora: "
                f"P1={product[18]}, P2={product[19]}"
            )
        end_step = product[19]
    return unit * end_step


def valid_timestamp(product: bytes, expected_indicator: int) -> int:
    year = (product[24] - 1) * 100 + product[12]
    reference = datetime(
        year,
        product[13],
        product[14],
        product[15],
        product[16],
        tzinfo=timezone.utc,
    )
    return int((reference + forecast_delta(product, expected_indicator)).timestamp())


def iter_weather_fields(path: Path) -> Iterator[GribField]:
    data = path.read_bytes()
    position = 0
    expected_grid = None
    previous_timestamps = {}

    while position < len(data):
        if data[position : position + 4] != b"GRIB":
            raise ValueError(f"firma GRIB assente all'offset {position}")
        if position + 8 > len(data) or data[position + 7] != 1:
            raise ValueError("il file non è un GRIB edizione 1 completo")
        message_length = unsigned(data[position + 4 : position + 7])
        message_end = position + message_length
        if (
            message_length < 12
            or message_end > len(data)
            or data[message_end - 4 : message_end] != b"7777"
        ):
            raise ValueError(f"messaggio GRIB non valido all'offset {position}")

        cursor = position + 8
        product_length = unsigned(data[cursor : cursor + 3])
        product = data[cursor : cursor + product_length]
        if len(product) < 28:
            raise ValueError("sezione prodotto GRIB troncata")
        cursor += product_length

        if product[4] != ECMWF_CENTRE:
            raise ValueError(f"centro GRIB inatteso: {product[4]}")
        try:
            parameter = PARAMETERS[product[8]]
        except KeyError as error:
            raise ValueError(f"parametro GRIB inatteso: {product[8]}") from error
        if product[9] != SURFACE_LEVEL_TYPE:
            raise ValueError(f"livello GRIB inatteso: {product[9]}")
        if not product[7] & 0x80:
            raise ValueError("griglia GRIB assente")

        grid_length = unsigned(data[cursor : cursor + 3])
        grid = data[cursor : cursor + grid_length]
        if len(grid) < 28 or grid[5] != 0:
            raise ValueError("è supportata soltanto la griglia lat/lon regolare")
        cursor += grid_length

        ni = unsigned(grid[6:8])
        nj = unsigned(grid[8:10])
        latitude_first = signed_magnitude(grid[10:13]) / 1000
        longitude_first = signed_magnitude(grid[13:16]) / 1000
        longitude_step = unsigned(grid[23:25]) / 1000
        latitude_step = unsigned(grid[25:27]) / 1000
        scan_mode = grid[27]
        if scan_mode != 0:
            raise ValueError(f"modalità di scansione GRIB non supportata: {scan_mode}")
        grid_signature = (
            ni,
            nj,
            latitude_first,
            longitude_first,
            latitude_step,
            longitude_step,
        )
        if expected_grid is None:
            expected_grid = grid_signature
        elif grid_signature != expected_grid:
            raise ValueError("la griglia cambia all'interno del file")

        point_count = ni * nj
        if product[7] & 0x40:
            bitmap_length = unsigned(data[cursor : cursor + 3])
            bitmap = data[cursor : cursor + bitmap_length]
            present = bitmap_values(bitmap, point_count)
            cursor += bitmap_length
        else:
            present = [True] * point_count

        binary_length = unsigned(data[cursor : cursor + 3])
        binary = data[cursor : cursor + binary_length]
        if len(binary) < 11:
            raise ValueError("sezione dati GRIB troncata")
        if binary[3] & 0xF0:
            raise ValueError(f"packing GRIB non supportato: flag {binary[3]:#04x}")
        binary_scale = signed_magnitude(binary[4:6])
        reference_value = ibm_float(binary[6:10])
        bits_per_value = binary[10]
        decimal_scale = signed_magnitude(product[26:28])
        packed_values = unpack_integers(
            binary[11:],
            bits_per_value,
            sum(present),
            binary[3] & 0x0F,
        )

        values = []
        packed_index = 0
        for point_index, is_present in enumerate(present):
            if not is_present:
                continue
            row, column = divmod(point_index, ni)
            kelvin = (
                reference_value
                + packed_values[packed_index] * (2.0**binary_scale)
            ) * (10.0 ** (-decimal_scale))
            converted = parameter.convert(kelvin)
            if parameter.name == "precipitation_mm":
                if converted < -1e-6:
                    raise ValueError(f"precipitazione negativa: {converted} mm")
                converted = max(0.0, converted)
            values.append(
                GribValue(
                    latitude=round(latitude_first - row * latitude_step, 6),
                    longitude=round(longitude_first + column * longitude_step, 6),
                    value=converted,
                )
            )
            packed_index += 1

        timestamp = valid_timestamp(product, parameter.time_range_indicator)
        previous_timestamp = previous_timestamps.get(parameter.name)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ValueError("timestamp GRIB duplicati o non crescenti")
        previous_timestamps[parameter.name] = timestamp
        yield GribField(
            valid_at_utc=timestamp,
            variable=parameter.name,
            unit=parameter.unit,
            forecast_step=(product[19] if parameter.time_range_indicator == 4 else None),
            values=tuple(values),
        )
        position = message_end


def count_grib1_messages(path: Path) -> int:
    return sum(1 for _ in iter_weather_fields(path))
