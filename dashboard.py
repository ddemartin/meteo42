import logging
import math
import os
import sqlite3
import json
import base64
import html
import re
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
from PIL import Image, ImageDraw
from astral import LocationInfo, Observer, moon
from astral.moon import riseset
from astral.sun import elevation as sun_elevation, sun

try:
    import ephem
except ImportError:  # Keep the rest of the dashboard usable during upgrades.
    ephem = None

NAKED_EYE_PLANETS = (
    [
        ("Mercurio", ephem.Mercury),
        ("Venere", ephem.Venus),
        ("Marte", ephem.Mars),
        ("Giove", ephem.Jupiter),
        ("Saturno", ephem.Saturn),
    ]
    if ephem is not None
    else []
)
# Condivisi tra il grafico delle altezze e le schede dei pianeti visibili: il
# pallino della scheda e la linea del grafico devono essere lo stesso colore,
# altrimenti le due viste vanno rilette una alla volta.
PLANET_COLORS = {
    "Mercurio": "#A78BFA",
    "Venere": "#0EA5E9",
    "Marte": "#EF4444",
    "Giove": "#FB923C",
    "Saturno": "#EAB308",
}

import scrape

DEFAULT_DATABASE_PATH = os.environ.get(
    "ARPAV_DATABASE_PATH", "arpav_meteo.sqlite"
)
STATIONS_CONFIG = Path("stations.json")
DASHBOARD_CONFIG = Path(".dashboard_config.json")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")

st.set_page_config(
    page_title="Meteo42 dashboard",
    page_icon="🌤️",
    layout="wide",
)

st.title("🌤️ Meteo42 dashboard")

# Un solo foglio di stile per tutte le schede costruite a mano (panoramica,
# cielo, previsioni, diario).
#
# I colori NON escono dalle variabili di tema di Streamlit: `--primary-color`,
# `--background-color` e `--text-color` non esistono più (verificato su 1.60,
# dove `getComputedStyle` le dà vuote), e le regole che le usavano rendevano
# schede senza sfondo né bordo. Al loro posto grigio neutro a bassa opacità,
# che su fondo bianco e su fondo scuro funziona uguale, e `currentColor` per
# il testo secondario, che eredita il colore del tema qualunque esso sia.
#
# Le griglie sono `auto-fit`, non `st.columns`: le colonne di Streamlit restano
# affiancate anche a 390px di larghezza, la griglia CSS invece va a capo da
# sola. Vedi MEMORANDUM.md (2026-08-07).
M42_STYLESHEET = """
<style>
:root {
--m42-accent: #FF4B4B;
--m42-surface: rgba(128, 128, 128, 0.09);
--m42-border: rgba(128, 128, 128, 0.30);
--m42-tint: rgba(255, 75, 75, 0.10);
}
.m42-eyebrow {
display: block;
color: var(--m42-accent);
font-size: 0.74rem;
font-weight: 750;
letter-spacing: 0.06em;
text-transform: uppercase;
}
.m42-head { margin: 0.35rem 0 0.9rem; }
.m42-head h3 { margin: 0.2rem 0 0; font-size: clamp(1.15rem, 4.2vw, 1.5rem); }
.m42-head p {
margin: 0.3rem 0 0;
color: color-mix(in srgb, currentColor 58%, transparent);
font-size: 0.87rem;
line-height: 1.45;
max-width: 62ch;
}
.m42-grid {
display: grid;
gap: 0.6rem;
grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
margin: 0.2rem 0 0.5rem;
}
.m42-grid-wide { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.m42-tile {
padding: 0.8rem 0.9rem;
border: 1px solid var(--m42-border);
border-radius: 15px;
background: var(--m42-surface);
}
.m42-tile-label {
color: color-mix(in srgb, currentColor 58%, transparent);
font-size: 0.78rem;
font-weight: 650;
}
.m42-tile-value {
margin-top: 0.22rem;
font-size: clamp(1.25rem, 5.2vw, 1.55rem);
font-weight: 700;
line-height: 1.15;
font-variant-numeric: tabular-nums;
}
.m42-tile-sub {
margin-top: 0.22rem;
color: color-mix(in srgb, currentColor 58%, transparent);
font-size: 0.76rem;
line-height: 1.35;
}
.m42-hero {
padding: 1.05rem 1.15rem 1.15rem;
border: 1px solid var(--m42-border);
border-radius: 20px;
background: linear-gradient(140deg,
var(--m42-tint),
var(--m42-surface) 65%);
}
.m42-hero-main {
display: flex;
flex-wrap: wrap;
align-items: baseline;
gap: 0.1rem 0.85rem;
margin-top: 0.4rem;
}
.m42-hero-temp {
font-size: clamp(2.7rem, 13vw, 3.6rem);
font-weight: 800;
line-height: 1;
letter-spacing: -0.02em;
font-variant-numeric: tabular-nums;
}
.m42-hero-note {
color: color-mix(in srgb, currentColor 58%, transparent);
font-size: clamp(0.85rem, 3.4vw, 1rem);
font-weight: 650;
}
.m42-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.8rem; }
.m42-chip {
padding: 0.3rem 0.7rem;
border: 1px solid var(--m42-border);
border-radius: 999px;
background: rgba(128, 128, 128, 0.13);
font-size: 0.82rem;
white-space: nowrap;
}
.m42-chip b { font-weight: 750; font-variant-numeric: tabular-nums; }
.m42-stamp {
display: block;
margin-top: 0.75rem;
color: color-mix(in srgb, currentColor 58%, transparent);
font-size: 0.75rem;
}
.m42-planet {
display: flex;
align-items: center;
gap: 0.65rem;
padding: 0.7rem 0.85rem;
border: 1px solid var(--m42-border);
border-radius: 14px;
background: var(--m42-surface);
}
.m42-planet-dot { flex: 0 0 auto; width: 11px; height: 11px; border-radius: 50%; }
.m42-planet-body { flex: 1 1 auto; min-width: 0; }
.m42-planet-name { font-weight: 700; font-size: 0.95rem; }
.m42-planet-meta { color: color-mix(in srgb, currentColor 58%, transparent); font-size: 0.76rem; }
.m42-planet-alt { font-size: 1.15rem; font-weight: 750; font-variant-numeric: tabular-nums; }
.m42-note {
margin: 0.3rem 0 0.6rem;
padding: 0.85rem 1.05rem;
border-left: 4px solid var(--m42-accent);
border-radius: 0 14px 14px 0;
background: rgba(255, 75, 75, 0.08);
}
.m42-note p { margin: 0.3rem 0 0; line-height: 1.55; }
.forecast-grid {
display: grid;
grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
gap: 0.9rem;
margin: 0.35rem 0 0.7rem;
}
.forecast-card {
overflow: hidden;
border: 1px solid var(--m42-border);
border-radius: 18px;
background: var(--m42-surface);
}
.forecast-card-featured {
grid-column: 1 / -1;
border-color: rgba(255, 75, 75, 0.45);
}
/* La carta di oggi occupa tutta la riga, ma è quella con MENO mappe: quella
   del mattino sparisce col passare della giornata, e a fine pomeriggio ne
   resta una sola. In griglia `auto-fit` la traccia unica si prendeva tutta la
   larghezza e la mappa da 600px veniva stirata a ~960. Da qui in su mappe a
   sinistra e testo a destra: la larghezza la usa il testo, che è quello che
   si legge. Sotto questa soglia la carta resta impilata come le altre. */
@media (min-width: 820px) {
.forecast-card-featured {
display: grid;
grid-template-columns: minmax(260px, 340px) 1fr;
grid-template-areas: "head head" "maps copy";
align-items: start;
}
.forecast-card-featured header { grid-area: head; }
.forecast-card-featured .forecast-maps {
grid-area: maps;
grid-template-columns: 1fr;
}
.forecast-card-featured .forecast-copy { grid-area: copy; font-size: 0.95rem; }
}
.forecast-card header {
display: flex;
flex-wrap: wrap;
align-items: center;
gap: 0.5rem;
padding: 0.9rem 1rem 0.2rem;
}
.forecast-day {
color: var(--m42-accent);
font-size: 0.78rem;
font-weight: 750;
letter-spacing: 0.055em;
text-transform: uppercase;
}
.forecast-badge {
padding: 0.12rem 0.5rem;
border-radius: 999px;
background: var(--m42-accent);
color: #fff;
font-size: 0.68rem;
font-weight: 750;
letter-spacing: 0.05em;
text-transform: uppercase;
}
.forecast-maps {
display: grid;
grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
gap: 0.6rem;
padding: 0.65rem;
justify-items: center;
}
/* Le mappe ARPAV sono 600x600: oltre non si ingrandiscono, si sgranerebbero. */
.forecast-maps figure {
overflow: hidden;
margin: 0;
width: 100%;
max-width: 600px;
border-radius: 12px;
background: #edf3f5;
}
.forecast-maps img { display: block; width: 100%; height: auto; }
.forecast-maps figcaption {
padding: 0.42rem 0.65rem;
color: #425466;
font-size: 0.74rem;
font-weight: 650;
text-align: center;
text-transform: capitalize;
}
.forecast-copy { padding: 0.55rem 1rem 1.1rem; font-size: 0.91rem; line-height: 1.5; }
.weather-diary-story {
margin: 0.4rem 0 1rem;
padding: 1.15rem 1.25rem;
border-radius: 18px;
border: 1px solid var(--m42-border);
background: linear-gradient(135deg,
var(--m42-tint),
var(--m42-surface));
}
.weather-diary-story h3 { margin: 0.2rem 0 0.65rem; }
.weather-diary-story p { margin: 0; line-height: 1.58; }
.weather-diary-story small { display: block; margin-top: 0.75rem; opacity: 0.65; }
/* Con otto schede la barra deborda: si scorre in orizzontale, senza la barra
   di scorrimento che su desktop mangerebbe una riga sotto le linguette. */
.stTabs [data-baseweb="tab-list"] { overflow-x: auto; scrollbar-width: none; }
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
.stTabs [data-baseweb="tab"] { white-space: nowrap; }
</style>
"""
st.markdown(M42_STYLESHEET, unsafe_allow_html=True)

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
UTC_TIMEZONE = "UTC"
# ARPAV marca le osservazioni in ora solare (UTC+1) tutto l'anno, non in UTC e
# non in ora locale: nelle notti di cambio ora il database non ha né il buco di
# marzo né l'ora doppia di ottobre, e il picco di RADSOL cade sempre nello
# stesso slot orario a gennaio come a giugno.
DB_TIMEZONE = timezone(timedelta(hours=1))
ARPAV_RADAR_API_URL = "https://api.arpa.veneto.it/REST/v1/radar_imgs_geo"
ARPAV_RADAR_PAGE_URL = (
    "https://www.arpa.veneto.it/dati-ambientali/dati-in-diretta/"
    "radar/mosaico-radar-meteo"
)
ARPAV_FORECAST_URL = (
    "https://meteo.arpa.veneto.it/meteo/bollettini/it/xml/"
    "bollettino_utenti.xml"
)
ARPAV_FORECAST_BULLETIN_ID = "MV"
ARPAV_FORECAST_PAGE_URL = "https://meteo.arpa.veneto.it/?lang=it&page=MV"

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
PLOTLY_CONFIG = {
    "responsive": True,
    "displayModeBar": False,
    "scrollZoom": False,
    "doubleClick": False,
}


def render_chart(fig, **kwargs) -> None:
    """Show a read-only chart. Su schermo touch lo scroll della pagina finisce
    facilmente dentro al grafico e lo zooma o lo trascina, senza un modo ovvio
    di tornare indietro: gli assi sono bloccati e la barra degli strumenti è
    nascosta. Il tocco su un punto continua a mostrare il tooltip."""
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    fig.update_layout(dragmode=False)
    kwargs.setdefault("width", "stretch")
    st.plotly_chart(fig, config=PLOTLY_CONFIG, **kwargs)


def m42_section(title: str, eyebrow: str = "", subtitle: str = "") -> None:
    """Section heading with an optional kicker and one line of orientation."""
    parts = ['<div class="m42-head">']
    if eyebrow:
        parts.append(f'<span class="m42-eyebrow">{html.escape(eyebrow)}</span>')
    parts.append(f"<h3>{html.escape(title)}</h3>")
    if subtitle:
        parts.append(f"<p>{html.escape(subtitle)}</p>")
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def m42_tile(label: str, value: str, sub: str = "") -> str:
    """One stat tile, as HTML: `m42_render_tiles` puts a row of them on screen."""
    sub_html = f'<div class="m42-tile-sub">{html.escape(sub)}</div>' if sub else ""
    return (
        '<div class="m42-tile">'
        f'<div class="m42-tile-label">{html.escape(label)}</div>'
        f'<div class="m42-tile-value">{html.escape(value)}</div>'
        f"{sub_html}</div>"
    )


def m42_render_tiles(tiles: list[str], wide: bool = False) -> None:
    """Emit tiles as a single grid.

    Una sola chiamata a `st.markdown` per l'intera griglia: Streamlit chiude
    ogni markdown in un contenitore suo, e tessere emesse una per volta
    finirebbero in griglie diverse, ognuna larga tutta la pagina.
    """
    if not tiles:
        return
    grid_class = "m42-grid m42-grid-wide" if wide else "m42-grid"
    st.markdown(
        f'<div class="{grid_class}">{"".join(tiles)}</div>',
        unsafe_allow_html=True,
    )


def observation_series_to_local(series: pd.Series) -> pd.Series:
    """Interpret observation timestamps as ora solare and show them local."""
    return (
        pd.to_datetime(series)
        .dt.tz_localize(DB_TIMEZONE)
        .dt.tz_convert(HOME_TIMEZONE)
    )


def offset_series_to_local(series: pd.Series) -> pd.Series:
    """Convert timestamps already carrying their own UTC offset to local."""
    return pd.to_datetime(series, utc=True).dt.tz_convert(HOME_TIMEZONE)


@st.cache_data(ttl=5 * 60, show_spinner=False)
def get_latest_arpav_radar() -> dict | None:
    """Fetch the latest official ARPAV North-East radar mosaic."""
    response = requests.get(ARPAV_RADAR_API_URL, timeout=20)
    response.raise_for_status()
    frames = response.json().get("data", [])
    if not frames:
        return None

    latest = max(frames, key=lambda frame: frame.get("date", ""))
    image_data = latest.get("image")
    if not image_data:
        return None
    observed_at = pd.to_datetime(latest["date"], utc=True).tz_convert(HOME_TIMEZONE)
    return {
        "image": base64.b64decode(image_data),
        "observed_at": observed_at,
    }


def _bulletin_plain_text(raw_text: str) -> str:
    """Turn the small HTML fragment in the XML feed into safe plain text."""
    decoded = html.unescape(raw_text or "")
    decoded = re.sub(r"<br\s*/?>", "\n", decoded, flags=re.IGNORECASE)
    decoded = re.sub(r"<[^>]+>", "", decoded)
    return "\n".join(line.strip() for line in decoded.splitlines() if line.strip())


