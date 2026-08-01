import json
import os
from typing import Any, Dict, List
import pandas as pd

CITIES = ["Paris", "Marseille", "Lyon", "Toulouse", "Nice"]

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

POLLUTANTS_MAP = {
    "pm25": "pm2_5",
    "pm10": "pm10",
    "no2": "no2",
    "so2": "so2",
    "co": "co",
    "o3": "o3",
}

PARAMETER_BOUNDS = {
    "aqi": (0, 500),
    "pm2_5": (0, 1000),
    "pm10": (0, 1000),
    "no2": (0, 1000),
    "so2": (0, 2000),
    "co": (0, 50000),
    "o3": (0, 1000),
}


def clean_outliers(df: pd.DataFrame) -> pd.DataFrame:
  """Remplace par NaN les valeurs hors bornes sans supprimer toute la ligne de mesure."""
  for param, (low, high) in PARAMETER_BOUNDS.items():
    if param in df.columns:
      mask = (df[param] < low) | (df[param] > high)
      n_outliers = mask.sum()
      if n_outliers > 0:
        print(
            f"  [outliers] {n_outliers} valeur(s) invalide(s) écartée(s) pour"
            f" '{param}'"
        )
        df.loc[mask, param] = None
  return df


def transform():
  os.makedirs("clean", exist_ok=True)
  records: List[Dict[str, Any]] = []

  raw_files = [f for f in os.listdir("raw") if f.endswith(".json")]
  if not raw_files:
    print("Aucun fichier brut trouvé dans raw/")
    return

  for filename in raw_files:
    filepath = os.path.join("raw", filename)
    with open(filepath, "r", encoding="utf-8") as f:
      try:
        data = json.load(f)
      except Exception as e:
        print(f"Erreur de lecture du fichier {filename} : {e}")
        continue

    city = filename.split("_")[0].capitalize()
    if city not in CITIES:
      city_raw = data.get("city", {}).get("name", "")
      for c in CITIES:
        if c.lower() in city_raw.lower():
          city = c
          break

    if city not in CITIES:
      continue

    timestamp = data.get("time", {}).get("iso")
    if not timestamp:
      continue

    geo = data.get("city", {}).get("geo", [])
    if isinstance(geo, list) and len(geo) >= 2:
      lat, lon = geo[0], geo[1]
    else:
      lat = CITY_METADATA[city]["latitude"]
      lon = CITY_METADATA[city]["longitude"]

    record: Dict[str, Any] = {
        "timestamp": timestamp,
        "city": city,
        "latitude": float(lat),
        "longitude": float(lon),
        "aqi": data.get("aqi"),
    }

    iaqi = data.get("iaqi", {})
    for waqi_key, col_name in POLLUTANTS_MAP.items():
      if waqi_key in iaqi and "v" in iaqi[waqi_key]:
        record[col_name] = iaqi[waqi_key]["v"]
      else:
        record[col_name] = None

    records.append(record)

  if not records:
    print("Aucune donnée extraite depuis raw/")
    return

  df = pd.DataFrame(records)

  df = df.dropna(subset=["timestamp", "city"])

  df = clean_outliers(df)

  dup_mask = df.duplicated(subset=["city", "timestamp"], keep="first")
  n_dup = dup_mask.sum()
  if n_dup > 0:
    print(f"  [doublons] {n_dup} enregistrement(s) en double éliminé(s)")
    df = df[~dup_mask]

  df["dt_tmp"] = pd.to_datetime(df["timestamp"], errors="coerce")
  df = df.sort_values("dt_tmp").drop(columns=["dt_tmp"])

  if df.empty:
    print("Toutes les données ont été rejetées lors du nettoyage.")
    return

  clean_path = "clean/clean.csv"
  df.to_csv(clean_path, index=False)

  print(f"Fichier clean reconstruit avec succès : {clean_path}")
  print(f"Total : {len(df)} lignes générées.")


if __name__ == "__main__":
  transform()

