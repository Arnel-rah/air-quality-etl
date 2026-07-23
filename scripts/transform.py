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


def upsert_dim_city(cities: List[str]) -> Dict[str, int]:
    records = [{"city_name": c} for c in cities]
    print(f"  [dim_city] {len(records)} enregistrements à upserter")
    if records:
        supabase.table("dim_city").upsert(records, on_conflict="city_name").execute()
    result = cast(List[Dict[str, Any]], supabase.table("dim_city").select("city_id, city_name").execute().data)
    print(f"  [dim_city] {len(result)} lignes en base")
    return {str(row["city_name"]): int(row["city_id"]) for row in result}


def upsert_dim_parameter(df: pd.DataFrame) -> Dict[str, int]:
    params = df[['parameter', 'unit']].drop_duplicates()
    records = [
        {"parameter_name": row['parameter'], "unit": row['unit']}
        for _, row in params.iterrows()
    ]
    print(f"  [dim_parameter] {len(records)} enregistrements à upserter")
    if records:
        supabase.table("dim_parameter").upsert(records, on_conflict="parameter_name").execute()
    result = cast(List[Dict[str, Any]], supabase.table("dim_parameter").select("parameter_id, parameter_name").execute().data)
    print(f"  [dim_parameter] {len(result)} lignes en base")
    return {str(row["parameter_name"]): int(row["parameter_id"]) for row in result}


def upsert_dim_date(timestamps: pd.Series) -> Dict[pd.Timestamp, int]:
    unique_ts = pd.to_datetime(timestamps.unique(), utc=True)
    records = [
        {
            "full_timestamp": ts.strftime('%Y-%m-%dT%H:%M:%S%z'),
            "date": ts.strftime('%Y-%m-%d'),
            "year": ts.year,
            "month": ts.month,
            "day": ts.day,
            "hour": ts.hour,
            "day_of_week": ts.dayofweek,
        }
        for ts in unique_ts
    ]
    print(f"  [dim_date] {len(records)} enregistrements à upserter")
    if records:
        supabase.table("dim_date").upsert(records, on_conflict="full_timestamp").execute()
    result = cast(List[Dict[str, Any]], supabase.table("dim_date").select("date_id, full_timestamp").execute().data)
    print(f"  [dim_date] {len(result)} lignes en base")
    return {
        pd.to_datetime(row["full_timestamp"], utc=True): int(row["date_id"])
        for row in result
    }


def run():
    data = supabase.table("raw_air_quality").select("*").limit(5000).execute().data
    df = pd.DataFrame(data)
    print(f"[raw_air_quality] {len(df)} lignes lues")

    if df.empty:
        print("Aucune donnée à transformer")
        return

    df = df.dropna(subset=['value', 'city', 'parameter', 'timestamp'])
    print(f"[après dropna] {len(df)} lignes restantes")

    if df.empty:
        print("Toutes les lignes ont été éliminées par dropna — vérifie les colonnes value/city/parameter/timestamp dans raw_air_quality")
        return

    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

    print("Alimentation des dimensions...")
    city_map = upsert_dim_city(df['city'].unique().tolist())
    parameter_map = upsert_dim_parameter(df)
    date_map = upsert_dim_date(df['timestamp'])

    df['city_id'] = df['city'].map(city_map)
    df['parameter_id'] = df['parameter'].map(parameter_map)
    df['date_id'] = df['timestamp'].map(date_map)

    print(f"[mapping] city_id nuls : {df['city_id'].isna().sum()}")
    print(f"[mapping] parameter_id nuls : {df['parameter_id'].isna().sum()}")
    print(f"[mapping] date_id nuls : {df['date_id'].isna().sum()}")

    fact_df = df[['city_id', 'parameter_id', 'date_id', 'value']].dropna()
    print(f"[fact_air_quality] {len(fact_df)} lignes prêtes à insérer")

    if fact_df.empty:
        print("Aucun enregistrement à insérer dans fact_air_quality après mapping")
        return

    fact_df = fact_df.where(pd.notnull(fact_df), None)
    records: List[Dict[str, Any]] = cast(List[Dict[str, Any]], fact_df.to_dict('records'))

    try:
        supabase.table("fact_air_quality").upsert(
            records, on_conflict="city_id,parameter_id,date_id"
        ).execute()
        print(f"{len(records)} faits upsertés dans le Data Warehouse (modèle en étoile)")
    except Exception as e:
        print(f"Erreur lors de l'insertion dans Supabase : {e}")


if __name__ == "__main__":
    run()
