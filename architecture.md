#Architecture Technique — Pipeline ETL Qualité de l'Air

## 1. Vue d'Ensemble & Objectifs
- **Type de Pipeline :** Batch (Exécution périodique automatisée).
- **Objectif :** Collecter, nettoyer et stocker les données de qualité de l'air de 5 métropoles françaises dans un Data Warehouse cloud pour alimenter des analyses et des modèles d'IA.

---

## 2. Diagramme d'Architecture
[ API WAQI ] ──(extract.py)──► [ Supabase : raw_air_quality ]
│
(transform.py)
│
▼
[ Data Warehouse : Schéma en Étoile ]
├── dim_city
├── dim_parameter ──► fact_air_quality
└── dim_date

---

## 3. Choix des Technologies & Justifications

| Composant | Technologie | Justification / Choix de l'équipe |
| :--- | :--- | :--- |
| **Langage** | **Python 3.10+** | Utilisation des librairies `requests`, `pandas` et `supabase-py` pour le traitement des données. |
| **Data Warehouse** | **Supabase (PostgreSQL)** | Retenu suite aux soucis de **timeout** rencontrés sur Neon et à l'abandon d'Oracle. |
| **Orchestration** | **GitHub Actions** | Automatisation du pipeline (`.github/workflows/pipeline.yml`) via un *cron job* sans coût d'infrastructure. |
| **Source** | **WAQI API** | Source de données fiables et structurées sur les polluants atmosphériques. |

---

## 4. Modélisation de la Base de Données (Schéma en Étoile)

### Tables de Dimensions
* **`dim_city`** : `city_id` (PK), `city_name`
* **`dim_parameter`** : `parameter_id` (PK), `parameter_name`, `unit`
* **`dim_date`** : `date_id` (PK), `full_timestamp`, `date`, `year`, `month`, `day`, `hour`, `day_of_week`

### Table de Faits
* **`fact_air_quality`** : `fact_id` (PK), `city_id` (FK), `parameter_id` (FK), `date_id` (FK), `value`, `created_at`
  * *Contrainte d'unicité :* `(city_id, parameter_id, date_id)`

---

## 5. Stratégie de Traitement & Qualité

- **Stockage Brut (Raw) :** Conservation des réponses API dans la table `raw_air_quality` pour garantir la traçabilité.
- **Gestion des Doublons :** Utilisation de requêtes `UPSERT` (avec contraintes d'unicité) lors des insertions dans Supabase.
- **Nettoyage :** Filtrage des valeurs nulles et hors plage (`0 <= value <= 1000`) durant la phase
