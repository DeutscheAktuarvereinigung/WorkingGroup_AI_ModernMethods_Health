"""Tests für services/data_loader.py"""

import io

import numpy as np
import pandas as pd
import pytest

from services.data_loader import erzeuge_altersgruppen, lade_csv, _validiere_bestand


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

    def _bestand_daten(self, **overrides):
        """Erzeugt gültige Bestandsdaten mit optionalen Overrides."""
        daten = {
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
        }
        daten.update(overrides)
        return daten

    def test_bestand_erfolgreich(self):
        csv = self._make_csv(self._bestand_daten())
        df, warnungen = lade_csv(csv, "bestand")
        assert "altersgruppe" in df.columns
        assert len(df) == 2
        assert isinstance(warnungen, list)

    def test_bestand_fehlende_spalte(self):
        csv = self._make_csv({"versicherten_id": ["V1"], "alter": [30]})
        with pytest.raises(ValueError, match="Fehlende Spalten"):
            lade_csv(csv, "bestand")

    def test_nicht_bestand_kein_check(self):
        csv = self._make_csv({"x": [1], "y": [2]})
        df, warnungen = lade_csv(csv, "sonstige")
        assert list(df.columns) == ["x", "y"]
        assert warnungen == []

    def test_altersgruppen_zuordnung(self):
        csv = self._make_csv(self._bestand_daten(
            versicherten_id=["V1"], alter=[42], geschlecht=["M"],
            tarifwerk=["Classic"], tarif_id=["CL-AMB"], tarifart=["ambulant"],
            praemie_alt_monatlich=[200], praemie_neu_monatlich=[220],
            erhoehung_absolut=[20], erhoehung_prozent=[10],
            alterungsrueckstellung=[5000], versicherungsdauer_jahre=[5],
        ))
        df, _ = lade_csv(csv, "bestand")
        assert df.iloc[0]["altersgruppe"] == "40-49"


# ── Datenvalidierung ────────────────────────────────────────────────────────


class TestValidierung:

    def _bestand_df(self, **overrides):
        daten = {
            "versicherten_id": ["V1", "V2"],
            "alter": [30, 50],
            "geschlecht": ["M", "W"],
            "tarifwerk": ["Classic", "Komfort"],
            "tarif_id": ["CL-AMB", "KO-AMB"],
            "tarifart": ["ambulant", "ambulant"],
            "praemie_alt_monatlich": [200.0, 300.0],
            "praemie_neu_monatlich": [220.0, 330.0],
            "erhoehung_absolut": [20.0, 30.0],
            "erhoehung_prozent": [10.0, 10.0],
            "alterungsrueckstellung": [5000.0, 10000.0],
            "versicherungsdauer_jahre": [5, 10],
        }
        daten.update(overrides)
        return pd.DataFrame(daten)

    def test_gueltiger_bestand_keine_fehler(self):
        df = self._bestand_df()
        warnungen = _validiere_bestand(df)
        assert isinstance(warnungen, list)

    def test_nicht_numerische_spalte(self):
        df = self._bestand_df(alter=["dreissig", "fuenfzig"])
        with pytest.raises(ValueError, match="numerisch"):
            _validiere_bestand(df)

    def test_nan_in_kritischer_spalte(self):
        df = self._bestand_df(alter=[30, np.nan])
        with pytest.raises(ValueError, match="fehlende Werte"):
            _validiere_bestand(df)

    def test_alter_ausserhalb_bereich(self):
        df = self._bestand_df(alter=[30, 150])
        with pytest.raises(ValueError, match="alter"):
            _validiere_bestand(df)

    def test_negative_praemie(self):
        df = self._bestand_df(praemie_alt_monatlich=[-100.0, 300.0])
        with pytest.raises(ValueError, match="praemie_alt_monatlich"):
            _validiere_bestand(df)

    def test_negative_praemie_neu(self):
        df = self._bestand_df(praemie_neu_monatlich=[220.0, -10.0])
        with pytest.raises(ValueError, match="praemie_neu_monatlich"):
            _validiere_bestand(df)

    def test_negative_versicherungsdauer(self):
        df = self._bestand_df(versicherungsdauer_jahre=[5, -1])
        with pytest.raises(ValueError, match="versicherungsdauer_jahre"):
            _validiere_bestand(df)

    def test_duplikate_warnung(self):
        df = self._bestand_df(versicherten_id=["V1", "V1"])
        warnungen = _validiere_bestand(df)
        assert any("doppelte" in w for w in warnungen)

    def test_unbekanntes_geschlecht_warnung(self):
        df = self._bestand_df(geschlecht=["M", "X"])
        warnungen = _validiere_bestand(df)
        assert any("Geschlechts-Codes" in w for w in warnungen)

    def test_negative_alterungsrueckstellung_warnung(self):
        df = self._bestand_df(alterungsrueckstellung=[-100.0, 10000.0])
        warnungen = _validiere_bestand(df)
        assert any("alterungsrueckstellung" in w for w in warnungen)

    def test_inkonsistente_erhoehung_warnung(self):
        df = self._bestand_df(
            praemie_alt_monatlich=[200.0, 300.0],
            praemie_neu_monatlich=[220.0, 330.0],
            erhoehung_absolut=[99.0, 30.0],  # V1: 99 statt 20
        )
        warnungen = _validiere_bestand(df)
        assert any("erhoehung_absolut" in w for w in warnungen)

    def test_tarife_fehlende_spalte(self):
        csv_buf = io.StringIO()
        pd.DataFrame({"nur_eine_spalte": [1]}).to_csv(csv_buf, sep=";", index=False)
        csv_buf.seek(0)
        with pytest.raises(ValueError, match="Tarife.*Fehlende Spalten"):
            lade_csv(csv_buf, "tarife")

    def test_ao_fehlende_spalte(self):
        csv_buf = io.StringIO()
        pd.DataFrame({"nur_eine_spalte": [1]}).to_csv(csv_buf, sep=";", index=False)
        csv_buf.seek(0)
        with pytest.raises(ValueError, match="Ausscheideordnung.*Fehlende Spalten"):
            lade_csv(csv_buf, "ao")