@st.cache_data(ttl=30 * 60, show_spinner=False)
def get_forecast_bulletin() -> dict | None:
    """Fetch the full Veneto plain-weather bulletin, maps included."""
    response = requests.get(ARPAV_FORECAST_URL, timeout=20)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    bulletin = next(
        (
            item
            for item in root.findall("./bollettini/bollettino")
            if item.get("bollettinoid") == ARPAV_FORECAST_BULLETIN_ID
        ),
        None,
    )
    if bulletin is None:
        return None

    days = []
    for day in bulletin.findall("giorno"):
        text_element = day.find("text")
        days.append(
            {
                "date": " ".join(day.get("data", "").split()),
                "text": _bulletin_plain_text(
                    text_element.text if text_element is not None else ""
                ),
                "images": [
                    {
                        "url": image.get("src", ""),
                        "caption": " ".join(image.get("caption", "").split()),
                    }
                    for image in day.findall("img")
                    if image.get("src")
                ],
            }
        )

    emission = root.find("data_emissione")
    evolution = bulletin.find("evoluzionegenerale")
    return {
        "title": bulletin.get("title", "Previsioni Veneto"),
        "emission": emission.get("date", "") if emission is not None else "",
        "evolution": _bulletin_plain_text(
            evolution.text if evolution is not None else ""
        ),
        "days": days,
    }


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def get_forecast_image_data_url(image_url: str) -> str:
    """Download a forecast map and return an embeddable data URL."""
    response = requests.get(image_url, timeout=15)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "image/jpeg").split(";")[0]
    encoded = base64.b64encode(response.content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def render_radar_nowcast() -> None:
    """Latest ARPAV radar mosaic: what is falling right now, before the forecast."""
    m42_section(
        "Radar precipitazioni Nord-Est",
        eyebrow="Adesso · nowcast",
        subtitle=(
            "Il mosaico ARPAV degli ultimi minuti. Intensità: verde debole, "
            "giallo moderata, rosso e viola forte."
        ),
    )
    try:
        radar = get_latest_arpav_radar()
    except requests.exceptions.RequestException:
        st.info("Radar momentaneamente non raggiungibile.")
    else:
        if radar is None:
            st.info("Immagine radar temporaneamente non disponibile.")
        else:
            st.image(radar["image"], width="stretch")
            st.caption(
                "Mosaico aggiornato alle "
                f"{radar['observed_at'].strftime('%H:%M del %d/%m/%Y')} "
                "(ora locale)."
            )
    st.link_button("Apri il radar originale", ARPAV_RADAR_PAGE_URL)


def render_forecast_bulletin() -> None:
    """Render the full forecast bulletin in responsive illustrated cards."""
    try:
        forecast = get_forecast_bulletin()
    except (requests.exceptions.RequestException, ET.ParseError):
        st.info("Bollettino momentaneamente non raggiungibile.")
        return
    if not forecast or not forecast["days"]:
        st.info("Previsioni momentaneamente non disponibili.")
        return

    if forecast["evolution"]:
        st.markdown(
            '<div class="m42-note">'
            '<span class="m42-eyebrow">Scenario</span>'
            f'<p>{html.escape(forecast["evolution"])}</p>'
            "</div>",
            unsafe_allow_html=True,
        )

    cards = []
    for index, day in enumerate(forecast["days"]):
        figures = []
        for image in day["images"]:
            try:
                image_src = get_forecast_image_data_url(image["url"])
            except requests.exceptions.RequestException:
                continue
            figures.append(
                "<figure>"
                f'<img src="{html.escape(image_src, quote=True)}" '
                f'alt="Previsione {html.escape(image["caption"], quote=True)}">'
                f'<figcaption>{html.escape(image["caption"])}</figcaption>'
                "</figure>"
            )
        forecast_text = html.escape(day["text"]).replace("\n", "<br><br>")
        # Il primo giorno occupa tutta la riga: è quello che si legge davvero,
        # e le sue mappe stanno affiancate invece che in colonna stretta.
        today_class = " forecast-card-featured" if index == 0 else ""
        badge = '<span class="forecast-badge">Oggi</span>' if index == 0 else ""
        cards.append(
            f'<article class="forecast-card{today_class}">'
            "<header>"
            f'<span class="forecast-day">{html.escape(day["date"])}</span>'
            f"{badge}</header>"
            f'<div class="forecast-maps">{"".join(figures)}</div>'
            f'<div class="forecast-copy">{forecast_text}</div>'
            "</article>"
        )

    st.markdown(
        '<div class="forecast-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Aggiornamento: {forecast['emission']}.")
    st.link_button("Apri il bollettino completo", ARPAV_FORECAST_PAGE_URL)


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
                raw_directory=scrape.DEFAULT_RAW_DIRECTORY,
                cloud_directory=scrape.DEFAULT_CLOUD_DIRECTORY,
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


@st.cache_data(ttl=60, show_spinner=False)
def get_weather_diary_dates() -> list:
    """Return local calendar dates having a bulletin or cloud frame."""
    conn = get_db_connection()
    try:
        bulletin_dates = {
            datetime.strptime(row[0], "%Y-%m-%d").date()
            for row in conn.execute(
                "SELECT weather_date FROM daily_weather_bulletins"
            ).fetchall()
        }
        cloud_rows = conn.execute(
            "SELECT observed_at_utc FROM cloud_type_images"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    cloud_dates = {
        datetime.fromisoformat(row[0])
        .astimezone(ZoneInfo(HOME_TIMEZONE))
        .date()
        for row in cloud_rows
    }
    return sorted(bulletin_dates | cloud_dates, reverse=True)


@st.cache_data(ttl=60, show_spinner=False)
def get_daily_weather_bulletin(weather_date) -> dict | None:
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT weather_date, issued_at, title, general_evolution
            FROM daily_weather_bulletins
            WHERE weather_date = ?
            """,
            (weather_date.isoformat(),),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    return dict(row) if row is not None else None


@st.cache_data(ttl=60, show_spinner=False)
def get_cloud_type_frames(weather_date) -> list[dict]:
    local_zone = ZoneInfo(HOME_TIMEZONE)
    start_local = datetime(
        weather_date.year,
        weather_date.month,
        weather_date.day,
        tzinfo=local_zone,
    )
    end_local = start_local + timedelta(days=1)
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT observed_at_utc, file_path
            FROM cloud_type_images
            WHERE observed_at_utc >= ? AND observed_at_utc < ?
            ORDER BY observed_at_utc
            """,
            (
                start_local.astimezone(timezone.utc).isoformat(timespec="seconds"),
                end_local.astimezone(timezone.utc).isoformat(timespec="seconds"),
            ),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    frames = []
    for row in rows:
        path = Path(row["file_path"])
        if not path.exists():
            continue
        observed_at = datetime.fromisoformat(row["observed_at_utc"])
        frames.append(
            {
                "path": str(path),
                "observed_at": observed_at.astimezone(local_zone),
            }
        )
    return frames


@st.cache_data(show_spinner=False)
def build_cloud_type_animation(
    frame_data: tuple[tuple[str, str], ...],
    duration_ms: int,
) -> bytes:
    """Compose archived hourly analyses into a looping labelled GIF."""
    frames = []
    for path_text, label in frame_data:
        with Image.open(path_text) as source:
            frame = source.convert("RGBA")
        overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        bar_height = max(30, frame.height // 15)
        draw.rectangle(
            (0, frame.height - bar_height, frame.width, frame.height),
            fill=(8, 18, 28, 190),
        )
        draw.text(
            (12, frame.height - bar_height + 8),
            label,
            fill=(255, 255, 255, 255),
        )
        labelled = Image.alpha_composite(frame, overlay).convert(
            "P", palette=Image.Palette.ADAPTIVE, colors=256
        )
        frames.append(labelled)
    if not frames:
        return b""
    output = BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return output.getvalue()


@st.cache_data(ttl=60, show_spinner=False)
def get_day_observations(station_id: str, weather_date) -> pd.DataFrame:
    """Read one civil Italian day from fixed-UTC+1 ARPAV timestamps."""
    local_zone = ZoneInfo(HOME_TIMEZONE)
    start_local = datetime(
        weather_date.year,
        weather_date.month,
        weather_date.day,
        tzinfo=local_zone,
    )
    end_local = start_local + timedelta(days=1)
    start_db = start_local.astimezone(DB_TIMEZONE).replace(tzinfo=None)
    end_db = end_local.astimezone(DB_TIMEZONE).replace(tzinfo=None)
    conn = get_db_connection()
    df = pd.read_sql_query(
        """
        SELECT observation_at, variable_type, value_numeric, unit
        FROM observations
        WHERE station_id = ?
          AND observation_at >= ?
          AND observation_at < ?
        ORDER BY observation_at
        """,
        conn,
        params=(
            station_id,
            start_db.strftime("%Y-%m-%d %H:%M:%S"),
            end_db.strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    if not df.empty:
        df["observation_at"] = observation_series_to_local(df["observation_at"])
    return df


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
        -- `now` è UTC, le osservazioni sono in ora solare: senza `+1 hour` la
        -- finestra sarebbe spostata di un'ora.
        WHERE observation_at >= datetime('now', '+1 hour', '-' || ? || ' days')
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
        df["observation_at"] = observation_series_to_local(df["observation_at"])
        if "downloaded_at" in df.columns:
            df["downloaded_at"] = offset_series_to_local(df["downloaded_at"])
    return df


@st.cache_data(ttl=60, show_spinner=False)
def observations_csv_bytes(
    station_id: str | None = None,
    variable_type: str | None = None,
    days: int = 7,
) -> bytes:
    """CSV della selezione corrente, pronto per `st.download_button`.

    Punto e virgola e BOM come separatore e codifica perché il consumo è
    Excel in locale italiano, dove la virgola è il separatore decimale.

    In cache perché `download_button` vuole i byte già pronti a ogni rerun:
    senza, ogni interazione con la pagina rigenererebbe l'export.
    """
    return (
        get_observations_df(
            station_id=station_id,
            variable_type=variable_type,
            days=days,
        )
        .to_csv(index=False, sep=";")
        .encode("utf-8-sig")
    )


def period_floor(timestamps: pd.Series, frequency: str) -> pd.Series:
    """Floor timestamps to the start of their day/week(Mon)/month period."""
    # Aggregations should use local calendar boundaries. Drop only the timezone
    # metadata after conversion, preserving the Europe/Rome wall-clock values.
    local_times = timestamps.dt.tz_localize(None)
    if frequency == "daily":
        return local_times.dt.floor("D")
    if frequency == "weekly":
        return local_times.dt.to_period("W-MON").dt.start_time
    return local_times.dt.to_period("M").dt.to_timestamp()


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
                    mode="lines",
                    line=dict(color=color, dash=dash, width=2.5),
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
    )
    fig.update_traces(line_width=2.5)
    fig.update_layout(
        hovermode="x unified",
        height=400,
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    render_chart(fig)


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
        local_times = numeric["observation_at"].dt.tz_localize(None)
        numeric["period"] = (
            local_times.dt.to_period("W-MON").dt.start_time
        )
    else:
        local_times = numeric["observation_at"].dt.tz_localize(None)
        numeric["period"] = (
            local_times.dt.to_period("M").dt.to_timestamp()
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
    render_chart(cumulative_fig)


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
        ],
    )


def find_home_station(stations_df: pd.DataFrame):
    """The home station row with usable coordinates, or None.

    Serve in più schede (panoramica, cielo, diario), che in Streamlit girano
    tutte a ogni rerun: la ricerca sta qui una volta sola.
    """
    candidates = stations_df[
        stations_df["station_name"]
        .str.lower()
        .str.contains(HOME_STATION_HINT, na=False)
        & stations_df["latitudine"].notna()
        & stations_df["longitudine"].notna()
    ]
    return None if candidates.empty else candidates.iloc[0]


def get_home_conditions(station_id: str) -> dict | None:
    """Latest reading of each headline variable, for the overview hero."""
    observations = get_observations_df(station_id=station_id, days=2)
    if observations.empty:
        return None

    latest = {}
    for variable in ("TARIA2M", "UMID2M", "VVENTO10M", "DVENTO10M", "PRESS"):
        readings = observations[
            (observations["variable_type"] == variable)
            & observations["value_numeric"].notna()
        ]
        if not readings.empty:
            row = readings.loc[readings["observation_at"].idxmax()]
            latest[variable] = (row["value_numeric"], row["observation_at"])

    if "TARIA2M" not in latest:
        return None

    today = datetime.now(ZoneInfo(HOME_TIMEZONE)).date()
    rain_today = observations[
        (observations["variable_type"] == "PREC")
        & observations["value_numeric"].notna()
        & (observations["observation_at"].dt.date == today)
    ]

    temperature, observed_at = latest["TARIA2M"]
    conditions = {
        "temperature": temperature,
        "observed_at": observed_at,
        "humidity": latest["UMID2M"][0] if "UMID2M" in latest else None,
        "wind_speed": latest["VVENTO10M"][0] if "VVENTO10M" in latest else None,
        "wind_direction": (
            latest["DVENTO10M"][0] if "DVENTO10M" in latest else None
        ),
        "pressure": latest["PRESS"][0] if "PRESS" in latest else None,
        "rain_today": (
            rain_today["value_numeric"].sum() if not rain_today.empty else None
        ),
        "perceived": None,
    }
    if conditions["humidity"] is not None:
        conditions["perceived"] = float(
            heat_index_celsius(temperature, conditions["humidity"])
        )
    return conditions


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
        df["observation_at"] = observation_series_to_local(df["observation_at"])
    return df


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

        yesterday_df = temp_df[
            temp_df["observation_at"].dt.date == (obs_time.date() - timedelta(days=1))
        ]
        if not yesterday_df.empty:
            y_max = yesterday_df.loc[yesterday_df["value_numeric"].idxmax()]
            lines.append(
                f"Ieri la massima è stata di {y_max['value_numeric']:.1f}°C "
                f"alle {y_max['observation_at'].strftime('%H:%M')}."
            )

    humidity_df = df_week[
        (df_week["variable_type"] == "UMID2M") & df_week["value_numeric"].notna()
    ].sort_values("observation_at")
    if not humidity_df.empty:
        lines.append(f"**Umidità**: {humidity_df.iloc[-1]['value_numeric']:.0f}%.")

    if not temp_df.empty and not humidity_df.empty:
        time_to_latest_temp = (
            humidity_df["observation_at"] - temp_df.iloc[-1]["observation_at"]
        ).abs()
        if time_to_latest_temp.min() <= timedelta(hours=1):
            closest_humidity = humidity_df.loc[
                time_to_latest_temp.idxmin(), "value_numeric"
            ]
            perceived = heat_index_celsius(
                temp_df.iloc[-1]["value_numeric"], closest_humidity
            )
            muggy_label = describe_muggy_level(perceived)
            if muggy_label:
                lines.append(f"**Percepito**: {perceived:.1f}°C ({muggy_label}).")

            wet_bulb = wet_bulb_temperature_celsius(
                temp_df.iloc[-1]["value_numeric"], closest_humidity
            )
            wet_bulb_risk = describe_wet_bulb_risk(wet_bulb)
            lines.append(
                f"**Bulbo umido stimato**: {wet_bulb:.1f}°C "
                f"({wet_bulb_risk})."
            )

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
            now_local = datetime.now(ZoneInfo(HOME_TIMEZONE))
            month_start = datetime(
                now_local.year,
                now_local.month,
                1,
                tzinfo=ZoneInfo(HOME_TIMEZONE),
            )
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


NARRATIVE_STYLE_HINTS = [
    "un breve bollettino colloquiale, come lo racconteresti a un amico",
    "un tono da cronista locale che osserva il cielo",
    "uno stile essenziale e diretto, quasi da messaggio vocale",
    "un tocco leggermente poetico ma sobrio, da chi ama osservare il tempo",
]


def current_narrative_style(cache_ttl_seconds: int = 1800) -> str:
    """Rotates the narration style roughly once per cache window, so repeated
    reports don't all read with the same structure."""
    bucket = int(datetime.now().timestamp() // cache_ttl_seconds)
    return NARRATIVE_STYLE_HINTS[bucket % len(NARRATIVE_STYLE_HINTS)]


@st.cache_data(ttl=1800, show_spinner="Genero il riassunto con l'AI...")
def generate_narrative_report(
    structured_report: str,
    station_name: str,
    historical_highlights: list[str],
    sun_context: str,
    style_hint: str,
) -> str:
    """Turn the templated report into a short natural-language summary via Ollama."""
    extra_context = ""
    if historical_highlights:
        extra_context += (
            "\nRecord/confronti storici (menzionane al massimo uno, solo se "
            "aggiunge qualcosa di interessante):\n- "
            + "\n- ".join(historical_highlights)
        )
    if sun_context:
        extra_context += f"\n\nSole e luna:\n{sun_context}"

    prompt = (
        "Sei un meteorologo che scrive per un pubblico non tecnico. "
        f"Riscrivi questi dati meteo per la stazione di {station_name} come un "
        "breve paragrafo discorsivo in italiano (massimo 4-5 frasi), con "
        f"{style_hint}. Varia la struttura e l'apertura della frase rispetto a "
        "un classico bollettino: non elencare sempre gli stessi dati nello "
        "stesso ordine. Puoi citare occasionalmente alba, tramonto o fase "
        "lunare, o un record storico, se pertinenti e interessanti — non è "
        "necessario includerli tutti insieme: se un dettaglio non entra in "
        "modo naturale e chiaro in una frase, omettilo piuttosto che "
        "forzarlo. Preferisci frasi brevi e comprensibili a frasi lunghe che "
        "accumulano troppe informazioni insieme. Puoi aggiungere un breve "
        "commento pratico (es. abbigliamento, ombrello) se pertinente. Non "
        "inventare numeri, eventi o condizioni (es. siccità, ondate di caldo "
        "passate, temporali) che non siano esplicitamente presenti nei dati "
        "forniti: attieniti solo a ciò che è scritto qui sotto. Non usare "
        "markdown.\n\n"
        f"Dati:\n{structured_report}{extra_context}"
    )
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.5},
        },
        timeout=90,
    )
    response.raise_for_status()
    return response.json()["response"].strip()


# --- Rianalisi ERA5-Land ----------------------------------------------------
#
# Il fondale climatico lungo (dal 1950) sta in un file suo per scelta
# (MEMORANDUM 2026-08-10): qui si apre in **sola lettura** e, quando serve
# incrociarlo con le osservazioni, si allega il DB operativo con `ATTACH`
# invece di fondere i due file.

ERA5_DATABASE_PATH = Path(
    os.environ.get("ERA5_DATABASE_PATH", "era5_land.sqlite")
)

# ERA5 registra in UTC, il resto della dashboard ragiona in ora solare fissa
# UTC+1 (MEMORANDUM 2026-08-02). Mesi e anni si raggruppano sull'ora locale:
# altrimenti gennaio comincerebbe alle 01:00 del primo giorno e ogni mese si
# porterebbe dietro un'ora di quello prima.
ERA5_LOCAL_OFFSET_SECONDS = 3600

# Le ricette pronte e i nomi dei mesi stanno in un modulo a parte per poterle
# eseguire tutte in un test senza tirarsi dietro Streamlit.
from era5_queries import (  # noqa: E402
    ITALIAN_MONTHS,
    ITALIAN_MONTHS_SHORT,
    catalogo_per_prompt,
    elimina_ricetta_utente,
    normalizza_parametri,
    parametri_da_sql,
    salva_ricetta_utente,
    schema_scelta,
    tutte_le_ricette,
)

# Il modello esterno per i compiti che il 9B locale non regge. Stessi nomi di
# variabili di brain42, che parla lo stesso dialetto OpenAI-compatibile, così
# la configurazione è una sola cosa da ricordare per entrambi i progetti.
#
# **Niente ricaduta automatica**, che è la regola scritta in brain42
# (MEMORANDUM 2026-08-03) e vale identica qui: chi chiede l'esterno lo chiede
# perché il locale non gli basta. Una dashboard che chiama da sola un'API a
# consumo quando il modello di casa incespica è un conto che cresce senza che
# nessuno l'abbia deciso.
LLM_EXTERNAL_BASE_URL = os.environ.get("LLM_EXTERNAL_BASE_URL")
LLM_EXTERNAL_MODEL = os.environ.get("LLM_EXTERNAL_MODEL", "gpt-5.6-luna")
LLM_EXTERNAL_API_KEY = os.environ.get("LLM_EXTERNAL_API_KEY")


def era5_esterno_configurato() -> bool:
    return bool(LLM_EXTERNAL_BASE_URL and LLM_EXTERNAL_MODEL)


def era5_connect_readonly(attach_observations: bool = False) -> sqlite3.Connection:
    """Sola lettura sulla rianalisi, con le osservazioni allegate a richiesta.

    Tre difese sovrapposte, perché da qui passa anche SQL scritto da un
    modello: `mode=ro` nell'URI, `PRAGMA query_only` e l'allegato anch'esso in
    `mode=ro`. Verificato che un `CREATE TABLE` sul database allegato fallisce
    con "attempt to write a readonly database".
    """
    conn = sqlite3.connect(
        f"file:{ERA5_DATABASE_PATH}?mode=ro", uri=True, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    if attach_observations and DATABASE_PATH.exists():
        conn.execute(
            "ATTACH DATABASE ? AS arpav", (f"file:{DATABASE_PATH}?mode=ro",)
        )
    return conn


@st.cache_data(ttl=600, show_spinner=False)
def get_era5_monthly() -> pd.DataFrame:
    """Una riga per mese: media oraria, estremi, pioggia e ore effettive.

    Le ore ERA5 durano tutte uguale, quindi la media semplice è già pesata
    sulla durata come vuole il MEMORANDUM (2026-07-30) — a differenza delle
    osservazioni, campionate a 10 minuti nel live e a un'ora nello storico.

    `ore` serve a riconoscere i mesi ancora incompleti: lo scaricamento dei 76
    anni dura giorni, e per tutto quel tempo l'ultimo mese è tronco. Un mese
    tronco in una media annua la falserebbe in silenzio.
    """
    if not ERA5_DATABASE_PATH.exists():
        return pd.DataFrame()
    conn = era5_connect_readonly()
    try:
        frame = pd.read_sql_query(
            """
            SELECT
                CAST(strftime('%Y', valid_at_utc + :offset, 'unixepoch') AS INTEGER)
                    AS anno,
                CAST(strftime('%m', valid_at_utc + :offset, 'unixepoch') AS INTEGER)
                    AS mese,
                AVG(temperature_c)          AS t_media,
                MIN(temperature_c)          AS t_min,
                MAX(temperature_c)          AS t_max,
                AVG(relative_humidity_pct)  AS rh_media,
                SUM(precipitation_mm)       AS prec_mm,
                COUNT(*)                    AS ore
            FROM weather_hourly
            GROUP BY anno, mese
            ORDER BY anno, mese
            """,
            conn,
            params={"offset": ERA5_LOCAL_OFFSET_SECONDS},
        )
    finally:
        conn.close()
    if frame.empty:
        return frame
    frame["ore_attese"] = [
        pd.Period(f"{anno}-{mese:02d}", freq="M").days_in_month * 24
        for anno, mese in zip(frame["anno"], frame["mese"])
    ]
    # Tolleranza di due ore, e servono entrambe per il primo mese del dataset:
    # una è quella che ERA5 non ha (a mezzanotte del 1950-01-01 manca la corsa
    # che la produrrebbe, MEMORANDUM 2026-08-10), l'altra la porta via lo
    # spostamento in ora locale, che fa cominciare il mese alle 02:00. Senza
    # tolleranza il 1950 sparirebbe da medie e confronti per due ore su 8760.
    # Non può nascondere un buco vero: il download valida ogni blocco sul
    # numero di messaggi, quindi i mesi interni non hanno ore mancanti.
    frame["completo"] = frame["ore"] >= frame["ore_attese"] - 2
    return frame


@st.cache_data(ttl=600, show_spinner=False)
def era5_media_ultimi_365_giorni() -> tuple[float, str] | None:
    """La media delle ultime 8.760 ore di archivio, con la data di fine.

    Non passa dagli anni completi come tutto il resto della scheda, e non è una
    contraddizione: la finestra è **lunga un anno per costruzione**, quindi
    contiene ogni stagione una volta sola e non ha lo squilibrio stagionale che
    rende falsa la media di un anno solare tronco. È l'unico modo di dire
    «com'è andato l'ultimo anno di dati» finché l'anno solare in corso non è
    finito.
    """
    if not ERA5_DATABASE_PATH.exists():
        return None
    conn = era5_connect_readonly()
    try:
        riga = conn.execute(
            """
            SELECT AVG(temperature_c) AS media,
                   -- Il secondo tolto è l'ora di chiusura: l'ultimo record
                   -- copre l'ora che comincia allora, e in ora locale quella
                   -- del 31 dicembre 23:00 UTC comincia il 1° gennaio. Senza,
                   -- la finestra si direbbe chiusa in un anno di cui non c'è
                   -- nemmeno un giorno.
                   date(MAX(valid_at_utc) + :offset - 1, 'unixepoch') AS fine,
                   COUNT(*) AS ore
            FROM weather_hourly
            WHERE valid_at_utc >
                  (SELECT MAX(valid_at_utc) FROM weather_hourly) - 365 * 86400
            """,
            {"offset": ERA5_LOCAL_OFFSET_SECONDS},
        ).fetchone()
    finally:
        conn.close()
    # Meno di un anno di dati: la finestra non è più lunga un anno e la media
    # varrebbe la stagione che ci è finita dentro, non il clima.
    if riga is None or riga["media"] is None or riga["ore"] < 8000:
        return None
    return float(riga["media"]), str(riga["fine"])


def era5_medie_per_decennio(yearly: pd.DataFrame) -> pd.DataFrame:
    """Una media per decennio, pesata sulle ore come quella annua.

    La media delle medie annue non sarebbe la stessa cosa: gli anni bisestili
    pesano un giorno in più, e un decennio tronco — il primo e l'ultimo
    dell'archivio — è fatto di meno anni. Il conteggio degli anni resta nella
    tabella perché è ciò che dice quanto ci si può fidare dello scalino.
    """
    if yearly.empty:
        return pd.DataFrame()
    decenni = yearly.assign(
        decennio=(yearly["anno"] // 10) * 10,
        _somma=yearly["t_media"] * yearly["ore"],
    ).groupby("decennio", as_index=False).agg(
        _somma=("_somma", "sum"),
        ore=("ore", "sum"),
        anni=("anno", "count"),
        primo=("anno", "min"),
        ultimo=("anno", "max"),
    )
    decenni["t_media"] = decenni["_somma"] / decenni["ore"]
    return decenni.drop(columns=["_somma"])


def era5_yearly_from_monthly(monthly: pd.DataFrame) -> pd.DataFrame:
    """Aggregati annui sui soli anni con dodici mesi completi."""
    if monthly.empty:
        return pd.DataFrame()
    complete = monthly[monthly["completo"]].copy()
    if complete.empty:
        return pd.DataFrame()
    complete["_somma"] = complete["t_media"] * complete["ore"]
    yearly = complete.groupby("anno", as_index=False).agg(
        _somma=("_somma", "sum"),
        ore=("ore", "sum"),
        prec_mm=("prec_mm", "sum"),
        t_min=("t_min", "min"),
        t_max=("t_max", "max"),
        mesi=("mese", "count"),
    )
    yearly["t_media"] = yearly["_somma"] / yearly["ore"]
    return yearly[yearly["mesi"] == 12].drop(columns=["_somma", "mesi"])


# --- Stile dei grafici della scheda Clima -----------------------------------
#
# Uno stile solo, applicato da `stile_clima` come ultimo passo di ogni figura
# invece di ripetere `update_layout` in ognuna. Cura quattro difetti osservati
# (MEMORANDUM 2026-08-13):
#  - i pallini su una serie continua non aggiungono niente e la ingrossano:
#    restano solo le linee, e il valore puntuale lo dà comunque il tooltip;
#  - le tacche automatiche dell'asse Y saltavano di 5 °C anche su una serie che
#    ne copre 9 — un luglio letto su una scala 15/20/25 non si legge;
#  - i mesi sull'asse X partivano dalla tacca che capitava (3, 6, 9…) invece
#    che dal primo valore;
#  - la legenda orizzontale finiva addosso al titolo dell'asse X.
# I titoli degli assi spariscono dove sono ovvi (mesi, anni) e l'unità di
# misura passa nel titolo del grafico: sotto al riquadro resta solo la legenda,
# che è anche il motivo per cui non si scontrano più.
CLIMATE_GRID_COLOR = "rgba(128, 128, 128, 0.20)"
CLIMATE_HEIGHT = 380
CLIMATE_LINE_WIDTH = 2.4
CLIMATE_WARM = "#EF4444"
CLIMATE_COOL = "#0EA5E9"
# I decenni sono ordinati, quindi vogliono una scala ordinata: freddo→caldo dal
# più vecchio al più recente. Con le tinte qualitative di `year_qualitative_color`
# — giuste altrove, dove un anno deve avere sempre lo stesso colore — lo
# spostamento del clima si vedeva solo leggendo la legenda.
CLIMATE_DECADE_SCALE = [
    "#1E40AF", "#3B82F6", "#0EA5E9", "#F59E0B", "#EF4444", "#991B1B",
]


def climate_decade_color(posizione: float) -> str:
    """Un colore della scala dei decenni, con `posizione` da 0 (vecchio) a 1."""
    scala = CLIMATE_DECADE_SCALE
    punto = min(max(posizione, 0.0), 1.0) * (len(scala) - 1)
    basso = int(math.floor(punto))
    alto = min(basso + 1, len(scala) - 1)
    frazione = punto - basso
    canali = []
    for indice in (0, 2, 4):
        inizio = int(scala[basso].lstrip("#")[indice : indice + 2], 16)
        fine = int(scala[alto].lstrip("#")[indice : indice + 2], 16)
        canali.append(round(inizio + (fine - inizio) * frazione))
    return "#{:02X}{:02X}{:02X}".format(*canali)


def passo_gradevole(intervallo: float, divisioni: int = 10) -> float:
    """Un passo «tondo» (1, 2 o 5 × 10^n) che divide l'intervallo in ~`divisioni`.

    Solo 1/2/5 e non 2.5: sulle temperature una scala che sale di 2,5 °C alla
    volta si legge peggio di una che ne salta 5, ed è il difetto che si voleva
    togliere, non spostare.
    """
    if not math.isfinite(intervallo) or intervallo <= 0:
        return 1.0
    grezzo = intervallo / max(divisioni, 1)
    esponente = math.floor(math.log10(grezzo))
    base = grezzo / 10**esponente
    for candidato in (1, 2, 5):
        if base <= candidato:
            return candidato * 10**esponente
    return 10 ** (esponente + 1)


def _valori_finiti(valori) -> list[float]:
    numeri = pd.to_numeric(pd.Series(list(valori)), errors="coerce").dropna()
    return [float(v) for v in numeri if math.isfinite(float(v))]


def stile_asse_y(fig: go.Figure, valori, *, da_zero: bool = False) -> None:
    """Tacche fitte quanto basta: ~10 divisioni tonde sull'intervallo dei dati."""
    finiti = _valori_finiti(valori)
    if not finiti:
        return
    minimo = min(finiti + ([0.0] if da_zero else []))
    massimo = max(finiti + ([0.0] if da_zero else []))
    passo = passo_gradevole(massimo - minimo)
    margine = 0 if da_zero else passo * 0.45
    fig.update_yaxes(
        tickmode="linear",
        tick0=math.floor(minimo / passo) * passo,
        dtick=passo,
        range=[minimo - margine, massimo + passo * 0.45],
    )


def stile_asse_x_numerico(fig: go.Figure, valori) -> None:
    """Su un asse di numeri interi le tacche partono dal primo valore.

    Mesi e giorni cominciano da 1: lasciata scegliere a Plotly, la prima tacca
    cadeva su 3 e la serie sembrava cominciare a marzo.
    """
    finiti = _valori_finiti(valori)
    if not finiti or any(valore % 1 for valore in finiti):
        return
    minimo, massimo = min(finiti), max(finiti)
    passo = max(1, round(passo_gradevole(massimo - minimo, divisioni=12)))
    fig.update_xaxes(tickmode="linear", tick0=minimo, dtick=passo)


def stile_clima(
    fig: go.Figure,
    *,
    etichette_x: list[str] | None = None,
    voci_di_legenda: int = 0,
    titolo_x: bool = False,
) -> go.Figure:
    """Lo stile comune, da chiamare per ultimo su ogni figura della scheda."""
    righe_legenda = math.ceil(voci_di_legenda / 3) if voci_di_legenda else 0
    sotto = (56 if titolo_x else 34) + 22 * righe_legenda
    fig.update_layout(
        height=CLIMATE_HEIGHT,
        # Il rosso e l'azzurro sono gli stessi delle figure fisse: in una serie
        # ricavata da una query la temperatura resta rossa e la pioggia azzurra.
        colorway=[
            CLIMATE_WARM, CLIMATE_COOL, "#8B5CF6",
            "#10B981", "#F59E0B", "#EC4899",
        ],
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        # `text` va ripetuto anche quando è vuoto: un `title` senza testo
        # arriva a plotly.js come `undefined`, e lì viene scritto sul grafico
        # per esteso, in grassetto, dove starebbe il titolo.
        title=dict(
            text=fig.layout.title.text or "",
            x=0,
            xanchor="left",
            font=dict(size=17),
        ),
        margin=dict(l=8, r=8, t=48, b=sotto),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.20 if titolo_x else -0.13,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        ),
        bargap=0.22,
    )
    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        showline=False,
        ticks="",
        automargin=True,
        tickfont=dict(size=12),
        title_font=dict(size=12),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=CLIMATE_GRID_COLOR,
        gridwidth=1,
        zeroline=False,
        showline=False,
        ticks="",
        automargin=True,
        tickfont=dict(size=12),
        title_font=dict(size=12),
    )
    if etichette_x is not None:
        # Tutte le etichette, sempre: su un asse di categorie Plotly ne salta
        # una sì e una no appena il riquadro si stringe.
        fig.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=etichette_x,
            tickmode="array",
            tickvals=list(range(len(etichette_x))),
            ticktext=etichette_x,
        )
    return fig


def build_era5_annual_temperature_figure(
    yearly: pd.DataFrame,
    *,
    decenni: bool = False,
    ultimi_365: tuple[float, str] | None = None,
) -> go.Figure:
    """La spezzata delle medie annue, con due strati che si accendono a parte.

    Spenti di default e non sempre presenti: il grafico di base risponde a una
    domanda sola — come sono andati gli anni — e chi vuole il confronto coi
    decenni o con l'ultimo anno di dati lo chiede. Tre linee sempre accese
    sarebbero tre linee da scartare ogni volta che se ne guarda una.
    """
    media = (yearly["t_media"] * yearly["ore"]).sum() / yearly["ore"].sum()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=yearly["anno"],
            y=yearly["t_media"],
            mode="lines",
            name="Media annua",
            line=dict(color=CLIMATE_WARM, width=CLIMATE_LINE_WIDTH),
            fill="tozeroy",
            fillcolor=hex_to_rgba(CLIMATE_WARM, 0.07),
            hovertemplate="%{x} · %{y:.2f} °C<extra></extra>",
        )
    )
    fig.add_hline(
        y=media,
        line_dash="dot",
        line_width=1.5,
        line_color="rgba(128, 128, 128, 0.75)",
        annotation_text=f"media del periodo · {media:.2f} °C",
        annotation_position="top left",
        annotation_font=dict(size=11),
    )

    valori_y = list(yearly["t_media"]) + [media]
    voci = 0
    if decenni:
        tabella = era5_medie_per_decennio(yearly)
        # `hv`: la media resta piatta per tutto il decennio e salta di netto a
        # quello dopo. È il disegno che dice la cosa vera — dentro il decennio
        # non c'è nessun andamento, c'è un unico numero — mentre unendo i
        # centri dei decenni con una retta si vedrebbe una pendenza inventata.
        passi_x = list(tabella["primo"]) + [yearly["anno"].max()]
        passi_y = list(tabella["t_media"]) + [tabella["t_media"].iloc[-1]]
        etichette = [
            f"{int(riga['primo'])}-{int(riga['ultimo'])} · {int(riga['anni'])} anni"
            for _, riga in tabella.iterrows()
        ]
        fig.add_trace(
            go.Scatter(
                x=passi_x,
                y=passi_y,
                mode="lines",
                name="Media del decennio",
                line=dict(
                    color="rgba(30, 41, 59, 0.85)",
                    width=1.8,
                    shape="hv",
                ),
                customdata=etichette + [etichette[-1]],
                hovertemplate="%{customdata} · %{y:.2f} °C<extra></extra>",
            )
        )
        valori_y += list(tabella["t_media"])
        voci += 1

    if ultimi_365 is not None:
        valore, fine = ultimi_365
        fig.add_hline(
            y=valore,
            line_dash="dash",
            line_width=1.5,
            line_color=CLIMATE_WARM,
            annotation_text=f"ultimi 365 giorni · {valore:.2f} °C",
            annotation_position="bottom right",
            annotation_font=dict(size=11, color=CLIMATE_WARM),
            annotation_hovertext=f"365 giorni fino al {fine}",
        )
        valori_y.append(valore)

    fig.update_layout(
        title="Temperatura media annua · °C", showlegend=bool(voci)
    )
    stile_clima(fig, voci_di_legenda=voci + 1 if voci else 0)
    stile_asse_y(fig, valori_y)
    stile_asse_x_numerico(fig, yearly["anno"])
    return fig


