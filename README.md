Projet Qualité de l'Air – Pipeline AQI

1. Objectif


Ce projet consiste à déployer un pipeline automatisé qui collecte en continu (24h/24) les données de qualité de l'air (AQI) pour 5 villes françaises.  

Les données sont stockées de manière structurée (zone brute + zone nettoyée) puis chargées dans un **data warehouse dimensionnel** hébergé sur Supabase (schéma en étoile), afin d’être consommées par le cours IA1.

Le pipeline est entièrement automatisé via **GitHub Actions** et continue de tourner après le rendu.
