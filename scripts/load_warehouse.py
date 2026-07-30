import os
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Any, Dict, List, cast

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL et SUPABASE_KEY doivent être définis dans le fichier .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def upsert_dim_city() -> Dict[str, int]:
    result = cast(List[Dict[str, Any]], supabase.table("dim_city").select("city_id, city_name").execute().data)
    return {str(row["city_name"]): int(row["city_id"]) for row in result}

def upsert_dim_parameter(df: pd.DataFrame) -> Dict[str, int]:
    params = df[['parameter', 'unit']].drop_duplicates(subset=['parameter'])
    records = [
        {"parameter_name": str(row['parameter']), "unit": str(row['unit'])}
        for _, row in params.iterrows()
    ]
    if records:
        supabase.table("dim_parameter").upsert(records, on_conflict="parameter_name").execute()
    result = cast(List[Dict[str, Any]], supabase.table("dim_parameter").select("parameter_id, parameter_name").execute().data)
    return {str(row["parameter_name"]): int(row["parameter_id"]) for row in result}

def upsert_dim_date(timestamps: pd.Series) -> Dict[pd.Timestamp, int]:
    print("Alimentation de dim_date...")
    ts_series = pd.to_datetime(timestamps, utc=True)
    df_dates = pd.DataFrame({'ts': ts_series})
    df_dates['full_timestamp'] = df_dates['ts'].dt.strftime('%Y-%m-%dT%H:%M:%S%z')
    df_dates['date'] = df_dates['ts'].dt.strftime('%Y-%m-%d')
    df_dates['year'] = df_dates['ts'].dt.year
    df_dates['month'] = df_dates['ts'].dt.month
    df_dates['day'] = df_dates['ts'].dt.day
    df_dates['hour'] = df_dates['ts'].dt.hour
    df_dates['day_of_week'] = df_dates['ts'].dt.dayofweek

    df_dates = df_dates.drop_duplicates(subset=['full_timestamp'])

    records = [
        {
            "full_timestamp": row["full_timestamp"],
            "date": row["date"],
            "year": int(row["year"]),
            "month": int(row["month"]),
            "day": int(row["day"]),
            "hour": int(row["hour"]),
            "day_of_week": int(row["day_of_week"]),
        }
        for _, row in df_dates.iterrows()
    ]

    batch_size = 2000
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        supabase.table("dim_date").upsert(batch, on_conflict="full_timestamp").execute()

    result = cast(List[Dict[str, Any]], supabase.table("dim_date").select("date_id, full_timestamp").execute().data)
    return {
        pd.to_datetime(row["full_timestamp"], utc=True): int(row["date_id"])
        for row in result
    }

def load_warehouse():
    clean_path = "clean/clean.csv"
    if not os.path.exists(clean_path):
        print("Fichier clean/clean.csv introuvable.")
        return

    print("Lecture de clean.csv...")
    df = pd.read_csv(clean_path)
    print(f"Total : {len(df)} lignes lues.")

    df = df.dropna(subset=['value', 'city', 'parameter', 'timestamp'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

    print("Mapping des dimensions...")
    city_map = upsert_dim_city()
    parameter_map = upsert_dim_parameter(df)
    date_map = upsert_dim_date(df['timestamp'])

    df['city_id'] = df['city'].map(city_map)
    df['parameter_id'] = df['parameter'].map(parameter_map)
    df['date_id'] = df['timestamp'].map(date_map)

    fact_df = df[['city_id', 'parameter_id', 'date_id', 'value']].dropna().copy()
    fact_df = fact_df.drop_duplicates(subset=['city_id', 'parameter_id', 'date_id'])

    fact_df['city_id'] = fact_df['city_id'].astype(int)
    fact_df['parameter_id'] = fact_df['parameter_id'].astype(int)
    fact_df['date_id'] = fact_df['date_id'].astype(int)
    fact_df['value'] = fact_df['value'].astype(float)

    print(f"Préparation de {len(fact_df)} faits pour fact_air_quality...")

    records: List[Dict[str, Any]] = cast(List[Dict[str, Any]], fact_df.to_dict('records'))

    batch_size = 3000
    total = len(records)
    for i in range(0, total, batch_size):
        batch = records[i:i + batch_size]
        try:
            supabase.table("fact_air_quality").upsert(
                batch, on_conflict="city_id,parameter_id,date_id"
            ).execute()
            print(f"   -> Progression : {min(i + batch_size, total)} / {total} faits chargés")
        except Exception as e:
            print(f"Erreur sur le lot {i}: {e}")

    print("Chargement complet du Data Warehouse terminé !")

if __name__ == "__main__":
    load_warehouse()
