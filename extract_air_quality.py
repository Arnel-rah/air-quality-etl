import os
import time
import requests
from datetime import datetime, timezone
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


def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None, retries: int = 3) -> Optional[dict]:
    """Generic call to the OpenWeatherMap free API with error handling and retries."""
    if params is None:
        params = {}
    params["appid"] = OPENWEATHER_API_KEY
    params["units"] = "metric"

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


def extract_current_weather(latitude: float, longitude: float, location_name: str) -> Optional[Dict[str, Any]]:
    """Fetch current, real-time weather for a given location."""
    data = api_get("weather", {"lat": latitude, "lon": longitude})
    if not data:
        return None

    main = data.get("main", {})
    wind = data.get("wind", {})
    weather_desc = (data.get("weather") or [{}])[0]
    dt = data.get("dt")

    return {
        "timestamp": datetime.fromtimestamp(dt, tz=timezone.utc).isoformat() if dt else None,
        "location": location_name,
        "latitude": latitude,
        "longitude": longitude,
        "temp": main.get("temp"),
        "feels_like": main.get("feels_like"),
        "humidity": main.get("humidity"),
        "pressure": main.get("pressure"),
        "wind_speed": wind.get("speed"),
        "weather_main": weather_desc.get("main"),
        "weather_description": weather_desc.get("description"),
    }


def run_extraction():
    locations = [
        {"name": "Antananarivo", "lat": -18.8792, "lon": 47.5079},
    ]

    records: List[Dict[str, Any]] = []
    for loc in locations:
        print(f"Fetching current weather for {loc['name']}...")
        record = extract_current_weather(loc["lat"], loc["lon"], loc["name"])
        if record:
            records.append(record)

    if records:
        supabase.table("weather_realtime").upsert(
            records, on_conflict="timestamp,location"
        ).execute()
        print(f"Success: {len(records)} records upserted")
    else:
        print("No data found")


if __name__ == "__main__":
    run_extraction()
