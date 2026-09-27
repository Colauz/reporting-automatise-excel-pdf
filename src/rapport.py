"""
Étape 4 — assembler le PDF.

Structure fixe, pensée pour être lue en 90 secondes le lundi matin :
  page 1  les quatre chiffres de la semaine, la courbe, les alertes
  page 2  agences, produits, variation
  page 3  qualité des données — ce qui a été écarté et pourquoi
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from .nettoyage import JournalQualite

ENCRE = colors.HexColor("#1B2430")
ENCRE_DOUCE = colors.HexColor("#6B7684")
TRAIT = colors.HexColor("#DDE2E8")
FOND_DOUX = colors.HexColor("#F4F6F8")
ACCENT = colors.HexColor("#1F5C8B")
ALERTE = colors.HexColor("#B3462F")
SUCCES = colors.HexColor("#2E7D5B")

LARGEUR_UTILE = A4[0] - 40 * mm


@dataclass
class Indicateur:
    libelle: str
    valeur: str
    detail: str = ""
    ton: str = "neutre"   # neutre | positif | negatif


def euros(valeur: float) -> str:
    return f"{valeur:,.0f} €".replace(",", " ")


def pct(valeur: float, signe: bool = False) -> str:
    """Pourcentage à la française : virgule décimale, espace insécable.

    Tiret demi-cadratin pour le signe moins : la police Helvetica standard
    du PDF n'a pas le glyphe U+2212."""
    texte = f"{valeur * 100:{'+' if signe else ''}.1f}".replace(".", ",").replace("-", "–")
    return f"{texte} %"


def pluriel(nombre: int, singulier: str, forme_plurielle: str) -> str:
    return f"{nombre} {singulier if nombre <= 1 else forme_plurielle}"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle("titre", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=19, leading=23, textColor=ENCRE, alignment=TA_LEFT, spaceAfter=2),
        "sous_titre": ParagraphStyle("sous_titre", parent=base["Normal"], fontName="Helvetica",
                                     fontSize=9.5, leading=13, textColor=ENCRE_DOUCE, spaceAfter=14),
        "section": ParagraphStyle("section", parent=base["Heading2"], fontName="Helvetica-Bold",
                                  fontSize=11.5, leading=15, textColor=ENCRE, spaceBefore=14, spaceAfter=7),
        "corps": ParagraphStyle("corps", parent=base["Normal"], fontName="Helvetica",
                                fontSize=9, leading=13, textColor=ENCRE),
        "note": ParagraphStyle("note", parent=base["Normal"], fontName="Helvetica-Oblique",
                               fontSize=8, leading=11, textColor=ENCRE_DOUCE),
        "kpi_valeur": ParagraphStyle("kpi_valeur", fontName="Helvetica-Bold", fontSize=16,
                                     leading=19, textColor=ENCRE),
        "kpi_libelle": ParagraphStyle("kpi_libelle", fontName="Helvetica", fontSize=7.5,
                                      leading=10, textColor=ENCRE_DOUCE),
        "kpi_detail": ParagraphStyle("kpi_detail", fontName="Helvetica", fontSize=8, leading=11),
    }


def _bandeau_kpi(indicateurs: list[Indicateur], st: dict) -> Table:
    tons = {"positif": SUCCES, "negatif": ALERTE, "neutre": ENCRE_DOUCE}
    cellules = []
    for ind in indicateurs:
        style_detail = ParagraphStyle("d", parent=st["kpi_detail"], textColor=tons[ind.ton])
        cellules.append([
            Paragraph(ind.libelle.upper(), st["kpi_libelle"]),
            Paragraph(ind.valeur, st["kpi_valeur"]),
            Paragraph(ind.detail, style_detail),
        ])

    colonnes = [[c[i] for c in cellules] for i in range(3)]
    table = Table([colonnes[0], colonnes[1], colonnes[2]],
                  colWidths=[LARGEUR_UTILE / len(cellules)] * len(cellules))
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 0), (-1, -1), FOND_DOUX),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.white),
    ]))
    return table


