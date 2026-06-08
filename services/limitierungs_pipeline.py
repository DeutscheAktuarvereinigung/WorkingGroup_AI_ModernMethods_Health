"""Orchestrierung der Limitierungsrechnung mit Mittelquellen.

Die bestehende Limitierungs-Kernlogik bleibt in ``services.limitierung``. Dieses
Modul verbindet sie mit der Mittelquellen-Logik aus ``services.mittelverwendung``:
regelunabhaengige Quellen wirken vor den UI-Regeln, regelgebundene Quellen
finanzieren anschliessend den entstandenen Bedarf.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from services.limitierung import berechne_limitierung, berechne_limitierung_person
from services.mittelverwendung import (
    berechne_mittelverwendung,
    wende_regelunabhaengige_mittel_an,
)

logger = logging.getLogger(__name__)

REGELUNABHAENGIGE_TRACE_SPALTEN = [
    "mittel_regelunabhaengig_entlastung_monatlich",
    "mittel_regelunabhaengig_einmaleinlage",
    "erhoehung_absolut_vor_mittel",
    "erhoehung_prozent_vor_mittel",
]


def _berechne_ui_limitierung(
    df_bestand: pd.DataFrame,
    df_bwf: pd.DataFrame,
    regeln: list[dict[str, Any]],
    modus: str,
    laufzeit_jahre: int,
    personen_aktiv: bool,
    personen_regel: dict[str, Any] | None,
    reihenfolge: str,
    verteilungsmodus: str,
) -> pd.DataFrame:
    """Berechnet die bestehende UI-Limitierung mit optionaler Personenebene."""
    if personen_aktiv:
        return berechne_limitierung_person(
            df_bestand,
            df_bwf,
            regeln,
            personen_regel or {},
            modus,
            laufzeit_jahre,
            reihenfolge=reihenfolge,
            verteilungsmodus=verteilungsmodus,
        )
    return berechne_limitierung(df_bestand, df_bwf, regeln, modus, laufzeit_jahre)


def _ergaenze_regelunabhaengige_trace_spalten(
    result: pd.DataFrame,
    df_rechenbestand: pd.DataFrame,
) -> pd.DataFrame:
    """Fuegt Nachweisspalten der Vorab-Mittelwirkung additiv zum Ergebnis hinzu."""
    erweitert = result.copy()
    trace_spalten = [
        c for c in df_rechenbestand.columns
        if c in REGELUNABHAENGIGE_TRACE_SPALTEN
        or c.startswith("mittel_entlastung_monatlich_")
        or c.startswith("mittel_verwendet_")
    ]
    for spalte in trace_spalten:
        if spalte not in erweitert.columns:
            erweitert[spalte] = df_rechenbestand[spalte].to_numpy()
    return erweitert


def finanziere_limitierungsergebnis(
    df_rechenbestand: pd.DataFrame,
    res_limitierung_basis: pd.DataFrame,
    df_mittelquellen: pd.DataFrame,
    bedarf_spalte: str = "einmaleinlage",
) -> pd.DataFrame:
    """Finanziert ein Limitierungsergebnis und erhaelt Vorab-Mittel-Trace.

    Diese Funktion ist insbesondere fuer die Befristungsmischung nutzbar: Die UI
    kann eine Kopie von ``res_limitierung_basis`` mit gemischter
    ``einmaleinlage`` uebergeben; die regelgebundenen Quellen werden dann erneut
    konsistent auf diesen Bedarf allokiert.
    """
    finanziert = berechne_mittelverwendung(
        df_rechenbestand,
        res_limitierung_basis,
        df_mittelquellen,
        bedarf_spalte=bedarf_spalte,
    )
    return _ergaenze_regelunabhaengige_trace_spalten(finanziert, df_rechenbestand)


def berechne_limitierung_mit_mittelquellen(
    df_bestand: pd.DataFrame,
    df_bwf: pd.DataFrame,
    df_mittelquellen: pd.DataFrame,
    regeln: list[dict[str, Any]],
    modus: str,
    laufzeit_jahre: int,
    personen_aktiv: bool = False,
    personen_regel: dict[str, Any] | None = None,
    reihenfolge: str = "tarif_zuerst",
    verteilungsmodus: str = "proportional",
) -> dict[str, Any]:
    """Berechnet die vollstaendige Limitierungs-Pipeline mit Mittelquellen.

    Reihenfolge:
    1. Regelunabhaengige Quellen reduzieren den Rechenbestand vor den UI-Regeln.
    2. Die bestehende Tarif-/Personen-Limitierung wird auf diesen Rechenbestand angewendet.
    3. Regelgebundene Quellen finanzieren den resultierenden Bedarf.

    Returns:
        dict mit ``df_rechenbestand``, ``res_limitierung_basis``,
        ``res_mittelverwendung`` und aggregierten Bedarf-/Mittelkennzahlen.
    """
    logger.info(
        "Starte Limitierungs-Pipeline mit Mittelquellen: %d Versicherte, %d Quellen",
        len(df_bestand), len(df_mittelquellen),
    )

    df_rechenbestand = wende_regelunabhaengige_mittel_an(
        df_bestand,
        df_bwf,
        df_mittelquellen,
    )

    res_ohne_vorab = _berechne_ui_limitierung(
        df_bestand,
        df_bwf,
        regeln,
        modus,
        laufzeit_jahre,
        personen_aktiv,
        personen_regel,
        reihenfolge,
        verteilungsmodus,
    )
    res_basis = _berechne_ui_limitierung(
        df_rechenbestand,
        df_bwf,
        regeln,
        modus,
        laufzeit_jahre,
        personen_aktiv,
        personen_regel,
        reihenfolge,
        verteilungsmodus,
    )

    res_finanziert = finanziere_limitierungsergebnis(
        df_rechenbestand,
        res_basis,
        df_mittelquellen,
    )
    res_finanziert["einmaleinlage_ohne_regelunabhaengige_mittel"] = res_ohne_vorab[
        "einmaleinlage"
    ].to_numpy()
    res_finanziert["einmaleinlage_regelgebunden"] = res_basis["einmaleinlage"].to_numpy()

    bedarf_vor_vorab = float(res_ohne_vorab["einmaleinlage"].sum())
    bedarf_nach_vorab = float(res_basis["einmaleinlage"].sum())
    regelunabhaengige_mittel = float(
        df_rechenbestand.get(
            "mittel_regelunabhaengig_einmaleinlage",
            pd.Series(np.zeros(len(df_rechenbestand))),
        ).sum()
    )
    regelgebunden_finanziert = float(res_finanziert.get("finanziert_gesamt", pd.Series(dtype=float)).sum())
    unterdeckung = float(res_finanziert.get("unterdeckung", pd.Series(dtype=float)).sum())

    logger.info(
        "Limitierungs-Pipeline abgeschlossen: Bedarf vor Vorab=%.2f Mio. EUR, "
        "nach Vorab=%.2f Mio. EUR, regelgebunden finanziert=%.2f Mio. EUR",
        bedarf_vor_vorab / 1e6,
        bedarf_nach_vorab / 1e6,
        regelgebunden_finanziert / 1e6,
    )

    return {
        "df_rechenbestand": df_rechenbestand,
        "res_limitierung_ohne_regelunabhaengige_mittel": res_ohne_vorab,
        "res_limitierung_basis": res_basis,
        "res_mittelverwendung": res_finanziert,
        "bedarf_vor_regelunabhaengigen_mitteln": bedarf_vor_vorab,
        "bedarf_nach_regelunabhaengigen_mitteln": bedarf_nach_vorab,
        "mittel_regelunabhaengig_einmaleinlage": regelunabhaengige_mittel,
        "mittel_regelgebunden_finanziert": regelgebunden_finanziert,
        "unterdeckung": unterdeckung,
    }
