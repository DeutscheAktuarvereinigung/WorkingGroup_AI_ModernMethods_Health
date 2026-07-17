"""Service-Logik fuer Mittelquellen und Topfverwendung.

Dieses Modul kapselt die fachliche Wirkung von regelunabhaengigen und
regelgebundenen Mittelquellen. Die UI konfiguriert nur Quellen und Reihenfolge;
die Berechnungslogik bleibt hier in der Service-Schicht.
"""

from __future__ import annotations

import logging
import re

import numpy as np
import pandas as pd

from services.data_loader import validiere_mittelquellen_config

logger = logging.getLogger(__name__)

KEY_SPALTEN_BWF = ["tarif_id", "geschlecht", "alter"]


WAHR_WERTE = {"true", "1", "ja", "yes", "wahr"}


def _ist_gesetzt(wert) -> bool:
    """Prueft, ob ein optionales Konfigurationsfeld fachlich befuellt ist."""
    if wert is None or pd.isna(wert):
        return False
    return str(wert).strip() != ""


def _als_bool(wert) -> bool:
    """Konvertiert bool-/CSV-Werte robust in bool."""
    if isinstance(wert, (bool, np.bool_)):
        return bool(wert)
    return str(wert).strip().lower() in WAHR_WERTE


def _split_pipe(wert) -> list[str]:
    """Splittet pipe-getrennte Konfigurationsfelder."""
    if not _ist_gesetzt(wert):
        return []
    return [teil.strip() for teil in str(wert).split("|") if teil.strip()]


def _spaltensuffix(quelle_id: str) -> str:
    """Erzeugt stabile, sichere Spaltensuffixe aus Quelle-IDs."""
    suffix = re.sub(r"[^0-9a-zA-Z_]+", "_", str(quelle_id).strip().lower())
    suffix = re.sub(r"_+", "_", suffix).strip("_")
    if not suffix:
        raise ValueError("Mittelquelle ohne gueltige quelle_id.")
    return suffix


def _aktive_quellen(df_config: pd.DataFrame, regelgebunden: bool) -> pd.DataFrame:
    """Filtert aktive Quellen nach Regelbindung und sortiert nach Prioritaet."""
    config = df_config.copy()
    aktiv = config["aktiv"].map(_als_bool)
    ist_regelgebunden = config["unterliegt_limitierungsregeln"].map(_als_bool)
    result = config[aktiv & (ist_regelgebunden == regelgebunden)].copy()
    return result.sort_values("prioritaet", kind="stable")


def _konvertiere_filter_wert(series: pd.Series, wert: str):
    """Konvertiert einen Filterwert passend zum Spaltentyp."""
    if pd.api.types.is_numeric_dtype(series):
        return float(wert)
    return wert


def _berechtigungsmaske(df: pd.DataFrame, quelle: pd.Series) -> np.ndarray:
    """Wertet die in der Konfiguration hinterlegten Berechtigungsfilter aus."""
    filter_spalten = _split_pipe(quelle.get("filter_spalten"))
    filter_operatoren = _split_pipe(quelle.get("filter_operatoren"))
    filter_werte = _split_pipe(quelle.get("filter_werte"))

    if not filter_spalten:
        return np.ones(len(df), dtype=bool)

    if not (len(filter_spalten) == len(filter_operatoren) == len(filter_werte)):
        raise ValueError(
            f"Mittelquelle '{quelle.get('quelle_id')}' hat inkonsistente Filterdefinitionen."
        )

    maske = np.ones(len(df), dtype=bool)
    for spalte, operator, wert_text in zip(filter_spalten, filter_operatoren, filter_werte):
        if spalte not in df.columns:
            raise ValueError(
                f"Mittelquelle '{quelle.get('quelle_id')}' referenziert fehlende Filterspalte '{spalte}'."
            )

        series = df[spalte]
        operator = operator.strip()
        if operator in {"in", "not in"}:
            werte = [
                _konvertiere_filter_wert(series, teil.strip())
                for teil in str(wert_text).split(",")
                if teil.strip()
            ]
            teilmaske = series.isin(werte).to_numpy()
            if operator == "not in":
                teilmaske = ~teilmaske
        else:
            wert = _konvertiere_filter_wert(series, wert_text)
            if operator == "==":
                teilmaske = (series == wert).to_numpy()
            elif operator == "!=":
                teilmaske = (series != wert).to_numpy()
            elif operator == ">=":
                teilmaske = (series >= wert).to_numpy()
            elif operator == ">":
                teilmaske = (series > wert).to_numpy()
            elif operator == "<=":
                teilmaske = (series <= wert).to_numpy()
            elif operator == "<":
                teilmaske = (series < wert).to_numpy()
            else:
                raise ValueError(
                    f"Mittelquelle '{quelle.get('quelle_id')}' verwendet unbekannten Filteroperator '{operator}'."
                )

        maske &= teilmaske

    return maske