# ── person_id Validierung ────────────────────────────────────────────────────


class TestPersonIdValidierung:

    def _bestand_df(self, **overrides):
        daten = {
            "versicherten_id": ["V1", "V2", "V3"],
            "person_id": ["P1", "P1", "P2"],
            "alter": [45, 45, 30],
            "geschlecht": ["M", "M", "W"],
            "tarifwerk": ["Classic", "Classic", "Komfort"],
            "tarif_id": ["CL-AMB", "CL-STAT", "KO-AMB"],
            "tarifart": ["ambulant", "stationaer", "ambulant"],
            "praemie_alt_monatlich": [200.0, 350.0, 180.0],
            "praemie_neu_monatlich": [260.0, 455.0, 216.0],
            "erhoehung_absolut": [60.0, 105.0, 36.0],
            "erhoehung_prozent": [30.0, 30.0, 20.0],
            "alterungsrueckstellung": [5000.0, 15000.0, 3000.0],
            "versicherungsdauer_jahre": [5, 15, 3],
        }
        daten.update(overrides)
        return pd.DataFrame(daten)

    def test_konsistente_person_id_keine_warnung(self):
        """Gleiche Demographie pro person_id → keine Warnung."""
        df = self._bestand_df()
        warnungen = _validiere_bestand(df)
        assert not any("person_id" in w for w in warnungen)

    def test_inkonsistentes_alter_warnung(self):
        """Verschiedene Alter innerhalb einer person_id → Warnung."""
        df = self._bestand_df(alter=[45, 50, 30])  # P1 hat Alter 45 und 50
        warnungen = _validiere_bestand(df)
        assert any("inkonsistente Demographie" in w for w in warnungen)

    def test_inkonsistentes_geschlecht_warnung(self):
        """Verschiedenes Geschlecht innerhalb einer person_id → Warnung."""
        df = self._bestand_df(geschlecht=["M", "W", "W"])  # P1 hat M und W
        warnungen = _validiere_bestand(df)
        assert any("inkonsistente Demographie" in w for w in warnungen)

    def test_bestand_ohne_person_id_kein_fehler(self):
        """Bestand ohne person_id wird problemlos validiert."""
        df = self._bestand_df()
        df = df.drop(columns=["person_id"])
        warnungen = _validiere_bestand(df)
        # Keine person_id-bezogene Warnung
        assert not any("person_id" in w for w in warnungen)

    def test_nan_in_person_id_warnung(self):
        """NaN-Werte in person_id → Warnung."""
        df = self._bestand_df(person_id=["P1", None, "P2"])
        warnungen = _validiere_bestand(df)
        assert any("person_id" in w and "fehlende" in w for w in warnungen)
