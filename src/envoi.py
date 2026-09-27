"""
Étape 5 — l'envoi.

Mode « essai » par défaut : le message est écrit sur disque au format .eml et
rien ne part. C'est ce qui permet de faire tourner le pipeline en développement
et en recette sans risquer d'arroser la direction d'un client.
"""

from __future__ import annotations

import logging
import mimetypes
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ResultatEnvoi:
    envoye: bool
    destinataires: tuple[str, ...]
    chemin_eml: Path | None = None
    erreur: str | None = None


def composer(
    expediteur: str,
    destinataires: tuple[str, ...],
    sujet: str,
    corps_texte: str,
    piece_jointe: Path,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = expediteur
    message["To"] = ", ".join(destinataires)
    message["Subject"] = sujet
    message.set_content(corps_texte)

    type_mime, _ = mimetypes.guess_type(piece_jointe.name)
    principal, secondaire = (type_mime or "application/octet-stream").split("/", 1)
    message.add_attachment(
        piece_jointe.read_bytes(),
        maintype=principal,
        subtype=secondaire,
        filename=piece_jointe.name,
    )
    return message


def envoyer(
    message: EmailMessage,
    serveur: str,
    port: int,
    utilisateur: str,
    mot_de_passe: str,
    essai: bool,
    dossier_essai: Path,
) -> ResultatEnvoi:
    destinataires = tuple(a.strip() for a in message["To"].split(","))

    if essai:
        dossier_essai.mkdir(parents=True, exist_ok=True)
        chemin = dossier_essai / "dernier_message.eml"
        chemin.write_bytes(bytes(message))
        # Chemin relatif au dossier courant : le journal est lu, capturé, partagé.
        affiche = chemin.resolve().relative_to(Path.cwd()) if chemin.resolve().is_relative_to(Path.cwd()) else chemin.name
        logger.info("Mode essai : message écrit dans %s (non envoyé)", affiche)
        return ResultatEnvoi(envoye=False, destinataires=destinataires, chemin_eml=chemin)

    try:
        contexte = ssl.create_default_context()
        with smtplib.SMTP(serveur, port, timeout=30) as session:
            session.starttls(context=contexte)
            if utilisateur:
                session.login(utilisateur, mot_de_passe)
            session.send_message(message)
    except (smtplib.SMTPException, OSError) as erreur:
        logger.error("Échec de l'envoi : %s", erreur)
        return ResultatEnvoi(envoye=False, destinataires=destinataires, erreur=str(erreur))

    logger.info("Rapport envoyé à %s", ", ".join(destinataires))
    return ResultatEnvoi(envoye=True, destinataires=destinataires)