def _barwertfaktoren_je_zeile(df: pd.DataFrame, df_bwf: pd.DataFrame) -> np.ndarray:
    """Ermittelt Barwertfaktoren je Bestandszeile ueber die fachlichen Schluessel."""
    fehlende_keys = [s for s in KEY_SPALTEN_BWF if s not in df.columns]
    if fehlende_keys:
        raise ValueError(f"Bestand: Fehlende BWF-Schluesselspalten: {fehlende_keys}")
    fehlende_bwf = [s for s in KEY_SPALTEN_BWF + ["barwertfaktor"] if s not in df_bwf.columns]
    if fehlende_bwf:
        raise ValueError(f"Barwertfaktoren: Fehlende Spalten: {fehlende_bwf}")

    merged = df[KEY_SPALTEN_BWF].merge(df_bwf, on=KEY_SPALTEN_BWF, how="left")
    if merged["barwertfaktor"].isna().any():
        betroffene = df.loc[merged["barwertfaktor"].isna().to_numpy(), KEY_SPALTEN_BWF].drop_duplicates()
        raise ValueError(
            "Barwertfaktoren-Merge: Fehlende Barwertfaktoren fuer "
            f"{len(betroffene)} eindeutige Kombinationen: {betroffene.head(10).to_dict('records')}"
        )
    return merged["barwertfaktor"].to_numpy(dtype=float)


def _verfuegbare_mittel(quelle: pd.Series, df: pd.DataFrame) -> np.ndarray:
    """Ermittelt verfuegbare Mittel je Zeile oder Quelle in Euro."""
    betrag_spalte = quelle.get("betrag_spalte")
    if _ist_gesetzt(betrag_spalte):
        spalte = str(betrag_spalte)
        if spalte not in df.columns:
            raise ValueError(
                f"Mittelquelle '{quelle.get('quelle_id')}' referenziert fehlende Betragsspalte '{spalte}'."
            )
        return df[spalte].to_numpy(dtype=float)

    betrag_euro = quelle.get("betrag_euro")
    if not _ist_gesetzt(betrag_euro):
        return np.zeros(len(df), dtype=float)
    return np.full(len(df), float(betrag_euro), dtype=float)


def _validiere_bwf_fuer_verwendung(
    quelle_id: str,
    bwf_werte: np.ndarray,
    maske: np.ndarray,
    verfuegbar: np.ndarray,
) -> None:
    """Stellt sicher, dass positive Mittel in Kapitalbasis umgerechnet werden koennen."""
    braucht_bwf = maske & (verfuegbar > 0)
    ungueltig = braucht_bwf & (bwf_werte <= 0)
    if np.any(ungueltig):
        raise ValueError(
            f"Mittelquelle '{quelle_id}' kann wegen fehlender oder nullnaher Barwertfaktoren "
            "nicht in monatliche Entlastung umgerechnet werden."
        )


