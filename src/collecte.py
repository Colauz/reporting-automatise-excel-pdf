"""
Étape 1 — lire des fichiers dont on ne maîtrise ni le format, ni les colonnes,
ni l'encodage, sans jamais planter le pipeline sur un fichier abîmé.

La difficulté n'est pas de lire un .xlsx : c'est de trouver *où commence le
tableau* quand trois lignes de titre et un logo le précèdent, et de continuer
la semaine suivante quand une agence change son modèle d'export.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".csv"}

# Tous les noms sous lesquels on a déjà vu passer chaque notion métier.
ALIAS_COLONNES: dict[str, set[str]] = {
    "date": {"date", "date vente", "date_vente", "date de vente", "jour", "date facture"},
    "client": {"client", "raison sociale", "raison_sociale", "nom client", "compte", "tiers"},
    "produit": {"produit", "designation", "désignation", "article", "libelle", "libellé", "reference", "référence"},
    "quantite": {"quantite", "quantité", "qte", "qté", "qty", "nb", "nombre"},
    "prix_unitaire": {"prix unitaire", "prix_unitaire", "pu", "p.u.", "pu ht", "prix"},
    "montant": {"montant", "montant ht", "ca", "ca ht", "ca_ht", "total", "total ht", "chiffre d'affaires"},
    "vendeur": {"vendeur", "commercial", "représentant", "representant", "conseiller"},
}

# Le nom de l'agence est dans le nom du fichier, pas dans les données.
MOTIF_AGENCE = re.compile(r"(chambery|chambéry|grenoble|annecy)", re.IGNORECASE)
MOTIF_SEMAINE = re.compile(r"[Ss](?:emaine)?[ _-]?(\d{1,2})\b")


@dataclass
class SourceLue:
    chemin: Path
    donnees: pd.DataFrame
    agence: str
    colonnes_reconnues: dict[str, str]
    lignes_brutes: int
    anomalies: list[str]


def _normaliser(texte: object) -> str:
    """Compare des en-têtes sans se faire piéger par les accents, la casse ou les espaces."""
    if texte is None or (isinstance(texte, float) and pd.isna(texte)):
        return ""
    brut = str(texte).strip().lower().replace(" ", " ")
    brut = "".join(c for c in unicodedata.normalize("NFKD", brut) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", brut)


def _alias_inverse() -> dict[str, str]:
    table = {}
    for canonique, alias in ALIAS_COLONNES.items():
        for a in alias:
            table[_normaliser(a)] = canonique
    return table


ALIAS_INVERSE = _alias_inverse()


def _score_entete(valeurs: list[object]) -> tuple[int, dict[str, str]]:
    """Combien de notions métier cette ligne reconnaît-elle ?"""
    trouvees: dict[str, str] = {}
    for valeur in valeurs:
        canonique = ALIAS_INVERSE.get(_normaliser(valeur))
        if canonique and canonique not in trouvees:
            trouvees[canonique] = str(valeur)
    return len(trouvees), trouvees


def _trouver_entete(brut: pd.DataFrame, profondeur: int = 12) -> tuple[int, dict[str, str]]:
    """
    Balaie les premières lignes et retient celle qui reconnaît le plus de colonnes.
    C'est ce qui permet d'avaler un export avec trois lignes de titre au-dessus
    du vrai tableau sans le paramétrer à la main.
    """
    meilleur_score, meilleure_ligne, meilleures_colonnes = 0, 0, {}
    for i in range(min(profondeur, len(brut))):
        score, colonnes = _score_entete(list(brut.iloc[i]))
        if score > meilleur_score:
            meilleur_score, meilleure_ligne, meilleures_colonnes = score, i, colonnes
    return meilleure_ligne, meilleures_colonnes


def _lire_brut(chemin: Path) -> pd.DataFrame:
    """Lit le fichier sans en-tête : on décidera nous-mêmes où il se trouve."""
    if chemin.suffix.lower() == ".csv":
        # Le séparateur et l'encodage varient d'un exportateur à l'autre.
        for encodage in ("utf-8-sig", "latin-1"):
            for separateur in (";", ",", "\t"):
                try:
                    df = pd.read_csv(chemin, sep=separateur, header=None, dtype=object, encoding=encodage)
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
                if df.shape[1] >= 4:
                    return df
        raise ValueError("aucune combinaison encodage/séparateur ne donne un tableau exploitable")
    return pd.read_excel(chemin, sheet_name=0, header=None, dtype=object)


def deviner_agence(chemin: Path) -> str:
    correspondance = MOTIF_AGENCE.search(chemin.stem)
    if correspondance:
        return correspondance.group(1).capitalize().replace("Chambery", "Chambéry")
    return "Non identifiée"


def deviner_semaine(chemin: Path) -> int | None:
    correspondance = MOTIF_SEMAINE.search(chemin.stem)
    return int(correspondance.group(1)) if correspondance else None


def lire_source(chemin: Path) -> SourceLue:
    anomalies: list[str] = []
    brut = _lire_brut(chemin)
    ligne_entete, colonnes = _trouver_entete(brut)

    manquantes = {"date", "montant"} - set(colonnes)
    if manquantes:
        raise ValueError(f"colonnes indispensables introuvables : {', '.join(sorted(manquantes))}")
    if ligne_entete > 0:
        anomalies.append(f"{ligne_entete} ligne{'s' if ligne_entete > 1 else ''} de titre ignorée{'s' if ligne_entete > 1 else ''} avant l'en-tête")
    non_reconnues = len(brut.columns) - len(colonnes)
    if non_reconnues > 0:
        anomalies.append(f"{non_reconnues} colonne{'s' if non_reconnues > 1 else ''} non reconnue{'s' if non_reconnues > 1 else ''}, ignorée{'s' if non_reconnues > 1 else ''}")

    donnees = brut.iloc[ligne_entete + 1:].copy()
    donnees.columns = [_normaliser(c) for c in brut.iloc[ligne_entete]]

    # Ne garder que les colonnes qui portent une notion métier, renommées au canonique.
    correspondance = {_normaliser(libelle): canonique for canonique, libelle in colonnes.items()}
    donnees = donnees[[c for c in donnees.columns if c in correspondance]]
    donnees = donnees.rename(columns=correspondance)
    donnees = donnees.loc[:, ~donnees.columns.duplicated()]

    return SourceLue(
        chemin=chemin,
        donnees=donnees.reset_index(drop=True),
        agence=deviner_agence(chemin),
        colonnes_reconnues=colonnes,
        lignes_brutes=len(donnees),
        anomalies=anomalies,
    )


def collecter(dossier: Path) -> tuple[list[SourceLue], list[tuple[Path, str]]]:
    """
    Renvoie (sources lues, échecs). Un fichier illisible n'interrompt jamais le
    traitement : il est journalisé et signalé dans le rapport.
    """
    sources: list[SourceLue] = []
    echecs: list[tuple[Path, str]] = []

    fichiers = sorted(c for c in dossier.iterdir() if c.suffix.lower() in EXTENSIONS and not c.name.startswith("~$"))
    for chemin in fichiers:
        try:
            source = lire_source(chemin)
        except Exception as erreur:  # on veut vraiment tout attraper : le pipeline doit finir
            logger.warning("%s : %s", chemin.name, erreur)
            echecs.append((chemin, str(erreur)))
            continue
        logger.info("%s : %d lignes, agence %s", chemin.name, source.lignes_brutes, source.agence)
        sources.append(source)

    return sources, echecs
