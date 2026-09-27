# Planification

Deux options selon le contexte client.

## cron — le plus simple

```bash
crontab -e
# puis coller le contenu de reporting.cron en adaptant les chemins
```

Le `flock -n` est là pour une raison précise : si le partage réseau ralentit et
qu'une exécution dépasse une semaine (c'est arrivé), la suivante ne démarre pas
par-dessus et ne produit pas deux rapports contradictoires.

## systemd — quand on veut du rattrapage et des journaux propres

```bash
sudo cp reporting.service reporting.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reporting.timer
systemctl list-timers reporting.timer     # vérifier la prochaine exécution
journalctl -u reporting.service -n 50     # lire le dernier passage
```

`Persistent=true` rattrape l'exécution si le serveur était éteint le lundi matin
— cas fréquent sur les petites infrastructures où la machine s'arrête le week-end.
`RandomizedDelaySec=300` évite que dix clients tapent le même partage à 6 h 30 pile.

## Variables d'environnement

À placer dans `/etc/reporting/env` (mode 600, propriétaire `reporting`) :

```
SMTP_HOTE=smtp.votre-hebergeur.fr
SMTP_PORT=587
SMTP_UTILISATEUR=reporting@client.fr
SMTP_MOT_DE_PASSE=...
RAPPORT_EXPEDITEUR=reporting@client.fr
RAPPORT_DESTINATAIRES=direction@client.fr,commerce@client.fr
```

Aucun secret n'est écrit dans le dépôt : `src/config.py` ne fait que les lire.

## Surveillance

Le script renvoie trois codes de retour, exploitables par n'importe quelle sonde :

| Code | Signification | Réaction attendue |
|---|---|---|
| 0 | Rapport produit et envoyé | rien |
| 1 | Échec bloquant (aucune source, envoi impossible) | alerte immédiate |
| 2 | Rapport produit, mais plus de 5 % de lignes écartées | prévenir l'agence concernée |

Le code 2 est celui qui compte : il attrape la dérive silencieuse, quand une
agence change son modèle d'export et que le rapport se met à sous-compter sans
que personne ne s'en aperçoive.
