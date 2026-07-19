import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

DATABASE_PATH = Path("arpav_meteo.sqlite")
STATIONS_CONFIG = Path("stations.json")

st.set_page_config(
    page_title="ARPAV Dashboard",
    page_icon="🌤️",
    layout="wide",
)

st.title("🌤️ ARPAV Meteo Dashboard")


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


def get_stations_from_db():
    conn = get_db_connection()
    query = """
        SELECT
            station_id,
            COALESCE(configured_name, api_name, station_id) AS station_name
        FROM stations
        ORDER BY station_id
    """
    return pd.read_sql_query(query, conn)


# Tabs
tab1, tab2, tab3 = st.tabs(
    ["📊 Dati", "⚙️ Stazioni", "📈 Grafici"]
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
    stations = ["Tutte"] + stations_df["station_id"].tolist()

    with col2:
        selected_station = st.selectbox(
            "Stazione",
            stations,
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
        )

    station_id = None if selected_station == "Tutte" else selected_station
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
        chart_stations = st.multiselect(
            "Stazioni",
            stations_df["station_id"].tolist(),
            default=stations_df["station_id"].head(3).tolist(),
        )

    if chart_stations:
        df = get_observations_df(days=chart_days)
        df = df[df["station_id"].isin(chart_stations)]

        if not df.empty:
            var_types = df["variable_type"].unique()

            for var in var_types:
                var_df = df[df["variable_type"] == var].copy()

                if var_df["value_numeric"].notna().sum() > 0:
                    fig = px.line(
                        var_df,
                        x="observation_at",
                        y="value_numeric",
                        color="station_name",
                        title=f"{var}",
                        labels={
                            "observation_at": "Data/Ora",
                            "value_numeric": f"{var} ({var_df['unit'].iloc[0] if len(var_df) > 0 and var_df['unit'].notna().any() else ''})",
                            "station_name": "Stazione",
                        },
                        markers=True,
                    )

                    fig.update_layout(
                        hovermode="x unified",
                        height=400,
                    )

                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                    )
        else:
            st.warning("Nessun dato disponibile per il periodo selezionato")
    else:
        st.info("Seleziona almeno una stazione")