def build_era5_annual_precipitation_figure(yearly: pd.DataFrame) -> go.Figure:
    media = yearly["prec_mm"].mean()
    fig = go.Figure(
        go.Bar(
            x=yearly["anno"],
            y=yearly["prec_mm"],
            marker=dict(color=CLIMATE_COOL, cornerradius=3),
            name="Totale annuo",
            hovertemplate="%{x} · %{y:.0f} mm<extra></extra>",
        )
    )
    fig.add_hline(
        y=media,
        line_dash="dot",
        line_width=1.5,
        line_color="rgba(128, 128, 128, 0.75)",
        annotation_text=f"media del periodo · {media:.0f} mm",
        annotation_position="top left",
        annotation_font=dict(size=11),
    )
    fig.update_layout(
        title="Precipitazione annua · mm",
        showlegend=False,
    )
    stile_clima(fig)
    stile_asse_y(fig, yearly["prec_mm"], da_zero=True)
    stile_asse_x_numerico(fig, yearly["anno"])
    return fig


def build_era5_monthly_climatology_figure(monthly: pd.DataFrame) -> go.Figure:
    """Ciclo annuale medio, con la banda tra l'anno più freddo e il più caldo.

    La banda è la dispersione delle **medie mensili tra gli anni**, non gli
    estremi orari: dice quanto può spostarsi un gennaio da un anno all'altro,
    che è la domanda climatica. Gli estremi assoluti stanno nelle tessere.
    """
    complete = monthly[monthly["completo"]]
    stats = complete.groupby("mese", as_index=False).agg(
        media=("t_media", "mean"),
        minimo=("t_media", "min"),
        massimo=("t_media", "max"),
    )
    labels = [ITALIAN_MONTHS_SHORT[mese - 1] for mese in stats["mese"]]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=stats["massimo"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=stats["minimo"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor=hex_to_rgba(CLIMATE_WARM, 0.13),
            name="Tra l'anno più freddo e il più caldo",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=stats["media"],
            mode="lines",
            line=dict(color=CLIMATE_WARM, width=CLIMATE_LINE_WIDTH),
            name="Media del mese",
            hovertemplate="%{x} · %{y:.2f} °C<extra></extra>",
        )
    )
    fig.update_layout(title="Ciclo annuale della temperatura · °C")
    stile_clima(fig, etichette_x=labels, voci_di_legenda=2)
    stile_asse_y(fig, list(stats["minimo"]) + list(stats["massimo"]))
    return fig


