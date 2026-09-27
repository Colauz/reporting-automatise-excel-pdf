"""
Tests des fonctions de parsing — le cœur fragile du pipeline.

Ce sont elles qui décident si une ligne entre dans le rapport ou part au rejet.
Chaque cas ci-dessous vient d'un désordre réellement rencontré dans un export client.

    python -m pytest tests/ -v
"""

from datetime import date

import pytest

from src.nettoyage import normaliser_vendeur, parser_date, parser_montant


class TestParserMontant:
    @pytest.mark.parametrize("brut, attendu", [
        (1234.56, 1234.56),
        (1234, 1234.0),
        ("1234.56", 1234.56),
        ("1234,56", 1234.56),
        ("1 234,56", 1234.56),
        ("1 234,56", 1234.56),      # espace insécable : export Excel français
        ("1 234,56", 1234.56),      # espace fine insécable : LibreOffice
        ("1.234,56", 1234.56),           # séparateur de milliers point, décimal virgule
        ("1,234.56", 1234.56),           # convention anglo-saxonne
        ("1 234,56 €", 1234.56),
        ("  42,00  ", 42.0),
    ])
    def test_formats_acceptes(self, brut, attendu):
        assert parser_montant(brut) == pytest.approx(attendu)

    @pytest.mark.parametrize("brut", ["", "   ", None, "n/a", "TOTAL", "—", float("nan")])
    def test_renvoie_none_plutot_que_deviner(self, brut):
        assert parser_montant(brut) is None


class TestParserDate:
    @pytest.mark.parametrize("brut, attendu", [
        ("15/03/2026", date(2026, 3, 15)),
        ("2026-03-15", date(2026, 3, 15)),
        ("15-03-2026", date(2026, 3, 15)),
        ("15.03.2026", date(2026, 3, 15)),
        (46096, date(2026, 3, 15)),        # numéro de série Excel
        (46096.0, date(2026, 3, 15)),
    ])
    def test_formats_acceptes(self, brut, attendu):
        assert parser_date(brut) == attendu

    def test_jour_avant_mois(self):
        """03/04/2026 est le 3 avril en France, pas le 4 mars."""
        assert parser_date("03/04/2026") == date(2026, 4, 3)

    @pytest.mark.parametrize("brut", ["", None, "TOTAL", 12, 999999, "semaine 12"])
    def test_rejette_ce_qui_n_est_pas_une_date(self, brut):
        assert parser_date(brut) is None


class TestNormaliserVendeur:
    @pytest.mark.parametrize("brut", ["M. Perrin", "Perrin Thomas", "T. Perrin", "PERRIN", "perrin t."])
    def test_ecritures_equivalentes(self, brut):
        """Cinq façons d'écrire le même commercial doivent se rejoindre."""
        assert normaliser_vendeur(brut) == "Perrin"

    def test_capitales_designent_le_nom_de_famille(self):
        """Convention répandue dans les exports : le nom est en capitales."""
        assert normaliser_vendeur("Amélie ROUX") == "Roux"
        assert normaliser_vendeur("ROUX Amelie") == "Roux"

    def test_accents_normalises(self):
        assert normaliser_vendeur("Fournier Gaël") == "Fournier"

    @pytest.mark.parametrize("brut", [None, "", "   ", float("nan")])
    def test_valeur_absente(self, brut):
        assert normaliser_vendeur(brut) == "Non renseigné"
