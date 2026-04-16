"""Tests für services/optimierung.py"""

import numpy as np
import pandas as pd
import pytest

from services.optimierung import (
    berechne_gitter,
    berechne_optimale_budgetstufen,
    berechne_pareto_front,
    finde_knickpunkt,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def beispiel_daten():
    """Erzeugt synthetische Bestandsdaten für Optimierer-Tests."""
    rng = np.random.default_rng(42)
    n = 200
    praemie_alt = rng.uniform(100, 500, n)
    erh_pct = rng.uniform(5, 40, n)
    erh_abs = praemie_alt * erh_pct / 100.0
    bwf_vals = rng.uniform(5, 20, n)
    return erh_pct, erh_abs, praemie_alt, bwf_vals


@pytest.fixture
def gitter_und_meta(beispiel_daten):
    """Vorberechnetes Gitter für abhängige Tests."""
    erh_pct, erh_abs, praemie_alt, bwf_vals = beispiel_daten
    return berechne_gitter(erh_pct, erh_abs, praemie_alt, bwf_vals)


# ═══════════════════════════════════════════════════════════════════════════════
# berechne_gitter
# ═══════════════════════════════════════════════════════════════════════════════


class TestBerechneGitter:

    def test_ergebnis_spalten(self, gitter_und_meta):
        df_gitter, meta = gitter_und_meta
        assert "pct_cap" in df_gitter.columns
        assert "abs_cap" in df_gitter.columns
        assert "rfb" in df_gitter.columns
        assert "score" in df_gitter.columns
        assert "max_pct" in df_gitter.columns
        assert "max_abs" in df_gitter.columns

    def test_meta_keys(self, gitter_und_meta):
        _, meta = gitter_und_meta
        assert "max_pct_vorher" in meta
        assert "max_abs_vorher" in meta
        assert "umrechnungsfaktor" in meta
        assert "norm_pct_range" in meta
        assert "norm_abs_range" in meta

    def test_rfb_nicht_negativ(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        assert (df_gitter["rfb"] >= 0).all()

    def test_score_nicht_negativ(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        assert (df_gitter["score"] >= -1e-10).all()

    def test_strengerer_deckel_mehr_rfb(self, gitter_und_meta):
        """Strengerer Deckel (niedriger) sollte tendenziell mehr RfB erfordern."""
        df_gitter, _ = gitter_und_meta
        niedrig = df_gitter[df_gitter["pct_cap"] == df_gitter["pct_cap"].min()]
        hoch = df_gitter[df_gitter["pct_cap"] == df_gitter["pct_cap"].max()]
        assert niedrig["rfb"].mean() >= hoch["rfb"].mean()

    def test_gitter_vergroeberung(self):
        """Bei großem Wertebereich wird das Gitter automatisch vergröbert."""
        rng = np.random.default_rng(99)
        n = 100
        praemie_alt = rng.uniform(100, 500, n)
        erh_pct = rng.uniform(5, 95, n)  # Großer Bereich → viele Schritte
        erh_abs = rng.uniform(10, 1900, n)
        bwf_vals = rng.uniform(5, 20, n)
        df_gitter, _ = berechne_gitter(erh_pct, erh_abs, praemie_alt, bwf_vals)
        assert len(df_gitter) <= 5000

    def test_modus_gewichtet(self, beispiel_daten):
        erh_pct, erh_abs, praemie_alt, bwf_vals = beispiel_daten
        df_minmax, _ = berechne_gitter(erh_pct, erh_abs, praemie_alt, bwf_vals, "Ausgewogen (Minmax)")
        df_gewichtet, _ = berechne_gitter(erh_pct, erh_abs, praemie_alt, bwf_vals, "Gewichtet", 0.7)
        # Scores sollten sich unterscheiden
        assert not np.allclose(df_minmax["score"].values, df_gewichtet["score"].values)


# ═══════════════════════════════════════════════════════════════════════════════
# berechne_optimale_budgetstufen
# ═══════════════════════════════════════════════════════════════════════════════


class TestBerechneOptimaleBudgetstufen:

    def test_ergebnis_spalten(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        df_opt = berechne_optimale_budgetstufen(df_gitter, 200, 50_000_000, 5)
        erwartete = {"Budget (Mio. €)", "Opt. %-Deckel", "Opt. €-Deckel",
                     "Max nachher (%)", "Max nachher (€)", "Limitierte",
                     "Anteil lim. (%)", "RfB-Bedarf (Mio. €)", "score"}
        assert erwartete.issubset(set(df_opt.columns))

    def test_budget_aufsteigend(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        df_opt = berechne_optimale_budgetstufen(df_gitter, 200, 50_000_000, 5)
        if len(df_opt) > 1:
            assert (np.diff(df_opt["Budget (Mio. €)"].values) > 0).all()

    def test_score_monoton_steigend(self, gitter_und_meta):
        """Score sollte mit steigendem Budget nicht fallen."""
        df_gitter, _ = gitter_und_meta
        df_opt = berechne_optimale_budgetstufen(df_gitter, 200, 50_000_000, 5)
        if len(df_opt) > 1:
            scores = df_opt["score"].values
            # Monotonie: jeder Score >= vorheriger (mit kleiner Toleranz)
            assert all(scores[i] >= scores[i - 1] - 1e-10 for i in range(1, len(scores)))

    def test_leeres_budget_keine_ergebnisse(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        df_opt = berechne_optimale_budgetstufen(df_gitter, 200, 100, 1)  # 100€ Budget
        assert len(df_opt) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# finde_knickpunkt
# ═══════════════════════════════════════════════════════════════════════════════


class TestFindeKnickpunkt:

    def test_knickpunkt_mit_genuegend_daten(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        df_opt = berechne_optimale_budgetstufen(df_gitter, 200, 100_000_000, 2)
        knick_row, knick_gefunden = finde_knickpunkt(df_opt)
        assert knick_row is not None
        assert isinstance(knick_gefunden, bool)

    def test_knickpunkt_leerer_dataframe(self):
        df_opt = pd.DataFrame()
        knick_row, knick_gefunden = finde_knickpunkt(df_opt)
        assert knick_row is None
        assert knick_gefunden is False

    def test_knickpunkt_wenige_zeilen(self):
        df_opt = pd.DataFrame({
            "Budget (Mio. €)": [5, 10],
            "score": [0.3, 0.6],
        })
        knick_row, knick_gefunden = finde_knickpunkt(df_opt)
        assert knick_row is not None
        assert knick_gefunden is False  # Zu wenig Daten

    def test_grenznutzen_spalte_erzeugt(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        df_opt = berechne_optimale_budgetstufen(df_gitter, 200, 100_000_000, 2)
        finde_knickpunkt(df_opt)
        assert "grenznutzen" in df_opt.columns


# ═══════════════════════════════════════════════════════════════════════════════
# berechne_pareto_front
# ═══════════════════════════════════════════════════════════════════════════════


class TestBerechneParetoFront:

    def test_pareto_nicht_leer(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        median_rfb = df_gitter["rfb"].median()
        pdf = berechne_pareto_front(df_gitter, median_rfb)
        assert len(pdf) > 0

    def test_pareto_dominanz(self, gitter_und_meta):
        """Kein Punkt auf der Pareto-Front darf einen anderen dominieren."""
        df_gitter, _ = gitter_und_meta
        median_rfb = df_gitter["rfb"].median()
        pdf = berechne_pareto_front(df_gitter, median_rfb)
        if len(pdf) > 1:
            # Sortiert nach pct_cap aufsteigend → abs_cap muss strikt fallend sein
            abs_caps = pdf["abs_cap"].values
            assert all(abs_caps[i] > abs_caps[i + 1] - 1e-10 for i in range(len(abs_caps) - 1))

    def test_pareto_leeres_budget(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        pdf = berechne_pareto_front(df_gitter, 0)
        # Bei Budget 0 könnte es leer sein oder Fallback greifen
        assert isinstance(pdf, pd.DataFrame)

    def test_pareto_sehr_hohes_budget(self, gitter_und_meta):
        df_gitter, _ = gitter_und_meta
        pdf = berechne_pareto_front(df_gitter, 1e12)
        assert isinstance(pdf, pd.DataFrame)
