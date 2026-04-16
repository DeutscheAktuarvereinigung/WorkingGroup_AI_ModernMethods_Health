"""Tests für services/data_loader.py"""

import io

import numpy as np
import pandas as pd
import pytest

from services.data_loader import erzeuge_altersgruppen, lade_csv


# ── erzeuge_altersgruppen ────────────────────────────────────────────────────


class TestErzeugeAltersgruppen:

    def test_standard_schritt_10(self):
        df = pd.DataFrame({"alter": [25, 35, 45, 55]})
        grenzen, labels = erzeuge_altersgruppen(df, schritt=10)
        assert labels == ["20-29", "30-39", "40-49", "50-59"]
        assert grenzen == [20, 30, 40, 50, 60]

    def test_schritt_5(self):
        df = pd.DataFrame({"alter": [22, 27]})
        grenzen, labels = erzeuge_altersgruppen(df, schritt=5)
        assert "20-24" in labels
        assert "25-29" in labels

    def test_einzelner_wert(self):
        df = pd.DataFrame({"alter": [50]})
        grenzen, labels = erzeuge_altersgruppen(df, schritt=10)
        assert len(labels) >= 1
        assert "50-59" in labels

    def test_breite_altersspanne(self):
        df = pd.DataFrame({"alter": [0, 99]})
        grenzen, labels = erzeuge_altersgruppen(df, schritt=10)
        assert labels[0] == "0-9"
        assert labels[-1] == "90-99"
        assert len(labels) == 10

    def test_gleiche_alter(self):
        df = pd.DataFrame({"alter": [30, 30, 30]})
        grenzen, labels = erzeuge_altersgruppen(df, schritt=10)
        assert len(labels) == 1
        assert labels[0] == "30-39"

    def test_randwert_genau_auf_grenze(self):
        """Alter genau auf einer 10er-Grenze."""
        df = pd.DataFrame({"alter": [20, 30]})
        grenzen, labels = erzeuge_altersgruppen(df, schritt=10)
        assert "20-29" in labels
        assert "30-39" in labels


# ── lade_csv ─────────────────────────────────────────────────────────────────


class TestLadeCsv:

    def _make_csv(self, data: dict) -> io.StringIO:
        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, sep=";", index=False)
        buf.seek(0)
        return buf

    def test_bestand_erfolgreich(self):
        csv = self._make_csv({
            "versicherten_id": ["V1", "V2"],
            "alter": [30, 50],
            "geschlecht": ["M", "W"],
            "tarifwerk": ["Classic", "Komfort"],
            "tarif_id": ["CL-AMB", "KO-AMB"],
            "tarifart": ["ambulant", "ambulant"],
            "praemie_alt_monatlich": [200, 300],
            "praemie_neu_monatlich": [220, 330],
            "erhoehung_absolut": [20, 30],
            "erhoehung_prozent": [10, 10],
            "alterungsrueckstellung": [5000, 10000],
            "versicherungsdauer_jahre": [5, 10],
        })
        df = lade_csv(csv, "bestand")
        assert "altersgruppe" in df.columns
        assert len(df) == 2

    def test_bestand_fehlende_spalte(self):
        csv = self._make_csv({"versicherten_id": ["V1"], "alter": [30]})
        with pytest.raises(ValueError, match="Fehlende Spalten"):
            lade_csv(csv, "bestand")

    def test_nicht_bestand_kein_check(self):
        csv = self._make_csv({"x": [1], "y": [2]})
        df = lade_csv(csv, "tarife")
        assert list(df.columns) == ["x", "y"]

    def test_altersgruppen_zuordnung(self):
        csv = self._make_csv({
            "versicherten_id": ["V1"],
            "alter": [42],
            "geschlecht": ["M"],
            "tarifwerk": ["Classic"],
            "tarif_id": ["CL-AMB"],
            "tarifart": ["ambulant"],
            "praemie_alt_monatlich": [200],
            "praemie_neu_monatlich": [220],
            "erhoehung_absolut": [20],
            "erhoehung_prozent": [10],
            "alterungsrueckstellung": [5000],
            "versicherungsdauer_jahre": [5],
        })
        df = lade_csv(csv, "bestand")
        assert df.iloc[0]["altersgruppe"] == "40-49"
