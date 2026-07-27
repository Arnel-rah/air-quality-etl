Projet Qualité de l'Air – Pipeline AQI

1. Objectif


Ce projet consiste à déployer un pipeline automatisé qui collecte en continu (24h/24) les données de qualité de l'air (AQI) pour 5 villes françaises.  

Les données sont stockées de manière structurée (zone brute + zone nettoyée) puis chargées dans un **data warehouse dimensionnel** hébergé sur Supabase (schéma en étoile), afin d’être consommées par le cours IA1.

Le pipeline est entièrement automatisé via **GitHub Actions** et continue de tourner après le rendu.


2. Villes couvertes

| Ville | Latitude | Longitude | Pays |
|---|---|---|---|
| Paris | 48.8566 | 2.3522 | France |
| Marseille | 43.2965 | 5.3698 | France |
| Lyon | 45.7640 | 4.8357 | France |
| Toulouse | 43.6047 | 1.4442 | France |
| Nice | 43.7102 | 7.2620 | France |