import os
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
