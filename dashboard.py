import logging
import math
import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from astral import LocationInfo
from astral.sun import sun

import scrape

DEFAULT_DATABASE_PATH = os.environ.get(
    "ARPAV_DATABASE_PATH", "arpav_meteo.sqlite"
)
STATIONS_CONFIG = Path("stations.json")
DASHBOARD_CONFIG = Path(".dashboard_config.json")

st.set_page_config(
    page_title="ARPAV Dashboard",
    page_icon="🌤️",
    layout="wide",
)

st.title("🌤️ ARPAV Meteo Dashboard")

VARIABLE_LABELS = {
    "TARIA2M": "Temperatura aria (2m)",
    "TARIA5M": "Temperatura aria (5m)",
    "UMID2M": "Umidità (2m)",
    "UMID5M": "Umidità (5m)",
    "VVENTO10M": "Velocità del vento (10m)",
    "VVENTO5M": "Velocità del vento (5m)",
    "VVENTO2M": "Velocità del vento (2m)",
    "DVENTO10M": "Direzione del vento (10m)",
    "DVENTO5M": "Direzione del vento (5m)",
    "DVENTO2M": "Direzione del vento (2m)",
    "RADSOL": "Radiazione solare",
    "PREC": "Precipitazione",
    "PRESS": "Pressione atmosferica",
    "NIVOM": "Altezza neve",
    "VISIB": "Visibilità",
    "BFOGL": "Bagnatura fogliare",
    "TSUOLO": "Temperatura del suolo (superficie)",
    "TSUOLO-10": "Temperatura del suolo (-10cm)",
    "TSUOLO-20": "Temperatura del suolo (-20cm)",
    "TSUOLO-30": "Temperatura del suolo (-30cm)",
}

SOIL_VARIABLES = ["TSUOLO", "TSUOLO-10", "TSUOLO-20", "TSUOLO-30"]
SOIL_DEPTH_LABELS = {
    "TSUOLO": "Superficie",
    "TSUOLO-10": "-10cm",
    "TSUOLO-20": "-20cm",
    "TSUOLO-30": "-30cm",
}
SOIL_DEPTH_DASHES = {
    "TSUOLO": "solid",
    "TSUOLO-10": "dash",
    "TSUOLO-20": "dot",
    "TSUOLO-30": "dashdot",
}
WIND_HEIGHTS = ["10M", "5M", "2M"]

VENETO_CAPOLUOGHI = {
    "Belluno": (46.1400, 12.2170),
    "Padova": (45.4064, 11.8768),
    "Rovigo": (45.0705, 11.7905),
    "Treviso": (45.6669, 12.2433),
    "Venezia": (45.4408, 12.3155),
    "Verona": (45.4384, 10.9916),
    "Vicenza": (45.5455, 11.5354),
}
HOME_STATION_HINT = "mogliano veneto"

WIND_COMPASS_LABELS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

HOME_TIMEZONE = "Europe/Rome"

# Horizontal legend below the plot area: a right-side vertical legend eats
# fixed width from the chart, which crushes the plot on narrow/mobile screens.
MOBILE_LEGEND = dict(
    orientation="h",
    yanchor="top",
    y=-0.25,
    xanchor="center",
    x=0.5,
)
MOBILE_CHART_MARGIN = dict(b=110)
PLOTLY_CONFIG = {"responsive": True}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


def degrees_to_compass(degrees: float) -> str:
    index = round(degrees / 22.5) % 16
    return WIND_COMPASS_LABELS[index]


def var_label(var: str) -> str:
    return VARIABLE_LABELS.get(var, var)


def load_dashboard_config() -> dict:
    if not DASHBOARD_CONFIG.exists():
        return {}
    try:
        return json.loads(DASHBOARD_CONFIG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_dashboard_config(config: dict) -> None:
    DASHBOARD_CONFIG.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if "database_path" not in st.session_state:
    st.session_state["database_path"] = load_dashboard_config().get(
        "database_path", DEFAULT_DATABASE_PATH
    )

with st.sidebar:
    st.text_input(
        "Percorso Database",
        key="database_path",
        on_change=lambda: save_dashboard_config(
            {"database_path": st.session_state["database_path"]}
        ),
    )
    if not Path(st.session_state["database_path"]).exists():
        st.caption("⚠️ File non trovato")

DATABASE_PATH = Path(st.session_state["database_path"])


class StreamlitLogHandler(logging.Handler):
    def __init__(self, placeholder):
        super().__init__()
        self.placeholder = placeholder
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))
        self.placeholder.code("\n".join(self.lines[-25:]))


def run_scrape(request_delay: float) -> None:
    log_placeholder = st.empty()
    handler = StreamlitLogHandler(log_placeholder)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    scrape.LOG.addHandler(handler)
    scrape.LOG.setLevel(logging.INFO)

    try:
        with st.spinner("Scaricamento in corso..."):
            scrape.collect_all(
                config_path=scrape.DEFAULT_CONFIG,
                database_path=DATABASE_PATH,
                csv_path=scrape.DEFAULT_CSV,
                raw_directory=scrape.DEFAULT_RAW_DIRECTORY,
                request_delay=request_delay,
            )
        st.success("Aggiornamento completato")
    except Exception as exc:
        st.error(f"Errore durante lo scraping: {exc}")
    finally:
        scrape.LOG.removeHandler(handler)


with st.sidebar:
    st.divider()
    st.write("### Aggiorna Dati")
    request_delay = st.number_input(
        "Ritardo tra stazioni (s)",
        min_value=0.0,
        value=0.5,
        step=0.1,
    )
    if st.button("Scarica dati ora"):
        run_scrape(request_delay)


def get_db_connection():
    conn = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn


def load_stations_config():
    if not STATIONS_CONFIG.exists():
        return {"stations": []}
    return json.loads(STATIONS_CONFIG.read_text(encoding="utf-8"))


def save_stations_config(config):
    STATIONS_CONFIG.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_observations_df(
    station_id: str | None = None,
    variable_type: str | None = None,
    days: int = 7,
) -> pd.DataFrame:
    conn = get_db_connection()
    query = """
        SELECT
            station_id,
            station_name,
            observation_at,
            variable_type,
            value_numeric,
            value_text,
            unit,
            downloaded_at
        FROM observations
        WHERE observation_at >= datetime('now', '-' || ? || ' days')
    """
    params = [days]

    if station_id:
        query += " AND station_id = ?"
        params.append(station_id)

    if variable_type:
        query += " AND variable_type = ?"
        params.append(variable_type)

    query += " ORDER BY observation_at DESC"

    df = pd.read_sql_query(query, conn, params=params)
    if not df.empty:
        df["observation_at"] = pd.to_datetime(df["observation_at"])
    return df

def period_floor(timestamps: pd.Series, frequency: str) -> pd.Series:
    """Floor timestamps to the start of their day/week(Mon)/month period."""
    if frequency == "daily":
        return timestamps.dt.floor("D")
    if frequency == "weekly":
        return timestamps.dt.to_period("W-MON").dt.start_time
    return timestamps.dt.to_period("M").dt.to_timestamp()


