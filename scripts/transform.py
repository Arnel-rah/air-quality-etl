import os
import json
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any

CITIES = ["Paris", "Marseille", "Lyon", "Toulouse", "Nice"]
PARAMETER_MAP = {
    "pm25": "pm25",
    "pm10": "pm10",
    "no2": "no2",
    "so2": "so2",
    "co": "co",
    "o3": "o3",
}

def transform():
    os.makedirs("clean", exist_ok=True)
    all_records: List[Dict[str, Any]] = []

    raw_files = [f for f in os.listdir("raw") if f.endswith(".json")]
    if not raw_files:
        print("Aucun fichier trouvé dans raw/")
        return

    for filename in raw_files:
        filepath = os.path.join("raw", filename)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        city = filename.split("_")[0].capitalize()
        if city not in CITIES:
            city = data.get("city", {}).get("name", "Unknown")

        timestamp = data.get("time", {}).get("iso")
        if not timestamp:
            continue

        global_aqi = data.get("aqi")
        if isinstance(global_aqi, (int, float)):
            all_records.append({
                "timestamp": timestamp,
                "city": city,
                "parameter": "aqi_global",
                "value": global_aqi,
                "unit": "AQI"
            })

        iaqi = data.get("iaqi", {})
        for waqi_key, parameter_name in PARAMETER_MAP.items():
            if waqi_key in iaqi:
                value = iaqi[waqi_key].get("v")
                if value is not None:
                    all_records.append({
                        "timestamp": timestamp,
                        "city": city,
                        "parameter": parameter_name,
                        "value": value,
                        "unit": "AQI"
                    })

    if not all_records:
        print("Aucune donnée à écrire dans clean/")
        return

    df = pd.DataFrame(all_records)
    df = df.dropna(subset=["value", "city", "parameter", "timestamp"])
    df = df.drop_duplicates(subset=["city", "parameter", "timestamp"])

    clean_path = "clean/clean.csv"
    df.to_csv(clean_path, index=False)

    print(f"Fichier clean reconstruit : {clean_path}")
    print(f"Nombre de lignes : {len(df)}")

if __name__ == "__main__":
    transform()
