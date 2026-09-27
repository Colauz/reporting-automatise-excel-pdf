"""
Fabrique le « avant » : un dossier de fichiers de ventes hétérogènes,
tel qu'on le trouve réellement sur un partage réseau de PME.

Chaque agence exporte à sa façon. Rien n'est normalisé. Ce script reproduit
fidèlement les désordres rencontrés en mission :

  - noms de colonnes différents d'un fichier à l'autre (CA / Montant HT / Total)
  - trois formats de date (JJ/MM/AAAA, AAAA-MM-JJ, numéro de série Excel)
  - lignes de titre et logos au-dessus du vrai en-tête
  - lignes de total collées en bas du tableau
  - montants stockés en texte avec espaces insécables et virgule décimale
  - onglets nommés « Feuil1 », « DATA », « Export final (2) »
  - un fichier CSV latin-1 au milieu des .xlsx
  - des doublons exacts et des références client mal saisies

Usage :
    python generer_sources_desordre.py [--semaines 6] [--seed 21]
"""

from __future__ import annotations

import argparse
import random
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

DOSSIER_SOURCES = Path(__file__).parent / "sources"

AGENCES = ["Chambery", "Grenoble", "Annecy"]

PRODUITS = [
    ("Disjoncteur modulaire 16A", 13.55, "Appareillage"),
    ("Disjoncteur différentiel 30mA", 76.47, "Appareillage"),
    ("Coffret 3 rangées 39 modules", 96.97, "Appareillage"),
    ("Câble U-1000 R2V 3G2.5 100m", 164.10, "Câbles"),
    ("Gaine ICTA Ø20 100m", 37.97, "Câbles"),
    ("Dalle LED 600x600 36W", 64.62, "Éclairage"),
    ("Projecteur LED 150W IP66", 113.43, "Éclairage"),
    ("Panneau PV 425Wc", 162.03, "Photovoltaïque"),
    ("Onduleur hybride 5kW", 1146.34, "Photovoltaïque"),
    ("Borne de recharge 7.4kW", 639.47, "Recharge VE"),
    ("Multimètre TRMS CAT III", 147.69, "Outillage"),
    ("Gants isolants classe 00", 88.14, "Outillage"),
]

CLIENTS = [
    "ELEC SAVOIE", "Bâti-Pro Alpes", "SARL MONTBLANC ELEC", "Mairie de Cognin",
    "Industries Rhône SAS", "Voltalp Installation", "GRENOBLE HABITAT",
    "ETS DUMONT & FILS", "Techni-Elec 74", "Domaine Skiable Courchevel",
    "CCI Savoie", "Alpes Energies Nouvelles",
]

# Chaque agence a son propre vocabulaire de colonnes.
SCHEMAS = {
    "Chambery": {
        "colonnes": ["Date", "Client", "Produit", "Qté", "PU HT", "Montant HT", "Commercial"],
        "format_date": "%d/%m/%Y",
        "onglet": "Feuil1",
        "lignes_titre": ["VOLTEA DISTRIBUTION - AGENCE DE CHAMBERY", "Export hebdomadaire des ventes", ""],
        "ligne_total": True,
        "montants_texte": False,
    },
    "Grenoble": {
        "colonnes": ["date_vente", "raison_sociale", "designation", "quantite", "prix_unitaire", "ca_ht", "vendeur"],
        "format_date": "%Y-%m-%d",
        "onglet": "DATA",
        "lignes_titre": [],
        "ligne_total": False,
        "montants_texte": True,   # « 1 234,56 » avec espace insécable
    },
    "Annecy": {
        "colonnes": ["DATE", "CLIENT", "ARTICLE", "QUANTITE", "P.U.", "TOTAL HT", "VENDEUR"],
        "format_date": "serie_excel",   # 45789 au lieu d'une date
        "onglet": "Export final (2)",
        "lignes_titre": ["Ventes semaine", ""],
        "ligne_total": True,
        "montants_texte": False,
    },
}

VENDEURS = {
    "Chambery": ["M. Perrin", "Perrin Thomas", "T. Perrin", "S. Blanc", "Blanc Sophie"],
    "Grenoble": ["L. Fournier", "Fournier Luc", "K. Meyer"],
    "Annecy": ["A. Roux", "ROUX Amelie", "Roux A."],
}


def sans_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def montant_en_texte(valeur: float | None) -> str | None:
    """Format français avec espace insécable — le cauchemar de pd.read_excel."""
    if valeur is None:
        return None
    entier, decimales = f"{valeur:.2f}".split(".")
    groupes = []
    while len(entier) > 3:
        groupes.insert(0, entier[-3:])
        entier = entier[:-3]
    groupes.insert(0, entier)
    return " ".join(groupes) + "," + decimales


def tirer_lignes(agence: str, debut: date, fin: date, nb: int) -> list[dict]:
    lignes = []
    for _ in range(nb):
        produit, prix, _famille = random.choice(PRODUITS)
        quantite = max(1, int(np.random.poisson(max(1, 40 / prix ** 0.5))))
        remise = max(0.0, np.random.normal(0.05, 0.03))
        pu = round(prix * (1 - remise), 2)
        jour = debut + timedelta(days=random.randint(0, (fin - debut).days))
        lignes.append({
            "date": jour,
            "client": random.choice(CLIENTS),
            "produit": produit,
            "quantite": quantite,
            "pu": pu,
            "montant": round(pu * quantite, 2),
            "vendeur": random.choice(VENDEURS[agence]),
        })
    return lignes