def aggregate_observations(
    observations: pd.DataFrame,
    frequency: str,
) -> pd.DataFrame:
    """Aggregate numeric observations by station and day/month."""
    required_columns = {
        "station_name",
        "observation_at",
        "value_numeric",
    }
    if observations.empty or not required_columns.issubset(observations.columns):
        return pd.DataFrame(
            columns=[
                "period",
                "station_name",
                "minimum",
                "average",
                "maximum",
            ]
        )

    if frequency not in {"daily", "weekly", "monthly"}:
        raise ValueError("frequency must be 'daily', 'weekly' or 'monthly'")

    numeric = observations.dropna(
        subset=["observation_at", "value_numeric"]
    ).copy()
    if numeric.empty:
        return pd.DataFrame(
            columns=[
                "period",
                "station_name",
                "minimum",
                "average",
                "maximum",
            ]
        )

    numeric["period"] = period_floor(numeric["observation_at"], frequency)

    min_max = numeric.groupby(["period", "station_name"], as_index=False)[
        "value_numeric"
    ].agg(minimum="min", maximum="max")

    # The average is a mean of *daily* time-weighted averages (not a naive
    # mean of raw readings): otherwise days with denser sampling (10-min live
    # data) would outweigh days with sparser sampling (hourly historical
    # data) within the same weekly/monthly average.
    daily_weighted = compute_daily_weighted_averages(observations)
    if daily_weighted.empty:
        min_max["average"] = float("nan")
        return min_max.sort_values(["period", "station_name"])[
            ["period", "station_name", "minimum", "average", "maximum"]
        ]

    daily_weighted["period"] = period_floor(daily_weighted["day"], frequency)
    averages = (
        daily_weighted.groupby(["period", "station_name"], as_index=False)[
            "value_numeric"
        ]
        .mean()
        .rename(columns={"value_numeric": "average"})
    )
    averages["average"] = averages["average"].round(1)

    return min_max.merge(
        averages, on=["period", "station_name"], how="left"
    ).sort_values(["period", "station_name"])[
        ["period", "station_name", "minimum", "average", "maximum"]
    ]


