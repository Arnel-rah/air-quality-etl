import os
import json
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

WAQI_API_TOKEN: Optional[str] = os.getenv("WAQI_API_TOKEN")

if not WAQI_API_TOKEN:
    raise ValueError(
        "WAQI_API_TOKEN doit être défini dans le fichier .env "
        "(token gratuit sur https://aqicn.org/data-platform/token/)"
    )

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
    os.makedirs("raw", exist_ok=True)
    run_timestamp = datetime.utcnow().strftime("%Y%m%d_%H")

    for city in CITIES:
        data = get_city_feed(city)
        if not data:
            continue

        filename = f"raw/{city.lower()}_{run_timestamp}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"Fichier brut sauvegardé : {filename}")
        time.sleep(0.1)

    print("Extraction terminée")

if __name__ == "__main__":
    extract()