def ecrire_xlsx(chemin: Path, agence: str, lignes: list[dict]) -> None:
    schema = SCHEMAS[agence]
    wb = Workbook()
    ws = wb.active
    ws.title = schema["onglet"]

    ligne_courante = 1
    for titre in schema["lignes_titre"]:
        if titre:
            ws.cell(row=ligne_courante, column=1, value=titre).font = Font(bold=True, size=13)
            ws.merge_cells(start_row=ligne_courante, start_column=1, end_row=ligne_courante, end_column=5)
            ws.cell(row=ligne_courante, column=1).alignment = Alignment(horizontal="center")
        ligne_courante += 1

    ligne_entete = ligne_courante
    for i, nom in enumerate(schema["colonnes"], start=1):
        ws.cell(row=ligne_entete, column=i, value=nom).font = Font(bold=True)
    ligne_courante += 1

    for ligne in lignes:
        if schema["format_date"] == "serie_excel":
            valeur_date = (ligne["date"] - date(1899, 12, 30)).days
        else:
            valeur_date = ligne["date"].strftime(schema["format_date"])

        montant = montant_en_texte(ligne["montant"]) if schema["montants_texte"] else ligne["montant"]
        pu = montant_en_texte(ligne["pu"]) if schema["montants_texte"] else ligne["pu"]

        valeurs = [valeur_date, ligne["client"], ligne["produit"], ligne["quantite"], pu, montant, ligne["vendeur"]]
        for i, v in enumerate(valeurs, start=1):
            ws.cell(row=ligne_courante, column=i, value=v)
        ligne_courante += 1

    if schema["ligne_total"]:
        ligne_courante += 1
        ws.cell(row=ligne_courante, column=1, value="TOTAL").font = Font(bold=True)
        total = round(sum(l["montant"] for l in lignes if l["montant"] is not None), 2)
        ws.cell(row=ligne_courante, column=6, value=total).font = Font(bold=True)

    chemin.parent.mkdir(exist_ok=True)
    wb.save(chemin)


def ecrire_csv_latin1(chemin: Path, lignes: list[dict]) -> None:
    """Le fichier qu'un commercial a exporté depuis son vieux logiciel de caisse."""
    df = pd.DataFrame([{
        "Date": l["date"].strftime("%d/%m/%Y"),
        "Client": l["client"],
        "Produit": l["produit"],
        "Qte": l["quantite"],
        "PU HT": f"{l['pu']:.2f}".replace(".", ","),
        "Montant HT": f"{l['montant']:.2f}".replace(".", ","),
        "Commercial": l["vendeur"],
    } for l in lignes])
    df.to_csv(chemin, sep=";", index=False, encoding="latin-1")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--semaines", type=int, default=6)
    parser.add_argument("--fin", type=date.fromisoformat, default=date(2026, 9, 20))
    parser.add_argument("--seed", type=int, default=21)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    if DOSSIER_SOURCES.exists():
        for ancien in DOSSIER_SOURCES.iterdir():
            ancien.unlink()
    DOSSIER_SOURCES.mkdir(exist_ok=True)

    ecrits = []
    for semaine in range(args.semaines):
        fin_semaine = args.fin - timedelta(weeks=semaine)
        debut_semaine = fin_semaine - timedelta(days=6)
        numero_iso = debut_semaine.isocalendar().week

        for agence in AGENCES:
            lignes = tirer_lignes(agence, debut_semaine, fin_semaine, nb=random.randint(38, 72))

            # Un doublon exact tous les deux fichiers — copier-coller malheureux.
            if random.random() < 0.5 and lignes:
                lignes.append(dict(random.choice(lignes)))
            # Une ligne sans montant — saisie interrompue.
            if random.random() < 0.35 and lignes:
                lignes[random.randrange(len(lignes))]["montant"] = None

            # Le nom du fichier n'obéit à aucune règle non plus.
            gabarits = [
                f"ventes_{sans_accents(agence).lower()}_S{numero_iso:02d}.xlsx",
                f"Export {agence} semaine {numero_iso}.xlsx",
                f"VENTES-{sans_accents(agence).upper()}-{debut_semaine:%Y%m%d}.xlsx",
                f"ventes {sans_accents(agence).lower()} s{numero_iso} (copie).xlsx",
            ]
            nom = random.choice(gabarits)
            ecrire_xlsx(DOSSIER_SOURCES / nom, agence, lignes)
            ecrits.append(nom)

        # Une fois sur trois, l'ancien logiciel de caisse crache un CSV latin-1.
        if semaine % 3 == 0:
            lignes = tirer_lignes("Chambery", debut_semaine, fin_semaine, nb=random.randint(12, 24))
            nom = f"caisse_comptoir_S{numero_iso:02d}.csv"
            ecrire_csv_latin1(DOSSIER_SOURCES / nom, lignes)
            ecrits.append(nom)

    print(f"{len(ecrits)} fichiers écrits dans {DOSSIER_SOURCES}/\n")
    for nom in sorted(ecrits):
        print(f"  {nom}")


if __name__ == "__main__":
    main()
