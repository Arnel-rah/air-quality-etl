import os
import requests
import time
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
SUPABASE_KEY: Optional[str] = os.getenv("SUPABASE_KEY")
WAQI_API_TOKEN: Optional[str] = os.getenv("WAQI_API_TOKEN")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL et SUPABASE_KEY doivent être définis dans le fichier .env")
if not WAQI_API_TOKEN:
    raise ValueError(
        "WAQI_API_TOKEN doit être défini dans le fichier .env "
        "(token gratuit sur https://aqicn.org/data-platform/token/)"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://api.waqi.info/feed"
CITIES = ["Paris", "Marseille", "Lyon", "Toulouse", "Nice"]

PARAMETER_MAP = {
    "pm25": "pm25",
    "pm10": "pm10",
    "no2": "no2",
    "so2": "so2",
    "co": "co",
    "o3": "o3",
}


def get_city_feed(city: str) -> Optional[dict]:
    url = f"{BASE_URL}/{city}/"
    params = {"token": WAQI_API_TOKEN}
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "ok":
            print(f"Réponse invalide pour {city} : {payload.get('data')}")
            return None
        return payload.get("data")
    except requests.exceptions.RequestException as e:
        print(f"Erreur lors de la récupération des données pour {city} : {e}")
        return None


def extract():
    records = []

    for city in CITIES:
        data = get_city_feed(city)
        if not data:
            continue

        timestamp = data.get("time", {}).get("iso")
        if not timestamp:
            print(f"Timestamp manquant pour {city}, ligne ignorée")
            continue

        global_aqi = data.get("aqi")
        if isinstance(global_aqi, (int, float)):
            records.append({
                "timestamp": timestamp,
                "city": city,
                "parameter": "aqi_global",
                "value": global_aqi,
                "unit": "AQI",
            })

        iaqi = data.get("iaqi", {})
        for waqi_key, parameter_name in PARAMETER_MAP.items():
            if waqi_key in iaqi:
                value = iaqi[waqi_key].get("v")
                if value is None:
                    continue
                records.append({
                    "timestamp": timestamp,
                    "city": city,
                    "parameter": parameter_name,
                    "value": value,
                    "unit": "AQI",
                })

        time.sleep(0.1)

    if records:
        try:
            supabase.table("raw_air_quality").upsert(
                records, on_conflict="city,parameter,timestamp"
            ).execute()
            print(f"{len(records)} mesures brutes upsertées")
        except Exception as e:
            print(f"Erreur lors de l'insertion dans Supabase : {e}")
    else:
        print("Aucune mesure récupérée")


if __name__ == "__main__":
    extract()
