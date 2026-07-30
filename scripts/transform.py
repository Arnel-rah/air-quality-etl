import os
import time
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Any, Callable, Dict, List, cast

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL et SUPABASE_KEY doivent être définis dans le fichier .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

PAGE_SIZE = 1000


PARAMETER_NAME_ALIASES = {
    "pm25": "pm2_5",
}

CONCENTRATION_PARAMETERS = {"co", "no", "no2", "o3", "so2", "pm10", "pm2_5", "nh3"}

INDEX_PARAMETERS = {"aqi", "aqi_global"}

PARAMETER_BOUNDS = {
    "aqi": (1, 5),
    "co": (0, 50000),
    "no": (0, 1000),
    "no2": (0, 1000),
    "o3": (0, 1000),
    "so2": (0, 2000),
    "pm2_5": (0, 1000),
    "pm10": (0, 1000),
    "nh3": (0, 1000),
}


MAX_RETRIES = 4
RETRY_BASE_DELAY = 3  


def execute_with_retry(build_query: Callable[[], Any], label: str = ""):
    """
    Exécute une requête Supabase avec retries en cas d'erreur réseau
    transitoire (ex: "Server disconnected" sur un script qui fait des
    centaines d'appels d'affilée). build_query est une fonction sans
    argument qui construit et renvoie la requête (pas encore exécutée),
    pour pouvoir la reconstruire à chaque tentative.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return build_query().execute()
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"  {label} : échec définitif après {MAX_RETRIES} tentatives : {e}")
                raise
            wait = RETRY_BASE_DELAY * attempt
            print(f"  {label} : erreur réseau (tentative {attempt}/{MAX_RETRIES}) : {e} — retry dans {wait}s")
            time.sleep(wait)


def fetch_all(table: str, select: str, page_size: int = 1000) -> List[Dict[str, Any]]:
    """
    Lit TOUTES les lignes d'une table par pages. Un simple .select(...).execute()
    est plafonné par défaut par PostgREST (souvent 1000 lignes) : au-delà, les
    lignes manquantes provoquent des mappings ratés (ex: date_id introuvable
    pour la plupart des timestamps une fois dim_date au-delà de 1000 lignes).
    """
    all_rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        response = execute_with_retry(
            lambda: supabase.table(table).select(select).range(start, start + page_size - 1),
            label=f"fetch_all({table})",
        )
        batch = response.data
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return all_rows


FACT_BATCH_SIZE = 500


def upsert_fact_batches(records: List[Dict[str, Any]]) -> None:
    total = len(records)
    for i in range(0, total, FACT_BATCH_SIZE):
        batch = records[i:i + FACT_BATCH_SIZE]
        execute_with_retry(
            lambda: supabase.table("fact_air_quality").upsert(
                batch, on_conflict="city_id,parameter_id,date_id"
            ),
            label=f"fact_air_quality[{i}:{i + len(batch)}]",
        )
        print(f"  -> {len(batch)} faits upsertés ({min(i + FACT_BATCH_SIZE, total)}/{total})")
        time.sleep(0.1)


def upsert_dim_city(cities: List[str]) -> Dict[str, int]:
    records = [{"city_name": c} for c in cities]
    print(f"  [dim_city] {len(records)} enregistrements à upserter")
    if records:
        execute_with_retry(
            lambda: supabase.table("dim_city").upsert(records, on_conflict="city_name"),
            label="dim_city upsert",
        )
    try:
        result = fetch_all("dim_city", "city_id, city_name")
    except Exception as e:
        print(f"  [dim_city] Erreur lors de la lecture : {e}")
        raise
    return {str(row["city_name"]): int(row["city_id"]) for row in result}


def upsert_dim_parameter(df: pd.DataFrame) -> Dict[str, int]:
  
    units_per_param = df.groupby('parameter')['unit'].nunique()
    inconsistent = units_per_param[units_per_param > 1]
    if not inconsistent.empty:
        print(f"  [dim_parameter] ATTENTION : unités incohérentes pour {list(inconsistent.index)} — vérifie tes scripts d'ingestion")
        for param in inconsistent.index:
            seen = df.loc[df['parameter'] == param, 'unit'].value_counts()
            print(f"    - {param}: {dict(seen)}")

    chosen_unit = df.groupby('parameter')['unit'].agg(lambda u: u.value_counts().idxmax())
    records = [
        {"parameter_name": param, "unit": unit}
        for param, unit in chosen_unit.items()
    ]
    print(f"  [dim_parameter] {len(records)} enregistrements à upserter")
    if records:
        execute_with_retry(
            lambda: supabase.table("dim_parameter").upsert(records, on_conflict="parameter_name"),
            label="dim_parameter upsert",
        )
    try:
        result = fetch_all("dim_parameter", "parameter_id, parameter_name")
    except Exception as e:
        print(f"  [dim_parameter] Erreur lors de la lecture : {e}")
        raise
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
        for i in range(0, len(records), FACT_BATCH_SIZE):
            batch = records[i:i + FACT_BATCH_SIZE]
            execute_with_retry(
                lambda: supabase.table("dim_date").upsert(batch, on_conflict="full_timestamp"),
                label=f"dim_date[{i}:{i + len(batch)}]",
            )
    try:
        result = fetch_all("dim_date", "date_id, full_timestamp")
    except Exception as e:
        print(f"  [dim_date] Erreur lors de la lecture : {e}")
        raise
    return {
        pd.to_datetime(row["full_timestamp"], utc=True): int(row["date_id"])
        for row in result
    }


def fetch_all_raw_air_quality() -> List[Dict[str, Any]]:
    """
    Lit TOUTE la table raw_air_quality par pages de PAGE_SIZE lignes.
    Un simple .select("*").limit(5000) ne récupère que les 5000 premières
    lignes de la table (silencieusement, sans erreur) — avec ~280k lignes
    sur 12 mois x 4 villes, ça ne couvrirait qu'une infime partie des données.
    """
    all_rows: List[Dict[str, Any]] = []
    start = 0
    while True:
        response = execute_with_retry(
            lambda: supabase.table("raw_air_quality").select("*").range(start, start + PAGE_SIZE - 1),
            label="raw_air_quality read",
        )
        batch = response.data
        if not batch:
            break
        all_rows.extend(batch)
        print(f"  [raw_air_quality] {len(all_rows)} lignes chargées...")
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return all_rows


def detect_outliers(df: pd.DataFrame) -> pd.DataFrame:
    lower = df["parameter"].map(lambda p: PARAMETER_BOUNDS.get(p, (0, float("inf")))[0])
    upper = df["parameter"].map(lambda p: PARAMETER_BOUNDS.get(p, (0, float("inf")))[1])

    mask = df["value"].between(lower, upper)
    n_rejected = (~mask).sum()
    if n_rejected > 0:
        print(f"[outliers] {n_rejected} ligne(s) hors bornes écartée(s)")
    return df[mask]


def run():
    try:
        data = fetch_all_raw_air_quality()
    except Exception as e:
        print(f"Erreur lors de la lecture de raw_air_quality : {e}")
        raise
    df = pd.DataFrame(data)
    print(f"[raw_air_quality] {len(df)} lignes lues au total")

    if df.empty:
        print("Aucune donnée à transformer")
        return

    df = df.dropna(subset=['value', 'city', 'parameter', 'timestamp'])
    print(f"[après dropna] {len(df)} lignes restantes")

    if df.empty:
        print("Toutes les lignes ont été éliminées par dropna — vérifie les colonnes value/city/parameter/timestamp dans raw_air_quality")
        return

    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)

 
    df['parameter'] = df['parameter'].replace(PARAMETER_NAME_ALIASES)

    idx_mask = df['parameter'].isin(INDEX_PARAMETERS) & (df['unit'] == 'AQI')
    df.loc[idx_mask, 'unit'] = 'index'

   
    quarantine_mask = df['parameter'].isin(CONCENTRATION_PARAMETERS) & (df['unit'] == 'AQI')
    n_quarantine = quarantine_mask.sum()
    if n_quarantine > 0:
        detail = df[quarantine_mask]['parameter'].value_counts()
        print(f"[quarantaine] {n_quarantine} ligne(s) avec unit='AQI' sur un paramètre de concentration, écartée(s) :")
        for param, count in detail.items():
            print(f"    - {param}: {count} ligne(s)")
        df = df[~quarantine_mask]

    dup_mask = df.duplicated(subset=['city', 'parameter', 'timestamp'], keep='first')
    n_dup = dup_mask.sum()
    if n_dup > 0:
        print(f"[doublons] {n_dup} ligne(s) en double sur (city, parameter, timestamp) après normalisation — première occurrence conservée")
        df = df[~dup_mask]

    df = detect_outliers(df)
    if df.empty:
        print("Toutes les lignes ont été écartées par detect_outliers")
        return

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

  
    fact_df = fact_df.astype({
        'city_id': 'int64',
        'parameter_id': 'int64',
        'date_id': 'int64',
    })

    fact_df = fact_df.where(pd.notnull(fact_df), None)
    records: List[Dict[str, Any]] = cast(List[Dict[str, Any]], fact_df.to_dict('records'))

    try:
        upsert_fact_batches(records)
        print(f"{len(records)} faits upsertés dans le Data Warehouse (modèle en étoile)")
    except Exception as e:
        print(f"Erreur lors de l'insertion dans Supabase : {e}")


if __name__ == "__main__":
    run()