"""Tests für services/bestandsanalyse.py"""

import numpy as np
import pandas as pd
import pytest

from services.bestandsanalyse import (
    berechne_hist_daten,
    berechne_interaktive_statistik,
    berechne_kpis,
    berechne_treemap_daten,
    df_hash,
    farb_map_dynamisch,
    formatiere_euro,
    geschlecht_label,
)


# ── geschlecht_label ─────────────────────────────────────────────────────────


class TestGeschlechtLabel:

    @pytest.mark.parametrize("code,erwartet", [
        ("M", "Männlich"),
        ("W", "Weiblich"),
        ("D", "Divers"),
    ])
    def test_bekannte_codes(self, code, erwartet):
        assert geschlecht_label(code) == erwartet

    def test_unbekannter_code(self):
        assert geschlecht_label("X") == "X"

    def test_leerer_string(self):
        assert geschlecht_label("") == ""


# ── farb_map_dynamisch ───────────────────────────────────────────────────────


class TestFarbMapDynamisch:

    def test_grundfall(self):
        df = pd.DataFrame({"typ": ["A", "B", "C"]})
        palette = ["rot", "gruen", "blau"]
        result = farb_map_dynamisch(df, "typ", palette)
        assert result == {"A": "rot", "B": "gruen", "C": "blau"}

    def test_zyklische_palette(self):
        df = pd.DataFrame({"typ": ["A", "B", "C", "D"]})
        palette = ["rot", "gruen"]
        result = farb_map_dynamisch(df, "typ", palette)
        assert result["C"] == "rot"  # Zyklus
        assert result["D"] == "gruen"

    def test_sortierung(self):
        df = pd.DataFrame({"typ": ["C", "A", "B"]})
        palette = ["1", "2", "3"]
        result = farb_map_dynamisch(df, "typ", palette)
        assert list(result.keys()) == ["A", "B", "C"]

    def test_einzelne_kategorie(self):
        df = pd.DataFrame({"typ": ["X", "X", "X"]})
        result = farb_map_dynamisch(df, "typ", ["farbe1"])
        assert result == {"X": "farbe1"}


# ── formatiere_euro ──────────────────────────────────────────────────────────


class TestFormatiereEuro:

    def test_millionen(self):
        result = formatiere_euro(2_500_000)
        assert "Mio" in result
        assert "€" in result

    def test_tausender(self):
        result = formatiere_euro(1_500)
        assert "€" in result
        assert "Mio" not in result

    def test_kleine_betraege(self):
        result = formatiere_euro(42.50)
        assert "42.50" in result

    def test_null(self):
        result = formatiere_euro(0)
        assert "€" in result

    def test_negative_millionen(self):
        result = formatiere_euro(-3_000_000)
        assert "Mio" in result

    def test_negative_tausender(self):
        result = formatiere_euro(-1_500)
        assert "€" in result


# ── df_hash ──────────────────────────────────────────────────────────────────


