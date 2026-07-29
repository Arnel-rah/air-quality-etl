import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in the environment")
if not OPENWEATHER_API_KEY:
    raise ValueError("OPENWEATHER_API_KEY must be set in the environment")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://api.openweathermap.org/data/2.5"
LOCATIONS_FILE = Path(__file__).parent / "locations.json"

TABLE_NAME = "raw_air_quality"   # <- adapte si le nom exact de ta table diffère
MONTHS_BACK = 12                 # profondeur de l'historique à récupérer
CHUNK_DAYS = 30                  # taille des fenêtres envoyées à l'API OpenWeather
BATCH_SIZE = 500                 # taille des lots envoyés à Supabase
SLEEP_BETWEEN_CALLS = 1          # secondes entre 2 appels API (rate limit)


def load_locations() -> List[Dict[str, Any]]:
    if not LOCATIONS_FILE.exists():
        raise FileNotFoundError(f"Locations file not found: {LOCATIONS_FILE}")

    with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
        locations = json.load(f)

    required_keys = {"name", "lat", "lon"}
    for loc in locations:
        missing = required_keys - loc.keys()
        if missing:
            raise ValueError(f"Location entry {loc} is missing keys: {missing}")

    return locations


def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Optional[dict]:
    if params is None:
        params = {}
    params["appid"] = OPENWEATHER_API_KEY

    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=60)
            if response.status_code == 401:
                raise ValueError("Invalid or inactive OpenWeatherMap API key")
            if response.status_code == 429:
                wait = 5 * attempt
                print(f"Rate limit reached, waiting {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API error (attempt {attempt}/{retries}): {e}")
            time.sleep(2 * attempt)
    return None


def build_time_windows(months_back: int, chunk_days: int) -> List[Tuple[datetime, datetime]]:
    """
    Découpe la période [now - months_back, now] en fenêtres de `chunk_days` jours.
    L'API air_pollution/history renvoie TOUTES les mesures horaires de la période
    demandée d'un coup : mieux vaut donc éviter d'envoyer 12 mois en une seule requête
    (payload énorme, risque de timeout) et travailler par tranches.
    """
    now = datetime.now(timezone.utc)
    start_global = now - timedelta(days=30 * months_back)

    windows = []
    current_start = start_global
    while current_start < now:
        current_end = min(current_start + timedelta(days=chunk_days), now)
        windows.append((current_start, current_end))
        current_start = current_end

    return windows


def extract_air_quality_history(
    latitude: float,
    longitude: float,
    location_name: str,
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    params = {
        "lat": latitude,
        "lon": longitude,
        "start": int(start.timestamp()),
        "end": int(end.timestamp()),
    }
    data = api_get("air_pollution/history", params)
    if not data:
        return []

    results = data.get("list", [])
    records: List[Dict[str, Any]] = []

    for entry in results:
        dt = entry.get("dt")
        if dt is None:import os
import json
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Any, Dict, List, Optional

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in the environment")
if not OPENWEATHER_API_KEY:
    raise ValueError("OPENWEATHER_API_KEY must be set in the environment")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://api.openweathermap.org/data/2.5"
LOCATIONS_FILE = Path(__file__).parent / "locations.json"


def load_locations() -> List[Dict[str, Any]]:
    if not LOCATIONS_FILE.exists():
        raise FileNotFoundError(f"Locations file not found: {LOCATIONS_FILE}")

    with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
        locations = json.load(f)

    required_keys = {"name", "lat", "lon"}
    for loc in locations:
        missing = required_keys - loc.keys()
        if missing:
            raise ValueError(f"Location entry {loc} is missing keys: {missing}")

    return locations


def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Optional[dict]:
    if params is None:
        params = {}
    params["appid"] = OPENWEATHER_API_KEY

    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 401:
                raise ValueError("Invalid or inactive OpenWeatherMap API key")
            if response.status_code == 429:
                wait = 5 * attempt
                print(f"Rate limit reached, waiting {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API error (attempt {attempt}/{retries}): {e}")
            time.sleep(2 * attempt)
    return None


def extract_air_quality(latitude: float, longitude: float, location_name: str) -> Optional[Dict[str, Any]]:
    data = api_get("air_pollution", {"lat": latitude, "lon": longitude})
    if not data:
        return None

    results = data.get("list", [])
    if not results:
        return None

    entry = results[0]
    aqi = (entry.get("main") or {}).get("aqi")
    components = entry.get("components", {})

    hour_timestamp = datetime.now(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    ).isoformat()

    return {
        "timestamp": hour_timestamp,
        "location": location_name,
        "latitude": latitude,
        "longitude": longitude,
        "aqi": aqi,
        "co": components.get("co"),
        "no": components.get("no"),
        "no2": components.get("no2"),
        "o3": components.get("o3"),
        "so2": components.get("so2"),
        "pm2_5": components.get("pm2_5"),
        "pm10": components.get("pm10"),
        "nh3": components.get("nh3"),
    }


def run_extraction():
    locations = load_locations()

    records: List[Dict[str, Any]] = []
    for loc in locations:
        print(f"Fetching air quality for {loc['name']}...")
        record = extract_air_quality(loc["lat"], loc["lon"], loc["name"])
        if record:
            records.append(record)
        time.sleep(1)

    if records:
        supabase.table("air_quality_realtime").upsert(
            records, on_conflict="timestamp,location"
        ).execute()
        print(f"Success: {len(records)} records upserted")
    else:
        print("No data found")


if __name__ == "__main__":
    run_extraction()

            continue

        timestamp = (
            datetime.fromtimestamp(dt, tz=timezone.utc)
            .replace(minute=0, second=0, microsecond=0)
            .isoformat()
        )

        components = entry.get("components", {})
        aqi = (entry.get("main") or {}).get("aqi")

        records.append({
            "timestamp": timestamp,
            "location": location_name,
            "latitude": latitude,
            "longitude": longitude,
            "aqi": aqi,
            "co": components.get("co"),
            "no": components.get("no"),
            "no2": components.get("no2"),
            "o3": components.get("o3"),
            "so2": components.get("so2"),
            "pm2_5": components.get("pm2_5"),
            "pm10": components.get("pm10"),
            "nh3": components.get("nh3"),
        })

    return records


def upsert_batch(records: List[Dict[str, Any]]) -> None:
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        supabase.table(TABLE_NAME).upsert(
            batch, on_conflict="timestamp,location"
        ).execute()
        print(f"  -> {len(batch)} lignes upsertées ({i + len(batch)}/{len(records)})")


def run_history_extraction():
    locations = load_locations()
    windows = build_time_windows(MONTHS_BACK, CHUNK_DAYS)

    print(f"{len(windows)} fenêtres temporelles x {len(locations)} localisations à récupérer")

    for loc in locations:
        print(f"\n=== Historique pour {loc['name']} ===")
        location_records: List[Dict[str, Any]] = []

        for start, end in windows:
            print(f"  Récupération {start.date()} -> {end.date()}...")
            records = extract_air_quality_history(
                loc["lat"], loc["lon"], loc["name"], start, end
            )
            if records:
                location_records.extend(records)
                print(f"    {len(records)} points reçus")
            else:
                print("    Aucune donnée pour cette fenêtre")

            time.sleep(SLEEP_BETWEEN_CALLS)

        if location_records:
            upsert_batch(location_records)
            print(f"Total pour {loc['name']}: {len(location_records)} lignes")
        else:
            print(f"Aucune donnée trouvée pour {loc['name']}")


if __name__ == "__main__":
    run_history_extraction()