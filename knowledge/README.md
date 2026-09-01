# Coach Chess 1500 — Dictionnaire maître V0.3

Cette base transforme l'analyse moteur en raisonnement pédagogique.

## Pipeline
POSITION → MENACE ADVERSE → COUP JOUÉ → TACTIQUE → RÉPONSE CRITIQUE → CONSÉQUENCE → MEILLEUR COUP → LEÇON

## Hiérarchie tactique
Mat → gain matériel → enfilade → fourchette → double attaque → élimination du défenseur → pièce en prise → clouage → attaque découverte → déviation → positionnel.

## Règle de sécurité
Une pièce attaquée n'est pas automatiquement en prise. L'analyse doit distinguer attaque, défense et vulnérabilité tactique.

## Philosophie
Le moteur fournit l'évaluation. Les concepts fournissent l'explication humaine.
Un bon coup doit être valorisé autant qu'une erreur doit être expliquée.
Les principes sont des heuristiques, pas des lois absolues.

## Prochaine couche
1. détecteur de caractéristiques de position
2. détecteurs tactiques
3. moteur de relations concept → motif → leçon
4. exemples de parties de maîtres
5. exemples de puzzles Lichess
6. calibration ACPL / accuracy séparée de la qualité pédagogique
