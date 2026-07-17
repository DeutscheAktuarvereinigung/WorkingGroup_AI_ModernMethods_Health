"""Tests fuer die Limitierungs-Pipeline mit Mittelquellen."""

import pandas as pd
import pytest

from app.pages.limitierung import erstelle_export_dataframe
from services.limitierungs_pipeline import (
    berechne_limitierung_mit_mittelquellen,
    finanziere_limitierungsergebnis,
)


@pytest.fixture
def bestand_pipeline():
    return pd.DataFrame({
        "versicherten_id": ["V1", "V2"],
        "person_id": ["P1", "P2"],
        "alter": [66, 60],
        "geschlecht": ["M", "W"],
        "tarifwerk": ["Classic", "Komfort"],
        "tarif_id": ["CL-VOLL", "KO-AMB"],
        "tarifart": ["voll", "ambulant"],
        "praemie_alt_monatlich": [100.0, 200.0],
        "praemie_neu_monatlich": [130.0, 220.0],
        "erhoehung_absolut": [30.0, 20.0],
        "erhoehung_prozent": [30.0, 10.0],
        "alterungsrueckstellung": [20_000.0, 10_000.0],
        "versicherungsdauer_jahre": [20, 10],
        "ueberzins_mittel_euro": [1200.0, 0.0],
        "zu10_mittel_euro": [500.0, 999.0],
    })


@pytest.fixture
def bwf_pipeline():
    return pd.DataFrame({
        "tarif_id": ["CL-VOLL", "KO-AMB"],
        "geschlecht": ["M", "W"],
        "alter": [66, 60],
        "barwertfaktor": [10.0, 10.0],
    })


@pytest.fixture
def mittelquellen_pipeline():
    return pd.DataFrame({
        "quelle_id": ["ueberzins", "zu10", "rfb_frei"],
        "name": ["Ueberzins", "ZU10", "Freie RfB"],
        "aktiv": [True, True, True],
        "prioritaet": [1, 2, 3],
        "typ": ["zeilenindividuell", "zeilenindividuell", "global"],
        "betrag_euro": [float("nan"), float("nan"), 1000.0],
        "betrag_spalte": ["ueberzins_mittel_euro", "zu10_mittel_euro", ""],
        "betrag_einheit": ["einmaleinlage", "einmaleinlage", "einmaleinlage"],
        "unterliegt_limitierungsregeln": [False, True, True],
        "einsatzmodus": ["pflicht_vollstaendig", "nur_bedarf_finanzieren", "nur_bedarf_finanzieren"],
        "anwendungsphase": ["vor_regeln", "nach_regeln", "nach_regeln"],
        "filter_spalten": ["", "tarifart|alter", ""],
        "filter_operatoren": ["", "==|>=", ""],
        "filter_werte": ["", "voll|65", ""],
        "fallback_erlaubt": [True, True, True],
    })


def test_berechne_limitierung_mit_mittelquellen_vorab_senkt_regelbedarf(
    bestand_pipeline,
    bwf_pipeline,
    mittelquellen_pipeline,
):
    original = bestand_pipeline.copy(deep=True)
    regeln = [{"ziel_pct": 10.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]

    result = berechne_limitierung_mit_mittelquellen(
        bestand_pipeline,
        bwf_pipeline,
        mittelquellen_pipeline,
        regeln,
        modus="dauerhaft",
        laufzeit_jahre=1,
    )
    res = result["res_mittelverwendung"]

    assert result["bedarf_vor_regelunabhaengigen_mitteln"] == pytest.approx(2400.0)
    assert result["bedarf_nach_regelunabhaengigen_mitteln"] == pytest.approx(1200.0)
    assert result["mittel_regelunabhaengig_einmaleinlage"] == pytest.approx(1200.0)
    assert res["mittel_verwendet_ueberzins"].sum() == pytest.approx(1200.0)
    assert res["mittel_verwendet_zu10"].sum() == pytest.approx(500.0)
    assert res["mittel_verwendet_rfb_frei"].sum() == pytest.approx(700.0)
    assert res["unterdeckung"].sum() == pytest.approx(0.0)
    pd.testing.assert_frame_equal(bestand_pipeline, original)


def test_finanziere_limitierungsergebnis_nutzt_gemischten_bedarf(
    bestand_pipeline,
    bwf_pipeline,
    mittelquellen_pipeline,
):
    regeln = [{"ziel_pct": 10.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
    pipeline = berechne_limitierung_mit_mittelquellen(
        bestand_pipeline,
        bwf_pipeline,
        mittelquellen_pipeline,
        regeln,
        modus="dauerhaft",
        laufzeit_jahre=1,
    )
    res_basis_gemischt = pipeline["res_limitierung_basis"].copy()
    res_basis_gemischt["einmaleinlage"] = res_basis_gemischt["einmaleinlage"] * 0.5

    finanziert = finanziere_limitierungsergebnis(
        pipeline["df_rechenbestand"],
        res_basis_gemischt,
        mittelquellen_pipeline,
    )

    assert finanziert["einmaleinlage"].sum() == pytest.approx(600.0)
    assert finanziert["mittel_verwendet_zu10"].sum() == pytest.approx(500.0)
    assert finanziert["mittel_verwendet_rfb_frei"].sum() == pytest.approx(100.0)
    assert finanziert["mittel_verwendet_ueberzins"].sum() == pytest.approx(1200.0)
    assert finanziert["unterdeckung"].sum() == pytest.approx(0.0)


def test_berechne_limitierung_mit_mittelquellen_personenlimitierung(
    bestand_pipeline,
    bwf_pipeline,
    mittelquellen_pipeline,
):
    regeln = []
    personen_regel = {"ziel_abs": 15.0, "ziel_pct": None}

    result = berechne_limitierung_mit_mittelquellen(
        bestand_pipeline,
        bwf_pipeline,
        mittelquellen_pipeline,
        regeln,
        modus="dauerhaft",
        laufzeit_jahre=1,
        personen_aktiv=True,
        personen_regel=personen_regel,
    )
    res = result["res_mittelverwendung"]

    assert "person_limitiert" in res.columns
    assert res["person_limitiert"].sum() == 2
    assert result["bedarf_nach_regelunabhaengigen_mitteln"] < result["bedarf_vor_regelunabhaengigen_mitteln"]


def test_erstelle_export_dataframe_enthaelt_mittelquellen_spalten(
    bestand_pipeline,
    bwf_pipeline,
    mittelquellen_pipeline,
):
    regeln = [{"ziel_pct": 10.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
    pipeline = berechne_limitierung_mit_mittelquellen(
        bestand_pipeline,
        bwf_pipeline,
        mittelquellen_pipeline,
        regeln,
        modus="dauerhaft",
        laufzeit_jahre=1,
    )

    export = erstelle_export_dataframe(bestand_pipeline, pipeline["res_mittelverwendung"])

    erwartete_spalten = {
        "versicherten_id",
        "tarif_id",
        "einmaleinlage",
        "einmaleinlage_ohne_regelunabhaengige_mittel",
        "einmaleinlage_regelgebunden",
        "mittel_verwendet_ueberzins",
        "mittel_verwendet_zu10",
        "mittel_verwendet_rfb_frei",
        "mittel_regelunabhaengig_einmaleinlage",
        "finanziert_gesamt",
        "unterdeckung",
        "finanzierungsquote",
    }
    assert erwartete_spalten.issubset(export.columns)
    assert export["versicherten_id"].tolist() == bestand_pipeline["versicherten_id"].tolist()