def build_era5_decade_profile_figure(monthly: pd.DataFrame) -> go.Figure:
    """Un ciclo annuale per decennio: è qui che si vede se il clima si sposta."""
    complete = monthly[monthly["completo"]].copy()
    complete["decennio"] = (complete["anno"] // 10) * 10
    complete["_somma"] = complete["t_media"] * complete["ore"]
    grouped = complete.groupby(["decennio", "mese"], as_index=False)[
        ["_somma", "ore"]
    ].sum()
    grouped["t_media"] = grouped["_somma"] / grouped["ore"]

    fig = go.Figure()
    decenni = sorted(grouped["decennio"].unique())
    ultimo = len(decenni) - 1
    for posizione, decennio in enumerate(decenni):
        block = grouped[grouped["decennio"] == decennio]
        # L'ultimo decennio è quello che si va a guardare: resta pieno, gli
        # altri arretrano di spessore invece di gareggiare con lui.
        recente = posizione == ultimo
        fig.add_trace(
            go.Scatter(
                x=[ITALIAN_MONTHS_SHORT[mese - 1] for mese in block["mese"]],
                y=block["t_media"],
                mode="lines",
                name=f"{decennio}-{str(decennio + 9)[-2:]}",
                line=dict(
                    color=climate_decade_color(
                        posizione / ultimo if ultimo else 1.0
                    ),
                    width=CLIMATE_LINE_WIDTH + (0.8 if recente else 0),
                ),
                opacity=1.0 if recente else 0.85,
                hovertemplate="%{x} · %{y:.2f} °C<extra></extra>",
            )
        )
    fig.update_layout(title="Ciclo annuale per decennio · °C")
    stile_clima(
        fig,
        etichette_x=list(ITALIAN_MONTHS_SHORT),
        voci_di_legenda=len(decenni),
    )
    stile_asse_y(fig, grouped["t_media"])
    return fig


# --- Interrogazione del database in linguaggio naturale ---------------------
#
# Il modello **propone** l'SQL, non lo esegue: la dashboard lo mostra, lo
# lascia correggere e lo esegue solo su conferma esplicita. È il compromesso
# scelto contro il text-to-SQL diretto, dove una query sbagliata restituisce
# un numero plausibile e falso — esattamente ciò che il MEMORANDUM
# (2026-07-31) vuole impedire al riassunto AI.

ERA5_SQL_SCHEMA = """\
Database principale (rianalisi ERA5-Land, una sola cella di griglia):
  weather_hourly(grid_point_id, valid_at_utc, temperature_c, dewpoint_c,
                 relative_humidity_pct, precipitation_accumulated_mm,
                 precipitation_mm)
    - una riga per ora; valid_at_utc e' Unix time in UTC
    - precipitation_mm e' la pioggia della singola ora, ed e' quella da sommare
    - precipitation_accumulated_mm e' l'accumulo grezzo dall'inizio della corsa
      di previsione: NON va sommato
    - la pioggia di un anno e' la SOMMA di precipitation_mm su quell'anno; la
      "media annua di pioggia" e' la media di quelle somme tra gli anni, mai
      la media delle singole ore, che darebbe frazioni di millimetro
  grid_points(grid_point_id, latitude, longitude)
  imports(source_path, sha256, first_valid_at_utc, last_valid_at_utc,
          message_count, value_count)

Database allegato con le osservazioni ARPAV, sempre col prefisso "arpav.":
  arpav.observations(station_id, observation_at, variable_type, station_name,
                     value_numeric, unit)
    - observation_at e' testo ISO in ora solare fissa UTC+1, tutto l'anno
    - variable_type: TARIA2M temperatura, PREC pioggia, UMID umidita'
  arpav.stations(station_id, configured_name, api_name, enabled)

Attenzione: lo scaricamento dello storico e' in corso, quindi l'ultimo anno
puo' essere parziale. Una media annua calcolata su un anno parziale e' falsa
(mancano i mesi freddi o caldi che non sono ancora stati scaricati): per medie,
massimi e minimi annui filtra sempre agli anni completi elencati qui sotto.

Per raggruppare le ore ERA5 per giorno/mese/anno locale:
  strftime('%Y', valid_at_utc + 3600, 'unixepoch')
Per confrontare le due sorgenti il timestamp ERA5 va portato in ora locale
nello stesso modo. ERA5 parte dal 1950, le osservazioni ARPAV dal 2010: prima
del 2010 il confronto non e' possibile.

Esempi di query corrette (gli anni vanno sostituiti con quelli effettivamente
disponibili, indicati piu' sotto):

D: Qual e' stato l'anno piu' caldo?
Q: SELECT strftime('%Y', valid_at_utc + 3600, 'unixepoch') AS anno,
          AVG(temperature_c) AS media
   FROM weather_hourly
   WHERE strftime('%Y', valid_at_utc + 3600, 'unixepoch') BETWEEN '1950' AND '1960'
   GROUP BY anno ORDER BY media DESC LIMIT 1

D: Quanta pioggia cade in media ogni anno?
Q: WITH per_anno AS (
     SELECT strftime('%Y', valid_at_utc + 3600, 'unixepoch') AS anno,
            SUM(precipitation_mm) AS mm
     FROM weather_hourly
     WHERE strftime('%Y', valid_at_utc + 3600, 'unixepoch') BETWEEN '1950' AND '1960'
     GROUP BY anno)
   SELECT AVG(mm) AS media_mm_anno FROM per_anno

D: Com'e' il ciclo annuale della temperatura?
Q: SELECT CAST(strftime('%m', valid_at_utc + 3600, 'unixepoch') AS INTEGER) AS mese,
          AVG(temperature_c) AS media
   FROM weather_hourly GROUP BY mese ORDER BY mese

Un'aggregazione di aggregazioni si scrive sempre con WITH, come nel secondo
esempio: SQLite rifiuta AVG(SUM(...)).
"""

# `mode=ro` e `query_only` bloccano già le scritture; questo elenco serve a
# rifiutare la query *prima* di eseguirla, con un motivo leggibile, invece di
# lasciare che fallisca a metà con un errore di SQLite.
ERA5_SQL_FORBIDDEN = re.compile(
    r"\b(attach|detach|pragma|insert|update|delete|drop|create|alter|"
    r"replace|vacuum|reindex|trigger)\b",
    re.IGNORECASE,
)


def era5_strip_sql_fences(text: str) -> str:
    """Toglie i recinti markdown che il modello aggiunge nonostante le istruzioni."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def era5_validate_sql(sql: str) -> str | None:
    """Il motivo del rifiuto, oppure None se la query è accettabile."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return "la query è vuota"
    if ";" in stripped:
        return "la query contiene più istruzioni separate da punto e virgola"
    if not re.match(r"^(select|with)\b", stripped, re.IGNORECASE):
        return "la query non inizia con SELECT o WITH"
    forbidden = ERA5_SQL_FORBIDDEN.search(stripped)
    if forbidden:
        return f"parola chiave non ammessa: {forbidden.group(0).upper()}"
    return None


def era5_propose_sql(
    question: str, coverage_hint: str, esterno: bool = False
) -> str:
    istruzioni = (
        "Traduci la domanda in una query SQLite di sola lettura. Rispondi con "
        "una sola istruzione SELECT (eventualmente preceduta da WITH), senza "
        "punto e virgola, senza commenti e senza blocchi markdown: soltanto "
        "l'SQL. Non inventare tabelle o colonne che non siano nello schema. "
        "Se la domanda può restituire molte righe, aggiungi un LIMIT."
    )
    contesto = (
        f"Schema:\n{ERA5_SQL_SCHEMA}\n"
        f"Dati attualmente disponibili: {coverage_hint}\n\n"
        f"Domanda: {question}"
    )
    if esterno:
        return era5_strip_sql_fences(
            era5_chiama_esterno(istruzioni, contesto)
        )

    prompt = f"{istruzioni}\n\n{contesto}\nSQL:"
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "think": False,
            # Bassa come per il riassunto: qui non si vuole varietà, si vuole
            # la stessa query per la stessa domanda.
            "options": {"temperature": 0.1},
        },
        timeout=90,
    )
    response.raise_for_status()
    return era5_strip_sql_fences(response.json()["response"])


def era5_run_query(
    sql: str,
    params: dict | None = None,
    timeout_seconds: float = 15.0,
    max_rows: int = 2000,
) -> tuple[pd.DataFrame, bool]:
    """Esegue la query e dice se il risultato è stato troncato.

    Il tetto alle righe si applica leggendo il cursore, non riscrivendo l'SQL:
    aggiungere un LIMIT a una query altrui ne cambierebbe il senso senza dirlo.
    """
    conn = era5_connect_readonly(attach_observations=True)
    deadline = time.monotonic() + timeout_seconds
    # Una scansione delle 671.000 ore senza indice bloccherebbe la pagina a
    # tempo indeterminato: il progress handler interrompe la query invece di
    # lasciare girare la clessidra.
    conn.set_progress_handler(
        lambda: 1 if time.monotonic() > deadline else 0, 20000
    )
    try:
        cursor = conn.execute(sql, params or {})
        columns = [column[0] for column in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        frame = pd.DataFrame(
            [tuple(row) for row in rows[:max_rows]], columns=columns
        )
        return frame, truncated
    finally:
        conn.set_progress_handler(None, 0)
        conn.close()


# Colonne che si disegnano a barre e non a linea: una pioggia oraria o
# giornaliera è una quantità che cade in un intervallo, non una grandezza che
# esiste fra un punto e l'altro. Unire con una linea due giorni piovosi
# suggerirebbe che sia piovuto anche nel mezzo.
ERA5_COLONNE_A_BARRE = re.compile(r"pioggia|prec|_mm$|mm$", re.IGNORECASE)


def era5_e_una_serie(valori: pd.Series) -> bool:
    """Dice se le righe procedono lungo l'asse orizzontale.

    Sei ricette della libreria sono una **classifica** — `ORDER BY media DESC
    LIMIT 15` — e restituiscono gli anni in ordine di temperatura: 1950, 1994, 1983,
    1952… Unirli con una linea disegna segmenti fra anni che nel tempo non si
    toccano e fa sparire in silenzio i cinquanta anni rimasti fuori dalla
    classifica: il grafico che ne esce non si legge, e quel poco che si legge
    è falso. Una classifica non è una serie, è un elenco ordinato, e si guarda
    nell'ordine in cui è arrivata.

    Il criterio è la monotonia dell'asse X e non il testo dell'SQL: vale anche
    per una query scritta a mano nella casella dell'SQL libero.
    """
    puliti = valori.dropna()
    if len(puliti) < 3:
        return True
    return bool(
        puliti.is_monotonic_increasing or puliti.is_monotonic_decreasing
    )


def era5_figura_risultato(
    frame: pd.DataFrame,
    colonna_x: str,
    colonne_y: list[str],
    tipo: str,
) -> go.Figure:
    """Disegna il risultato di una query, tenendo separate le unità di misura.

    Quando nella stessa tabella ci sono temperature e pioggia — cosa normale,
    la serie giornaliera di un mese le ha entrambe — su un asse solo i gradi
    stanno fra -20 e 35 e i millimetri fra 0 e 80: il grafico si legge male e
    suggerisce confronti che non esistono. La pioggia va allora sull'asse
    destro, a barre, e le temperature restano linee a sinistra. È il
    meteogramma di sempre, e qui viene da sé perché i due gruppi si
    riconoscono dal nome della colonna.
    """
    colonne_mm = [c for c in colonne_y if ERA5_COLONNE_A_BARRE.search(c)]
    colonne_altre = [c for c in colonne_y if c not in colonne_mm]
    doppio_asse = bool(colonne_mm) and bool(colonne_altre)
    classifica = not era5_e_una_serie(frame[colonna_x])
    if classifica or doppio_asse:
        # Due casi, stessa divisione delle colonne. Con due unità: pioggia a
        # barre a destra, temperature a linee a sinistra. In una classifica:
        # l'ordine delle righe non è quello dell'asse, quindi niente linee —
        # i gradi diventano punti su un asse di categorie — e restano a barre
        # solo le colonne con uno zero vero, i millimetri. Una barra dice
        # "quanto", e 0 °C non è un'assenza di temperatura ma una convenzione:
        # da zero, una classifica di luglio fra 23 e 26 °C sarebbe una fila di
        # barre tutte uguali.
        a_barre, a_linee = colonne_mm, colonne_altre
    else:
        # Un gruppo solo: comanda la scelta di chi guarda.
        a_barre = colonne_y if tipo == "Barre" else []
        a_linee = [] if tipo == "Barre" else colonne_y

    valori_x = frame[colonna_x].astype(str) if classifica else frame[colonna_x]

    fig = go.Figure()
    for colonna in a_linee:
        fig.add_trace(
            go.Scatter(
                x=valori_x,
                y=frame[colonna],
                name=colonna,
                mode="markers" if classifica else "lines",
                marker=dict(size=9),
                line=dict(width=CLIMATE_LINE_WIDTH),
                hovertemplate="%{x} · %{y}<extra>" + colonna + "</extra>",
            )
        )
    for colonna in a_barre:
        # A destra ci va la pioggia, e solo lei: in una classifica anche le
        # temperature sono barre, ma restano gradi sull'asse di sinistra.
        a_destra = doppio_asse and colonna in colonne_mm
        fig.add_trace(
            go.Bar(
                x=valori_x,
                y=frame[colonna],
                name=colonna,
                yaxis="y2" if a_destra else "y",
                marker=dict(
                    color=CLIMATE_COOL if a_destra else None,
                    cornerradius=3,
                ),
                opacity=0.65 if a_destra else 1.0,
                hovertemplate="%{x} · %{y}<extra>" + colonna + "</extra>",
            )
        )

    fig.update_layout(
        xaxis_title=colonna_x,
        yaxis_title=colonne_y[0] if len(colonne_y) == 1 else "",
        barmode="group",
        showlegend=len(colonne_y) > 1,
    )
    stile_clima(
        fig,
        etichette_x=list(valori_x) if classifica else None,
        voci_di_legenda=len(colonne_y) if len(colonne_y) > 1 else 0,
        titolo_x=True,
    )
    if doppio_asse:
        fig.update_layout(
            yaxis_title="°C",
            yaxis2=dict(
                title="mm",
                overlaying="y",
                side="right",
                showgrid=False,
                rangemode="tozero",
                automargin=True,
                title_font=dict(size=12),
                tickfont=dict(size=12),
            ),
        )
        stile_asse_y(fig, pd.concat([frame[c] for c in colonne_altre]))
    else:
        stile_asse_y(
            fig,
            pd.concat([frame[c] for c in colonne_y]),
            da_zero=bool(a_barre),
        )

    if classifica:
        # L'asse è di categorie: non ha tacche da scegliere né mesi da
        # tradurre, e le etichette le ha già messe `stile_clima`.
        return fig

    # Le tacche dell'asse X: un mese porta il suo nome, e ogni altra serie di
    # numeri interi comincia dal primo valore invece che dalla tacca che capita.
    numeri_x = pd.to_numeric(frame[colonna_x], errors="coerce").dropna()
    mesi = (
        re.fullmatch(r"mes[ei]|month", colonna_x, re.I)
        and not numeri_x.empty
        and numeri_x.between(1, 12).all()
        and not (numeri_x % 1).any()
    )
    if mesi:
        presenti = sorted({int(v) for v in numeri_x})
        fig.update_xaxes(
            tickmode="array",
            tickvals=presenti,
            ticktext=[ITALIAN_MONTHS_SHORT[mese - 1] for mese in presenti],
        )
    else:
        stile_asse_x_numerico(fig, frame[colonna_x])
    return fig


def era5_chiama_esterno(
    sistema: str,
    utente: str,
    schema: dict | None = None,
    temperatura: float = 0.1,
) -> str:
    """Una richiesta al modello esterno, dialetto OpenAI-compatibile.

    `reasoning_effort: "none"` perché questi sono lavori meccanici — scegliere
    da un elenco, riscrivere numeri in una frase — e i livelli più alti si
    alzano quando un compito sbaglia per aver pensato troppo poco, non per
    sicurezza: alzarli senza una misura vuol dire pagare di più per un
    miglioramento mai osservato (brain42, MEMORANDUM 2026-08-03).
    """
    payload = {
        "model": LLM_EXTERNAL_MODEL,
        "temperature": temperatura,
        "reasoning_effort": "none",
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": utente},
        ],
    }
    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "scelta",
                "strict": True,
                "schema": schema,
            },
        }
    headers = {}
    if LLM_EXTERNAL_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_EXTERNAL_API_KEY}"
    response = requests.post(
        f"{LLM_EXTERNAL_BASE_URL.rstrip('/')}/chat/completions",
        json=payload,
        headers=headers,
        timeout=90,
    )
    response.raise_for_status()
    dati = response.json()
    try:
        return dati["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as errore:
        raise ValueError(f"risposta inattesa dal modello: {dati!r}") from errore


def era5_chiave_parametro(ricetta: dict, parametro: dict) -> str:
    """Chiave del widget, distinta per ricetta.

    Senza l'identificativo della ricetta nella chiave, `soglia` si trascina da
    una ricetta all'altra: passando da «giorni con massima ≥ 30 °C» a «periodo
    asciutto più lungo» la soglia restava 30, ma lì si misura in millimetri, e
    il risultato era un periodo di siccità di 161 giorni in mezzo alla
    pioggia. Sbagliato e silenzioso, perché nessuno dei due numeri è assurdo.
    """
    return f"era5_par_{ricetta['id']}_{parametro['nome']}"


def era5_scegli_ricetta(
    domanda: str, copertura: str, ricette: list[dict], esterno: bool = False
) -> dict:
    """Fa scegliere al modello una ricetta della libreria e i suoi parametri.

    Scegliere fra venti opzioni e compilare due campi numerici è un compito di
    tutt'altra difficoltà rispetto a scrivere SQL: il 9B sbagliava
    sistematicamente la generazione libera (funzioni finestra nel WHERE,
    `AVG(SUM(...))`), mentre qui l'unico errore possibile è scegliere la
    ricetta sbagliata — e si vede, perché il titolo è scritto a schermo.
    """
    istruzioni = (
        "Scegli dalla libreria la ricetta che risponde alla domanda e riempi "
        "i suoi parametri. Rispondi **solo** con un oggetto JSON della forma "
        '{"id": "identificativo", "parametri": {"nome": valore}}, senza '
        "spiegazioni e senza blocchi markdown. I valori dei parametri sono "
        "numeri: i mesi come numero da 1 a 12. Lascia a null i parametri che "
        "la ricetta scelta non usa. Se nessuna ricetta risponde alla domanda, "
        'rispondi con "id": null.'
    )
    contesto = (
        f"Libreria:\n{catalogo_per_prompt(ricette)}\n\n"
        f"Dati disponibili: {copertura}\n\n"
        f"Domanda: {domanda}"
    )
    if esterno:
        # Sull'esterno lo schema vincola il decoding: l'identificativo esce da
        # un enum, quindi una ricetta inesistente non è proprio rappresentabile.
        testo = era5_chiama_esterno(istruzioni, contesto, schema=schema_scelta(ricette))
        try:
            scelta = json.loads(testo)
        except json.JSONDecodeError as errore:
            raise ValueError(f"JSON non valido: {errore}") from None
        if not isinstance(scelta, dict):
            raise ValueError("la risposta non è un oggetto JSON")
        return scelta

    prompt = f"{istruzioni}\n\n{contesto}\nJSON:"
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1},
        },
        timeout=90,
    )
    response.raise_for_status()
    testo = era5_strip_sql_fences(response.json()["response"])
    # Il modello aggiunge volentieri una frase prima o dopo il JSON nonostante
    # le istruzioni: si prende il primo oggetto graffato invece di arrendersi.
    match = re.search(r"\{.*\}", testo, re.DOTALL)
    if not match:
        raise ValueError("nessun JSON nella risposta")
    try:
        scelta = json.loads(match.group(0))
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON non valido: {error}") from None
    if not isinstance(scelta, dict):
        raise ValueError("la risposta non è un oggetto JSON")
    return scelta


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


