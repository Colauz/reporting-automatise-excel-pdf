"""
Étape 3 — les quatre figures du rapport hebdomadaire.

Une charte unique définie une fois (`appliquer_charte`) : le rapport doit
ressembler à un document d'entreprise, pas à une sortie matplotlib par défaut.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # aucun serveur graphique sur la machine qui exécute le cron

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd

ENCRE = "#1B2430"
ENCRE_DOUCE = "#6B7684"
TRAIT = "#DDE2E8"
ACCENT = "#1F5C8B"
ACCENT_CLAIR = "#7FA8C6"
ALERTE = "#B3462F"
SUCCES = "#2E7D5B"

PALETTE_AGENCES = {"Chambéry": ACCENT, "Grenoble": "#4E8F73", "Annecy": "#C08A3E", "Non identifiée": ENCRE_DOUCE}


def appliquer_charte() -> None:
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": TRAIT,
        "axes.labelcolor": ENCRE_DOUCE,
        "axes.titlecolor": ENCRE,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlepad": 12,
        "axes.labelsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": ENCRE_DOUCE,
        "ytick.color": ENCRE_DOUCE,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "grid.color": TRAIT,
        "grid.linewidth": 0.7,
        "font.family": "DejaVu Sans",
        "figure.dpi": 150,
    })


def _formateur_euros(ax) -> None:
    ax.yaxis.set_major_formatter(
        ticker.FuncFormatter(lambda v, _: f"{v / 1000:,.0f} k€".replace(",", " ") if v >= 1000 else f"{v:,.0f} €")
    )


def evolution_hebdomadaire(table: pd.DataFrame, chemin: Path) -> Path:
    """CA par semaine ISO, toutes agences confondues, avec la dernière semaine mise en avant."""
    serie = table.groupby("periode_iso")["montant"].sum().sort_index()
    fig, ax = plt.subplots(figsize=(7.2, 2.9))

    couleurs = [ACCENT_CLAIR] * len(serie)
    if len(couleurs):
        couleurs[-1] = ACCENT
    ax.bar(serie.index, serie.values, color=couleurs, width=0.62)

    for x, valeur in zip(serie.index, serie.values):
        ax.text(x, valeur, f"{valeur / 1000:.0f} k€", ha="center", va="bottom",
                fontsize=8, color=ENCRE_DOUCE)

    ax.set_title("Chiffre d'affaires par semaine")
    ax.set_ylabel("")
    ax.set_ylim(0, serie.max() * 1.18 if len(serie) else 1)
    ax.yaxis.set_visible(False)
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    fig.tight_layout()
    fig.savefig(chemin, bbox_inches="tight")
    plt.close(fig)
    return chemin


def repartition_agences(table: pd.DataFrame, chemin: Path) -> Path:
    """Trajectoire de chaque agence — c'est le croisement qui déclenche les questions."""
    pivot = table.pivot_table(index="periode_iso", columns="agence", values="montant", aggfunc="sum").sort_index()
    fig, ax = plt.subplots(figsize=(7.2, 2.9))

    for agence in pivot.columns:
        ax.plot(pivot.index, pivot[agence], marker="o", markersize=4, linewidth=1.8,
                color=PALETTE_AGENCES.get(agence, ENCRE_DOUCE), label=agence)

    ax.set_title("Chiffre d'affaires par agence")
    ax.grid(axis="y")
    ax.set_axisbelow(True)
    _formateur_euros(ax)
    ax.legend(frameon=False, fontsize=8.5, ncol=len(pivot.columns), loc="upper center",
              bbox_to_anchor=(0.5, -0.16))
    fig.tight_layout()
    fig.savefig(chemin, bbox_inches="tight")
    plt.close(fig)
    return chemin


def top_produits(table: pd.DataFrame, chemin: Path, n: int = 8) -> Path:
    serie = table.groupby("produit")["montant"].sum().nlargest(n).sort_values()
    fig, ax = plt.subplots(figsize=(7.2, 0.38 * len(serie) + 1.1))

    ax.barh(serie.index, serie.values, color=ACCENT, height=0.6)
    for y, valeur in enumerate(serie.values):
        ax.text(valeur, y, f"  {valeur / 1000:.1f} k€", va="center", fontsize=8.5, color=ENCRE_DOUCE)

    ax.set_title(f"Top {n} des produits sur la période")
    ax.xaxis.set_visible(False)
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(0, serie.max() * 1.22 if len(serie) else 1)
    fig.tight_layout()
    fig.savefig(chemin, bbox_inches="tight")
    plt.close(fig)
    return chemin


def variation_semaine(table: pd.DataFrame, chemin: Path) -> Path:
    """Écart de la dernière semaine par rapport à la précédente, agence par agence."""
    semaines = sorted(table["periode_iso"].unique())
    fig, ax = plt.subplots(figsize=(7.2, 2.5))

    if len(semaines) < 2:
        ax.text(0.5, 0.5, "Historique insuffisant pour comparer", ha="center", va="center",
                color=ENCRE_DOUCE, transform=ax.transAxes)
        ax.set_axis_off()
    else:
        courante, precedente = semaines[-1], semaines[-2]
        par_agence = table.pivot_table(index="agence", columns="periode_iso", values="montant", aggfunc="sum")
        variation = ((par_agence[courante] - par_agence[precedente]) / par_agence[precedente]).dropna()
        variation = variation.sort_values()

        couleurs = [ALERTE if v < 0 else SUCCES for v in variation.values]
        ax.barh(variation.index, variation.values * 100, color=couleurs, height=0.5)
        ax.axvline(0, color=ENCRE, linewidth=1)
        for y, valeur in enumerate(variation.values):
            decalage = 1.2 if valeur >= 0 else -1.2
            ax.text(valeur * 100 + decalage, y, f"{valeur * 100:+.1f} %".replace(".", ",").replace("-", "−"), va="center",
                    ha="left" if valeur >= 0 else "right", fontsize=8.5, color=ENCRE)

        marge = max(abs(variation.values * 100).max() * 1.45, 8)
        ax.set_xlim(-marge, marge)
        ax.set_title(f"Variation {courante} vs {precedente}")
        ax.xaxis.set_visible(False)
        ax.grid(False)
        ax.spines["bottom"].set_visible(False)

    fig.tight_layout()
    fig.savefig(chemin, bbox_inches="tight")
    plt.close(fig)
    return chemin


def produire_toutes(table: pd.DataFrame, dossier: Path) -> dict[str, Path]:
    appliquer_charte()
    dossier.mkdir(parents=True, exist_ok=True)
    return {
        "evolution": evolution_hebdomadaire(table, dossier / "evolution.png"),
        "agences": repartition_agences(table, dossier / "agences.png"),
        "produits": top_produits(table, dossier / "produits.png"),
        "variation": variation_semaine(table, dossier / "variation.png"),
    }
