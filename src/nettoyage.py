"""
Étape 2 — transformer un empilement de tableaux hétérogènes en une table unique
sur laquelle on peut compter.

Chaque règle appliquée est journalisée : le rapport final affiche combien de
lignes ont été écartées et pourquoi. Un nettoyage silencieux est un nettoyage
qu'on ne peut pas défendre devant le client.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
import pandas as pd

from .collecte import SourceLue, deviner_semaine

# Excel compte les jours depuis le 30/12/1899 (le fameux bug de l'année 1900).
ORIGINE_EXCEL = datetime(1899, 12, 30)

MOTIF_INITIALE = re.compile(r"^(?:m\.|mme|mr)?\s*[a-z]\.?$", re.IGNORECASE)


@dataclass
class JournalQualite:
    lignes_lues: int = 0
    lignes_retenues: int = 0
    rejets: dict[str, int] = field(default_factory=dict)
    avertissements: list[str] = field(default_factory=list)
    fichiers_en_echec: list[tuple[str, str]] = field(default_factory=list)

    def rejeter(self, motif: str, nombre: int) -> None:
        if nombre > 0:
            self.rejets[motif] = self.rejets.get(motif, 0) + int(nombre)

    @property
    def lignes_rejetees(self) -> int:
        return sum(self.rejets.values())

    @property
    def taux_rejet(self) -> float:
        return self.lignes_rejetees / self.lignes_lues if self.lignes_lues else 0.0


def parser_montant(valeur: object) -> float | None:
    """
    Accepte 1234.56, « 1 234,56 », « 1 234,56 » (espace insécable), « 1,234.56 »
    et renvoie None sur tout le reste plutôt que de deviner.
    """
    if valeur is None or (isinstance(valeur, float) and np.isnan(valeur)):
        return None
    if isinstance(valeur, (int, float, np.integer, np.floating)):
        return float(valeur)

    texte = str(valeur).strip().replace(" ", "").replace(" ", "").replace(" ", "")
    texte = texte.replace("€", "").replace("EUR", "")
    if not texte:
        return None

    # Si les deux séparateurs sont présents, le dernier rencontré est le décimal.
    if "," in texte and "." in texte:
        if texte.rfind(",") > texte.rfind("."):
            texte = texte.replace(".", "").replace(",", ".")
        else:
            texte = texte.replace(",", "")
    else:
        texte = texte.replace(",", ".")

    try:
        return float(texte)
    except ValueError:
        return None


def parser_date(valeur: object) -> date | None:
    """Gère JJ/MM/AAAA, AAAA-MM-JJ, les objets datetime et les numéros de série Excel."""
    if valeur is None or (isinstance(valeur, float) and np.isnan(valeur)):
        return None
    if isinstance(valeur, datetime):
        return valeur.date()
    if isinstance(valeur, date):
        return valeur

    # Numéro de série Excel : un entier entre 1990 et 2100 environ.
    if isinstance(valeur, (int, float, np.integer, np.floating)):
        serie = float(valeur)
        if 30000 <= serie <= 80000:
            return (ORIGINE_EXCEL + pd.Timedelta(days=serie)).date()
        return None

    texte = str(valeur).strip()
    if not texte:
        return None
    for gabarit in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return datetime.strptime(texte, gabarit).date()
        except ValueError:
            continue
    # Dernier recours : pandas, en forçant le jour d'abord (convention française).
    try:
        converti = pd.to_datetime(texte, dayfirst=True, errors="raise")
        return converti.date()
    except (ValueError, TypeError):
        return None


def normaliser_vendeur(valeur: object) -> str:
    """
    « M. Perrin », « Perrin Thomas » et « T. Perrin » désignent la même personne.
    On retient le nom de famille — le seul jeton qui ne soit ni une civilité,
    ni une initiale — pour réconcilier les trois écritures.
    """
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return "Non renseigné"
    texte = str(valeur).strip()
    if not texte:
        return "Non renseigné"

    jetons = [j for j in re.split(r"[\s,]+", texte) if j]
    candidats = [j for j in jetons if not MOTIF_INITIALE.match(j)]
    if not candidats:
        return texte.title()

    # Beaucoup d'exports écrivent le nom de famille en capitales : c'est le
    # signal le plus fiable. À défaut, on retient le jeton le plus long.
    capitales = [j for j in candidats if j.isupper() and len(j) > 1]
    nom = capitales[0] if capitales else max(candidats, key=len)
    nom = "".join(c for c in unicodedata.normalize("NFKD", nom) if not unicodedata.combining(c))
    return nom.capitalize()


def consolider(sources: list[SourceLue], journal: JournalQualite) -> pd.DataFrame:
    """Empile les sources et applique les règles de qualité, en traçant chaque rejet."""
    morceaux = []
    for source in sources:
        df = source.donnees.copy()
        df["agence"] = source.agence
        df["fichier_source"] = source.chemin.name
        df["semaine_fichier"] = deviner_semaine(source.chemin)
        for message in source.anomalies:
            journal.avertissements.append(f"{source.chemin.name} — {message}")
        morceaux.append(df)

    if not morceaux:
        return pd.DataFrame()

    table = pd.concat(morceaux, ignore_index=True)
    journal.lignes_lues = len(table)

    # --- Typage -------------------------------------------------------------
    table["date"] = table["date"].map(parser_date)
    table["montant"] = table["montant"].map(parser_montant)
    for colonne in ("quantite", "prix_unitaire"):
        if colonne in table:
            table[colonne] = table[colonne].map(parser_montant)
    for colonne in ("client", "produit"):
        if colonne in table:
            table[colonne] = table[colonne].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
    if "vendeur" in table:
        table["vendeur"] = table["vendeur"].map(normaliser_vendeur)

    # --- Règles de rejet ----------------------------------------------------
    avant = len(table)

    # Les lignes de total collées en bas du tableau n'ont pas de date.
    sans_date = table["date"].isna()
    journal.rejeter("date absente ou illisible (lignes de total, séparateurs)", sans_date.sum())
    table = table[~sans_date]

    sans_montant = table["montant"].isna()
    journal.rejeter("montant absent (saisie incomplète)", sans_montant.sum())
    table = table[~sans_montant]

    montant_nul = table["montant"] <= 0
    journal.rejeter("montant nul ou négatif (avoir non traité)", montant_nul.sum())
    table = table[~montant_nul]

    # Doublons exacts : même fichier, même date, même client, même produit, même montant.
    cles = [c for c in ("date", "client", "produit", "quantite", "montant", "agence") if c in table]
    doublons = table.duplicated(subset=cles, keep="first")
    journal.rejeter("doublon exact (copier-coller entre exports)", doublons.sum())
    table = table[~doublons]

    journal.lignes_retenues = len(table)
    assert journal.lignes_retenues + journal.lignes_rejetees == avant, "comptage des rejets incohérent"

    # --- Enrichissement -----------------------------------------------------
    table["date"] = pd.to_datetime(table["date"])
    iso = table["date"].dt.isocalendar()
    table["annee_iso"] = iso["year"].astype(int)
    table["semaine_iso"] = iso["week"].astype(int)
    table["periode_iso"] = table["annee_iso"].astype(str) + "-S" + table["semaine_iso"].astype(str).str.zfill(2)
    table["jour_nom"] = table["date"].dt.dayofweek.map(
        {0: "lundi", 1: "mardi", 2: "mercredi", 3: "jeudi", 4: "vendredi", 5: "samedi", 6: "dimanche"}
    )

    return table.sort_values("date").reset_index(drop=True)


def detecter_anomalies(table: pd.DataFrame, seuil_ligne: float) -> pd.DataFrame:
    """
    Lignes à faire vérifier par un humain. Deux critères complémentaires :
    un seuil absolu (erreur de saisie grossière) et un écart interquartile
    par produit (montant plausible dans l'absolu mais anormal pour ce produit).
    """
    if table.empty:
        return table

    signale = table["montant"] > seuil_ligne
    motifs = pd.Series(np.where(signale, f"montant > {seuil_ligne:,.0f} €".replace(",", " "), ""), index=table.index)

    if "produit" in table:
        bornes = table.groupby("produit")["montant"].quantile([0.25, 0.75]).unstack()
        bornes["iqr"] = bornes[0.75] - bornes[0.25]
        bornes["plafond"] = bornes[0.75] + 3 * bornes["iqr"]
        plafonds = table["produit"].map(bornes["plafond"])
        hors_norme = (table["montant"] > plafonds) & plafonds.notna()
        motifs = motifs.where(~hors_norme | signale, "montant atypique pour ce produit")
        signale = signale | hors_norme

    anomalies = table[signale].copy()
    anomalies["motif"] = motifs[signale]
    return anomalies.sort_values("montant", ascending=False)
