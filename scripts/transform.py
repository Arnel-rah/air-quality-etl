import json
import os
from typing import Any, Dict, List, Tuple
import pandas as pd

CITIES = ["Paris", "Marseille", "Lyon", "Toulouse", "Nice"]

PARAMETER_NAME_ALIASES = {
    "pm25": "pm2_5",
}

INDEX_PARAMETERS = {"aqi", "aqi_global"}

CONCENTRATION_PARAMETERS = {
    "co",
    "no",
    "no2",
    "o3",
    "so2",
    "pm10",
    "pm2_5",
    "nh3",
}

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

PARAMETER_MAP = {
    "pm25": "pm2_5",
    "pm10": "pm10",
    "no2": "no2",
    "so2": "so2",
    "co": "co",
    "o3": "o3",
}


def detect_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """Filtre les valeurs aberrantes selon les bornes définies."""
    def get_bounds(p: Any) -> Tuple[float, float]:
        if isinstance(p, str):
            return PARAMETER_BOUNDS.get(p, (0, float("inf")))
        return (0, float("inf"))

    lower = df["parameter"].map(lambda p: get_bounds(p)[0])
    upper = df["parameter"].map(lambda p: get_bounds(p)[1])

    mask = df["value"].between(lower, upper)
    n_rejected = (~mask).sum()
    if n_rejected > 0:
        print(f"  [outliers] {n_rejected} ligne(s) hors bornes écartée(s)")
    return df[mask]


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
                "unit": "AQI",
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
                        "unit": "AQI",
                    })

    if not all_records:
        print("Aucune donnée à écrire dans clean/")
        return

    df = pd.DataFrame(all_records)

    df = df.dropna(subset=["value", "city", "parameter", "timestamp"])

    df["parameter"] = df["parameter"].replace(PARAMETER_NAME_ALIASES)

    idx_mask = df["parameter"].isin(INDEX_PARAMETERS) & (df["unit"] == "AQI")
    df.loc[idx_mask, "unit"] = "index"

    quarantine_mask = df["parameter"].isin(CONCENTRATION_PARAMETERS) & (
        df["unit"] == "AQI"
    )
    if quarantine_mask.sum() > 0:
        df = df[~quarantine_mask]

    dup_mask = df.duplicated(
        subset=["city", "parameter", "timestamp"], keep="first"
    )
    n_dup = dup_mask.sum()
    if n_dup > 0:
        print(f"  [doublons] {n_dup} ligne(s) en double éliminée(s)")
        df = df[~dup_mask]

    df = detect_outliers(df)

    if df.empty:
        print("Toutes les lignes ont été écartées après nettoyage")
        return

    clean_path = "clean/clean.csv"
    df.to_csv(clean_path, index=False)

    print(f"Fichier clean reconstruit : {clean_path}")
    print(f"Nombre de lignes : {len(df)}")


if __name__ == "__main__":
    transform()
