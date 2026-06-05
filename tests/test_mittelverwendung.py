"""Tests fuer services/mittelverwendung.py"""

import pandas as pd
import pytest

from services.mittelverwendung import (
    berechne_mittelverwendung,
    wende_regelunabhaengige_mittel_an,
)


@pytest.fixture
def bestand_mittel():
    return pd.DataFrame({
        "versicherten_id": ["V1", "V2", "V3", "V4"],
        "alter": [66, 62, 70, 45],
        "geschlecht": ["M", "W", "M", "W"],
        "tarifwerk": ["Classic", "Komfort", "Classic", "Premium"],
        "tarif_id": ["CL-VOLL", "KO-AMB", "CL-AMB", "PR-VOLL"],
        "tarifart": ["voll", "ambulant", "ambulant", "voll"],
        "praemie_alt_monatlich": [500.0, 200.0, 300.0, 250.0],
        "praemie_neu_monatlich": [600.0, 230.0, 360.0, 275.0],
        "erhoehung_absolut": [100.0, 30.0, 60.0, 25.0],
        "erhoehung_prozent": [20.0, 15.0, 20.0, 10.0],
        "alterungsrueckstellung": [30000.0, 10000.0, 20000.0, 8000.0],
        "versicherungsdauer_jahre": [20, 8, 25, 4],
        "ueberzins_mittel_euro": [1200.0, 600.0, 0.0, 3000.0],
        "zu10_mittel_euro": [500.0, 999.0, 400.0, 700.0],
    })


@pytest.fixture
def bwf_mittel(bestand_mittel):
    return pd.DataFrame({
        "tarif_id": bestand_mittel["tarif_id"],
        "geschlecht": bestand_mittel["geschlecht"],
        "alter": bestand_mittel["alter"],
        "barwertfaktor": [10.0, 5.0, 8.0, 6.0],
    })


@pytest.fixture
def mittelquellen_config():
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


def test_wende_regelunabhaengige_mittel_an_ueberzins_reduziert_vor_regeln(
    bestand_mittel, bwf_mittel, mittelquellen_config,
):
    original = bestand_mittel.copy(deep=True)

    result = wende_regelunabhaengige_mittel_an(bestand_mittel, bwf_mittel, mittelquellen_config)

    # Ueberzins: 1200 / (12 * 10) = 10 €/Mon, 600 / (12 * 5) = 10 €/Mon,
    # V3 hat keine Mittel, V4 wird auf maximal vorhandene 25 €/Mon begrenzt.
    assert result["erhoehung_absolut"].tolist() == pytest.approx([90.0, 20.0, 60.0, 0.0])
    assert result["mittel_entlastung_monatlich_ueberzins"].tolist() == pytest.approx([10.0, 10.0, 0.0, 25.0])
    assert result["mittel_verwendet_ueberzins"].tolist() == pytest.approx([1200.0, 600.0, 0.0, 1800.0])
    pd.testing.assert_frame_equal(bestand_mittel, original)


def test_wende_regelunabhaengige_mittel_an_ohne_ui_regel_wirkt(
    bestand_mittel, bwf_mittel, mittelquellen_config,
):
    result = wende_regelunabhaengige_mittel_an(bestand_mittel, bwf_mittel, mittelquellen_config)

    assert result["mittel_regelunabhaengig_entlastung_monatlich"].sum() == pytest.approx(45.0)
    assert result["erhoehung_absolut"].sum() < bestand_mittel["erhoehung_absolut"].sum()


def test_wende_regelunabhaengige_mittel_an_fehlender_bwf_fehler(
    bestand_mittel, bwf_mittel, mittelquellen_config,
):
    bwf_unvollstaendig = bwf_mittel.iloc[1:].copy()

    with pytest.raises(ValueError, match="Barwertfaktoren-Merge"):
        wende_regelunabhaengige_mittel_an(bestand_mittel, bwf_unvollstaendig, mittelquellen_config)


def test_berechne_mittelverwendung_zu10_nur_voll_ab_65(bestand_mittel, mittelquellen_config):
    res_limitierung = pd.DataFrame({"einmaleinlage": [800.0, 800.0, 800.0, 800.0]})

    result = berechne_mittelverwendung(bestand_mittel, res_limitierung, mittelquellen_config)

    # Nur V1 ist voll und >= 65. V4 ist voll, aber zu jung.
    assert result["mittel_verwendet_zu10"].tolist() == pytest.approx([500.0, 0.0, 0.0, 0.0])
    assert result["finanziert_gesamt"].sum() <= res_limitierung["einmaleinlage"].sum()


def test_berechne_mittelverwendung_fallback_globaler_topf_deckt_rest(bestand_mittel, mittelquellen_config):
    res_limitierung = pd.DataFrame({"einmaleinlage": [800.0, 800.0, 800.0, 800.0]})

    result = berechne_mittelverwendung(bestand_mittel, res_limitierung, mittelquellen_config)

    assert result["mittel_verwendet_rfb_frei"].sum() == pytest.approx(1000.0)
    assert result["finanziert_gesamt"].sum() == pytest.approx(1500.0)
    assert result["unterdeckung"].sum() == pytest.approx(1700.0)


def test_berechne_mittelverwendung_globaler_topf_proportional_bei_unterdeckung(bestand_mittel, mittelquellen_config):
    cfg = mittelquellen_config.copy()
    cfg.loc[cfg["quelle_id"] == "zu10", "aktiv"] = False
    cfg.loc[cfg["quelle_id"] == "rfb_frei", "betrag_euro"] = 400.0
    res_limitierung = pd.DataFrame({"einmaleinlage": [100.0, 300.0, 600.0, 1000.0]})

    result = berechne_mittelverwendung(bestand_mittel, res_limitierung, cfg)

    # Gesamtbedarf 2.000, globaler Topf 400 -> proportionaler Faktor 20%.
    assert result["mittel_verwendet_rfb_frei"].tolist() == pytest.approx([20.0, 60.0, 120.0, 200.0])
    assert result["unterdeckung"].sum() == pytest.approx(1600.0)


def test_berechne_mittelverwendung_fehlende_bedarfsspalte_fehler(bestand_mittel, mittelquellen_config):
    res_limitierung = pd.DataFrame({"bedarf": [1.0, 2.0, 3.0, 4.0]})

    with pytest.raises(ValueError, match="Bedarfsspalte"):
        berechne_mittelverwendung(bestand_mittel, res_limitierung, mittelquellen_config)
