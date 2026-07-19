import requests
import json
from pathlib import Path

API_URL = "https://api.arpa.veneto.it/REST/v1/meteo_meteogrammi"
OUTPUT_FILE = Path("stations.json")


def fetch_all_stations() -> dict:
    """Scarica tutte le stazioni dal MGRAMMI API"""
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
                "id": codseqst,
                "name": record.get("nome_stazione"),
                "enabled": True,
            }

    return stations


def main():
    print("Fetching all stations from MGRAMMI API...")
    stations = fetch_all_stations()

    config = {
        "stations": list(stations.values())
    }

    OUTPUT_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"✅ Generated {OUTPUT_FILE} with {len(stations)} stations")
    print(f"Example stations:")
    for station in list(stations.values())[:5]:
        print(f"  - {station['id']}: {station['name']}")


if __name__ == "__main__":
    main()