def _ephem_altitudes(lat: float, lon: float, moments, body_type) -> list[float]:
    """Return topocentric body altitudes for timezone-aware local moments."""
    observer = ephem.Observer()
    observer.lat = str(lat)
    observer.lon = str(lon)
    observer.pressure = 0  # Geometric altitude, consistent across all bodies.
    altitudes = []
    for moment in moments:
        observer.date = moment.to_pydatetime().astimezone(
            ZoneInfo(UTC_TIMEZONE)
        ).replace(tzinfo=None)
        body = body_type(observer)
        altitudes.append(math.degrees(float(body.alt)))
    return altitudes


def build_sun_altitude_figure(
    lat: float,
    lon: float,
    target_date,
) -> go.Figure:
    """Altitude of Sun, Moon and naked-eye planets over the civil day."""
    tzinfo = ZoneInfo(HOME_TIMEZONE)
    observer = Observer(latitude=lat, longitude=lon)
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=tzinfo)
    day_end = datetime.combine(
        target_date + timedelta(days=1), datetime.min.time(), tzinfo=tzinfo
    )
    moments = pd.date_range(
        day_start,
        day_end,
        freq="5min",
        inclusive="both",
    )
    altitudes = [sun_elevation(observer, moment.to_pydatetime()) for moment in moments]
    all_altitudes = list(altitudes)

    fig = go.Figure()
    fig.add_hrect(y0=-90, y1=-18, fillcolor="#020617", opacity=0.16, line_width=0)
    fig.add_hrect(y0=-18, y1=-12, fillcolor="#172554", opacity=0.20, line_width=0)
    fig.add_hrect(y0=-12, y1=-6, fillcolor="#4338CA", opacity=0.13, line_width=0)
    fig.add_hrect(y0=-6, y1=0, fillcolor="#F59E0B", opacity=0.10, line_width=0)
    fig.add_trace(
        go.Scatter(
            x=moments,
            y=np.maximum(altitudes, 0),
            mode="lines",
            line=dict(width=0),
            fill="tozeroy",
            fillcolor="rgba(251,191,36,0.22)",
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=moments,
            y=altitudes,
            mode="lines",
            line=dict(color="#F59E0B", width=3),
            name="Sole",
            hovertemplate="%{x|%H:%M} · %{y:.1f}°<extra></extra>",
        )
    )

    if ephem is not None:
        moon_altitudes = _ephem_altitudes(lat, lon, moments, ephem.Moon)
        all_altitudes.extend(moon_altitudes)
        fig.add_trace(
            go.Scatter(
                x=moments,
                y=moon_altitudes,
                mode="lines",
                line=dict(color="#94A3B8", width=2.5, dash="dot"),
                name="Luna",
                hovertemplate="%{x|%H:%M} · %{y:.1f}°<extra></extra>",
            )
        )

        for planet_name, planet_type in NAKED_EYE_PLANETS:
            planet_altitudes = _ephem_altitudes(lat, lon, moments, planet_type)
            all_altitudes.extend(planet_altitudes)
            fig.add_trace(
                go.Scatter(
                    x=moments,
                    y=planet_altitudes,
                    mode="lines",
                    line=dict(color=PLANET_COLORS[planet_name], width=2),
                    name=planet_name,
                    hovertemplate="%{x|%H:%M} · %{y:.1f}°<extra></extra>",
                )
            )

    now_local = datetime.now(tzinfo)
    if now_local.date() == target_date:
        current_altitude = sun_elevation(observer, now_local)
        fig.add_trace(
            go.Scatter(
                x=[now_local],
                y=[current_altitude],
                mode="markers",
                marker=dict(color="#F97316", size=10, line=dict(color="white", width=2)),
                name="Adesso",
                showlegend=False,
                hovertemplate="Adesso · %{y:.1f}°<extra></extra>",
            )
        )
        if ephem is not None:
            current_moment = [pd.Timestamp(now_local)]
            current_bodies = [
                ("Luna", ephem.Moon, "#94A3B8"),
                *[
                    (planet_name, planet_type, PLANET_COLORS[planet_name])
                    for planet_name, planet_type in NAKED_EYE_PLANETS
                ],
            ]
            for body_name, body_type, color in current_bodies:
                body_altitude = _ephem_altitudes(
                    lat, lon, current_moment, body_type
                )[0]
                fig.add_trace(
                    go.Scatter(
                        x=[now_local],
                        y=[body_altitude],
                        mode="markers",
                        marker=dict(
                            color=color,
                            size=9,
                            line=dict(color="white", width=1.5),
                        ),
                        name=f"{body_name} adesso",
                        showlegend=False,
                        hovertemplate=(
                            f"{body_name} adesso · %{{y:.1f}}°<extra></extra>"
                        ),
                    )
                )

    fig.add_hline(y=0, line_color="rgba(100,116,139,0.55)", line_width=1)
    # The full nightly solar arc determines the useful lower edge. Other bodies
    # may approach the nadir while they are not observable; including those
    # values would compress the visible portion of every trajectory.
    lower_bound = max(-90, math.floor(min(altitudes) / 10) * 10)
    upper_bound = min(90, math.ceil(max(all_altitudes) / 10) * 10)
    fig.update_layout(
        title="Percorsi nel cielo oggi",
        xaxis=dict(title=None, tickformat="%H:%M", dtick=3 * 60 * 60 * 1000),
        yaxis=dict(
            title="Altezza sull'orizzonte",
            ticksuffix="°",
            range=[lower_bound, upper_bound],
        ),
        hovermode="x",
        height=430,
        showlegend=True,
        legend=MOBILE_LEGEND,
        margin=dict(l=45, r=20, t=55, b=105),
    )
    return fig


def get_moon_details(lat: float, lon: float, target_date) -> dict:
    """Moon phase, estimated illumination, rise and set in local time."""
    observer = Observer(latitude=lat, longitude=lon)
    tzinfo = ZoneInfo(HOME_TIMEZONE)
    phase_day = moon.phase(target_date)
    illumination = (1 - math.cos(2 * math.pi * phase_day / 28)) / 2 * 100

    def local_event(index: int):
        """Sorgere (0) o tramontare (1) della luna nel giorno *locale*.

        `moon.moonrise` e `moon.moonset` ragionano a giorni UTC: a est di
        Greenwich un sorgere subito dopo la mezzanotte locale cade nella
        finestra del giorno UTC precedente, e la funzione solleva `ValueError`
        ("Moon never rises on this date") pur essendoci l'evento. Si guardano
        quindi le finestre vicine e si tiene quella la cui data locale è
        davvero quella richiesta.
        """
        for offset in (0, -1, 1):
            event = riseset(target_date + timedelta(days=offset), observer)[index]
            if event is not None:
                local = event.astimezone(tzinfo)
                if local.date() == target_date:
                    return local
        return None

    return {
        "phase": get_moon_phase_label(target_date),
        "phase_day": phase_day,
        "illumination": illumination,
        "moonrise": local_event(0),
        "moonset": local_event(1),
    }