def wende_regelunabhaengige_mittel_an(
    df_bestand: pd.DataFrame,
    df_bwf: pd.DataFrame,
    df_mittelquellen: pd.DataFrame,
) -> pd.DataFrame:
    """Wendet regelunabhaengige Mittel vor den UI-Limitierungsregeln an.

    Regelunabhaengige Quellen reduzieren die vorhandene Beitragsanpassung bereits
    vor den eigentlichen Limitierungsregeln. Die Funktion gibt einen neuen
    Rechenbestand zurueck und mutiert die Eingabe-DataFrames nicht.
    """
    validiere_mittelquellen_config(df_mittelquellen, df_bestand)
    result = df_bestand.copy()
    n = len(result)
    bwf_werte = _barwertfaktoren_je_zeile(result, df_bwf)
    rest_erhoehung = result["erhoehung_absolut"].to_numpy(dtype=float).copy()

    result["mittel_regelunabhaengig_entlastung_monatlich"] = np.zeros(n, dtype=float)
    result["mittel_regelunabhaengig_einmaleinlage"] = np.zeros(n, dtype=float)

    for _, quelle in _aktive_quellen(df_mittelquellen, regelgebunden=False).iterrows():
        quelle_id = str(quelle["quelle_id"])
        suffix = _spaltensuffix(quelle_id)
        maske = _berechtigungsmaske(result, quelle)
        verfuegbar = _verfuegbare_mittel(quelle, result)
        verfuegbar = np.where(maske, np.maximum(verfuegbar, 0.0), 0.0)
        _validiere_bwf_fuer_verwendung(quelle_id, bwf_werte, maske, verfuegbar)

        if str(quelle["betrag_einheit"]) == "monatlich":
            max_entlastung_monatlich = verfuegbar
        else:
            max_entlastung_monatlich = np.zeros(n, dtype=float)
            gueltig = (bwf_werte > 0) & (verfuegbar > 0)
            max_entlastung_monatlich[gueltig] = verfuegbar[gueltig] / (12.0 * bwf_werte[gueltig])

        entlastung = np.minimum(rest_erhoehung, max_entlastung_monatlich)
        entlastung = np.where(maske, np.maximum(entlastung, 0.0), 0.0)
        verwendung_einmaleinlage = np.round(entlastung * 12.0 * bwf_werte, 2)

        result[f"mittel_entlastung_monatlich_{suffix}"] = np.round(entlastung, 2)
        result[f"mittel_verwendet_{suffix}"] = verwendung_einmaleinlage

        rest_erhoehung = np.maximum(rest_erhoehung - entlastung, 0.0)
        result["mittel_regelunabhaengig_entlastung_monatlich"] += entlastung
        result["mittel_regelunabhaengig_einmaleinlage"] += verwendung_einmaleinlage

        logger.info(
            "Regelunabhaengige Mittelquelle angewendet: %s, Mittel=%.2f, Entlastung=%.2f €/Mon",
            quelle_id,
            float(verwendung_einmaleinlage.sum()),
            float(entlastung.sum()),
        )

    result["erhoehung_absolut_vor_mittel"] = df_bestand["erhoehung_absolut"].to_numpy(dtype=float)
    result["erhoehung_prozent_vor_mittel"] = df_bestand["erhoehung_prozent"].to_numpy(dtype=float)
    result["erhoehung_absolut"] = np.round(rest_erhoehung, 2)
    praemie_alt = result["praemie_alt_monatlich"].to_numpy(dtype=float)
    result["praemie_neu_monatlich"] = np.round(praemie_alt + rest_erhoehung, 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        result["erhoehung_prozent"] = np.round(
            np.where(praemie_alt > 0, rest_erhoehung / praemie_alt * 100.0, 0.0),
            2,
        )
    result["mittel_regelunabhaengig_entlastung_monatlich"] = np.round(
        result["mittel_regelunabhaengig_entlastung_monatlich"], 2
    )
    result["mittel_regelunabhaengig_einmaleinlage"] = np.round(
        result["mittel_regelunabhaengig_einmaleinlage"], 2
    )
    return result


def _verteile_globalen_topf(
    restbedarf: np.ndarray,
    maske: np.ndarray,
    verfuegbar_gesamt: float,
) -> np.ndarray:
    """Verteilt einen globalen/segmentierten Topf proportional auf offenen Bedarf."""
    verwendung = np.zeros(len(restbedarf), dtype=float)
    if verfuegbar_gesamt <= 0:
        return verwendung

    berechtigter_bedarf = np.where(maske, restbedarf, 0.0)
    gesamtbedarf = float(berechtigter_bedarf.sum())
    if gesamtbedarf <= 0:
        return verwendung
    if gesamtbedarf <= verfuegbar_gesamt:
        return berechtigter_bedarf
    return berechtigter_bedarf * (verfuegbar_gesamt / gesamtbedarf)


def _runde_verwendung_ohne_budgetueberschreitung(
    verwendung: np.ndarray,
    verfuegbar_gesamt: float | None,
) -> np.ndarray:
    """Rundet auf Cent, ohne ein globales Quellenbudget zu ueberschreiten."""
    gerundet = np.round(np.maximum(verwendung, 0.0), 2)
    if verfuegbar_gesamt is None:
        return gerundet

    ueberschuss = round(float(gerundet.sum()) - float(verfuegbar_gesamt), 2)
    if ueberschuss <= 0:
        return gerundet

    positive_idx = np.where(gerundet > 0)[0]
    if len(positive_idx) == 0:
        return gerundet

    # Korrigiere Cent-Rundungsdifferenzen deterministisch auf der groessten Position.
    idx = positive_idx[np.argmax(gerundet[positive_idx])]
    gerundet[idx] = round(max(gerundet[idx] - ueberschuss, 0.0), 2)
    return gerundet


def berechne_mittelverwendung(
    df_bestand: pd.DataFrame,
    res_limitierung: pd.DataFrame,
    df_mittelquellen: pd.DataFrame,
    bedarf_spalte: str = "einmaleinlage",
) -> pd.DataFrame:
    """Ordnet regelgebundene Mittelquellen dem Limitierungsbedarf zu.

    Die Limitierungswirkung selbst bleibt unveraendert. Diese Funktion ergaenzt
    nur den Finanzierungsnachweis je Quelle sowie Unterdeckung und Quote.
    """
    validiere_mittelquellen_config(df_mittelquellen, df_bestand)
    if bedarf_spalte not in res_limitierung.columns:
        raise ValueError(f"Limitierungsergebnis: Bedarfsspalte '{bedarf_spalte}' fehlt.")
    if len(df_bestand) != len(res_limitierung):
        raise ValueError("Bestand und Limitierungsergebnis muessen gleich viele Zeilen haben.")

    result = res_limitierung.copy()
    restbedarf = result[bedarf_spalte].to_numpy(dtype=float).copy()
    restbedarf = np.maximum(restbedarf, 0.0)

    for _, quelle in _aktive_quellen(df_mittelquellen, regelgebunden=True).iterrows():
        quelle_id = str(quelle["quelle_id"])
        suffix = _spaltensuffix(quelle_id)
        maske = _berechtigungsmaske(df_bestand, quelle)
        typ = str(quelle["typ"])

        if typ == "zeilenindividuell":
            verfuegbar = _verfuegbare_mittel(quelle, df_bestand)
            verwendung = np.minimum(restbedarf, np.where(maske, verfuegbar, 0.0))
            verfuegbar_gesamt = None
        elif typ in {"global", "segmentiert"}:
            betrag_spalte = quelle.get("betrag_spalte")
            if _ist_gesetzt(betrag_spalte):
                verfuegbar_gesamt = float(np.where(maske, _verfuegbare_mittel(quelle, df_bestand), 0.0).sum())
            else:
                verfuegbar_gesamt = float(quelle["betrag_euro"])
            verwendung = _verteile_globalen_topf(restbedarf, maske, verfuegbar_gesamt)
        else:
            raise ValueError(f"Unbekannter Mittelquellen-Typ: '{typ}'.")

        verwendung = _runde_verwendung_ohne_budgetueberschreitung(verwendung, verfuegbar_gesamt)
        result[f"mittel_verwendet_{suffix}"] = verwendung
        restbedarf = np.maximum(restbedarf - verwendung, 0.0)

        logger.info(
            "Regelgebundene Mittelquelle verwendet: %s, Mittel=%.2f",
            quelle_id,
            float(verwendung.sum()),
        )

    verwendungs_spalten = [c for c in result.columns if c.startswith("mittel_verwendet_")]
    if verwendungs_spalten:
        result["finanziert_gesamt"] = np.round(result[verwendungs_spalten].sum(axis=1), 2)
    else:
        result["finanziert_gesamt"] = 0.0
    result["unterdeckung"] = np.round(np.maximum(result[bedarf_spalte] - result["finanziert_gesamt"], 0.0), 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        result["finanzierungsquote"] = np.round(
            np.where(result[bedarf_spalte] > 0, result["finanziert_gesamt"] / result[bedarf_spalte], 1.0),
            6,
        )
    return result
