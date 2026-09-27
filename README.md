# 02 — Automatisation d'un reporting hebdomadaire

**Avant** : 20 fichiers Excel disparates sur un partage réseau, une demi-journée
de copier-coller le lundi matin, et un chiffre qui change selon la personne qui l'a calculé.

**Après** : un PDF de 3 pages dans la boîte mail du dirigeant à 6 h 30, tous les lundis,
avec la trace de ce qui a été écarté et pourquoi.

```
sources/*.xlsx ─┐
sources/*.csv  ─┴─► collecte ─► nettoyage ─► graphiques ─► PDF ─► e-mail
                       │            │
                       └── journal de qualité ──────────────┘
```

## Démarrer

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python generer_sources_desordre.py   # fabrique le « avant » : 20 fichiers hétérogènes
python main.py --essai               # produit le PDF, écrit l'e-mail en .eml sans l'envoyer
python -m pytest tests/ -v           # 42 tests sur les fonctions de parsing
```

Sorties dans `sorties/` : le PDF, la table consolidée en CSV, et
`sorties/.travail/` (journal d'exécution, figures, message .eml).

## Le désordre traité

`generer_sources_desordre.py` reproduit fidèlement ce qu'on trouve sur un partage
réseau de PME. Chaque désordre de la liste est une ligne de code du pipeline :

| Dans les fichiers | Comment le pipeline s'en sort |
|---|---|
| `Montant HT`, `ca_ht`, `TOTAL HT` selon l'agence | Table d'alias, comparaison sans accents ni casse |
| 3 lignes de titre et un logo avant le tableau | Détection de l'en-tête par score : la ligne qui reconnaît le plus de colonnes gagne |
| `15/03/2026`, `2026-03-15`, `46096` | `parser_date` : 6 gabarits + numéro de série Excel, jour avant mois |
| `1 234,56` avec espace insécable | `parser_montant` : détecte lequel des deux séparateurs est le décimal |
| Ligne `TOTAL` collée en bas du tableau | Écartée : pas de date exploitable |
| Doublons exacts entre exports | Dédoublonnage sur date + client + produit + montant |
| `M. Perrin`, `Perrin Thomas`, `T. Perrin` | Réconciliés en un seul commercial (capitales, puis jeton le plus long) |
| Un CSV latin-1 avec `;` au milieu des .xlsx | Détection encodage × séparateur par essais successifs |
| Un fichier corrompu | Journalisé, signalé dans le rapport, le pipeline continue |

Sur le jeu de démonstration : **1 013 lignes lues, 973 retenues, 3,9 % écartées**
— 24 lignes de total, 9 doublons, 7 saisies incomplètes.

## Ce que fait le rapport, et que ne fait pas un export Excel

- **Il se compare à lui-même.** Chaque KPI porte son écart à la semaine précédente,
  et les agences en repli de plus de 10 % remontent en « Points d'attention ».
- **Il signale les lignes à vérifier** par deux critères complémentaires : un seuil
  absolu (25 000 €, erreur de saisie grossière) et un écart interquartile *par produit*
  — un montant de 5 400 € est normal pour un onduleur, aberrant pour une boîte de prises.
- **Il rend le nettoyage vérifiable.** La page 3 liste chaque règle de rejet et son
  volume. Un nettoyage silencieux est un nettoyage qu'on ne peut pas défendre.

## La partie qui compte vraiment : le code de retour 2

Le script renvoie `2` quand le rapport est produit mais que plus de 5 % des lignes
ont été écartées. C'est ce qui attrape la panne silencieuse : une agence change son
modèle d'export, le pipeline continue de tourner, le PDF arrive à l'heure — et
sous-compte de 30 % sans que personne ne s'en aperçoive pendant six semaines.

Un pipeline qui ne sait pas dire qu'il va mal est plus dangereux qu'un pipeline
qui plante.

## Planification

`planification/` contient une ligne cron (avec `flock` contre les exécutions
concurrentes) et une paire service/timer systemd (avec `Persistent=true` pour
rattraper un lundi où le serveur était éteint). Détails et variables
d'environnement dans `planification/README.md`.

Aucun secret dans le dépôt : `src/config.py` lit `SMTP_*` et `RAPPORT_*`
depuis l'environnement, et le mode `--essai` écrit le message en `.eml`
au lieu de l'envoyer.

## Structure

```
generer_sources_desordre.py  fabrique le jeu de démonstration
main.py                      orchestration + codes de retour
src/config.py                seuils et secrets (lus depuis l'environnement)
src/collecte.py              lecture tolérante, détection d'en-tête, alias de colonnes
src/nettoyage.py             typage, règles de rejet, journal de qualité, anomalies
src/graphiques.py            4 figures matplotlib, charte unique
src/rapport.py               assemblage du PDF (reportlab)
src/envoi.py                 SMTP + mode essai
tests/test_nettoyage.py      42 tests sur le parsing
planification/               cron, systemd, variables d'environnement
```

---

Projet du portfolio de **Laurian Jamin** — data, automatisation et IA appliquée pour les PME.  
Portfolio : <https://colauz.github.io/Portfolio/> · Malt : <https://www.malt.fr/profile/laurianjamin>
