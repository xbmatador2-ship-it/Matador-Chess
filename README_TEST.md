# Coach Chess 1500 V0.5 — bundle test

## Objectif
Tester la première intégration du « cerveau pédagogique » avec l'application.

## Installation
```bash
python -m venv chess-env
source chess-env/bin/activate
pip install -r requirements.txt
```
Installer Stockfish côté système si nécessaire.

## Test automatique
```bash
python test_coach_brain.py
```

Le test vérifie deux régressions importantes :
1. le 14...Nd3+ de la partie de référence est reconnu comme **Fourchette royale** ;
2. une pièce attaquée mais défendue n'est pas classée « en prise ».

## Lancement
```bash
streamlit run app.py
```

## Ce qu'il faut tester manuellement
- les bons coups doivent recevoir une explication, pas seulement « aucune erreur » ;
- une menace résolue ne doit pas être reprochée au coup ;
- « attaquée », « non défendue » et « en prise » doivent rester distincts ;
- une tactique concrète doit passer avant une explication stratégique générique ;
- le meilleur coup doit être expliqué même lorsqu'il est calme (prophylaxie, activité, sécurité du roi, amélioration de pièce, structure) ;
- les réponses adverses affichées doivent être pertinentes, pas des coups arbitraires de la PV.

## Limite volontaire
Le moteur fournit l'évaluation et la variante. Le cerveau pédagogique refuse d'inventer une intention humaine ou une justification lorsqu'elle ne peut pas être établie avec suffisamment de fiabilité.
