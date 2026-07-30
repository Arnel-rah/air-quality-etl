import os
import json
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv
from typing import Dict, Any, Optional, cast

load_dotenv()

SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
SUPABASE_KEY: Optional[str] = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Vérifiez SUPABASE_URL et SUPABASE_KEY dans votre fichier .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CITY_COORDS: Dict[str, Dict[str, Any]] = {
    "Paris": {"lat": 48.8566, "lon": 2.3522, "country": "FR"},
    "Marseille": {"lat": 43.2965, "lon": 5.3698, "country": "FR"},
    "Lyon": {"lat": 45.7640, "lon": 4.8357, "country": "FR"},
    "Toulouse": {"lat": 43.6047, "lon": 1.4442, "country": "FR"},
    "Nice": {"lat": 43.7102, "lon": 7.2620, "country": "FR"}
}

def get_city_info(city_name: Any, key: str, default: Any = None) -> Any:
    city_str = str(city_name)
    city_data = CITY_COORDS.get(city_str)
    if isinstance(city_data, dict):
        return city_data.get(key, default)
    return default

def recover() -> None:
    print("1. Récupération des données depuis Supabase (raw_air_quality)...")

    all_data: list[dict[str, Any]] = []
    limit = 5000
    offset = 0

    while True:
        response = supabase.table("raw_air_quality").select("*").range(offset, offset + limit - 1).execute()
        rows = cast(list[dict[str, Any]], response.data)

        if not rows:
            break

        all_data.extend(rows)
        offset += limit
        print(f"   -> {len(all_data)} lignes récupérées...")

    if not all_data:
        print("Aucune donnée trouvée dans raw_air_quality.")
        return

    df = pd.DataFrame(all_data)

    os.makedirs("clean", exist_ok=True)

    df['country'] = df['city'].map(lambda c: get_city_info(c, "country", "FR"))
    df['latitude'] = df['city'].map(lambda c: get_city_info(c, "lat"))
    df['longitude'] = df['city'].map(lambda c: get_city_info(c, "lon"))

    clean_df = df[['timestamp', 'city', 'country', 'latitude', 'longitude', 'parameter', 'value', 'unit']].copy()
    clean_df = clean_df.drop_duplicates(subset=['timestamp', 'city', 'parameter'])
    clean_path = "clean/clean.csv"
    clean_df.to_csv(clean_path, index=False)
    print(f"fichier {clean_path} generer ({len(clean_df)} lignes).")
    os.makedirs("raw", exist_ok=True)

    grouped = df.groupby(['city', 'timestamp'])

    json_count = 0
    for (city_val, ts_val), group in grouped:
        city_str = str(city_val)
        ts_str = str(ts_val)

        dt_formatted = ts_str.replace("-", "").replace(":", "").replace(" ", "_").replace("+0000", "").replace("+00:00", "")[:13]
        filename = f"raw/{city_str.lower()}_{dt_formatted}.json"

        iaqi_dict: dict[str, dict[str, Any]] = {}
        global_aqi = None

        for _, row in group.iterrows():
            param = row['parameter']
            val = row['value']
            if param == "aqi_global":
                global_aqi = val
            else:
                iaqi_dict[str(param)] = {"v": val}

        lat = get_city_info(city_str, "lat", 0.0)
        lon = get_city_info(city_str, "lon", 0.0)

        raw_json = {
            "status": "ok",
            "data": {
                  "aqi": global_aqi if global_aqi is not None else 0,
                "city": {
                    "name": city_str,
                    "geo": [lat, lon]
                },
                "time": {
                    "iso": ts_str
                },
                "iaqi": iaqi_dict
            }
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(raw_json, f, ensure_ascii=False, indent=2)

        json_count += 1

    print(f"{json_count} fichiers JSON bruts créés dans le dossier raw/.")

if __name__ == "__main__":
    recover()
