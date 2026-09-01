# Coach Chess 1500 V0.6 — bundle test

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


## V0.6 — ouverture intégrée
- L'ouverture devient un contexte de raisonnement : structure, développement, cases, plans et objectifs.
- Les bons coups sont explicitement valorisés et expliqués.
- Si le coup joué est exactement le meilleur coup Stockfish, il est forcé à `Meilleur coup` et sa perte est remise à 0.
- Ajout d'un détecteur d'enfilade et d'un signal de pièce enfermée.
- Une fourchette royale met l'échec au roi avant la deuxième cible.
- Les formules génériques d'attaque/défense ne doivent plus être le commentaire principal.

### Test manuel V0.6
Vérifier en priorité :
1. un coup joué = meilleur coup n'est jamais classé inexactitude ;
2. un meilleur coup reçoit une explication positive et concrète ;
3. une ouverture connue affiche son idée directrice ;
4. une fourchette royale commence par l'échec ;
5. une enfilade est détectée quand la géométrie la justifie ;
6. une pièce réellement enfermée est signalée même si la perte moteur est faible ;
7. les phrases vagues du type « répond mieux aux contraintes concrètes » ne sont plus le texte principal.
