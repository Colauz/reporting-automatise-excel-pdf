"""Configuration du pipeline — un seul endroit à modifier pour l'adapter à un client."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ConfigEnvoi:
    serveur_smtp: str = os.getenv("SMTP_HOTE", "smtp.example.fr")
    port: int = int(os.getenv("SMTP_PORT", "587"))
    utilisateur: str = os.getenv("SMTP_UTILISATEUR", "")
    mot_de_passe: str = os.getenv("SMTP_MOT_DE_PASSE", "")
    expediteur: str = os.getenv("RAPPORT_EXPEDITEUR", "reporting@voltea-distribution.fr")
    destinataires: tuple[str, ...] = tuple(
        d.strip() for d in os.getenv("RAPPORT_DESTINATAIRES", "direction@voltea-distribution.fr").split(",") if d.strip()
    )


@dataclass(frozen=True)
class Config:
    dossier_sources: Path = RACINE / "sources"
    dossier_sorties: Path = RACINE / "sorties"
    dossier_travail: Path = RACINE / "sorties" / ".travail"

    # Seuils qui déclenchent une alerte dans le rapport.
    seuil_baisse_ca: float = -0.10          # une agence en repli de plus de 10 % vs S-1
    seuil_ligne_aberrante: float = 25_000    # une ligne de vente au-dessus est suspecte
    seuil_taux_rejet: float = 0.05           # plus de 5 % de lignes rejetées = source à corriger

    envoi: ConfigEnvoi = field(default_factory=ConfigEnvoi)

    def preparer(self) -> None:
        self.dossier_sorties.mkdir(parents=True, exist_ok=True)
        self.dossier_travail.mkdir(parents=True, exist_ok=True)