def _tableau(entetes: list[str], lignes: list[list[str]], largeurs: list[float],
             alignements_droite: tuple[int, ...] = ()) -> Table:
    table = Table([entetes] + lignes, colWidths=largeurs, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("TEXTCOLOR", (0, 0), (-1, 0), ENCRE_DOUCE),
        ("TEXTCOLOR", (0, 1), (-1, -1), ENCRE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, TRAIT),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, colors.HexColor("#EEF1F4")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for colonne in alignements_droite:
        style.append(("ALIGN", (colonne, 0), (colonne, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table


def _image_ajustee(chemin: Path, largeur: float = LARGEUR_UTILE) -> Image:
    from PIL import Image as PILImage

    with PILImage.open(chemin) as img:
        ratio = img.height / img.width
    return Image(str(chemin), width=largeur, height=largeur * ratio)


def construire_kpi(table: pd.DataFrame, journal: JournalQualite, seuil_baisse: float) -> list[Indicateur]:
    semaines = sorted(table["periode_iso"].unique())
    courante = semaines[-1]
    semaine = table[table["periode_iso"] == courante]
    ca = semaine["montant"].sum()

    if len(semaines) >= 2:
        precedent = table[table["periode_iso"] == semaines[-2]]["montant"].sum()
        variation = (ca - precedent) / precedent if precedent else 0.0
        detail = f"{pct(variation, signe=True)} vs {semaines[-2]}"
        ton = "negatif" if variation < seuil_baisse else ("positif" if variation > 0 else "neutre")
    else:
        detail, ton = "pas d'historique", "neutre"

    nb_commandes = len(semaine)
    panier = ca / nb_commandes if nb_commandes else 0
    clients = semaine["client"].nunique() if "client" in semaine else 0

    return [
        Indicateur("CA de la semaine", euros(ca), detail, ton),
        Indicateur("Lignes de vente", f"{nb_commandes:,}".replace(",", " "),
                   f"{clients} clients actifs"),
        Indicateur("Panier moyen", euros(panier), f"sur {courante}"),
        Indicateur("Lignes écartées", pct(journal.taux_rejet),
                   f"{journal.lignes_rejetees} sur {journal.lignes_lues:,}".replace(",", "\u00a0"),
                   "negatif" if journal.taux_rejet > 0.05 else "positif"),
    ]


def generer_pdf(
    chemin: Path,
    table: pd.DataFrame,
    anomalies: pd.DataFrame,
    journal: JournalQualite,
    figures: dict[str, Path],
    seuil_baisse: float,
    date_edition: date | None = None,
) -> Path:
    st = _styles()
    date_edition = date_edition or date.today()
    semaines = sorted(table["periode_iso"].unique())
    courante = semaines[-1]

    chemin.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(chemin), pagesize=A4,
                          leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=18 * mm, bottomMargin=20 * mm,
                          title=f"Rapport commercial {courante}",
                          author="Pipeline de reporting automatisé")

    def decorer(canevas, document):
        canevas.saveState()
        canevas.setStrokeColor(TRAIT)
        canevas.setLineWidth(0.6)
        canevas.line(20 * mm, 15 * mm, A4[0] - 20 * mm, 15 * mm)
        canevas.setFont("Helvetica", 7.5)
        canevas.setFillColor(ENCRE_DOUCE)
        canevas.drawString(20 * mm, 10.5 * mm,
                           f"Voltéa Distribution — rapport hebdomadaire {courante}")
        canevas.drawRightString(A4[0] - 20 * mm, 10.5 * mm, f"page {document.page}")
        canevas.restoreState()

    cadre = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="corps")
    doc.addPageTemplates([PageTemplate(id="standard", frames=[cadre], onPage=decorer)])

    histoire = []
    histoire.append(Paragraph(f"Rapport commercial — semaine {courante.split('-S')[1]}", st["titre"]))
    histoire.append(Paragraph(
        f"Période consolidée du {table['date'].min():%d/%m/%Y} au {table['date'].max():%d/%m/%Y} · "
        f"{journal.lignes_retenues:,} lignes retenues sur {journal.lignes_lues:,} lues · "
        f"généré le {date_edition:%d/%m/%Y}".replace(",", " "),
        st["sous_titre"]))

    histoire.append(_bandeau_kpi(construire_kpi(table, journal, seuil_baisse), st))
    histoire.append(Spacer(1, 16))
    histoire.append(_image_ajustee(figures["evolution"]))

    # --- Alertes ------------------------------------------------------------
    histoire.append(Paragraph("Points d'attention", st["section"]))
    alertes = []
    if len(semaines) >= 2:
        pivot = table.pivot_table(index="agence", columns="periode_iso", values="montant", aggfunc="sum")
        for agence in pivot.index:
            avant, apres = pivot.loc[agence, semaines[-2]], pivot.loc[agence, courante]
            if pd.notna(avant) and pd.notna(apres) and avant > 0:
                variation = (apres - avant) / avant
                if variation < seuil_baisse:
                    alertes.append(f"<b>{agence}</b> recule de {pct(-variation)} "
                                   f"({euros(avant)} → {euros(apres)}).")
    if journal.taux_rejet > 0.05:
        alertes.append(f"<b>{pct(journal.taux_rejet)} des lignes</b> ont été écartées au nettoyage — "
                       f"voir le détail en page 3.")
    if len(anomalies):
        plus_grosse = anomalies.iloc[0]
        alertes.append(f"<b>{pluriel(len(anomalies), 'ligne atypique', 'lignes atypiques')}</b> à vérifier, "
                       f"dont {euros(plus_grosse['montant'])} sur « {plus_grosse['produit']} » "
                       f"({plus_grosse['fichier_source']}).")
    if journal.fichiers_en_echec:
        alertes.append(f"<b>{pluriel(len(journal.fichiers_en_echec), 'fichier', 'fichiers')}</b> "
                       f"{'n’a' if len(journal.fichiers_en_echec) == 1 else 'n’ont'} pas pu être lu{'' if len(journal.fichiers_en_echec) == 1 else 's'}.")

    if alertes:
        for alerte in alertes:
            histoire.append(Paragraph(f"• {alerte}", st["corps"]))
            histoire.append(Spacer(1, 3))
    else:
        histoire.append(Paragraph("Aucun écart au-delà des seuils configurés.", st["corps"]))

    # --- Page 2 -------------------------------------------------------------
    histoire.append(Paragraph("Activité par agence", st["section"]))
    histoire.append(_image_ajustee(figures["agences"]))
    histoire.append(Spacer(1, 6))
    histoire.append(_image_ajustee(figures["variation"]))
    histoire.append(Paragraph("Produits", st["section"]))
    histoire.append(_image_ajustee(figures["produits"]))

    if len(anomalies):
        histoire.append(Paragraph("Lignes à vérifier", st["section"]))
        lignes = [[
            f"{r['date']:%d/%m}", str(r.get("agence", ""))[:12],
            str(r.get("produit", ""))[:34], euros(r["montant"]), r["motif"],
        ] for _, r in anomalies.head(10).iterrows()]
        histoire.append(_tableau(
            ["Date", "Agence", "Produit", "Montant", "Motif"], lignes,
            [16 * mm, 22 * mm, 58 * mm, 24 * mm, 50 * mm], alignements_droite=(3,)))

    # --- Page 3 : qualité ---------------------------------------------------
    histoire.append(Paragraph("Qualité des données", st["section"]))
    histoire.append(Paragraph(
        "Chaque ligne écartée l'est par une règle explicite. Ce tableau est la contrepartie "
        "de l'automatisation : il rend le nettoyage vérifiable.", st["corps"]))
    histoire.append(Spacer(1, 8))

    if journal.rejets:
        lignes = [[motif, f"{nombre:,}".replace(",", " "),
                   pct(nombre / journal.lignes_lues)]
                  for motif, nombre in sorted(journal.rejets.items(), key=lambda kv: -kv[1])]
        lignes.append(["Total écarté", f"{journal.lignes_rejetees:,}".replace(",", " "),
                       pct(journal.taux_rejet)])
        histoire.append(_tableau(["Motif de rejet", "Lignes", "Part"], lignes,
                                 [110 * mm, 26 * mm, 24 * mm], alignements_droite=(1, 2)))
    else:
        histoire.append(Paragraph("Aucune ligne écartée.", st["corps"]))

    if journal.fichiers_en_echec:
        histoire.append(Paragraph("Fichiers non lus", st["section"]))
        histoire.append(_tableau(
            ["Fichier", "Raison"],
            [[nom[:44], raison[:70]] for nom, raison in journal.fichiers_en_echec],
            [70 * mm, 90 * mm]))

    if journal.avertissements:
        histoire.append(Paragraph("Journal de lecture", st["section"]))
        for message in journal.avertissements[:14]:
            histoire.append(Paragraph(f"• {message}", st["note"]))
        reste = len(journal.avertissements) - 14
        if reste > 0:
            histoire.append(Paragraph(f"… et {pluriel(reste, 'autre avertissement', 'autres avertissements')}.", st["note"]))

    doc.build(histoire)
    return chemin
