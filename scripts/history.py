import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from supabase import Client, create_client




ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_FILE)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")


if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "SUPABASE_URL and SUPABASE_KEY must be set"
    )


if not OPENWEATHER_API_KEY:
    raise ValueError(
        "OPENWEATHER_API_KEY must be set"
    )


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
)




BASE_URL = (
    "https://api.openweathermap.org/data/2.5"
)

LOCATIONS_FILE = (
    Path(__file__).resolve().parent.parent
    / "locations.json"
)


TABLE_NAME = "raw_air_quality"


START_DATE = datetime(
    2025,
    7,
    29,
    tzinfo=timezone.utc,
)

END_DATE = datetime(
    2026,
    6,
    29,
    tzinfo=timezone.utc,
)



CHUNK_DAYS = 5

SLEEP_BETWEEN_CALLS = 1

MAX_RETRIES = 3




def load_locations() -> List[Dict[str, Any]]:

    if not LOCATIONS_FILE.exists():
        raise FileNotFoundError(
            f"Missing {LOCATIONS_FILE}"
        )


    with open(
        LOCATIONS_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        locations = json.load(file)


    return locations





def fetch_history(
    latitude: float,
    longitude: float,
    start: datetime,
    end: datetime,
) -> Optional[dict]:


    url = (
        f"{BASE_URL}/air_pollution/history"
    )


    params = {
        "lat": latitude,
        "lon": longitude,
        "start": int(start.timestamp()),
        "end": int(end.timestamp()),
        "appid": OPENWEATHER_API_KEY,
    }


    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = requests.get(
                url,
                params=params,
                timeout=60,
            )


            if response.status_code == 401:
                raise ValueError(
                    "Invalid OpenWeather API key"
                )

            if response.status_code == 429:
                wait = 5 * attempt
                print(f"Rate limit, waiting {wait}s...")
                time.sleep(wait)
                continue


            response.raise_for_status()


            return response.json()


        except requests.exceptions.RequestException as error:

            print(
                f"OpenWeather error (attempt {attempt}/{MAX_RETRIES}):",
                error
            )
            time.sleep(3 * attempt)


    print(f"Abandon de la fenêtre {start.date()} -> {end.date()} après {MAX_RETRIES} tentatives")
    return None





def generate_chunks():

    current = START_DATE


    while current < END_DATE:

        next_date = min(
            current.timestamp()
            + CHUNK_DAYS * 86400,
            END_DATE.timestamp(),
        )


        window_end = datetime.fromtimestamp(
            next_date,
            tz=timezone.utc,
        )


        yield (current, window_end)


        current = window_end + timedelta(hours=1)





def transform_records(
    data: dict,
    city: str,
) -> List[Dict[str, Any]]:


    records = []


    for item in data.get("list", []):


        timestamp = (
            datetime.fromtimestamp(
                item["dt"],
                tz=timezone.utc,
            )
            .isoformat()
        )


        components = item.get(
            "components",
            {},
        )

        aqi = (item.get("main") or {}).get("aqi")


        measurements = {

            "aqi": {
                "value": aqi,
                "unit": "index",
            },

            "co": {
                "value": components.get("co"),
                "unit": "µg/m³",
            },

            "no": {
                "value": components.get("no"),
                "unit": "µg/m³",
            },

            "no2": {
                "value": components.get("no2"),
                "unit": "µg/m³",
            },

            "o3": {
                "value": components.get("o3"),
                "unit": "µg/m³",
            },

            "so2": {
                "value": components.get("so2"),
                "unit": "µg/m³",
            },

            "pm2_5": {
                "value": components.get("pm2_5"),
                "unit": "µg/m³",
            },

            "pm10": {
                "value": components.get("pm10"),
                "unit": "µg/m³",
            },

            "nh3": {
                "value": components.get("nh3"),
                "unit": "µg/m³",
            },
        }


        for parameter, info in measurements.items():

            if info["value"] is not None:

                records.append(
                    {
                        "timestamp": timestamp,
                        "city": city,
                        "parameter": parameter,
                        "value": info["value"],
                        "unit": info["unit"],
                    }
                )


    return records




def save_records(
    records: List[Dict[str, Any]],
):

    if not records:
        return


    batch_size = 500


    for index in range(
        0,
        len(records),
        batch_size,
    ):

        batch = records[
            index:index + batch_size
        ]

      
        supabase.table(
            TABLE_NAME
        ).upsert(
            batch,
            on_conflict="city,parameter,timestamp",
        ).execute()


        print(
            f"{len(batch)} upserted"
        )





def run_history_extraction():


    locations = load_locations()

    chunks = list(
        generate_chunks()
    )


    print(
        f"{len(chunks)} periods to fetch"
    )


    for location in locations:


        print(
            f"\n=== {location['name']} ==="
        )

       
        location_records: List[Dict[str, Any]] = []


        for start, end in chunks:


            print(
                f"{start.date()} -> {end.date()}"
            )


            data = fetch_history(
                location["lat"],
                location["lon"],
                start,
                end,
            )


            if data:

                records = transform_records(
                    data,
                    location["name"],
                )


                location_records.extend(
                    records
                )


                print(
                    f"{len(records)} measurements"
                )


            time.sleep(
                SLEEP_BETWEEN_CALLS
            )


        print(
            f"Total {location['name']}: {len(location_records)} records"
        )

        save_records(
            location_records
        )



if __name__ == "__main__":
    run_history_extraction()