def build_range_figure(
    aggregated: pd.DataFrame,
    title: str,
    unit: str,
) -> go.Figure:
    """Build a min/average/max chart, using one color per station."""
    fig = go.Figure()
    station_names = sorted(aggregated["station_name"].unique())
    colors = px.colors.qualitative.Plotly
    metric_styles = {
        "minimum": ("Min", "dot"),
        "average": ("Media", "solid"),
        "maximum": ("Max", "dot"),
    }

    for station_index, station_name in enumerate(station_names):
        station_df = aggregated[
            aggregated["station_name"] == station_name
        ]
        color = colors[station_index % len(colors)]
        for metric, (label, dash) in metric_styles.items():
            fig.add_trace(
                go.Scatter(
                    x=station_df["period"],
                    y=station_df[metric],
                    name=f"{station_name} - {label}",
                    mode="lines+markers",
                    line=dict(color=color, dash=dash),
                    legendgroup=station_name,
                )
            )

    fig.update_layout(
        title=title,
        xaxis_title="Periodo",
        yaxis_title=unit or "Valore",
        hovermode="x unified",
        height=430,
        legend_title="Stazione / statistica",
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    return fig


def aggregate_extremes_bands(
    observations: pd.DataFrame,
    frequency: str,
) -> pd.DataFrame:
    """For each station/period, the range of daily highs and the range of
    daily lows (not just one overall min and one overall max): e.g. "in July
    the daily highs ranged 28-37°C and the daily lows ranged 17-28°C". Built
    from per-day min/max, so a single unusually hot or cold day doesn't
    collapse the whole period into one flat min/max line."""
    columns = [
        "period",
        "station_name",
        "highs_min",
        "highs_max",
        "lows_min",
        "lows_max",
        "average",
    ]
    required_columns = {"station_name", "observation_at", "value_numeric"}
    if observations.empty or not required_columns.issubset(observations.columns):
        return pd.DataFrame(columns=columns)

    if frequency not in {"daily", "weekly", "monthly"}:
        raise ValueError("frequency must be 'daily', 'weekly' or 'monthly'")

    clean = observations.dropna(subset=["observation_at", "value_numeric"]).copy()
    if clean.empty:
        return pd.DataFrame(columns=columns)

    clean["day"] = clean["observation_at"].dt.floor("D")
    daily_extremes = clean.groupby(["day", "station_name"], as_index=False)[
        "value_numeric"
    ].agg(day_min="min", day_max="max")
    daily_extremes["period"] = period_floor(daily_extremes["day"], frequency)

    bands = daily_extremes.groupby(["period", "station_name"], as_index=False).agg(
        highs_min=("day_max", "min"),
        highs_max=("day_max", "max"),
        lows_min=("day_min", "min"),
        lows_max=("day_min", "max"),
    )
    for column in ["highs_min", "highs_max", "lows_min", "lows_max"]:
        bands[column] = bands[column].round(1)

    daily_weighted = compute_daily_weighted_averages(observations)
    if daily_weighted.empty:
        bands["average"] = float("nan")
        return bands.sort_values(["period", "station_name"])[columns]

    daily_weighted["period"] = period_floor(daily_weighted["day"], frequency)
    averages = (
        daily_weighted.groupby(["period", "station_name"], as_index=False)[
            "value_numeric"
        ]
        .mean()
        .rename(columns={"value_numeric": "average"})
    )
    averages["average"] = averages["average"].round(1)

    return bands.merge(
        averages, on=["period", "station_name"], how="left"
    ).sort_values(["period", "station_name"])[columns]


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def build_extremes_band_figure(
    bands: pd.DataFrame,
    title: str,
    unit: str,
) -> go.Figure:
    """Two shaded bands per station (range of daily highs, range of daily
    lows) plus the time-weighted average as a centerline."""
    fig = go.Figure()
    station_names = sorted(bands["station_name"].unique())
    colors = px.colors.qualitative.Plotly

    for station_index, station_name in enumerate(station_names):
        color = colors[station_index % len(colors)]
        station_df = bands[
            bands["station_name"] == station_name
        ].sort_values("period")
        if station_df.empty:
            continue

        # Highs band: invisible upper edge, then lower edge filled up to it.
        fig.add_trace(
            go.Scatter(
                x=station_df["period"],
                y=station_df["highs_max"],
                mode="lines",
                line=dict(color=color, width=0),
                legendgroup=station_name,
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=station_df["period"],
                y=station_df["highs_min"],
                mode="lines",
                line=dict(color=color, width=1),
                fill="tonexty",
                fillcolor=hex_to_rgba(color, 0.25),
                name=f"{station_name} - Massime (range)",
                legendgroup=station_name,
            )
        )

        # Lows band: same trick, independent of the highs band above it.
        fig.add_trace(
            go.Scatter(
                x=station_df["period"],
                y=station_df["lows_max"],
                mode="lines",
                line=dict(color=color, width=0),
                legendgroup=station_name,
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=station_df["period"],
                y=station_df["lows_min"],
                mode="lines",
                line=dict(color=color, width=1),
                fill="tonexty",
                fillcolor=hex_to_rgba(color, 0.15),
                name=f"{station_name} - Minime (range)",
                legendgroup=station_name,
            )
        )

        fig.add_trace(
            go.Scatter(
                x=station_df["period"],
                y=station_df["average"],
                mode="lines",
                line=dict(color=color, width=2),
                name=f"{station_name} - Media",
                legendgroup=station_name,
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Periodo",
        yaxis_title=unit or "Valore",
        hovermode="x unified",
        height=430,
        legend_title="Stazione / serie",
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    return fig


def build_wind_figure(
    speed_df: pd.DataFrame,
    direction_df: pd.DataFrame,
    title: str,
    unit: str,
) -> go.Figure:
    """Bar chart of wind speed with direction arrows sampled every N points."""
    fig = go.Figure()
    colors = px.colors.qualitative.Plotly
    station_names = sorted(speed_df["station_name"].unique())

    for station_index, station_name in enumerate(station_names):
        color = colors[station_index % len(colors)]
        s_df = speed_df[
            speed_df["station_name"] == station_name
        ].sort_values("observation_at")

        fig.add_trace(
            go.Bar(
                x=s_df["observation_at"],
                y=s_df["value_numeric"],
                name=station_name,
                marker_color=color,
                legendgroup=station_name,
            )
        )

        d_df = direction_df[
            direction_df["station_name"] == station_name
        ].sort_values("observation_at")

        if d_df.empty:
            continue

        merged = pd.merge_asof(
            s_df[["observation_at", "value_numeric"]],
            d_df[["observation_at", "value_numeric"]].rename(
                columns={"value_numeric": "direction"}
            ),
            on="observation_at",
            tolerance=pd.Timedelta("30min"),
            direction="nearest",
        ).dropna(subset=["direction"])

        if merged.empty:
            continue

        step = max(1, len(merged) // 24)
        sampled = merged.iloc[::step]

        fig.add_trace(
            go.Scatter(
                x=sampled["observation_at"],
                y=sampled["value_numeric"],
                mode="markers",
                marker=dict(
                    symbol="arrow",
                    size=13,
                    angle=sampled["direction"],
                    color=color,
                    line=dict(width=1, color="rgba(0,0,0,0.5)"),
                ),
                name=f"{station_name} - direzione",
                legendgroup=station_name,
                showlegend=False,
                hovertemplate="Direzione: %{customdata:.0f}°<extra></extra>",
                customdata=sampled["direction"],
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Data/Ora",
        yaxis_title=unit or "Valore",
        hovermode="x unified",
        height=420,
        barmode="group",
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    return fig


def build_soil_figure(soil_df: pd.DataFrame) -> go.Figure:
    """Combine all soil-temperature depths into a single chart."""
    fig = go.Figure()
    colors = px.colors.qualitative.Plotly
    station_names = sorted(soil_df["station_name"].unique())

    for station_index, station_name in enumerate(station_names):
        color = colors[station_index % len(colors)]
        station_df = soil_df[soil_df["station_name"] == station_name]

        for depth in SOIL_VARIABLES:
            depth_df = station_df[
                station_df["variable_type"] == depth
            ].sort_values("observation_at")
            if depth_df.empty:
                continue

            fig.add_trace(
                go.Scatter(
                    x=depth_df["observation_at"],
                    y=depth_df["value_numeric"],
                    mode="lines",
                    name=f"{station_name} - {SOIL_DEPTH_LABELS[depth]}",
                    line=dict(color=color, dash=SOIL_DEPTH_DASHES[depth]),
                    legendgroup=station_name,
                )
            )

    fig.update_layout(
        title="Temperatura del suolo",
        xaxis_title="Data/Ora",
        yaxis_title="°C",
        hovermode="x unified",
        height=430,
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    return fig


def render_line_chart(var_df: pd.DataFrame, var: str) -> None:
    """Draw a standard per-station line chart for a single variable."""
    fig = px.line(
        var_df,
        x="observation_at",
        y="value_numeric",
        color="station_name",
        title=var_label(var),
        labels={
            "observation_at": "Data/Ora",
            "value_numeric": f"{var_label(var)} ({var_df['unit'].iloc[0] if len(var_df) > 0 and var_df['unit'].notna().any() else ''})",
            "station_name": "Stazione",
        },
        markers=True,
    )
    fig.update_layout(
        hovermode="x unified",
        height=400,
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def aggregate_precipitation_totals(
    observations: pd.DataFrame,
    frequency: str,
) -> pd.DataFrame:
    """Sum precipitation by station and week/month (missing readings count as 0)."""
    if frequency not in {"weekly", "monthly"}:
        raise ValueError("frequency must be 'weekly' or 'monthly'")

    required_columns = {"station_name", "observation_at", "value_numeric"}
    if observations.empty or not required_columns.issubset(observations.columns):
        return pd.DataFrame(columns=["period", "station_name", "totale"])

    numeric = observations.dropna(subset=["observation_at"]).copy()
    numeric["value_numeric"] = numeric["value_numeric"].fillna(0.0)
    if numeric.empty:
        return pd.DataFrame(columns=["period", "station_name", "totale"])

    if frequency == "weekly":
        numeric["period"] = (
            numeric["observation_at"].dt.to_period("W-MON").dt.start_time
        )
    else:
        numeric["period"] = (
            numeric["observation_at"].dt.to_period("M").dt.to_timestamp()
        )

    return (
        numeric.groupby(["period", "station_name"], as_index=False)[
            "value_numeric"
        ]
        .sum()
        .rename(columns={"value_numeric": "totale"})
        .sort_values(["period", "station_name"])
    )


def build_precipitation_totals_figure(
    aggregated: pd.DataFrame,
    title: str,
) -> go.Figure:
    """Grouped bar chart of precipitation totals per station and period."""
    fig = px.bar(
        aggregated,
        x="period",
        y="totale",
        color="station_name",
        barmode="group",
        title=title,
        labels={
            "period": "Periodo",
            "totale": "Precipitazione (mm)",
            "station_name": "Stazione",
        },
    )
    fig.update_layout(
        hovermode="x unified",
        height=400,
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    return fig


# Dash only encodes station: a handful of values, so it stays legible. Year is
# encoded by color instead (see build_yearly_precipitation_comparison) because
# with a decade-plus of history, cycling dash styles for "year" repeats after
# a few and different years become visually indistinguishable.
STATION_DASH_CYCLE = ["solid", "dash", "dot", "dashdot"]


# Distinct hues (red/green/blue/yellow/...) rather than shades of one color:
# with a decade-plus of years on screen, a light-to-dark single-hue ramp puts
# adjacent years a few shades apart and they become impossible to tell apart.
# Light24 has 24 clearly distinct colors, enough for years through 2033.
# Indexed from a fixed anchor year (not from position within the currently
# filtered years) so a given year always gets the same color regardless of
# which other years/stations are selected alongside it.
YEAR_COLOR_ANCHOR = 2000
YEAR_COLOR_PALETTE = px.colors.qualitative.Light24


def year_qualitative_color(year: int) -> str:
    return YEAR_COLOR_PALETTE[
        (year - YEAR_COLOR_ANCHOR) % len(YEAR_COLOR_PALETTE)
    ]


def build_yearly_precipitation_comparison(prec_df: pd.DataFrame) -> go.Figure:
    """Cumulative precipitation per calendar year, aligned on a Jan-Dec axis so
    different years can be compared station by station."""
    fig = go.Figure()
    station_names = sorted(prec_df["station_name"].unique())
    current_year = datetime.now().year

    for station_index, station_name in enumerate(station_names):
        dash = STATION_DASH_CYCLE[station_index % len(STATION_DASH_CYCLE)]
        station_df = prec_df[
            prec_df["station_name"] == station_name
        ].sort_values("observation_at")

        years = sorted(station_df["observation_at"].dt.year.unique())
        for year in years:
            year_df = station_df[
                station_df["observation_at"].dt.year == year
            ].copy()
            if year_df.empty:
                continue

            year_df["cumulata"] = year_df["value_numeric"].fillna(0.0).cumsum()
            # Reference year 2000 (leap) so Feb 29 lines up and all years share
            # a single Jan-Dec axis.
            reference_date = pd.to_datetime(
                {
                    "year": 2000,
                    "month": year_df["observation_at"].dt.month,
                    "day": year_df["observation_at"].dt.day,
                }
            )
            is_current_year = year == current_year
            trace_name = (
                f"{station_name} - {year}"
                if len(station_names) > 1
                else str(year)
            )

            fig.add_trace(
                go.Scatter(
                    x=reference_date,
                    y=year_df["cumulata"],
                    name=trace_name,
                    mode="lines",
                    line=dict(
                        color=year_qualitative_color(year),
                        dash=dash,
                        width=3 if is_current_year else 1.5,
                    ),
                    legendgroup=station_name,
                )
            )

    fig.update_layout(
        title="Precipitazione cumulata - confronto tra anni",
        xaxis=dict(title="Mese", tickformat="%d %b"),
        yaxis_title="Cumulata (mm)",
        hovermode="x unified",
        height=450,
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    return fig


def render_precipitation_cumulative(chart_stations: list) -> None:
    """Draw yearly cumulative precipitation as its own standalone chart."""
    year_start = datetime(datetime.now().year, 1, 1)
    days_since_year_start = (datetime.now() - year_start).days + 1
    prec_year_df = get_observations_df(
        days=days_since_year_start,
        variable_type="PREC",
    )
    prec_year_df = prec_year_df[
        prec_year_df["station_id"].isin(chart_stations)
    ]
    if prec_year_df.empty:
        return

    prec_year_df = prec_year_df.sort_values("observation_at")
    prec_year_df["cumulata"] = prec_year_df.groupby("station_id")[
        "value_numeric"
    ].cumsum()

    cumulative_fig = go.Figure()
    for station_id in chart_stations:
        station_cum = prec_year_df[prec_year_df["station_id"] == station_id]
        if station_cum.empty:
            continue
        station_name = station_cum["station_name"].iloc[0]
        cumulative_fig.add_trace(
            go.Scatter(
                x=station_cum["observation_at"],
                y=station_cum["cumulata"],
                name=station_name,
                mode="lines",
            )
        )

    cumulative_fig.update_layout(
        title="Precipitazione cumulata annua",
        xaxis_title="Data/Ora",
        yaxis_title="Cumulata annua (mm)",
        hovermode="x unified",
        height=400,
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    st.plotly_chart(cumulative_fig, use_container_width=True, config=PLOTLY_CONFIG)


def get_stations_from_db():
    conn = get_db_connection()
    query = """
        SELECT
            s.station_id,
            COALESCE(
                m.nome_stazione,
                s.configured_name,
                s.api_name,
                s.station_id
            ) AS station_name,
            m.provincia,
            m.quota,
            m.latitudine,
            m.longitudine
        FROM stations s
        LEFT JOIN station_metadata m
            ON m.station_id = s.station_id
        ORDER BY
            COALESCE(m.nome_stazione, s.configured_name, s.api_name, s.station_id)
    """
    return pd.read_sql_query(query, conn)


def find_nearest_stations(stations_df: pd.DataFrame) -> pd.DataFrame:
    """For each Veneto provincial capital, find the closest station with coordinates."""
    candidates = stations_df.dropna(subset=["latitudine", "longitudine"])
    rows = []
    for city, (city_lat, city_lon) in VENETO_CAPOLUOGHI.items():
        if candidates.empty:
            continue
        distances = candidates.apply(
            lambda row: haversine_km(
                city_lat, city_lon, row["latitudine"], row["longitudine"]
            ),
            axis=1,
        )
        nearest_index = distances.idxmin()
        nearest = candidates.loc[nearest_index]
        rows.append(
            {
                "label": city,
                "station_id": nearest["station_id"],
                "station_name": nearest["station_name"],
                "latitudine": nearest["latitudine"],
                "longitudine": nearest["longitudine"],
                "distanza_km": distances.loc[nearest_index],
                "is_home": False,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "label",
            "station_id",
            "station_name",
            "latitudine",
            "longitudine",
            "distanza_km",
            "is_home",
        ],
    )


def get_latest_temperatures(station_ids: list) -> pd.DataFrame:
    """Latest TARIA2M reading per station."""
    if not station_ids:
        return pd.DataFrame(
            columns=["station_id", "value_numeric", "observation_at"]
        )
    conn = get_db_connection()
    placeholders = ",".join("?" for _ in station_ids)
    query = f"""
        SELECT station_id, value_numeric, MAX(observation_at) AS observation_at
        FROM observations
        WHERE variable_type = 'TARIA2M'
          AND value_numeric IS NOT NULL
          AND station_id IN ({placeholders})
        GROUP BY station_id
    """
    df = pd.read_sql_query(query, conn, params=station_ids)
    if not df.empty:
        df["observation_at"] = pd.to_datetime(df["observation_at"])
    return df


def build_overview_map(points_df: pd.DataFrame) -> go.Figure:
    """Map of the nearest station to each Veneto capoluogo, plus the home station."""
    fig = go.Figure()

    capoluoghi = points_df[~points_df["is_home"]]
    home = points_df[points_df["is_home"]]

    if not capoluoghi.empty:
        fig.add_trace(
            go.Scattermap(
                lat=capoluoghi["latitudine"],
                lon=capoluoghi["longitudine"],
                mode="markers+text",
                marker=dict(size=14, color="#2E86AB"),
                text=capoluoghi["label"],
                textposition="top center",
                hovertext=[
                    f"{row.station_name} — {row.temp_text}"
                    for row in capoluoghi.itertuples()
                ],
                hoverinfo="text",
                name="Capoluoghi",
            )
        )

    if not home.empty:
        fig.add_trace(
            go.Scattermap(
                lat=home["latitudine"],
                lon=home["longitudine"],
                mode="markers+text",
                marker=dict(size=18, color="#E63946"),
                text=home["label"],
                textposition="top center",
                hovertext=[
                    f"{row.station_name} — {row.temp_text}"
                    for row in home.itertuples()
                ],
                hoverinfo="text",
                name="Casa",
            )
        )

    fig.update_layout(
        autosize=True,
        uirevision="overview-map",
        map=dict(
            style="open-street-map",
            center=dict(lat=45.6, lon=11.9),
            zoom=7.2,
        ),
        height=520,
        margin=dict(l=0, r=0, t=36, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
    )
    return fig


def build_station_report(station_id: str, station_name: str) -> str:
    """Templated Italian summary of recent conditions for one station."""
    df_week = get_observations_df(station_id=station_id, days=7)
    if df_week.empty:
        return f"Nessun dato disponibile per {station_name}."

    lines = []

    temp_df = df_week[
        (df_week["variable_type"] == "TARIA2M") & df_week["value_numeric"].notna()
    ].sort_values("observation_at")

    if not temp_df.empty:
        latest = temp_df.iloc[-1]
        obs_time = latest["observation_at"]
        lines.append(
            f"**Temperatura**: {latest['value_numeric']:.1f}°C "
            f"(rilevata alle {obs_time.strftime('%H:%M')} del "
            f"{obs_time.strftime('%d/%m')})."
        )

        target_time = obs_time - timedelta(hours=24)
        time_diff = (temp_df["observation_at"] - target_time).abs()
        near_yesterday = temp_df[time_diff <= timedelta(hours=1)]
        if not near_yesterday.empty:
            closest = near_yesterday.loc[
                (near_yesterday["observation_at"] - target_time).abs().idxmin()
            ]
            delta = latest["value_numeric"] - closest["value_numeric"]
            if delta > 0.1:
                trend = "in aumento"
            elif delta < -0.1:
                trend = "in calo"
            else:
                trend = "stabile"
            lines.append(
                f"Rispetto alla stessa ora di ieri: {trend} ({delta:+.1f}°C)."
            )

        last_24h = temp_df[temp_df["observation_at"] >= obs_time - timedelta(hours=24)]
        if not last_24h.empty:
            lines.append(
                f"Nelle ultime 24 ore: minima {last_24h['value_numeric'].min():.1f}°C, "
                f"massima {last_24h['value_numeric'].max():.1f}°C."
            )

    humidity_df = df_week[
        (df_week["variable_type"] == "UMID2M") & df_week["value_numeric"].notna()
    ].sort_values("observation_at")
    if not humidity_df.empty:
        lines.append(f"**Umidità**: {humidity_df.iloc[-1]['value_numeric']:.0f}%.")

    wind_speed_df = df_week[
        (df_week["variable_type"] == "VVENTO10M") & df_week["value_numeric"].notna()
    ].sort_values("observation_at")
    wind_dir_df = df_week[
        (df_week["variable_type"] == "DVENTO10M") & df_week["value_numeric"].notna()
    ].sort_values("observation_at")
    if not wind_speed_df.empty:
        wind_text = f"**Vento**: {wind_speed_df.iloc[-1]['value_numeric']:.1f} m/s"
        if not wind_dir_df.empty:
            wind_text += f" da {degrees_to_compass(wind_dir_df.iloc[-1]['value_numeric'])}"
        lines.append(wind_text + ".")

    prec_df = df_week[
        (df_week["variable_type"] == "PREC") & df_week["value_numeric"].notna()
    ]
    if not prec_df.empty:
        last_obs = prec_df["observation_at"].max()
        last_24h_total = prec_df[
            prec_df["observation_at"] >= last_obs - timedelta(hours=24)
        ]["value_numeric"].sum()
        last_7d_total = prec_df["value_numeric"].sum()
        lines.append(
            f"**Precipitazione**: {last_24h_total:.1f} mm nelle ultime 24 ore, "
            f"{last_7d_total:.1f} mm negli ultimi 7 giorni."
        )

        year_start = datetime(datetime.now().year, 1, 1)
        days_since_year_start = (datetime.now() - year_start).days + 1
        prec_year_df = get_observations_df(
            station_id=station_id,
            days=days_since_year_start,
            variable_type="PREC",
        )
        if not prec_year_df.empty:
            month_start = datetime(datetime.now().year, datetime.now().month, 1)
            month_total = prec_year_df[
                prec_year_df["observation_at"] >= month_start
            ]["value_numeric"].sum()
            year_total = prec_year_df["value_numeric"].sum()
            lines.append(
                f"Cumulata: {month_total:.1f} mm questo mese, "
                f"{year_total:.1f} mm da inizio anno."
            )

    soil_df = df_week[
        (df_week["variable_type"] == "TSUOLO") & df_week["value_numeric"].notna()
    ].sort_values("observation_at")
    if not soil_df.empty:
        lines.append(
            f"**Temperatura del suolo** (superficie): "
            f"{soil_df.iloc[-1]['value_numeric']:.1f}°C."
        )

    return "\n\n".join(lines)


def compute_sun_times(lat: float, lon: float, target_date) -> dict:
    """Sunrise, solar noon (culmine) and sunset for a location, plus day/night length."""
    location = LocationInfo(latitude=lat, longitude=lon)
    tzinfo = ZoneInfo(HOME_TIMEZONE)
    times = sun(location.observer, date=target_date, tzinfo=tzinfo)
    day_length = times["sunset"] - times["sunrise"]
    night_length = timedelta(hours=24) - day_length
    return {
        "sunrise": times["sunrise"],
        "noon": times["noon"],
        "sunset": times["sunset"],
        "day_length": day_length,
        "night_length": night_length,
    }


def format_timedelta_hm(delta: timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


def heat_index_celsius(temp_c, humidity_pct):
    """NOAA/NWS heat index (Rothfusz regression). Accepts scalars or arrays, returns °C."""
    temp_f = temp_c * 9 / 5 + 32
    hi_simple = 0.5 * (temp_f + 61.0 + (temp_f - 68.0) * 1.2 + humidity_pct * 0.094)

    hi_full = (
        -42.379
        + 2.04901523 * temp_f
        + 10.14333127 * humidity_pct
        - 0.22475541 * temp_f * humidity_pct
        - 0.00683783 * temp_f**2
        - 0.05481717 * humidity_pct**2
        + 0.00122874 * temp_f**2 * humidity_pct
        + 0.00085282 * temp_f * humidity_pct**2
        - 0.00000199 * temp_f**2 * humidity_pct**2
    )

    low_adjustment = ((13 - humidity_pct) / 4) * np.sqrt(
        np.clip((17 - np.abs(temp_f - 95)) / 17, 0, None)
    )
    high_adjustment = ((humidity_pct - 85) / 10) * ((87 - temp_f) / 5)

    needs_low_adj = (humidity_pct < 13) & (temp_f >= 80) & (temp_f <= 112)
    needs_high_adj = (humidity_pct > 85) & (temp_f >= 80) & (temp_f <= 87)

    hi_full = np.where(needs_low_adj, hi_full - low_adjustment, hi_full)
    hi_full = np.where(needs_high_adj, hi_full + high_adjustment, hi_full)

    use_full_formula = ((temp_f + hi_simple) / 2) >= 80
    heat_index_f = np.where(use_full_formula, hi_full, hi_simple)

    return (heat_index_f - 32) * 5 / 9


def duration_weighted_mean(times: list, values: list, period_end) -> float | None:
    """Mean of `values` weighted by how long each one held (until the next
    reading, or until `period_end` for the last one), instead of a naive
    unweighted mean: e.g. 20h at 30°C and 10h at 10°C should not average to
    20°C, it should reflect that 30°C held for twice as long. This also keeps
    periods with denser sampling (10-min live data) from outweighing periods
    with sparser sampling (hourly historical data) within the same average."""
    boundaries = times + [period_end]

    weighted_sum = 0.0
    total_weight = 0.0
    for index, value in enumerate(values):
        weight_hours = (
            boundaries[index + 1] - boundaries[index]
        ).total_seconds() / 3600
        weighted_sum += value * weight_hours
        total_weight += weight_hours

    return weighted_sum / total_weight if total_weight > 0 else None


def compute_weighted_daily_temperature(temp_df: pd.DataFrame) -> pd.DataFrame:
    """Per-day temperature average weighted by how long each reading held."""
    clean = temp_df.dropna(subset=["observation_at", "value_numeric"]).sort_values(
        "observation_at"
    )
    if clean.empty:
        return pd.DataFrame(columns=["day", "weighted_average"])

    clean = clean.copy()
    clean["day"] = clean["observation_at"].dt.floor("D")

    rows = []
    for day, group in clean.groupby("day"):
        weighted_average = duration_weighted_mean(
            group["observation_at"].tolist(),
            group["value_numeric"].tolist(),
            day + timedelta(days=1),
        )
        if weighted_average is not None:
            rows.append(
                {"day": day, "weighted_average": round(weighted_average, 1)}
            )

    return pd.DataFrame(rows)


def compute_daily_weighted_averages(observations: pd.DataFrame) -> pd.DataFrame:
    """Per-station, per-day average weighted by how long each reading held.
    Used as the building block for weekly/monthly aggregates: averaging this
    day-by-day, instead of averaging raw readings directly, keeps days with
    denser sampling from outweighing days with sparser sampling within the
    same weekly/monthly average."""
    required_columns = {"station_name", "observation_at", "value_numeric"}
    if observations.empty or not required_columns.issubset(observations.columns):
        return pd.DataFrame(columns=["day", "station_name", "value_numeric"])

    clean = observations.dropna(
        subset=["observation_at", "value_numeric"]
    ).sort_values("observation_at").copy()
    if clean.empty:
        return pd.DataFrame(columns=["day", "station_name", "value_numeric"])

    clean["day"] = clean["observation_at"].dt.floor("D")

    rows = []
    for (day, station_name), group in clean.groupby(["day", "station_name"]):
        weighted_average = duration_weighted_mean(
            group["observation_at"].tolist(),
            group["value_numeric"].tolist(),
            day + timedelta(days=1),
        )
        if weighted_average is not None:
            rows.append(
                {
                    "day": day,
                    "station_name": station_name,
                    "value_numeric": weighted_average,
                }
            )

    return pd.DataFrame(rows)


def render_temperature_chart_with_overlays(
    full_df: pd.DataFrame,
    temp_df: pd.DataFrame,
    chart_stations: list,
    station_id_to_name: dict,
) -> None:
    """TARIA2M chart with optional heat index / duration-weighted daily average
    overlays, toggleable so they don't clutter the base temperature chart."""
    station_names = sorted(temp_df["station_name"].unique())
    colors = px.colors.qualitative.Plotly
    color_map = {
        name: colors[index % len(colors)] for index, name in enumerate(station_names)
    }

    overlay_col1, overlay_col2 = st.columns(2)
    with overlay_col1:
        show_heat_index = st.checkbox(
            "🌡️ Mostra indice di calore", key="show_heat_index_overlay"
        )
    with overlay_col2:
        show_weighted_avg = st.checkbox(
            "📅 Mostra media ponderata giornaliera", key="show_weighted_avg_overlay"
        )

    fig = px.line(
        temp_df,
        x="observation_at",
        y="value_numeric",
        color="station_name",
        color_discrete_map=color_map,
        title=var_label("TARIA2M"),
        labels={
            "observation_at": "Data/Ora",
            "value_numeric": f"{var_label('TARIA2M')} (°C)",
            "station_name": "Stazione",
        },
        markers=True,
    )

    if show_heat_index:
        humidity_df = full_df[
            (full_df["variable_type"] == "UMID2M") & full_df["value_numeric"].notna()
        ]
        for station_id in chart_stations:
            station_name = station_id_to_name.get(station_id)
            station_temp = temp_df[
                temp_df["station_id"] == station_id
            ].sort_values("observation_at")
            station_hum = humidity_df[
                humidity_df["station_id"] == station_id
            ].sort_values("observation_at")
            if station_name is None or station_temp.empty or station_hum.empty:
                continue

            merged = pd.merge_asof(
                station_temp[["observation_at", "value_numeric"]].rename(
                    columns={"value_numeric": "temperatura"}
                ),
                station_hum[["observation_at", "value_numeric"]].rename(
                    columns={"value_numeric": "umidita"}
                ),
                on="observation_at",
                tolerance=pd.Timedelta("30min"),
                direction="nearest",
            ).dropna(subset=["umidita"])
            if merged.empty:
                continue

            merged["indice_calore"] = heat_index_celsius(
                merged["temperatura"], merged["umidita"]
            )
            fig.add_trace(
                go.Scatter(
                    x=merged["observation_at"],
                    y=merged["indice_calore"],
                    mode="lines",
                    name=f"{station_name} - Indice di calore",
                    line=dict(color=color_map.get(station_name), dash="dot"),
                )
            )

    if show_weighted_avg:
        for station_id in chart_stations:
            station_name = station_id_to_name.get(station_id)
            if station_name is None:
                continue
            station_temp = temp_df[temp_df["station_id"] == station_id]
            weighted = compute_weighted_daily_temperature(station_temp)
            if weighted.empty:
                continue

            fig.add_trace(
                go.Scatter(
                    x=weighted["day"] + timedelta(hours=12),
                    y=weighted["weighted_average"],
                    mode="lines+markers",
                    name=f"{station_name} - Media pond. giornaliera",
                    line=dict(color=color_map.get(station_name), dash="dash", width=3),
                    marker=dict(size=8, symbol="diamond"),
                )
            )

    fig.update_layout(
        hovermode="x unified",
        height=430,
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


# Tabs
tab0, tab1, tab2, tab3, tab4 = st.tabs(
    [
        "📍 Panoramica",
        "📊 Dati",
        "⚙️ Stazioni",
        "📈 Grafici",
        "📅 Storico Annuale",
    ]
)

# TAB 0: Overview
with tab0:
    st.subheader("Panoramica Veneto")

    overview_stations_df = get_stations_from_db()
    nearest_df = find_nearest_stations(overview_stations_df)

    home_candidates = overview_stations_df[
        overview_stations_df["station_name"]
        .str.lower()
        .str.contains(HOME_STATION_HINT, na=False)
        & overview_stations_df["latitudine"].notna()
    ]

    home_row = None
    if not home_candidates.empty:
        home_row = home_candidates.iloc[0]
        home_entry = pd.DataFrame(
            [
                {
                    "label": "Mogliano Veneto (casa)",
                    "station_id": home_row["station_id"],
                    "station_name": home_row["station_name"],
                    "latitudine": home_row["latitudine"],
                    "longitudine": home_row["longitudine"],
                    "distanza_km": float("nan"),
                    "is_home": True,
                }
            ]
        )
        overview_points = pd.concat(
            [nearest_df, home_entry], ignore_index=True
        )
    else:
        overview_points = nearest_df

    if overview_points.empty:
        st.info(
            "Nessuna stazione con coordinate disponibili: aggiungi "
            "latitudine/longitudine in station_metadata per abilitare "
            "la mappa."
        )
    else:
        latest_temps = get_latest_temperatures(
            overview_points["station_id"].unique().tolist()
        )
        overview_points = overview_points.merge(
            latest_temps, on="station_id", how="left"
        )
        overview_points["temp_text"] = overview_points["value_numeric"].apply(
            lambda v: f"{v:.1f}°C" if pd.notna(v) else "n/d"
        )
        overview_points["distanza_km"] = overview_points["distanza_km"].round(1)

        map_col, info_col = st.columns([2, 1])

        with map_col:
            st.plotly_chart(
                build_overview_map(overview_points),
                use_container_width=True,
                config=PLOTLY_CONFIG,
            )

        with info_col:
            if home_row is not None:
                home_temp_row = latest_temps[
                    latest_temps["station_id"] == home_row["station_id"]
                ]
                if not home_temp_row.empty:
                    st.metric(
                        f"🌡️ {home_row['station_name']}",
                        f"{home_temp_row['value_numeric'].iloc[0]:.1f} °C",
                    )
                    st.caption(
                        "Rilevata alle "
                        + home_temp_row["observation_at"]
                        .iloc[0]
                        .strftime("%H:%M del %d/%m/%Y")
                    )
                else:
                    st.info(
                        "Nessuna temperatura recente per la stazione di casa"
                    )
            else:
                st.info(
                    "Nessuna stazione 'Mogliano Veneto' trovata: aggiungila "
                    "in Gestione Stazioni per vedere qui i dati di casa"
                )

            st.dataframe(
                overview_points[
                    ["label", "station_name", "distanza_km", "temp_text"]
                ].rename(
                    columns={
                        "label": "Zona",
                        "station_name": "Stazione",
                        "distanza_km": "Distanza (km)",
                        "temp_text": "Temperatura",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

        if home_row is not None:
            st.divider()
            st.subheader(f"Report — {home_row['station_name']}")
            st.markdown(
                build_station_report(
                    home_row["station_id"], home_row["station_name"]
                )
            )

            if pd.notna(home_row["latitudine"]) and pd.notna(home_row["longitudine"]):
                st.divider()
                st.subheader("☀️ Sole e durata del giorno")
                sun_times = compute_sun_times(
                    home_row["latitudine"],
                    home_row["longitudine"],
                    datetime.now().date(),
                )

                sunrise_col, noon_col, sunset_col = st.columns(3)
                sunrise_col.metric("🌅 Sorge", sun_times["sunrise"].strftime("%H:%M"))
                noon_col.metric("🕛 Culmina", sun_times["noon"].strftime("%H:%M"))
                sunset_col.metric("🌇 Tramonta", sun_times["sunset"].strftime("%H:%M"))

                day_col, night_col = st.columns(2)
                day_col.metric(
                    "☀️ Durata del giorno",
                    format_timedelta_hm(sun_times["day_length"]),
                )
                night_col.metric(
                    "🌙 Durata della notte",
                    format_timedelta_hm(sun_times["night_length"]),
                )


# TAB 1: Data View
with tab1:
    st.subheader("Visualizza Osservazioni")

    col1, col2, col3 = st.columns(3)

    with col1:
        days = st.slider(
            "Ultimi giorni",
            min_value=1,
            max_value=90,
            value=7,
        )

    stations_df = get_stations_from_db()
    stations_dict = {
        row["station_name"]: row["station_id"]
        for _, row in stations_df.iterrows()
    }
    station_names = ["Tutte"] + list(stations_dict.keys())

    with col2:
        selected_station_name = st.selectbox(
            "Stazione",
            station_names,
        )

    with col3:
        var_types = (
            get_observations_df(days=days)["variable_type"]
            .unique()
            .tolist()
        )
        var_types = sorted(["Tutte"] + var_types)
        selected_var = st.selectbox(
            "Tipo Variabile",
            var_types,
            format_func=lambda v: v if v == "Tutte" else var_label(v),
        )

    station_id = (
        None
        if selected_station_name == "Tutte"
        else stations_dict[selected_station_name]
    )
    variable_type = (
        None if selected_var == "Tutte" else selected_var
    )

    df = get_observations_df(
        station_id=station_id,
        variable_type=variable_type,
        days=days,
    )

    if not df.empty:
        st.dataframe(
            df.sort_values("observation_at", ascending=False),
            use_container_width=True,
        )
        st.info(
            f"Total records: {len(df)}"
        )
    else:
        st.warning("Nessun dato disponibile")


# TAB 2: Station Management
with tab2:
    st.subheader("Gestione Stazioni")

    config = load_stations_config()
    stations = config.get("stations", [])

    col1, col2 = st.columns([2, 1])

    with col1:
        st.write("### Stazioni Configurate")
        if stations:
            for idx, station in enumerate(stations):
                col_id, col_name, col_enabled, col_delete = st.columns(
                    [1, 2, 1, 0.5]
                )

                with col_id:
                    st.text_input(
                        f"ID #{idx}",
                        value=station.get("id", ""),
                        key=f"id_{idx}",
                        disabled=True,
                    )

                with col_name:
                    st.text_input(
                        f"Nome #{idx}",
                        value=station.get("name", ""),
                        key=f"name_{idx}",
                    )

                with col_enabled:
                    st.checkbox(
                        f"Abilitata #{idx}",
                        value=station.get("enabled", True),
                        key=f"enabled_{idx}",
                    )

                with col_delete:
                    if st.button("🗑️", key=f"del_{idx}"):
                        config["stations"].pop(idx)
                        save_stations_config(config)
                        st.rerun()

    with col2:
        st.write("### Aggiungi Stazione")

        new_id = st.text_input("ID Stazione")
        new_name = st.text_input("Nome Stazione")

        if st.button("✅ Aggiungi"):
            if new_id.strip():
                config["stations"].append(
                    {
                        "id": new_id.strip(),
                        "name": new_name.strip() or None,
                        "enabled": True,
                    }
                )
                save_stations_config(config)
                st.success("Stazione aggiunta!")
                st.rerun()
            else:
                st.error("ID richiesto")

    if st.button("💾 Salva Modifiche"):
        updated_config = {"stations": []}
        for idx, station in enumerate(config.get("stations", [])):
            updated_config["stations"].append(
                {
                    "id": station.get("id"),
                    "name": st.session_state.get(f"name_{idx}"),
                    "enabled": st.session_state.get(
                        f"enabled_{idx}",
                        True,
                    ),
                }
            )
        save_stations_config(updated_config)
        st.success("Configurazione salvata!")


# TAB 3: Charts
with tab3:
    st.subheader("Grafici")

    col1, col2 = st.columns([1, 2])

    with col1:
        chart_days = st.slider(
            "Giorni",
            min_value=1,
            max_value=90,
            value=7,
            key="chart_days",
        )
        stations_df = get_stations_from_db()
        stations_dict = {
            row["station_name"]: row["station_id"]
            for _, row in stations_df.iterrows()
        }
        station_names_list = list(stations_dict.keys())
        mogliano_name = next(
            (
                name
                for name in station_names_list
                if "mogliano" in name.lower()
            ),
            None,
        )
        if mogliano_name:
            default_stations = [mogliano_name]
        else:
            default_stations = (
                station_names_list[:3]
                if len(station_names_list) >= 3
                else station_names_list
            )

        chart_station_names = st.multiselect(
            "Stazioni",
            station_names_list,
            default=default_stations,
        )

    chart_stations = [
        stations_dict[name] for name in chart_station_names
    ]

    if chart_stations:
        df = get_observations_df(days=chart_days)
        df = df[df["station_id"].isin(chart_stations)]

        if not df.empty:
            var_types = sorted(df["variable_type"].unique())
            rendered_vars = set()

            def render_vars_in_order(vars_in_order):
                for var in vars_in_order:
                    if var not in var_types or var in rendered_vars:
                        continue
                    var_df = df[df["variable_type"] == var].copy()
                    if var_df["value_numeric"].notna().sum() == 0:
                        continue
                    render_line_chart(var_df, var)
                    rendered_vars.add(var)

            # 1. Temperatura aria (TARIA2M con overlay opzionali indice di
            # calore / media ponderata giornaliera; TARIA5M come al solito)
            if "TARIA2M" in var_types:
                taria2m_df = df[
                    (df["variable_type"] == "TARIA2M") & df["value_numeric"].notna()
                ].copy()
                if not taria2m_df.empty:
                    station_id_to_name = {
                        station_id: name for name, station_id in stations_dict.items()
                    }
                    render_temperature_chart_with_overlays(
                        df, taria2m_df, chart_stations, station_id_to_name
                    )
                rendered_vars.add("TARIA2M")

            render_vars_in_order(["TARIA5M"])

            # 2. Umidità
            render_vars_in_order(["UMID2M", "UMID5M"])

            # 3. Vento: velocità a barre con freccette di direzione
            for height in WIND_HEIGHTS:
                speed_var = f"VVENTO{height}"
                direction_var = f"DVENTO{height}"
                if speed_var not in var_types:
                    continue

                speed_df = df[
                    (df["variable_type"] == speed_var)
                    & df["value_numeric"].notna()
                ]
                if speed_df.empty:
                    continue

                direction_df = df[
                    (df["variable_type"] == direction_var)
                    & df["value_numeric"].notna()
                ]
                unit_values = speed_df["unit"].dropna()
                speed_unit = (
                    str(unit_values.iloc[0]) if not unit_values.empty else ""
                )

                st.plotly_chart(
                    build_wind_figure(
                        speed_df,
                        direction_df,
                        var_label(speed_var),
                        speed_unit,
                    ),
                    use_container_width=True,
                    config=PLOTLY_CONFIG,
                )
                rendered_vars.add(speed_var)
                rendered_vars.add(direction_var)

            # 4. Radiazione solare
            render_vars_in_order(["RADSOL"])

            # 5. Temperatura del suolo: tutte le profondità in un unico grafico
            soil_df = df[
                df["variable_type"].isin(SOIL_VARIABLES)
                & df["value_numeric"].notna()
            ]
            if not soil_df.empty:
                st.plotly_chart(
                    build_soil_figure(soil_df),
                    use_container_width=True,
                    config=PLOTLY_CONFIG,
                )
                rendered_vars.update(SOIL_VARIABLES)

            # 6. Precipitazione: istantanea + cumulata annua separata
            if "PREC" in var_types:
                prec_df = df[df["variable_type"] == "PREC"].copy()
                if prec_df["value_numeric"].notna().sum() > 0:
                    render_line_chart(prec_df, "PREC")
                    render_precipitation_cumulative(chart_stations)
                rendered_vars.add("PREC")

            # 7. Tutte le altre variabili, in ordine alfabetico per etichetta
            remaining_vars = sorted(
                (v for v in var_types if v not in rendered_vars),
                key=var_label,
            )
            render_vars_in_order(remaining_vars)

            st.divider()
            st.subheader("Medie e range temporali")
            st.caption(
                "Per ogni periodo vengono mostrati il valore minimo, la media "
                "e il valore massimo rilevati."
            )

            agg_col1, agg_col2 = st.columns([1, 2])
            with agg_col1:
                aggregation_period_days = st.selectbox(
                    "Periodo analizzato",
                    options=[90, 180, 365, 730, 1825],
                    index=2,
                    format_func=lambda value: {
                        90: "Ultimi 3 mesi",
                        180: "Ultimi 6 mesi",
                        365: "Ultimo anno",
                        730: "Ultimi 2 anni",
                        1825: "Ultimi 5 anni",
                    }[value],
                    key="aggregation_period_days",
                )

            aggregation_df = get_observations_df(
                days=aggregation_period_days
            )
            aggregation_df = aggregation_df[
                aggregation_df["station_id"].isin(chart_stations)
            ]
            numeric_aggregation_vars = sorted(
                aggregation_df.loc[
                    aggregation_df["value_numeric"].notna(), "variable_type"
                ].unique()
            )

            with agg_col2:
                if numeric_aggregation_vars:
                    default_aggregation_var = (
                        "TARIA2M"
                        if "TARIA2M" in numeric_aggregation_vars
                        else numeric_aggregation_vars[0]
                    )
                    selected_aggregation_var = st.selectbox(
                        "Variabile da aggregare",
                        numeric_aggregation_vars,
                        index=numeric_aggregation_vars.index(
                            default_aggregation_var
                        ),
                        format_func=var_label,
                        key="aggregation_variable",
                    )
                else:
                    selected_aggregation_var = None
                    st.info("Nessuna variabile numerica disponibile")

            if selected_aggregation_var:
                selected_aggregation_df = aggregation_df[
                    aggregation_df["variable_type"]
                    == selected_aggregation_var
                ]
                unit_values = selected_aggregation_df["unit"].dropna()
                aggregation_unit = (
                    str(unit_values.iloc[0]) if not unit_values.empty else ""
                )

                daily_aggregation = aggregate_observations(
                    selected_aggregation_df, "daily"
                )
                monthly_aggregation = aggregate_observations(
                    selected_aggregation_df, "monthly"
                )

                daily_col, monthly_col = st.columns(2)
                with daily_col:
                    if daily_aggregation.empty:
                        st.info("Nessun dato giornaliero disponibile")
                    else:
                        st.plotly_chart(
                            build_range_figure(
                                daily_aggregation,
                                f"{var_label(selected_aggregation_var)} - andamento giornaliero",
                                aggregation_unit,
                            ),
                            use_container_width=True,
                            config=PLOTLY_CONFIG,
                        )
                with monthly_col:
                    if monthly_aggregation.empty:
                        st.info("Nessun dato mensile disponibile")
                    else:
                        st.plotly_chart(
                            build_range_figure(
                                monthly_aggregation,
                                f"{var_label(selected_aggregation_var)} - andamento mensile",
                                aggregation_unit,
                            ),
                            use_container_width=True,
                            config=PLOTLY_CONFIG,
                        )
        else:
            st.warning("Nessun dato disponibile per il periodo selezionato")
    else:
        st.info("Seleziona almeno una stazione")


# TAB 4: Yearly / long-range history
with tab4:
    st.subheader("Storico Annuale")
    st.caption(
        "Medie e bande di oscillazione settimanali/mensili, e precipitazioni "
        "settimanali, mensili e cumulate a confronto tra anni."
    )

    col1, col2 = st.columns([1, 2])

    with col1:
        yearly_period_options = {
            "Ultimo anno": 365,
            "Ultimi 2 anni": 730,
            "Ultimi 3 anni": 1095,
            "Ultimi 5 anni": 1825,
            "Tutto lo storico": 3650,
        }
        selected_yearly_period = st.selectbox(
            "Periodo",
            list(yearly_period_options.keys()),
            index=1,
            key="yearly_period",
        )
        yearly_period_days = yearly_period_options[selected_yearly_period]

    stations_df = get_stations_from_db()
    stations_dict = {
        row["station_name"]: row["station_id"]
        for _, row in stations_df.iterrows()
    }
    station_names_list = list(stations_dict.keys())
    mogliano_name = next(
        (name for name in station_names_list if "mogliano" in name.lower()),
        None,
    )
    default_yearly_stations = (
        [mogliano_name] if mogliano_name else station_names_list[:1]
    )

    with col2:
        yearly_station_names = st.multiselect(
            "Stazioni",
            station_names_list,
            default=default_yearly_stations,
            key="yearly_stations",
        )

    yearly_stations = [
        stations_dict[name] for name in yearly_station_names
    ]

    if not yearly_stations:
        st.info("Seleziona almeno una stazione")
    else:
        yearly_df = get_observations_df(days=yearly_period_days)
        yearly_df = yearly_df[yearly_df["station_id"].isin(yearly_stations)]

        if yearly_df.empty:
            st.warning("Nessun dato disponibile per il periodo selezionato")
        else:
            st.divider()
            st.write("### Medie e oscillazione settimanale/mensile")

            numeric_vars = sorted(
                yearly_df.loc[
                    yearly_df["value_numeric"].notna()
                    & (yearly_df["variable_type"] != "PREC"),
                    "variable_type",
                ].unique()
            )

            if numeric_vars:
                default_yearly_var = (
                    "TARIA2M" if "TARIA2M" in numeric_vars else numeric_vars[0]
                )
                selected_yearly_var = st.selectbox(
                    "Variabile",
                    numeric_vars,
                    index=numeric_vars.index(default_yearly_var),
                    format_func=var_label,
                    key="yearly_variable",
                )

                yearly_var_df = yearly_df[
                    yearly_df["variable_type"] == selected_yearly_var
                ]
                unit_values = yearly_var_df["unit"].dropna()
                yearly_var_unit = (
                    str(unit_values.iloc[0]) if not unit_values.empty else ""
                )

                weekly_bands = aggregate_extremes_bands(
                    yearly_var_df, "weekly"
                )
                monthly_bands = aggregate_extremes_bands(
                    yearly_var_df, "monthly"
                )

                if weekly_bands.empty:
                    st.info("Nessun dato settimanale disponibile")
                else:
                    st.plotly_chart(
                        build_extremes_band_figure(
                            weekly_bands,
                            f"{var_label(selected_yearly_var)} - andamento settimanale",
                            yearly_var_unit,
                        ),
                        use_container_width=True,
                        config=PLOTLY_CONFIG,
                    )

                if monthly_bands.empty:
                    st.info("Nessun dato mensile disponibile")
                else:
                    st.plotly_chart(
                        build_extremes_band_figure(
                            monthly_bands,
                            f"{var_label(selected_yearly_var)} - andamento mensile",
                            yearly_var_unit,
                        ),
                        use_container_width=True,
                        config=PLOTLY_CONFIG,
                    )
            else:
                st.info(
                    "Nessuna variabile numerica disponibile per il periodo/"
                    "stazioni selezionati"
                )

            st.divider()
            st.write("### Precipitazioni")

            yearly_prec_df = yearly_df[
                yearly_df["variable_type"] == "PREC"
            ].copy()

            if yearly_prec_df.empty:
                st.info("Nessun dato di precipitazione disponibile")
            else:
                weekly_totals = aggregate_precipitation_totals(
                    yearly_prec_df, "weekly"
                )
                monthly_totals = aggregate_precipitation_totals(
                    yearly_prec_df, "monthly"
                )

                weekly_prec_col, monthly_prec_col = st.columns(2)
                with weekly_prec_col:
                    if weekly_totals.empty:
                        st.info("Nessun totale settimanale disponibile")
                    else:
                        st.plotly_chart(
                            build_precipitation_totals_figure(
                                weekly_totals, "Precipitazione settimanale"
                            ),
                            use_container_width=True,
                            config=PLOTLY_CONFIG,
                        )
                with monthly_prec_col:
                    if monthly_totals.empty:
                        st.info("Nessun totale mensile disponibile")
                    else:
                        st.plotly_chart(
                            build_precipitation_totals_figure(
                                monthly_totals, "Precipitazione mensile"
                            ),
                            use_container_width=True,
                            config=PLOTLY_CONFIG,
                        )

                # Year-over-year comparison always looks at full history,
                # regardless of the period picked above for the other charts.
                prec_history_df = get_observations_df(
                    days=3650, variable_type="PREC"
                )
                prec_history_df = prec_history_df[
                    prec_history_df["station_id"].isin(yearly_stations)
                ]
                if not prec_history_df.empty:
                    st.plotly_chart(
                        build_yearly_precipitation_comparison(prec_history_df),
                        use_container_width=True,
                        config=PLOTLY_CONFIG,
                    )