def moon_phase_icon(phase_day: float) -> str:
    icons = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]
    return icons[int(phase_day // 3.5) % len(icons)]


def get_visible_planets(lat: float, lon: float, target_date) -> list[dict]:
    """Naked-eye planets observable during the local night, best first.

    Restituisce valori grezzi e non stringhe già formattate: le schede dei
    pianeti mostrano altezza e magnitudine con formati diversi, e ordinano per
    altezza.
    """
    if ephem is None:
        return []

    tzinfo = ZoneInfo(HOME_TIMEZONE)
    today_times = compute_sun_times(lat, lon, target_date)
    now_local = datetime.now(tzinfo)
    if now_local.date() == target_date and now_local < today_times["sunrise"]:
        previous_day = target_date - timedelta(days=1)
        start = compute_sun_times(lat, lon, previous_day)["sunset"]
        end = today_times["sunrise"]
    else:
        start = today_times["sunset"]
        end = compute_sun_times(lat, lon, target_date + timedelta(days=1))["sunrise"]

    moments = pd.date_range(start, end, freq="10min")
    rows = []
    for italian_name, planet_type in NAKED_EYE_PLANETS:
        candidates = []
        for moment in moments:
            local_moment = moment.to_pydatetime()
            observer = ephem.Observer()
            observer.lat = str(lat)
            observer.lon = str(lon)
            observer.date = local_moment.astimezone(ZoneInfo(UTC_TIMEZONE)).replace(
                tzinfo=None
            )
            sun_body = ephem.Sun(observer)
            planet = planet_type(observer)
            altitude = math.degrees(float(planet.alt))
            sun_altitude = math.degrees(float(sun_body.alt))
            if altitude >= 10 and sun_altitude <= -6 and float(planet.mag) <= 6:
                candidates.append((altitude, local_moment, float(planet.mag)))

        if not candidates:
            continue
        altitude, best_time, magnitude = max(candidates, key=lambda item: item[0])
        midpoint = start + (end - start) / 2
        rows.append(
            {
                "name": italian_name,
                "visibility": "sera" if best_time <= midpoint else "mattino",
                "best_time": best_time,
                "altitude": altitude,
                "magnitude": magnitude,
            }
        )
    return sorted(rows, key=lambda row: row["altitude"], reverse=True)


def format_timedelta_hm(delta: timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m"


ITALIAN_WEEKDAYS = [
    "lunedì", "martedì", "mercoledì", "giovedì",
    "venerdì", "sabato", "domenica",
]


def italian_date_label(value, with_time: bool = False) -> str:
    """«Venerdì 07/08/2026».

    I nomi dei giorni sono a mano perché `%A` segue la locale del processo, e
    il servizio launchd gira senza `LANG`: dava «Friday» in mezzo a una
    dashboard tutta in italiano.
    """
    weekday = ITALIAN_WEEKDAYS[value.weekday()].capitalize()
    pattern = "%d/%m/%Y · %H:%M" if with_time else "%d/%m/%Y"
    return f"{weekday} {value.strftime(pattern)}"


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


def wet_bulb_temperature_celsius(temp_c, humidity_pct):
    """Estimate wet-bulb temperature at sea-level pressure.

    Uses the Stull (2011) approximation, valid for air temperatures from
    -20 to 50°C and relative humidity from 5 to 99%. Inputs outside the
    humidity range are clipped so bad sensor values cannot break the chart.
    """
    humidity_pct = np.clip(humidity_pct, 5, 99)
    return (
        temp_c * np.arctan(0.151977 * np.sqrt(humidity_pct + 8.313659))
        + np.arctan(temp_c + humidity_pct)
        - np.arctan(humidity_pct - 1.676331)
        + 0.00391838 * humidity_pct**1.5 * np.arctan(0.023101 * humidity_pct)
        - 4.686035
    )


def describe_wet_bulb_risk(wet_bulb_c: float) -> str:
    """Prudent heat-stress bands for estimated wet-bulb temperature.

    These are contextual warning bands, not clinical thresholds: activity,
    sunshine, wind, acclimatisation, age and health can change the actual risk.
    """
    if wet_bulb_c < 26:
        return "rischio contenuto"
    if wet_bulb_c < 28:
        return "attenzione"
    if wet_bulb_c < 30:
        return "pericolo"
    return "pericolo estremo"


def describe_muggy_level(heat_index_c: float) -> str | None:
    """Qualitative Italian label for a heat-index value (NWS caution bands)."""
    if heat_index_c < 27:
        return None
    if heat_index_c < 32:
        return "afa moderata"
    if heat_index_c < 39:
        return "afosa"
    if heat_index_c < 51:
        return "molto afosa"
    return "afa estrema"


def get_moon_phase_label(target_date) -> str:
    """Coarse Italian label for the moon phase on a given date (astral, 0-27.99 scale)."""
    labels = [
        "luna nuova",
        "luna crescente",
        "primo quarto",
        "luna gibbosa crescente",
        "luna piena",
        "luna gibbosa calante",
        "ultimo quarto",
        "luna calante",
    ]
    phase = moon.phase(target_date)
    return labels[int(phase // 3.5) % len(labels)]


@st.cache_data(ttl=6 * 3600, show_spinner="Confronto con le serie storiche...")
def compute_historical_highlights(station_id: str) -> list[str]:
    """Compare the current week/month against the station's full history and
    surface only genuinely notable records (gap of several years), so the
    narrative report has fresh, non-repetitive material to draw from."""
    HOT_DAY_THRESHOLD = 34.0
    MIN_RECORD_GAP_YEARS = 3

    conn = get_db_connection()
    # I giorni qui sono quelli dell'ora solare, non quelli locali: rileggere e
    # convertire in pandas sedici anni di dati a 10 minuti costerebbe troppo, e
    # il giorno in ora solare è comunque la convenzione climatologica ARPAV.
    tmax_daily = pd.read_sql_query(
        """
        SELECT date(observation_at) AS day, MAX(value_numeric) AS tmax
        FROM observations
        WHERE station_id = ? AND variable_type = 'TARIA2M' AND value_numeric IS NOT NULL
        GROUP BY day
        """,
        conn,
        params=[station_id],
    )
    prec_daily = pd.read_sql_query(
        """
        SELECT date(observation_at) AS day, SUM(value_numeric) AS prec
        FROM observations
        WHERE station_id = ? AND variable_type = 'PREC' AND value_numeric IS NOT NULL
        GROUP BY day
        """,
        conn,
        params=[station_id],
    )

    highlights = []

    def most_recent_match(series: pd.Series, current_value: float):
        matches = series[series >= current_value]
        return matches.index.max() if not matches.empty else None

    if not tmax_daily.empty:
        tmax_daily["day"] = pd.to_datetime(tmax_daily["day"])
        s = tmax_daily.set_index("day")["tmax"].sort_index()
        rolling_avg = s.rolling(7, min_periods=5).mean()
        rolling_hot_days = s.rolling(7, min_periods=5).apply(
            lambda w: (w > HOT_DAY_THRESHOLD).sum()
        )

        last_date = s.index.max()
        current_year = last_date.year
        first_year = s.index.min().year
        cutoff = last_date - timedelta(days=7)
        prior_avg = rolling_avg[rolling_avg.index <= cutoff]
        prior_hot = rolling_hot_days[rolling_hot_days.index <= cutoff]

        current_avg = rolling_avg.get(last_date)
        if pd.notna(current_avg):
            match_date = most_recent_match(prior_avg, current_avg)
            match_year = match_date.year if match_date is not None else first_year
            if current_year - match_year >= MIN_RECORD_GAP_YEARS:
                since = (
                    f"dal {match_year}"
                    if match_date is not None
                    else f"dall'inizio delle rilevazioni ({first_year})"
                )
                highlights.append(
                    f"Questa è la settimana più calda {since}, con una "
                    f"massima media di {current_avg:.1f}°C."
                )

        current_hot_days = rolling_hot_days.get(last_date)
        if pd.notna(current_hot_days) and current_hot_days >= 3:
            match_date = most_recent_match(prior_hot, current_hot_days)
            match_year = match_date.year if match_date is not None else first_year
            if current_year - match_year >= MIN_RECORD_GAP_YEARS:
                since = (
                    f"dal {match_year}"
                    if match_date is not None
                    else f"dall'inizio delle rilevazioni ({first_year})"
                )
                highlights.append(
                    f"{int(current_hot_days)} giorni con massima sopra "
                    f"{HOT_DAY_THRESHOLD:.0f}°C negli ultimi 7 giorni: "
                    f"non succedeva {since}."
                )

    if not prec_daily.empty:
        prec_daily["day"] = pd.to_datetime(prec_daily["day"])
        p = prec_daily.set_index("day")["prec"].sort_index()
        today = p.index.max()
        current_year = today.year
        month_start = today.replace(day=1)
        days_elapsed = (today - month_start).days + 1
        current_total = p[(p.index >= month_start) & (p.index <= today)].sum()

        candidate_years = []
        for year in sorted(p.index.year.unique()):
            if year == current_year:
                continue
            y_month_start = datetime(year, today.month, 1)
            y_cutoff = y_month_start + timedelta(days=days_elapsed - 1)
            mask = (p.index >= y_month_start) & (p.index <= y_cutoff)
            if not mask.any():
                continue
            if p[mask].sum() >= current_total:
                candidate_years.append(year)

        other_years = [y for y in p.index.year.unique() if y != current_year]
        if other_years:
            first_year = min(other_years)
            match_year = max(candidate_years) if candidate_years else first_year
            if current_year - match_year >= MIN_RECORD_GAP_YEARS:
                since = (
                    f"dal {match_year}"
                    if candidate_years
                    else f"dall'inizio delle rilevazioni ({first_year})"
                )
                highlights.append(
                    f"Con {current_total:.0f} mm finora, questo mese è il più "
                    f"piovoso {since} (confronto sullo stesso periodo del mese)."
                )

    return highlights


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
    )
    fig.update_traces(line_width=2.5)

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
                    mode="lines",
                    name=f"{station_name} - Media pond. giornaliera",
                    line=dict(color=color_map.get(station_name), dash="dash", width=3),
                )
            )

    fig.update_layout(
        hovermode="x unified",
        height=430,
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    render_chart(fig)


def render_wet_bulb_chart(
    full_df: pd.DataFrame,
    temp_df: pd.DataFrame,
    chart_stations: list,
    station_id_to_name: dict,
) -> None:
    """Render estimated wet-bulb temperature as a standalone risk chart."""
    humidity_df = full_df[
        (full_df["variable_type"] == "UMID2M") & full_df["value_numeric"].notna()
    ]
    if humidity_df.empty:
        return

    station_names = sorted(temp_df["station_name"].unique())
    colors = px.colors.qualitative.Plotly
    color_map = {
        name: colors[index % len(colors)] for index, name in enumerate(station_names)
    }
    fig = go.Figure()

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

        merged["bulbo_umido"] = wet_bulb_temperature_celsius(
            merged["temperatura"], merged["umidita"]
        )
        fig.add_trace(
            go.Scatter(
                x=merged["observation_at"],
                y=merged["bulbo_umido"],
                customdata=merged[["temperatura", "umidita"]],
                mode="lines",
                name=station_name,
                line=dict(color=color_map.get(station_name), width=2.5),
                hovertemplate=(
                    "Bulbo umido: %{y:.1f}°C"
                    "<br>Temperatura aria: %{customdata[0]:.1f}°C"
                    "<br>Umidità: %{customdata[1]:.0f}%<extra></extra>"
                ),
            )
        )

    if not fig.data:
        return

    risk_bands = [
        (0, 26, "rgba(76,175,80,0.08)"),
        (26, 28, "rgba(255,193,7,0.13)"),
        (28, 30, "rgba(255,152,0,0.15)"),
        (30, 35, "rgba(244,67,54,0.15)"),
    ]
    for lower, upper, color in risk_bands:
        fig.add_hrect(
            y0=lower,
            y1=upper,
            fillcolor=color,
            line_width=0,
            layer="below",
        )

    fig.update_layout(
        title="Stress termico - temperatura di bulbo umido stimata",
        xaxis_title="Data/Ora",
        yaxis=dict(title="Bulbo umido (°C Tw)", range=[0, 35]),
        hovermode="x unified",
        height=400,
        legend=MOBILE_LEGEND,
        margin=MOBILE_CHART_MARGIN,
    )
    render_chart(fig)
    st.caption(
        "Fasce indicative: verde <26°C, attenzione 26–28°C, pericolo "
        "28–30°C, pericolo estremo ≥30°C. Stima in ombra da temperatura e "
        "umidità: non è il WBGT e non include sole, vento o attività fisica."
    )


def merge_temperature_humidity(observations: pd.DataFrame) -> pd.DataFrame:
    """Match temperature and humidity readings from the same station in time."""
    temperature = observations[
        (observations["variable_type"] == "TARIA2M")
        & observations["value_numeric"].notna()
    ].sort_values("observation_at")
    humidity = observations[
        (observations["variable_type"] == "UMID2M")
        & observations["value_numeric"].notna()
    ].sort_values("observation_at")
    if temperature.empty or humidity.empty:
        return pd.DataFrame(
            columns=["observation_at", "temperatura", "umidita"]
        )

    return pd.merge_asof(
        temperature[["observation_at", "value_numeric"]].rename(
            columns={"value_numeric": "temperatura"}
        ),
        humidity[["observation_at", "value_numeric"]].rename(
            columns={"value_numeric": "umidita"}
        ),
        on="observation_at",
        tolerance=pd.Timedelta("30min"),
        direction="nearest",
    ).dropna(subset=["umidita"])


def build_compact_timeseries(
    data: pd.DataFrame,
    value_column: str,
    title: str,
    yaxis_title: str,
    color: str,
    yaxis_range: list | None = None,
) -> go.Figure:
    """Small, consistent line chart for the 72-hour overview grid."""
    fig = go.Figure(
        go.Scatter(
            x=data["observation_at"],
            y=data[value_column],
            mode="lines",
            line=dict(color=color, width=2.5),
            hovertemplate=f"%{{x|%d/%m %H:%M}} · %{{y:.1f}} {yaxis_title}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        xaxis=dict(title=None, tickformat="%d/%m\n%H:%M"),
        yaxis=dict(title=yaxis_title, range=yaxis_range),
        hovermode="x",
        height=310,
        showlegend=False,
        margin=dict(l=45, r=15, t=55, b=45),
    )
    return fig


def render_now_hero(station_name: str, conditions: dict) -> None:
    """Current conditions as one glanceable block: the answer to «com'è adesso»."""
    note = ""
    perceived = conditions["perceived"]
    # L'indice di calore sotto i ~27°C coincide con la temperatura: mostrarlo
    # sempre aggiungerebbe una riga che non dice nulla per mezzo anno.
    if perceived is not None and perceived - conditions["temperature"] >= 0.5:
        muggy = describe_muggy_level(perceived)
        note = f"percepiti {perceived:.1f}°" + (f" · {muggy}" if muggy else "")

    chips = []
    if conditions["humidity"] is not None:
        chips.append(f"💧 Umidità <b>{conditions['humidity']:.0f}%</b>")
    if conditions["wind_speed"] is not None:
        wind = f"{conditions['wind_speed']:.1f} m/s"
        if conditions["wind_direction"] is not None:
            wind += f" da {degrees_to_compass(conditions['wind_direction'])}"
        chips.append(f"🌬️ Vento <b>{wind}</b>")
    if conditions["rain_today"] is not None:
        chips.append(f"🌧️ Pioggia oggi <b>{conditions['rain_today']:.1f} mm</b>")
    if conditions["pressure"] is not None:
        chips.append(f"🧭 Pressione <b>{conditions['pressure']:.0f} hPa</b>")

    chips_html = "".join(f'<span class="m42-chip">{chip}</span>' for chip in chips)
    note_html = f'<span class="m42-hero-note">{html.escape(note)}</span>' if note else ""
    st.markdown(
        '<div class="m42-hero">'
        f'<span class="m42-eyebrow">Adesso · {html.escape(station_name)}</span>'
        '<div class="m42-hero-main">'
        f'<span class="m42-hero-temp">{conditions["temperature"]:.1f}°</span>'
        f"{note_html}</div>"
        f'<div class="m42-chips">{chips_html}</div>'
        '<small class="m42-stamp">Ultima lettura alle '
        f'{conditions["observed_at"].strftime("%H:%M del %d/%m/%Y")}</small>'
        "</div>",
        unsafe_allow_html=True,
    )


def format_day_length_delta(delta: timedelta) -> str:
    """«+2 min su ieri». `format_timedelta_hm` non serve: qui il segno conta e
    la differenza tra due giorni consecutivi sta sempre in pochi minuti."""
    minutes = round(delta.total_seconds() / 60)
    if minutes == 0:
        return "come ieri"
    # Meno tipografico, non trattino: sta accanto ai «−6°» del resto del cielo.
    sign = "+" if minutes > 0 else "−"
    return f"{sign}{abs(minutes)} min su ieri"


def render_visible_planets(planets: list[dict]) -> None:
    """Naked-eye planets as cards; the dot colour matches the altitude chart."""
    if ephem is None:
        st.info(
            "Installa le dipendenze aggiornate per abilitare il calcolo dei "
            "pianeti."
        )
        return
    if not planets:
        st.info(
            "Stanotte nessun pianeta maggiore supera i 10° con il cielo "
            "abbastanza scuro."
        )
        return

    cards = []
    for planet in planets:
        color = PLANET_COLORS.get(planet["name"], "#94A3B8")
        when = "di sera" if planet["visibility"] == "sera" else "al mattino"
        cards.append(
            '<div class="m42-planet">'
            f'<span class="m42-planet-dot" style="background:{color}"></span>'
            '<div class="m42-planet-body">'
            f'<div class="m42-planet-name">{html.escape(planet["name"])}</div>'
            f'<div class="m42-planet-meta">{when} · al meglio alle '
            f'{planet["best_time"].strftime("%H:%M")} · '
            f'magnitudine {planet["magnitude"]:.1f}</div>'
            "</div>"
            f'<span class="m42-planet-alt">{planet["altitude"]:.0f}°</span>'
            "</div>"
        )
    st.markdown(
        f'<div class="m42-grid m42-grid-wide">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def render_sky_section(lat: float, lon: float, target_date) -> None:
    """Sun, moon and planets for one day: times, trajectories, visibility."""
    sun_times = compute_sun_times(lat, lon, target_date)
    yesterday_times = compute_sun_times(lat, lon, target_date - timedelta(days=1))
    peak_altitude = sun_elevation(
        Observer(latitude=lat, longitude=lon), sun_times["noon"]
    )

    m42_section(
        "Il Sole",
        eyebrow="Cielo di oggi",
        subtitle=(
            "Alba e tramonto sono calcolati per Mogliano Veneto, orizzonte "
            "libero e senza rilievi."
        ),
    )
    m42_render_tiles(
        [
            m42_tile("🌅 Alba", sun_times["sunrise"].strftime("%H:%M")),
            m42_tile(
                "☀️ Culmine",
                sun_times["noon"].strftime("%H:%M"),
                f"{peak_altitude:.0f}° sull'orizzonte",
            ),
            m42_tile("🌇 Tramonto", sun_times["sunset"].strftime("%H:%M")),
            # La durata del giorno sta qui, con il Sole che la determina, e non
            # accanto alla Luna dov'era finita.
            m42_tile(
                "⏳ Ore di luce",
                format_timedelta_hm(sun_times["day_length"]),
                f"notte {format_timedelta_hm(sun_times['night_length'])} · "
                + format_day_length_delta(
                    sun_times["day_length"] - yesterday_times["day_length"]
                ),
            ),
        ]
    )

    moon_details = get_moon_details(lat, lon, target_date)
    moonrise = moon_details["moonrise"]
    moonset = moon_details["moonset"]
    m42_section("La Luna", eyebrow="Cielo di oggi")
    m42_render_tiles(
        [
            m42_tile(
                f"{moon_phase_icon(moon_details['phase_day'])} Fase",
                moon_details["phase"].capitalize(),
                f"{moon_details['illumination']:.0f}% illuminata",
            ),
            m42_tile(
                "🌙 Sorge", moonrise.strftime("%H:%M") if moonrise else "—"
            ),
            m42_tile(
                "🌘 Tramonta", moonset.strftime("%H:%M") if moonset else "—"
            ),
        ]
    )

    m42_section(
        "Percorsi nel cielo",
        eyebrow="Cielo di oggi",
        subtitle=(
            "Altezza sull'orizzonte di Sole, Luna e pianeti nell'arco della "
            "giornata. Le fasce sotto lo zero sono i crepuscoli: civile, "
            "nautico e astronomico."
        ),
    )
    render_chart(build_sun_altitude_figure(lat, lon, target_date))

    m42_section(
        "Pianeti a occhio nudo",
        eyebrow="Stanotte",
        subtitle=(
            "Pianeti che superano i 10° sull'orizzonte con il Sole sotto i "
            "−6°. Nuvole e ostacoli locali non sono considerati."
        ),
    )
    render_visible_planets(get_visible_planets(lat, lon, target_date))


def render_overview_72h_charts(station_id: str) -> None:
    """Render temperature, humidity and heat-stress indicators for 72 hours."""
    observations = get_observations_df(station_id=station_id, days=3)
    if observations.empty:
        return

    temperature = observations[
        (observations["variable_type"] == "TARIA2M")
        & observations["value_numeric"].notna()
    ].sort_values("observation_at")
    humidity = observations[
        (observations["variable_type"] == "UMID2M")
        & observations["value_numeric"].notna()
    ].sort_values("observation_at")
    matched = merge_temperature_humidity(observations)
    if not matched.empty:
        matched["bulbo_umido"] = wet_bulb_temperature_celsius(
            matched["temperatura"], matched["umidita"]
        )
        matched["indice_calore"] = heat_index_celsius(
            matched["temperatura"], matched["umidita"]
        )

    m42_section(
        "Ultime 72 ore",
        eyebrow="Andamento",
        subtitle="Orari locali, letture della stazione di casa.",
    )
    first_row_left, first_row_right = st.columns(2)
    with first_row_left:
        if not temperature.empty:
            render_chart(
                build_compact_timeseries(
                    temperature,
                    "value_numeric",
                    "Temperatura dell’aria",
                    "°C",
                    "#EF4444",
                ),
            )
    with first_row_right:
        if not humidity.empty:
            render_chart(
                build_compact_timeseries(
                    humidity,
                    "value_numeric",
                    "Umidità relativa",
                    "%",
                    "#0EA5E9",
                    [0, 100],
                ),
            )

    if matched.empty:
        st.caption(
            "Bulbo umido e indice di calore non disponibili: servono letture "
            "abbinate di temperatura e umidità."
        )
        return

    second_row_left, second_row_right = st.columns(2)
    with second_row_left:
        wet_bulb_fig = build_compact_timeseries(
            matched,
            "bulbo_umido",
            "Bulbo umido stimato",
            "°C Tw",
            "#2563EB",
            [0, 35],
        )
        for lower, upper, color in [
            (0, 26, "rgba(76,175,80,0.08)"),
            (26, 28, "rgba(255,193,7,0.13)"),
            (28, 30, "rgba(255,152,0,0.15)"),
            (30, 35, "rgba(244,67,54,0.15)"),
        ]:
            wet_bulb_fig.add_hrect(
                y0=lower, y1=upper, fillcolor=color, line_width=0, layer="below"
            )
        render_chart(
            wet_bulb_fig,
        )

    with second_row_right:
        heat_index_fig = build_compact_timeseries(
            matched,
            "indice_calore",
            "Indice di calore",
            "°C",
            "#F97316",
        )
        heat_index_fig.add_hrect(
            y0=27, y1=32, fillcolor="rgba(255,193,7,0.10)", line_width=0,
            layer="below",
        )
        heat_index_fig.add_hrect(
            y0=32, y1=39, fillcolor="rgba(255,152,0,0.12)", line_width=0,
            layer="below",
        )
        heat_index_fig.add_hrect(
            y0=39, y1=51, fillcolor="rgba(244,67,54,0.13)", line_width=0,
            layer="below",
        )
        render_chart(
            heat_index_fig,
        )

    st.caption(
        "Orari locali. Bulbo umido stimato e indice di calore sono calcolati "
        "abbinando le letture entro 30 minuti; l’indice di calore descrive "
        "condizioni in ombra."
    )


# Tabs
# Un argomento per scheda, e le schede in ordine di frequenza d'uso: prima
# «com'è adesso», poi «come sarà», poi il resto. Le previsioni stanno in una
# scheda propria e non più in fondo alla panoramica, e il cielo — Sole, Luna,
# pianeti — ha la sua invece di stare in mezzo alle osservazioni.
(
    tab_now,
    tab_forecast,
    tab_sky,
    tab_diary,
    tab_data,
    tab_charts,
    tab_history,
    tab_climate,
    tab_stations,
) = st.tabs(
    [
        "📍 Adesso",
        "🔭 Previsioni",
        "🌌 Cielo",
        "🕰️ Che tempo fece",
        "📊 Dati",
        "📈 Grafici",
        "📅 Storico Annuale",
        "🌡️ Clima",
        "⚙️ Stazioni",
    ]
)

overview_stations_df = get_stations_from_db()
home_row = find_home_station(overview_stations_df)
local_today = datetime.now(ZoneInfo(HOME_TIMEZONE)).date()

# TAB: Adesso
with tab_now:
    if home_row is None:
        st.info(
            "Nessuna stazione «Mogliano Veneto» con coordinate: aggiungila in "
            "⚙️ Stazioni per vedere qui i dati di casa."
        )
    else:
        home_conditions = get_home_conditions(home_row["station_id"])
        if home_conditions is None:
            st.info("Nessuna lettura recente per la stazione di casa.")
        else:
            render_now_hero(home_row["station_name"], home_conditions)

        sun_times = compute_sun_times(
            home_row["latitudine"], home_row["longitudine"], local_today
        )
        sun_context = (
            f"Alba alle {sun_times['sunrise'].strftime('%H:%M')}, "
            f"culmine alle {sun_times['noon'].strftime('%H:%M')}, "
            f"tramonto alle {sun_times['sunset'].strftime('%H:%M')} "
            f"(giorno di {format_timedelta_hm(sun_times['day_length'])}). "
            f"Fase lunare: {get_moon_phase_label(local_today)}."
        )

        m42_section(
            "Come sta andando",
            eyebrow=f"Report · {home_row['station_name']}",
        )
        use_ai_report = st.toggle("✨ Riassunto AI", key="use_ai_report")

        structured_report = build_station_report(
            home_row["station_id"], home_row["station_name"]
        )
        if use_ai_report:
            try:
                historical_highlights = compute_historical_highlights(
                    home_row["station_id"]
                )
                st.markdown(
                    generate_narrative_report(
                        structured_report,
                        home_row["station_name"],
                        historical_highlights,
                        sun_context,
                        current_narrative_style(),
                    )
                )
            except requests.exceptions.Timeout:
                st.caption(
                    "⚠️ Ollama sta impiegando troppo tempo a rispondere "
                    "(modello ancora in caricamento?), mostro il report "
                    "standard."
                )
            except requests.exceptions.RequestException:
                st.caption(
                    f"⚠️ Ollama non raggiungibile su {OLLAMA_BASE_URL}, "
                    "mostro il report standard."
                )
                st.markdown(structured_report)
        else:
            st.markdown(structured_report)

        render_overview_72h_charts(home_row["station_id"])

    nearest_df = find_nearest_stations(overview_stations_df)
    if home_row is not None and not nearest_df.empty:
        nearest_df = pd.concat(
            [
                nearest_df,
                pd.DataFrame(
                    [
                        {
                            "label": "Mogliano Veneto (casa)",
                            "station_id": home_row["station_id"],
                            "station_name": home_row["station_name"],
                            "latitudine": home_row["latitudine"],
                            "longitudine": home_row["longitudine"],
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )

    if nearest_df.empty:
        st.info(
            "Nessuna stazione con coordinate disponibili: aggiungi "
            "latitudine/longitudine in station_metadata per abilitare "
            "la panoramica territoriale."
        )
    else:
        m42_section(
            "Temperature in Veneto",
            eyebrow="Capoluoghi",
            subtitle=(
                "Ultima lettura della stazione più vicina a ogni capoluogo."
            ),
        )
        veneto_temps = nearest_df.merge(
            get_latest_temperatures(
                nearest_df["station_id"].unique().tolist()
            ),
            on="station_id",
            how="left",
        )
        # Tessere e non `st.dataframe`: una tabella a due colonne su un
        # telefono diventa una striscia stretta da scorrere, la griglia si
        # impagina da sola su una, due o quattro colonne.
        m42_render_tiles(
            [
                m42_tile(
                    row["label"],
                    (
                        f"{row['value_numeric']:.1f}°"
                        if pd.notna(row["value_numeric"])
                        else "n/d"
                    ),
                    (
                        row["observation_at"].strftime("alle %H:%M")
                        if pd.notna(row["observation_at"])
                        else ""
                    ),
                )
                for _, row in veneto_temps.iterrows()
            ]
        )


# TAB: Previsioni
with tab_forecast:
    render_radar_nowcast()
    st.divider()
    m42_section(
        "Previsioni Veneto",
        eyebrow="Bollettino ARPAV",
        subtitle=(
            "Il bollettino Meteo Veneto, giorno per giorno, con le mappe "
            "ufficiali."
        ),
    )
    render_forecast_bulletin()


# TAB: Cielo
with tab_sky:
    if home_row is None:
        st.info(
            "Serve una stazione di casa con le coordinate per calcolare "
            "effemeridi e percorsi nel cielo."
        )
    else:
        sky_date = st.date_input(
            "Giorno",
            value=local_today,
            format="DD/MM/YYYY",
            key="sky_date",
        )
        render_sky_section(
            home_row["latitudine"], home_row["longitudine"], sky_date
        )


# TAB: Che tempo fece
with tab_diary:
    m42_section(
        "Che tempo fece",
        eyebrow="Diario",
        subtitle=(
            "Il racconto del giorno, le osservazioni di Mogliano e "
            "l’evoluzione oraria della nuvolosità."
        ),
    )

    diary_dates = get_weather_diary_dates()
    if not diary_dates:
        st.info(
            "Lo storico comincerà con il prossimo aggiornamento dello scraper."
        )
    else:
        # Calendario e non elenco a tendina: l'archivio cresce di un giorno al
        # giorno, e in una tendina lunga un anno cercare «il 3 marzo» vuol dire
        # scorrere. Gli estremi sono quelli davvero in archivio, ma dentro
        # l'intervallo si può cadere su un giorno vuoto — i buchi si dicono,
        # non si nascondono.
        selected_diary_date = st.date_input(
            "Giorno",
            value=diary_dates[0],
            min_value=diary_dates[-1],
            max_value=diary_dates[0],
            format="DD/MM/YYYY",
            key="weather_diary_date",
        )
        st.caption(italian_date_label(selected_diary_date))
        if selected_diary_date not in set(diary_dates):
            st.info(
                "Per questo giorno non c'è niente in archivio: né bollettino "
                "né analisi delle nubi."
            )

        daily_bulletin = get_daily_weather_bulletin(selected_diary_date)
        if daily_bulletin:
            issued_at = datetime.fromisoformat(daily_bulletin["issued_at"])
            st.markdown(
                '<div class="weather-diary-story">'
                '<span class="m42-eyebrow">Il racconto del giorno</span>'
                f'<h3>{html.escape(daily_bulletin["title"])}</h3>'
                f'<p>{html.escape(daily_bulletin["general_evolution"])}</p>'
                f'<small>Aggiornato alle {issued_at.strftime("%H:%M")}</small>'
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("Per questo giorno non è stato archiviato un bollettino.")

        diary_stations = get_stations_from_db()
        diary_home = diary_stations[
            diary_stations["station_name"]
            .str.lower()
            .str.contains(HOME_STATION_HINT, na=False)
        ]
        if not diary_home.empty:
            day_observations = get_day_observations(
                diary_home.iloc[0]["station_id"],
                selected_diary_date,
            )
            if not day_observations.empty:
                temperature = day_observations[
                    (day_observations["variable_type"] == "TARIA2M")
                    & day_observations["value_numeric"].notna()
                ]
                rain = day_observations[
                    (day_observations["variable_type"] == "PREC")
                    & day_observations["value_numeric"].notna()
                ]
                wind = day_observations[
                    (day_observations["variable_type"] == "VVENTO10M")
                    & day_observations["value_numeric"].notna()
                ]
                humidity = day_observations[
                    (day_observations["variable_type"] == "UMID2M")
                    & day_observations["value_numeric"].notna()
                ]
                m42_render_tiles(
                    [
                        m42_tile(
                            "🌡️ Temperatura",
                            (
                                f"{temperature['value_numeric'].min():.1f} / "
                                f"{temperature['value_numeric'].max():.1f}°"
                                if not temperature.empty
                                else "—"
                            ),
                            "minima e massima della giornata civile",
                        ),
                        m42_tile(
                            "🌧️ Pioggia",
                            f"{rain['value_numeric'].sum():.1f} mm"
                            if not rain.empty
                            else "—",
                        ),
                        m42_tile(
                            "🌬️ Vento massimo",
                            f"{wind['value_numeric'].max():.1f} m/s"
                            if not wind.empty
                            else "—",
                        ),
                        m42_tile(
                            "💧 Umidità media",
                            f"{humidity['value_numeric'].mean():.0f}%"
                            if not humidity.empty
                            else "—",
                        ),
                    ]
                )

        cloud_frames = get_cloud_type_frames(selected_diary_date)
        st.divider()
        m42_section(
            "Nuvole durante la giornata",
            eyebrow="Analisi oraria",
            subtitle=(
                "Un fotogramma per ogni ora, dalla tipologia delle nubi "
                "ARPAV, in ora italiana."
            ),
        )
        if not cloud_frames:
            st.info("Nessuna analisi delle nubi archiviata per questo giorno.")
        else:
            speed_label = st.select_slider(
                "Velocità animazione",
                options=["Lenta", "Normale", "Veloce"],
                value="Normale",
                key="cloud_animation_speed",
            )
            duration_ms = {"Lenta": 1400, "Normale": 850, "Veloce": 450}[
                speed_label
            ]
            frame_data = tuple(
                (
                    frame["path"],
                    italian_date_label(frame["observed_at"], with_time=True),
                )
                for frame in cloud_frames
            )
            with st.spinner("Creo l’animazione della giornata..."):
                animation = build_cloud_type_animation(frame_data, duration_ms)
            if animation:
                st.image(animation, width="stretch")
                st.caption(
                    f"{len(cloud_frames)} fotogrammi orari, mostrati in ora italiana."
                )

            with st.expander("Esplora un singolo orario"):
                selected_frame_index = st.select_slider(
                    "Ora",
                    options=list(range(len(cloud_frames))),
                    value=len(cloud_frames) - 1,
                    format_func=lambda index: cloud_frames[index][
                        "observed_at"
                    ].strftime("%H:%M"),
                    key="cloud_frame_hour",
                )
                selected_frame = cloud_frames[selected_frame_index]
                st.image(
                    selected_frame["path"],
                    caption=selected_frame["observed_at"].strftime(
                        "%H:%M del %d/%m/%Y (ora italiana)"
                    ),
                    width="stretch",
                )


# TAB: Dati
with tab_data:
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
            width="stretch",
        )
        st.info(
            f"Total records: {len(df)}"
        )

        slug = (
            f"{selected_station_name}_{selected_var}_{days}g"
            .lower()
            .replace(" ", "-")
        )
        st.download_button(
            "⬇️ Scarica CSV della selezione",
            data=observations_csv_bytes(
                station_id=station_id,
                variable_type=variable_type,
                days=days,
            ),
            file_name=f"meteo42_{slug}.csv",
            mime="text/csv",
            help=(
                "Esporta le righe filtrate qui sopra. Per l'intero database "
                "conviene copiare arpav_meteo.sqlite, che è già un file."
            ),
        )
    else:
        st.warning("Nessun dato disponibile")


# TAB: Stazioni
with tab_stations:
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


# TAB: Grafici
with tab_charts:
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
                    render_wet_bulb_chart(
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

                render_chart(
                    build_wind_figure(
                        speed_df,
                        direction_df,
                        var_label(speed_var),
                        speed_unit,
                    ),
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
                render_chart(
                    build_soil_figure(soil_df),
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
                        render_chart(
                            build_range_figure(
                                daily_aggregation,
                                f"{var_label(selected_aggregation_var)} - andamento giornaliero",
                                aggregation_unit,
                            ),
                        )
                with monthly_col:
                    if monthly_aggregation.empty:
                        st.info("Nessun dato mensile disponibile")
                    else:
                        render_chart(
                            build_range_figure(
                                monthly_aggregation,
                                f"{var_label(selected_aggregation_var)} - andamento mensile",
                                aggregation_unit,
                            ),
                        )
        else:
            st.warning("Nessun dato disponibile per il periodo selezionato")
    else:
        st.info("Seleziona almeno una stazione")


# TAB: Storico annuale
with tab_history:
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
                    render_chart(
                        build_extremes_band_figure(
                            weekly_bands,
                            f"{var_label(selected_yearly_var)} - andamento settimanale",
                            yearly_var_unit,
                        ),
                    )

                if monthly_bands.empty:
                    st.info("Nessun dato mensile disponibile")
                else:
                    render_chart(
                        build_extremes_band_figure(
                            monthly_bands,
                            f"{var_label(selected_yearly_var)} - andamento mensile",
                            yearly_var_unit,
                        ),
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
                        render_chart(
                            build_precipitation_totals_figure(
                                weekly_totals, "Precipitazione settimanale"
                            ),
                        )
                with monthly_prec_col:
                    if monthly_totals.empty:
                        st.info("Nessun totale mensile disponibile")
                    else:
                        render_chart(
                            build_precipitation_totals_figure(
                                monthly_totals, "Precipitazione mensile"
                            ),
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
                    render_chart(
                        build_yearly_precipitation_comparison(prec_history_df),
                    )


# TAB: Clima
@st.cache_data(ttl=3600, show_spinner=False)
def get_first_observation_year() -> int | None:
    """Primo anno con osservazioni ARPAV, per sapere da quando il confronto esiste."""
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT MIN(observation_at) FROM observations"
        ).fetchone()
    finally:
        conn.close()
    if not row or not row[0]:
        return None
    return int(str(row[0])[:4])


with tab_climate:
    m42_section(
        "Clima",
        eyebrow="ERA5-Land · rianalisi ECMWF",
        subtitle=(
            "Il fondale lungo sotto una serie osservata corta: temperatura, "
            "umidità e precipitazione orarie dal 1950 per la cella di griglia "
            "più vicina alla stazione."
        ),
    )

    if not ERA5_DATABASE_PATH.exists():
        st.info(
            f"Nessun database di rianalisi in `{ERA5_DATABASE_PATH}`. "
            "Si costruisce scaricando i GRIB dal CDS e importandoli:\n\n"
            "```bash\n"
            ".venv/bin/python download_era5_land.py \\\n"
            "  --from 1950-01-01 --to 2026-07-31 --lat 45.6 --lon 12.3\n"
            ".venv/bin/python import_era5_land.py \\\n"
            "  raw/era5-land --database era5_land.sqlite\n"
            "```"
        )
    else:
        monthly_era5 = get_era5_monthly()

        if monthly_era5.empty:
            st.warning(
                "Il database di rianalisi esiste ma è vuoto: manca l'import "
                "dei GRIB scaricati."
            )
        else:
            yearly_era5 = era5_yearly_from_monthly(monthly_era5)
            ore_totali = int(monthly_era5["ore"].sum())
            primo = monthly_era5.iloc[0]
            ultimo = monthly_era5.iloc[-1]
            incompleti = monthly_era5[~monthly_era5["completo"]]

            tiles = [
                m42_tile(
                    "Periodo coperto",
                    f"{int(primo['anno'])}-{int(ultimo['anno'])}",
                    f"{ore_totali:,} ore".replace(",", "."),
                ),
                m42_tile(
                    "Anni completi",
                    str(len(yearly_era5)),
                    "usati per medie e confronti",
                ),
            ]
            if not yearly_era5.empty:
                piu_caldo = yearly_era5.loc[yearly_era5["t_media"].idxmax()]
                piu_freddo = yearly_era5.loc[yearly_era5["t_media"].idxmin()]
                tiles += [
                    m42_tile(
                        "Media del periodo",
                        f"{(yearly_era5['t_media'] * yearly_era5['ore']).sum() / yearly_era5['ore'].sum():.2f} °C",
                        f"pioggia {yearly_era5['prec_mm'].mean():.0f} mm/anno",
                    ),
                    m42_tile(
                        "Anno più caldo",
                        f"{int(piu_caldo['anno'])}",
                        f"{piu_caldo['t_media']:.2f} °C",
                    ),
                    m42_tile(
                        "Anno più freddo",
                        f"{int(piu_freddo['anno'])}",
                        f"{piu_freddo['t_media']:.2f} °C",
                    ),
                    m42_tile(
                        "Estremi orari",
                        f"{yearly_era5['t_min'].min():.1f} / {yearly_era5['t_max'].max():.1f} °C",
                        "minimo e massimo assoluti",
                    ),
                ]
            m42_render_tiles(tiles)

            if not incompleti.empty:
                mesi_parziali = ", ".join(
                    f"{ITALIAN_MONTHS_SHORT[int(riga['mese']) - 1]} {int(riga['anno'])}"
                    for _, riga in incompleti.iterrows()
                )
                singolare = len(incompleti) == 1
                st.caption(
                    f"⏳ Scaricamento in corso: {mesi_parziali} "
                    + (
                        "è ancora incompleto e resta fuori"
                        if singolare
                        else "sono ancora incompleti e restano fuori"
                    )
                    + " da medie e confronti, che altrimenti risulterebbero"
                    " falsati."
                )

            st.divider()

            if len(yearly_era5) < 2:
                st.info(
                    "Servono almeno due anni completi per i confronti annuali. "
                    "Per ora c'è "
                    f"{len(yearly_era5)} anno completo: i grafici compaiono "
                    "man mano che lo scaricamento avanza."
                )
            else:
                st.write("### Andamento annuale")
                # Due strati facoltativi sulla sola figura delle temperature:
                # spenti di default, perché il grafico di base risponde già a
                # una domanda sua e non deve pagare il prezzo di chi ne ha
                # un'altra.
                sovrapp_1, sovrapp_2 = st.columns(2)
                with sovrapp_1:
                    mostra_decenni = st.checkbox(
                        "📐 Medie per decennio",
                        key="era5_annuale_decenni",
                    )
                with sovrapp_2:
                    ultimi_365 = era5_media_ultimi_365_giorni()
                    mostra_365 = (
                        st.checkbox(
                            "🗓️ Media degli ultimi 365 giorni",
                            key="era5_annuale_365",
                            help=(
                                f"365 giorni fino al {ultimi_365[1]}: una "
                                "finestra lunga un anno, quindi confrontabile "
                                "con le medie annue anche se non coincide con "
                                "un anno solare."
                            )
                            if ultimi_365
                            else None,
                            disabled=ultimi_365 is None,
                        )
                        and ultimi_365 is not None
                    )
                render_chart(
                    build_era5_annual_temperature_figure(
                        yearly_era5,
                        decenni=mostra_decenni,
                        ultimi_365=ultimi_365 if mostra_365 else None,
                    )
                )
                render_chart(build_era5_annual_precipitation_figure(yearly_era5))

                st.write("### Ciclo annuale")
                render_chart(build_era5_monthly_climatology_figure(monthly_era5))

                decenni = (
                    monthly_era5.loc[monthly_era5["completo"], "anno"] // 10
                ).nunique()
                if decenni >= 2:
                    render_chart(
                        build_era5_decade_profile_figure(monthly_era5)
                    )
                else:
                    st.caption(
                        "Il confronto tra decenni compare quando lo storico "
                        "ne copre almeno due completi."
                    )

            primo_anno_arpav = get_first_observation_year()
            ultimo_anno_era5 = int(monthly_era5["anno"].max())
            if primo_anno_arpav and ultimo_anno_era5 < primo_anno_arpav:
                st.info(
                    f"Il confronto con le osservazioni ARPAV — che partono dal "
                    f"{primo_anno_arpav} — sarà possibile quando la rianalisi "
                    f"arriverà a quell'anno: oggi si ferma al "
                    f"{ultimo_anno_era5}. Nessuna ora in comune, quindi "
                    "nessun grafico di scarto."
                )

            st.divider()
            st.write("### Interroga i dati")
            st.caption(
                "Ricette pronte, scritte e verificate. Il modello "
                "locale non scrive SQL: **sceglie** la ricetta e ne riempie i "
                "parametri, che restano correggibili prima di eseguire. Chi "
                "preferisce fa da sé, dalla libreria o scrivendo SQL."
            )
            st.caption(
                "⚠️ ERA5 è la media di una cella di circa 11 × 8 km campionata "
                "ogni ora: gli estremi risultano più smorzati di quelli di un "
                "termometro. I conteggi di giorni oltre una soglia non sono "
                "confrontabili con quelli di una stazione — in tutto "
                "l'archivio non c'è un giorno a 35 °C, e non vuol dire che non "
                "abbia mai fatto così caldo."
            )

            anni_completi = [int(anno) for anno in yearly_era5["anno"]]
            copertura = (
                f"ore dal {int(primo['anno'])} al {ultimo_anno_era5}. Anni "
                "completi, gli unici utilizzabili per medie e confronti "
                "annui: "
                + (
                    f"{anni_completi[0]}-{anni_completi[-1]}"
                    if anni_completi
                    else "nessuno"
                )
                + "."
            )

            modo = st.radio(
                "Come vuoi procedere",
                ("Chiedi in italiano", "Scegli dalla libreria", "SQL libero"),
                horizontal=True,
                key="era5_modo",
                label_visibility="collapsed",
            )

            # Libreria di serie più le ricette salvate dall'utente. Si
            # rilegge a ogni giro invece di stare in cache: il file è minuscolo
            # e una ricetta appena salvata deve comparire subito, altrimenti
            # sembra che il salvataggio non abbia funzionato.
            ricette_disponibili = tutte_le_ricette()
            ricette_per_id = {r["id"]: r for r in ricette_disponibili}

            ricetta_scelta = None

            if modo == "Chiedi in italiano":
                domanda = st.text_input(
                    "Domanda",
                    key="era5_domanda",
                    placeholder=(
                        "Nel 1960 quanti giorni con massima ≥ 30 gradi?"
                    ),
                )
                if st.button("Trova la ricetta", key="era5_proponi"):
                    if not domanda.strip():
                        st.warning("Scrivi prima una domanda.")
                    else:
                        try:
                            with st.spinner("Il modello sta scegliendo…"):
                                scelta = era5_scegli_ricetta(
                                    domanda, copertura, ricette_disponibili
                                )
                            if scelta.get("id") in ricette_per_id:
                                st.session_state["era5_ricetta"] = scelta["id"]
                                ricetta_llm = ricette_per_id[scelta["id"]]
                                proposti = scelta.get("parametri") or {}
                                # I valori proposti diventano il contenuto dei
                                # widget: restano correggibili prima di
                                # eseguire, che è tutto il punto della forma
                                # ibrida. Vanno riportati nei limiti, altrimenti
                                # un valore fuori scala fa esplodere il widget
                                # prima che la validazione possa spiegarlo.
                                for parametro in ricetta_llm["parametri"]:
                                    nome = parametro["nome"]
                                    if nome not in proposti:
                                        continue
                                    try:
                                        valore = float(proposti[nome])
                                    except (TypeError, ValueError):
                                        continue
                                    valore = min(
                                        max(valore, parametro["minimo"]),
                                        parametro["massimo"],
                                    )
                                    st.session_state[
                                        era5_chiave_parametro(
                                            ricetta_llm, parametro
                                        )
                                    ] = (
                                        valore
                                        if parametro["tipo"] == "decimale"
                                        else int(valore)
                                    )
                                st.session_state.pop("era5_risultato", None)
                            else:
                                st.warning(
                                    "Nessuna ricetta della libreria risponde a "
                                    "questa domanda. Prova a sceglierla a mano "
                                    "o passa a «SQL libero», dove può provarci un "
                                    "modello più capace."
                                )
                        except requests.RequestException as error:
                            st.warning(
                                f"⚠️ Modello {OLLAMA_MODEL} non raggiungibile "
                                f"({error}). Puoi scegliere la ricetta a mano."
                            )
                        except ValueError as error:
                            st.warning(
                                f"Il modello non ha risposto in modo "
                                f"utilizzabile ({error}). Scegli la ricetta a "
                                "mano."
                            )
                if st.session_state.get("era5_ricetta") in ricette_per_id:
                    ricetta_scelta = ricette_per_id[
                        st.session_state["era5_ricetta"]
                    ]
                    st.success(f"Ricetta scelta: **{ricetta_scelta['titolo']}**")

            elif modo == "Scegli dalla libreria":
                titoli = {
                    (
                        f"{q['titolo']} ⭐"
                        if q.get("utente")
                        else q["titolo"]
                    ): q["id"]
                    for q in ricette_disponibili
                }
                titolo = st.selectbox(
                    "Ricetta", list(titoli.keys()), key="era5_titolo"
                )
                ricetta_scelta = ricette_per_id[titoli[titolo]]
                if ricetta_scelta.get("esempio"):
                    st.caption(
                        f"Esempio di domanda: _{ricetta_scelta['esempio']}_"
                    )
                if ricetta_scelta.get("utente"):
                    st.caption("⭐ Ricetta salvata da te.")
                    if st.button("Elimina questa ricetta", key="era5_elimina"):
                        elimina_ricetta_utente(ricetta_scelta["id"])
                        # Via anche la selezione, altrimenti al rerun il menù
                        # cerca un titolo che non esiste più e si pianta.
                        st.session_state.pop("era5_titolo", None)
                        st.rerun()

            if ricetta_scelta is not None:
                valori = {}
                if ricetta_scelta["parametri"]:
                    colonne = st.columns(len(ricetta_scelta["parametri"]))
                    for colonna, parametro in zip(
                        colonne, ricetta_scelta["parametri"]
                    ):
                        chiave = era5_chiave_parametro(
                            ricetta_scelta, parametro
                        )
                        with colonna:
                            if parametro["tipo"] == "mese":
                                indice = int(
                                    st.session_state.get(
                                        chiave, parametro["default"]
                                    )
                                )
                                indice = min(max(indice, 1), 12)
                                nome_mese = st.selectbox(
                                    parametro["etichetta"],
                                    ITALIAN_MONTHS,
                                    index=indice - 1,
                                    key=f"{chiave}_sel",
                                )
                                valori[parametro["nome"]] = (
                                    ITALIAN_MONTHS.index(nome_mese) + 1
                                )
                            else:
                                st.session_state.setdefault(
                                    chiave, parametro["default"]
                                )
                                valori[parametro["nome"]] = st.number_input(
                                    parametro["etichetta"],
                                    min_value=parametro["minimo"],
                                    max_value=parametro["massimo"],
                                    step=1.0
                                    if parametro["tipo"] == "decimale"
                                    else 1,
                                    key=chiave,
                                )

                try:
                    parametri_puliti = normalizza_parametri(
                        ricetta_scelta, valori
                    )
                except ValueError as error:
                    parametri_puliti = None
                    st.error(str(error))

                with st.expander("La query che verrà eseguita"):
                    st.code(ricetta_scelta["sql"], language="sql")

                if st.button(
                    "Esegui",
                    key="era5_esegui_ricetta",
                    disabled=parametri_puliti is None,
                ):
                    try:
                        with st.spinner("Eseguo…"):
                            risultato, troncato = era5_run_query(
                                ricetta_scelta["sql"], parametri_puliti
                            )
                        st.session_state["era5_risultato"] = risultato
                        st.session_state["era5_troncato"] = troncato
                    except sqlite3.Error as error:
                        st.session_state.pop("era5_risultato", None)
                        st.error(f"SQLite: {error}")

            if modo == "SQL libero":
                st.session_state.setdefault("era5_sql", "")
                # Il modello esterno vive **solo** qui. Scegliere una ricetta
                # dall'elenco il 9B locale lo fa senza sbagliare; scrivere SQL
                # nuovo no, ed è l'unico compito rimasto che meriti un modello
                # più capace. Resta una scelta a mano: è a consumo, e una
                # dashboard che ci passa da sola fa crescere un conto che
                # nessuno ha deciso (brain42, MEMORANDUM 2026-08-03).
                usa_esterno = False
                if era5_esterno_configurato():
                    motore = st.radio(
                        "Chi scrive la query",
                        (
                            f"Locale · {OLLAMA_MODEL}",
                            f"Esterno · {LLM_EXTERNAL_MODEL}",
                        ),
                        horizontal=True,
                        key="era5_motore",
                        help="L'esterno è a consumo e va scelto apposta.",
                    )
                    usa_esterno = motore.startswith("Esterno")
                nome_modello = (
                    LLM_EXTERNAL_MODEL if usa_esterno else OLLAMA_MODEL
                )
                domanda_libera = st.text_input(
                    "Domanda (facoltativa, serve al modello per scrivere l'SQL)",
                    key="era5_domanda_libera",
                )
                if st.button("Proponi la query", key="era5_proponi_sql"):
                    if not domanda_libera.strip():
                        st.warning("Scrivi prima una domanda.")
                    else:
                        try:
                            with st.spinner("Il modello sta scrivendo…"):
                                st.session_state["era5_sql"] = era5_propose_sql(
                                    domanda_libera, copertura, usa_esterno
                                )
                            st.session_state.pop("era5_risultato", None)
                        except requests.RequestException as error:
                            st.warning(
                                f"⚠️ Modello {nome_modello} non raggiungibile "
                                f"({error}). Puoi scrivere l'SQL a mano qui "
                                "sotto."
                            )
                sql_libero = st.text_area(
                    "SQL da eseguire",
                    key="era5_sql",
                    height=160,
                    help=(
                        "Sola lettura: connessione in mode=ro con PRAGMA "
                        "query_only, query interrotta dopo 15 secondi."
                    ),
                )
                problema = (
                    era5_validate_sql(sql_libero) if sql_libero.strip() else None
                )
                if problema:
                    st.error(f"Query rifiutata: {problema}.")

                # Se l'SQL contiene `:nome`, i valori si riempiono qui: senza,
                # una query parametrica non sarebbe eseguibile, e quindi non
                # sarebbe verificabile prima di finire nel ricettario — che è
                # invece il solo modo in cui ha senso salvarla.
                valori_liberi = {}
                parametri_liberi = (
                    parametri_da_sql(sql_libero) if sql_libero.strip() else []
                )
                if parametri_liberi:
                    colonne_libere = st.columns(len(parametri_liberi))
                    for colonna, parametro in zip(
                        colonne_libere, parametri_liberi
                    ):
                        with colonna:
                            chiave_libera = f"era5_libero_{parametro['nome']}"
                            st.session_state.setdefault(
                                chiave_libera, parametro["default"]
                            )
                            valori_liberi[parametro["nome"]] = st.number_input(
                                parametro["etichetta"],
                                min_value=parametro["minimo"],
                                max_value=parametro["massimo"],
                                step=1.0
                                if parametro["tipo"] == "decimale"
                                else 1,
                                key=chiave_libera,
                            )

                if st.button(
                    "Esegui",
                    key="era5_esegui",
                    disabled=bool(problema) or not sql_libero.strip(),
                ):
                    try:
                        with st.spinner("Eseguo…"):
                            risultato, troncato = era5_run_query(
                                sql_libero, valori_liberi
                            )
                        st.session_state["era5_risultato"] = risultato
                        st.session_state["era5_troncato"] = troncato
                        st.session_state["era5_sql_eseguito"] = sql_libero
                    except sqlite3.Error as error:
                        st.session_state.pop("era5_risultato", None)
                        st.error(f"SQLite: {error}")

            if "era5_risultato" in st.session_state:
                risultato = st.session_state["era5_risultato"]
                if risultato.empty:
                    st.info("La query non ha restituito righe.")
                else:
                    colonne_numeriche = [
                        colonna
                        for colonna in risultato.columns
                        if pd.api.types.is_numeric_dtype(risultato[colonna])
                    ]
                    # Una serie si guarda meglio disegnata, un conteggio no:
                    # la vista parte da quella giusta per la forma del
                    # risultato, poi resta quella che sceglie chi guarda.
                    st.session_state.setdefault(
                        "era5_vista",
                        "Grafico"
                        if len(risultato) >= 3 and colonne_numeriche
                        else "Tabella",
                    )
                    vista = st.radio(
                        "Vista",
                        ("Tabella", "Grafico"),
                        horizontal=True,
                        key="era5_vista",
                        label_visibility="collapsed",
                    )

                    if vista == "Tabella":
                        st.dataframe(risultato, width="stretch")
                    elif not colonne_numeriche or len(risultato) < 2:
                        st.info(
                            "Questo risultato non ha la forma di una serie: "
                            "una riga sola, o nessuna colonna numerica. "
                            "Guardalo come tabella."
                        )
                    else:
                        non_numeriche = [
                            colonna
                            for colonna in risultato.columns
                            if colonna not in colonne_numeriche
                        ]
                        asse_x_default = (
                            non_numeriche[0]
                            if non_numeriche
                            else risultato.columns[0]
                        )
                        colonna_x = st.selectbox(
                            "Asse orizzontale",
                            list(risultato.columns),
                            index=list(risultato.columns).index(asse_x_default),
                            key="era5_grafico_x",
                        )
                        candidate_y = [
                            colonna
                            for colonna in colonne_numeriche
                            if colonna != colonna_x
                        ]
                        # Le percentuali restano fuori dalla scelta iniziale
                        # quando c'è dell'altro: un'umidità fra 0 e 100 sullo
                        # stesso asse di temperature fra -20 e 5 schiaccia le
                        # temperature contro il fondo. Si aggiunge a mano se
                        # interessa, e da sola si disegna benissimo.
                        percentuali = [
                            colonna
                            for colonna in candidate_y
                            if re.search(r"pct|umidit|percent", colonna, re.I)
                        ]
                        preselezione = [
                            colonna
                            for colonna in candidate_y
                            if colonna not in percentuali
                        ] or candidate_y
                        colonne_y = st.multiselect(
                            "Cosa disegnare",
                            candidate_y,
                            default=preselezione,
                            key="era5_grafico_y",
                        )
                        if not colonne_y:
                            st.info("Scegli almeno una colonna da disegnare.")
                        else:
                            gruppi_misti = any(
                                ERA5_COLONNE_A_BARRE.search(colonna)
                                for colonna in colonne_y
                            ) and any(
                                not ERA5_COLONNE_A_BARRE.search(colonna)
                                for colonna in colonne_y
                            )
                            tipo_default = (
                                "Barre"
                                if all(
                                    ERA5_COLONNE_A_BARRE.search(colonna)
                                    for colonna in colonne_y
                                )
                                else "Linee"
                            )
                            # La chiave dipende dalla famiglia di colonne
                            # scelte: altrimenti il tipo scelto per una serie
                            # di temperature resta appiccicato quando si passa
                            # alla sola pioggia, che vuole le barre. Stesso
                            # difetto dei parametri delle ricette, stessa cura.
                            chiave_tipo = (
                                "era5_grafico_tipo_mm"
                                if tipo_default == "Barre"
                                else "era5_grafico_tipo_altro"
                            )
                            st.session_state.setdefault(
                                chiave_tipo, tipo_default
                            )
                            # Una classifica (`ORDER BY media DESC LIMIT 15`)
                            # non ha un asse orizzontale su cui procedere: la
                            # scelta non si applica, e dirlo evita di lasciare
                            # acceso un "Linee" che il grafico ignora.
                            classifica = not era5_e_una_serie(
                                risultato[colonna_x]
                            )
                            if classifica:
                                tipo = tipo_default
                                st.caption(
                                    f"Le righe non sono in ordine di "
                                    f"«{colonna_x}»: è una classifica, non un "
                                    "andamento. Restano nell'ordine del "
                                    "risultato, senza linee che uniscano "
                                    "valori lontani nel tempo."
                                )
                            elif gruppi_misti:
                                # La scelta linee/barre non si applica: qui
                                # comanda l'unità di misura, non il gusto.
                                tipo = tipo_default
                                st.caption(
                                    "Pioggia a barre sull'asse destro (mm), "
                                    "temperature a linee su quello sinistro "
                                    "(°C): unità diverse non stanno sulla "
                                    "stessa scala."
                                )
                            else:
                                tipo = st.radio(
                                    "Tipo",
                                    ("Linee", "Barre"),
                                    horizontal=True,
                                    key=chiave_tipo,
                                    label_visibility="collapsed",
                                )
                            render_chart(
                                era5_figura_risultato(
                                    risultato, colonna_x, colonne_y, tipo
                                )
                            )

                    if st.session_state.get("era5_troncato"):
                        st.caption(
                            "Mostrate le prime 2000 righe: il risultato è più "
                            "lungo."
                        )

                    # Una query verificata funzionante vale quanto una di
                    # quelle di serie: si salva e la volta dopo il modello può
                    # sceglierla da sé, invece di riscriverla e risbagliarla.
                    if modo == "SQL libero" and st.session_state.get(
                        "era5_sql_eseguito"
                    ):
                        sql_da_salvare = st.session_state["era5_sql_eseguito"]
                        with st.expander("Salva questa query nel ricettario"):
                            parametri_rilevati = parametri_da_sql(sql_da_salvare)
                            if parametri_rilevati:
                                st.caption(
                                    "Parametri riconosciuti: "
                                    + ", ".join(
                                        f"`:{p['nome']}`"
                                        for p in parametri_rilevati
                                    )
                                    + " — diventeranno campi da riempire."
                                )
                            else:
                                st.caption(
                                    "Nessun parametro: la ricetta userà sempre "
                                    "questi stessi valori. Per renderla "
                                    "riusabile, sostituisci i numeri fissi con "
                                    "`:anno`, `:mese`, `:soglia` o `:limite` "
                                    "nell'SQL qui sopra, riesegui e salva."
                                )
                            st.session_state.setdefault(
                                "era5_salva_esempio",
                                st.session_state.get("era5_domanda_libera", ""),
                            )
                            titolo_nuovo = st.text_input(
                                "Titolo della ricetta",
                                key="era5_salva_titolo",
                                placeholder="Giorni caldi tra due anni",
                            )
                            st.text_input(
                                "Domanda d'esempio",
                                key="era5_salva_esempio",
                                help=(
                                    "Serve al modello per capire quando questa "
                                    "ricetta è quella giusta."
                                ),
                            )
                            if st.button("Salva", key="era5_salva"):
                                try:
                                    salvata = salva_ricetta_utente(
                                        titolo_nuovo,
                                        st.session_state["era5_salva_esempio"],
                                        sql_da_salvare,
                                    )
                                except (ValueError, OSError) as error:
                                    st.error(f"Non salvata: {error}")
                                else:
                                    st.success(
                                        f"Salvata come «{salvata['titolo']}»: "
                                        "ora è nella libreria e il modello può "
                                        "sceglierla."
                                    )
