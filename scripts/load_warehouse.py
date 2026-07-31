import os
from typing import Any, Dict, List, cast
from dotenv import load_dotenv
import pandas as pd
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError(
        "SUPABASE_URL et SUPABASE_KEY doivent être définis dans le fichier .env"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

CITY_METADATA = {
    "Paris": {"country": "France", "latitude": 48.8566, "longitude": 2.3522},
    "Marseille": {
        "country": "France",
        "latitude": 43.2965,
        "longitude": 5.3698,
    },
    "Lyon": {"country": "France", "latitude": 45.7640, "longitude": 4.8357},
    "Toulouse": {"country": "France", "latitude": 43.6047, "longitude": 1.4442},
    "Nice": {"country": "France", "latitude": 43.7102, "longitude": 7.2620},
}


def fetch_all(table: str, select_cols: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    page_size = 1000
    while True:
        res = (
            supabase.table(table)
            .select(select_cols)
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = cast(List[Dict[str, Any]], res.data)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def upsert_dim_city(df: pd.DataFrame) -> Dict[str, int]:
    print("1. Alimentation de dim_city...")
    cities = df["city"].unique()
    records = []

    for c in cities:
        sub_df = df[df["city"] == c]
        lat = sub_df["latitude"].iloc[0] if "latitude" in sub_df.columns else None
        lon = sub_df["longitude"].iloc[0] if "longitude" in sub_df.columns else None

        meta = CITY_METADATA.get(c, {})
        records.append({
            "city_name": str(c).strip(),
            "country": meta.get("country", "France"),
            "latitude": float(lat) if pd.notnull(lat) else meta.get("latitude"),
            "longitude": float(lon) if pd.notnull(lon) else meta.get("longitude"),
        })

    supabase.table("dim_city").upsert(records, on_conflict="city_name").execute()

    result = fetch_all("dim_city", "*")
    city_map: Dict[str, int] = {}
    for row in result:
        val = row.get("city_id") if row.get("city_id") is not None else row.get("id")
        if val is not None and row.get("city_name") is not None:
            city_map[str(row["city_name"]).strip()] = int(val)
    return city_map


def upsert_dim_date(timestamps: pd.Series) -> Dict[str, int]:
    print("2. Alimentation de dim_date...")
    ts_series = pd.to_datetime(timestamps.unique(), utc=True)

    records = [
        {
            "full_timestamp": ts.isoformat(),
            "date": ts.strftime("%Y-%m-%d"),
            "year": int(ts.year),
            "month": int(ts.month),
            "day": int(ts.day),
            "hour": int(ts.hour),
            "day_of_week": int(ts.isoweekday()),
            "is_weekend": bool(ts.dayofweek >= 5),
        }
        for ts in ts_series
    ]

    batch_size = 1000
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        supabase.table("dim_date").upsert(
            batch, on_conflict="full_timestamp"
        ).execute()

    result = fetch_all("dim_date", "*")
    date_map: Dict[str, int] = {}
    for row in result:
        val = row.get("date_id") if row.get("date_id") is not None else row.get("id")
        if val is not None and row.get("full_timestamp") is not None:
            iso_key = pd.to_datetime(row["full_timestamp"]).isoformat()
            date_map[iso_key] = int(val)
    return date_map


def fetch_param_map() -> Dict[str, int]:
    """Récupère la correspondance nom_du_paramètre -> parameter_id depuis dim_parameter."""
    params = fetch_all("dim_parameter", "parameter_id, parameter_name")
    param_map: Dict[str, int] = {}
    for row in params:
        p_name = row.get("parameter_name")
        p_id = row.get("parameter_id")
        if p_name and p_id is not None:
            param_map[str(p_name).strip()] = int(p_id)
    if "pm25" in param_map and "pm2_5" not in param_map:
        param_map["pm2_5"] = param_map["pm25"]
    elif "pm2_5" in param_map and "pm25" not in param_map:
        param_map["pm25"] = param_map["pm2_5"]

    return param_map


def load_warehouse():
    clean_path = "clean/clean.csv"
    if not os.path.exists(clean_path):
        print("Fichier clean/clean.csv introuvable.")
        return

    print("Lecture de clean.csv...")
    df = pd.read_csv(clean_path)
    print(f"Total : {len(df)} lignes lues.")

    if df.empty:
        print("Fichier clean.csv vide.")
        return

    df = df.dropna(subset=["timestamp", "city"])

    df["city_norm"] = df["city"].astype(str).str.strip()
    df["full_timestamp_norm"] = df["timestamp"].apply(
        lambda x: pd.to_datetime(x, utc=True).isoformat()
    )

    city_map = upsert_dim_city(df)
    date_map = upsert_dim_date(df["timestamp"])
    param_map = fetch_param_map()

    df["city_id"] = df["city_norm"].map(city_map)
    df["date_id"] = df["full_timestamp_norm"].map(date_map)

    if df["city_id"].isnull().any() or df["date_id"].isnull().any():
        print(
            "Attention : Certaines lignes n'ont pas pu être associées aux dimensions !"
        )
        df = df.dropna(subset=["city_id", "date_id"])

    available_pollutant_cols = [col for col in df.columns if col in param_map]

    if not available_pollutant_cols:
        print("Erreur : Aucune colonne de polluant du CSV ne correspond à dim_parameter !")
        return

    melted = df.melt(
        id_vars=["city_id", "date_id"],
        value_vars=available_pollutant_cols,
        var_name="parameter_name",
        value_name="value",
    )

    melted = melted.dropna(subset=["value"])
    melted["parameter_id"] = melted["parameter_name"].map(param_map)

    fact_df = melted[["city_id", "parameter_id", "date_id", "value"]].copy()
    fact_df["city_id"] = fact_df["city_id"].astype(int)
    fact_df["parameter_id"] = fact_df["parameter_id"].astype(int)
    fact_df["date_id"] = fact_df["date_id"].astype(int)
    fact_df["value"] = fact_df["value"].astype(float)

    fact_df = fact_df.drop_duplicates(subset=["city_id", "parameter_id", "date_id"])

    raw_records = cast(List[Dict[Any, Any]], fact_df.to_dict(orient="records"))
    fact_records: List[Dict[str, Any]] = [
        {str(k): (None if pd.isna(v) else v) for k, v in record.items()}
        for record in raw_records
    ]

    print(f"Chargement de {len(fact_records)} lignes de faits dans fact_air_quality...")

    batch_size = 1000
    total = len(fact_records)
    for i in range(0, total, batch_size):
        batch = fact_records[i : i + batch_size]
        try:
            supabase.table("fact_air_quality").upsert(
                batch, on_conflict="city_id,parameter_id,date_id"
            ).execute()
            print(
                f"   -> Progression : {min(i + batch_size, total)} / {total} faits"
                " insérés/mis à jour"
            )
        except Exception as e:
            print(f"Erreur sur le lot {i} : {e}")

    print("Chargement complet du Data Warehouse terminé avec succès !")


if __name__ == "__main__":
    load_warehouse()
