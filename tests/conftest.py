"""Shared fixtures für alle Service-Tests."""

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def bestand_klein():
    """Kleiner Testbestand mit 6 Versicherten – deckt verschiedene Tarife, Geschlechter und Alter ab."""
    return pd.DataFrame({
        "versicherten_id": ["V001", "V002", "V003", "V004", "V005", "V006"],
        "alter": [30, 45, 60, 25, 70, 50],
        "geschlecht": ["M", "W", "M", "W", "M", "W"],
        "tarifwerk": ["Classic", "Classic", "Komfort", "Komfort", "Premium", "Premium"],
        "tarif_id": ["CL-AMB", "CL-STAT", "KO-AMB", "KO-STAT", "PR-AMB", "PR-STAT"],
        "tarifart": ["ambulant", "stationaer", "ambulant", "stationaer", "ambulant", "stationaer"],
        "praemie_alt_monatlich": [200.0, 350.0, 180.0, 400.0, 150.0, 300.0],
        "praemie_neu_monatlich": [260.0, 455.0, 216.0, 480.0, 165.0, 345.0],
        "erhoehung_absolut": [60.0, 105.0, 36.0, 80.0, 15.0, 45.0],
        "erhoehung_prozent": [30.0, 30.0, 20.0, 20.0, 10.0, 15.0],
        "alterungsrueckstellung": [5000.0, 15000.0, 3000.0, 20000.0, 25000.0, 18000.0],
        "versicherungsdauer_jahre": [5, 15, 3, 8, 30, 20],
    })


@pytest.fixture
def bestand_mit_altersgruppen(bestand_klein):
    """Bestand mit Altersgruppen-Spalte."""
    from services.data_loader import erzeuge_altersgruppen
    grenzen, labels = erzeuge_altersgruppen(bestand_klein)
    bestand_klein["altersgruppe"] = pd.cut(
        bestand_klein["alter"], bins=grenzen, right=False, labels=labels,
    ).astype(str)
    return bestand_klein


@pytest.fixture
def tarife():
    """Tarifstammdaten für Tests."""
    return pd.DataFrame({
        "tarif_id": ["CL-AMB", "CL-STAT", "KO-AMB", "KO-STAT", "PR-AMB", "PR-STAT"],
        "rechnungszins": [0.025, 0.025, 0.0175, 0.0175, 0.01, 0.01],
    })


@pytest.fixture
def ausscheideordnung(tarife):
    """Vereinfachte Ausscheideordnung für Tests (Alter 0–100)."""
    rows = []
    for _, tarif in tarife.iterrows():
        tid = tarif["tarif_id"]
        for geschl in ["M", "W"]:
            for alter in range(101):
                qx = min(0.001 * np.exp(0.05 * alter), 1.0)
                storno = max(0.005 * np.exp(-0.03 * alter), 0.001)
                rows.append({
                    "tarif_id": tid,
                    "geschlecht": geschl,
                    "alter": alter,
                    "qx": round(qx, 8),
                    "storno": round(storno, 6),
                })
    return pd.DataFrame(rows)


@pytest.fixture
def barwertfaktoren(ausscheideordnung, tarife):
    """Vorberechnete Barwertfaktoren."""
    from services.limitierung import berechne_barwertfaktoren
    return berechne_barwertfaktoren(ausscheideordnung, tarife)
