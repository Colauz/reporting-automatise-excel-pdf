#!/usr/bin/env python3
"""
Pipeline de reporting hebdomadaire.

    sources/*.xlsx  ─┐
    sources/*.csv   ─┴─► collecte ─► nettoyage ─► graphiques ─► PDF ─► e-mail

Exécution manuelle :
    python main.py --essai              # produit le PDF, n'envoie rien
    python main.py                      # produit et envoie

Exécution planifiée : voir planification/README.md (cron ou systemd timer).

Codes de retour : 0 succès · 1 erreur bloquante · 2 succès avec avertissements
(un rapport a été produit mais le taux de rejet dépasse le seuil configuré).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from src.collecte import collecter
from src.config import Config
from src.envoi import composer, envoyer
from src.graphiques import produire_toutes
from src.nettoyage import JournalQualite, consolider, detecter_anomalies
from src.rapport import euros, generer_pdf

logger = logging.getLogger("reporting")


def configurer_journalisation(dossier: Path, verbeux: bool) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbeux else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)-18s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(dossier / "pipeline.log", encoding="utf-8"),
        ],
    )


def corps_du_message(table, journal: JournalQualite, semaine: str) -> str:
    derniere = table[table["periode_iso"] == semaine]
    ca = derniere["montant"].sum()
    par_agence = derniere.groupby("agence")["montant"].sum().sort_values(ascending=False)
    lignes_agences = "\n".join(f"  - {agence:<12} {euros(montant)}" for agence, montant in par_agence.items())

    return f"""Bonjour,

Voici le rapport commercial de la semaine {semaine}.

Chiffre d'affaires : {euros(ca)}
Lignes de vente    : {len(derniere)}

Par agence :
{lignes_agences}

Qualité des sources : {journal.lignes_retenues} lignes retenues sur {journal.lignes_lues} lues
({journal.taux_rejet:.1%} écartées, détail en page 3 du rapport).

Le détail se trouve dans le PDF joint.

--
Message généré automatiquement — pipeline de reporting hebdomadaire.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", type=Path, help="dossier des fichiers à consolider")
    parser.add_argument("--sorties", type=Path, help="dossier de destination du rapport")
    parser.add_argument("--essai", action="store_true", help="n'envoie pas l'e-mail, l'écrit en .eml")
    parser.add_argument("--sans-envoi", action="store_true", help="s'arrête après le PDF")
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()

    config = Config()
    if args.sources:
        config = Config(dossier_sources=args.sources)
    if args.sorties:
        config = Config(dossier_sources=config.dossier_sources, dossier_sorties=args.sorties,
                        dossier_travail=args.sorties / ".travail")
    config.preparer()
    configurer_journalisation(config.dossier_travail, args.verbeux)

    if not config.dossier_sources.exists():
        logger.error("Dossier source introuvable : %s", config.dossier_sources)
        return 1

    # --- 1. Collecte --------------------------------------------------------
    sources, echecs = collecter(config.dossier_sources)
    if not sources:
        logger.error("Aucun fichier exploitable dans %s", config.dossier_sources)
        return 1
    logger.info("%d fichiers lus, %d en échec", len(sources), len(echecs))

    # --- 2. Nettoyage -------------------------------------------------------
    journal = JournalQualite()
    journal.fichiers_en_echec = [(c.name, message) for c, message in echecs]
    table = consolider(sources, journal)
    if table.empty:
        logger.error("Aucune ligne exploitable après nettoyage")
        return 1
    logger.info("%d lignes retenues sur %d (%.1f %% écartées)",
                journal.lignes_retenues, journal.lignes_lues, journal.taux_rejet * 100)

    anomalies = detecter_anomalies(table, config.seuil_ligne_aberrante)
    if len(anomalies):
        logger.info("%d ligne%s atypique%s signalée%s", len(anomalies), *(["s" if len(anomalies) > 1 else ""] * 3))

    # Table consolidée exportée : c'est souvent elle que le client réutilise.
    semaine = sorted(table["periode_iso"].unique())[-1]
    export = config.dossier_sorties / f"ventes_consolidees_{semaine}.csv"
    table.to_csv(export, index=False, encoding="utf-8-sig")
    logger.info("Table consolidée : %s", export.name)

    # --- 3. Graphiques ------------------------------------------------------
    figures = produire_toutes(table, config.dossier_travail / "figures")

    # --- 4. PDF -------------------------------------------------------------
    chemin_pdf = config.dossier_sorties / f"rapport_commercial_{semaine}.pdf"
    generer_pdf(chemin_pdf, table, anomalies, journal, figures,
                config.seuil_baisse_ca, date_edition=date.today())
    logger.info("Rapport : %s (%.0f Ko)", chemin_pdf.name, chemin_pdf.stat().st_size / 1024)

    # --- 5. Envoi -----------------------------------------------------------
    if not args.sans_envoi:
        message = composer(
            expediteur=config.envoi.expediteur,
            destinataires=config.envoi.destinataires,
            sujet=f"Rapport commercial — semaine {semaine}",
            corps_texte=corps_du_message(table, journal, semaine),
            piece_jointe=chemin_pdf,
        )
        resultat = envoyer(
            message, config.envoi.serveur_smtp, config.envoi.port,
            config.envoi.utilisateur, config.envoi.mot_de_passe,
            essai=args.essai, dossier_essai=config.dossier_travail,
        )
        if resultat.erreur:
            logger.error("Le rapport est produit mais n'a pas pu être envoyé.")
            return 1

    if journal.taux_rejet > config.seuil_taux_rejet:
        logger.warning("Taux de rejet %.1f %% au-dessus du seuil %.1f %% — sources à corriger",
                       journal.taux_rejet * 100, config.seuil_taux_rejet * 100)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