class TestDfHash:

    def test_leerer_df(self):
        assert df_hash(pd.DataFrame()) == "empty"

    def test_gleiche_daten_gleicher_hash(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        assert df_hash(df) == df_hash(df.copy())

    def test_unterschiedliche_daten_anderer_hash(self):
        df1 = pd.DataFrame({"a": [1, 2, 3]})
        df2 = pd.DataFrame({"a": [4, 5, 6]})
        assert df_hash(df1) != df_hash(df2)

    def test_einzeiler(self):
        df = pd.DataFrame({"a": [42]})
        h = df_hash(df)
        assert isinstance(h, str)
        assert len(h) == 32  # MD5


# ── berechne_kpis ────────────────────────────────────────────────────────────


class TestBerechneKpis:

    def test_grundfall(self, bestand_klein):
        kpis = berechne_kpis(bestand_klein)
        assert kpis["n"] == 6
        assert kpis["praemie_alt_mean"] == pytest.approx(bestand_klein["praemie_alt_monatlich"].mean())
        assert kpis["praemie_neu_mean"] == pytest.approx(bestand_klein["praemie_neu_monatlich"].mean())

    def test_jahresvolumen(self, bestand_klein):
        kpis = berechne_kpis(bestand_klein)
        erwartet = (bestand_klein["erhoehung_absolut"] * 12).sum()
        assert kpis["jahres_vol"] == pytest.approx(erwartet)

    def test_median_vs_mean(self, bestand_klein):
        kpis = berechne_kpis(bestand_klein)
        # Median kann von Mean abweichen bei asymm. Verteilung
        assert isinstance(kpis["erh_pct_median"], float)
        assert isinstance(kpis["erh_pct_mean"], float)

    def test_einzelner_datensatz(self):
        df = pd.DataFrame({
            "praemie_alt_monatlich": [100.0],
            "praemie_neu_monatlich": [120.0],
            "erhoehung_prozent": [20.0],
            "erhoehung_absolut": [20.0],
        })
        kpis = berechne_kpis(df)
        assert kpis["n"] == 1
        assert kpis["erh_pct_mean"] == 20.0
        assert kpis["erh_pct_median"] == 20.0


# ── berechne_treemap_daten ───────────────────────────────────────────────────


class TestBerechneTreemapDaten:

    def test_hierarchie_struktur(self, bestand_mit_altersgruppen):
        result = berechne_treemap_daten(bestand_mit_altersgruppen, "erhoehung_prozent")
        assert "id" in result.columns
        assert "parent" in result.columns
        assert "label" in result.columns
        assert "anzahl" in result.columns
        assert "erh" in result.columns

    def test_wurzelebene_hat_leere_parents(self, bestand_mit_altersgruppen):
        result = berechne_treemap_daten(bestand_mit_altersgruppen, "erhoehung_prozent")
        wurzel = result[result["parent"] == ""]
        assert len(wurzel) > 0
        # Alle Tarifwerke sollten auf der Wurzelebene sein
        tarifwerke = bestand_mit_altersgruppen["tarifwerk"].unique()
        for tw in tarifwerke:
            assert tw in wurzel["id"].values

    def test_anzahl_konsistenz(self, bestand_mit_altersgruppen):
        result = berechne_treemap_daten(bestand_mit_altersgruppen, "erhoehung_prozent")
        wurzel = result[result["parent"] == ""]
        assert wurzel["anzahl"].sum() == len(bestand_mit_altersgruppen)


# ── berechne_interaktive_statistik ───────────────────────────────────────────


class TestBerechneInteraktiveStatistik:

    def test_ohne_gruppierung(self, bestand_klein):
        result = berechne_interaktive_statistik(bestand_klein, tuple())
        assert len(result) == 1
        assert "Versicherte" in result.columns
        assert result.iloc[0]["Versicherte"] == 6

    def test_gruppierung_nach_tarifwerk(self, bestand_klein):
        result = berechne_interaktive_statistik(bestand_klein, ("tarifwerk",))
        assert "Tarifwerk" in result.columns
        assert len(result) == 3  # Classic, Komfort, Premium

    def test_gruppierung_nach_geschlecht(self, bestand_klein):
        result = berechne_interaktive_statistik(bestand_klein, ("geschlecht",))
        assert "Geschlecht" in result.columns
        assert len(result) == 2

    def test_mehrstufige_gruppierung(self, bestand_klein):
        result = berechne_interaktive_statistik(bestand_klein, ("tarifwerk", "geschlecht"))
        assert "Tarifwerk" in result.columns
        assert "Geschlecht" in result.columns

    def test_sortierung_nach_versicherte(self, bestand_klein):
        result = berechne_interaktive_statistik(bestand_klein, ("tarifwerk",))
        versicherte = result["Versicherte"].values
        assert list(versicherte) == sorted(versicherte, reverse=True)

    def test_spalten_vollstaendig(self, bestand_klein):
        result = berechne_interaktive_statistik(bestand_klein, tuple())
        erwartete = [
            "Versicherte", "Ø Prämie alt (€)", "Ø Prämie neu (€)",
            "Ø Erhöhung (%)", "Median Erhöhung (%)", "Ø Erhöhung (€)",
            "Median Erhöhung (€)", "P95 Erhöhung (%)", "P95 Erhöhung (€)",
            "Ø Alter.-Rückst. (€)", "Volumen p.a. (€)",
        ]
        for s in erwartete:
            assert s in result.columns, f"Spalte '{s}' fehlt"

    def test_rundung(self, bestand_klein):
        result = berechne_interaktive_statistik(bestand_klein, ("tarifwerk",))
        for col in result.columns:
            if "(%)" in col:
                # Prozent-Spalten auf 1 Dezimale gerundet
                for v in result[col]:
                    assert round(v, 1) == v


# ── berechne_hist_daten ──────────────────────────────────────────────────────


class TestBerechneHistDaten:

    def test_mit_farb_spalte(self, bestand_klein):
        result = berechne_hist_daten(bestand_klein, "geschlecht", "erhoehung_prozent")
        assert "M" in result
        assert "W" in result
        assert len(result["M"]) == 3
        assert len(result["W"]) == 3

    def test_ohne_farb_spalte(self, bestand_klein):
        result = berechne_hist_daten(bestand_klein, None, "erhoehung_prozent")
        assert "_gesamt" in result
        assert len(result["_gesamt"]) == 6

    def test_leere_farb_spalte_string(self, bestand_klein):
        result = berechne_hist_daten(bestand_klein, "", "erhoehung_prozent")
        assert "_gesamt" in result

    def test_nicht_existente_farb_spalte(self, bestand_klein):
        result = berechne_hist_daten(bestand_klein, "nicht_existent", "erhoehung_prozent")
        assert "_gesamt" in result

    def test_werte_korrekt(self, bestand_klein):
        result = berechne_hist_daten(bestand_klein, None, "erhoehung_absolut")
        np.testing.assert_array_equal(
            sorted(result["_gesamt"]),
            sorted(bestand_klein["erhoehung_absolut"].values),
        )
