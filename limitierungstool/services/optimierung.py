"""
RfB-Optimierer — Gittersuche nach optimaler Deckel-Kombination.

Findet für jede Budget-Stufe die beste Kombination aus prozentualem und
absolutem Erhöhungsdeckel. Identifiziert den Knickpunkt, ab dem
zusätzliches Budget kaum noch Spitzenreduktion bringt.
"""

import logging

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter1d

logger = logging.getLogger(__name__)


def berechne_gitter(
    erh_pct: np.ndarray,
    erh_abs: np.ndarray,
    praemie_alt: np.ndarray,
    bwf_vals: np.ndarray,
    opt_modus: str = "Ausgewogen (Minmax)",
    opt_gewicht_pct: float = 0.5,
) -> tuple[pd.DataFrame, dict]:
    """
    Baut ein Gitter aus (%-Deckel, €-Deckel)-Kombinationen auf, bewertet jede
    und gibt das Ergebnis inkl. Normalisierungsparametern zurück.

    Args:
        erh_pct: Prozentuale Erhöhungen je Versichertem.
        erh_abs: Absolute Erhöhungen (€/Mon) je Versichertem.
        praemie_alt: Alte Prämien je Versichertem.
        bwf_vals: Barwertfaktoren je Versichertem.
        opt_modus: "Ausgewogen (Minmax)" oder "Gewichtet".
        opt_gewicht_pct: Gewicht des prozentualen Scores (nur bei Gewichtet).

    Returns:
        (df_gitter, meta):
            df_gitter mit Spalten pct_cap, abs_cap, rfb, n_lim, max_pct, max_abs, score.
            meta-Dict mit max_pct_vorher, max_abs_vorher, norm_pct_range,
            norm_abs_range, umrechnungsfaktor.
    """
    pct_p50 = np.percentile(erh_pct, 50)
    pct_max_data = erh_pct.max()
    abs_p50 = np.percentile(erh_abs, 50)
    abs_max_data = erh_abs.max()

    pct_schritte = np.arange(
        max(np.floor(pct_p50), 5),
        min(np.ceil(pct_max_data) + 1, 100),
        0.5,
    )
    abs_schritte = np.arange(
        max(np.floor(abs_p50 / 5) * 5, 10),
        min(np.ceil(abs_max_data / 5) * 5 + 1, 2000),
        5.0,
    )

    # Automatisch vergröbern falls > 5000 Kombis
    schritt_pct, schritt_abs = 0.5, 5.0
    while len(pct_schritte) * len(abs_schritte) > 5000:
        schritt_pct *= 2
        schritt_abs *= 2
        pct_schritte = np.arange(pct_schritte[0], pct_schritte[-1] + 1, schritt_pct)
        abs_schritte = np.arange(abs_schritte[0], abs_schritte[-1] + 1, schritt_abs)

    logger.info(
        "Optimierer-Gitter: %d pct × %d abs = %d Kombinationen",
        len(pct_schritte), len(abs_schritte),
        len(pct_schritte) * len(abs_schritte),
    )

    max_pct_vorher = erh_pct.max()
    max_abs_vorher = erh_abs.max()
    best_pct = pct_schritte.min()
    best_abs = abs_schritte.min()
    norm_pct_range = max(max_pct_vorher - best_pct, 1)
    norm_abs_range = max(max_abs_vorher - best_abs, 1)
    umrechnungsfaktor = norm_abs_range / norm_pct_range

    # Gitter-Berechnung
    gitter_ergebnisse = []
    for pc in pct_schritte:
        erh_pct_cap = np.minimum(erh_pct, pc)
        erh_abs_aus_pct = praemie_alt * erh_pct_cap / 100.0
        for ac in abs_schritte:
            erh_abs_cap = np.minimum(erh_abs, ac)
            erh_abs_final = np.minimum(erh_abs_cap, erh_abs_aus_pct)
            erh_pct_final = np.where(
                praemie_alt > 0,
                erh_abs_final / praemie_alt * 100.0, 0.0,
            )

            diff = np.maximum(erh_abs - erh_abs_final, 0)
            rfb = (diff * 12 * bwf_vals).sum()
            n_lim = (diff > 0.01).sum()

            gitter_ergebnisse.append({
                "pct_cap": pc, "abs_cap": ac,
                "rfb": rfb, "n_lim": n_lim,
                "max_pct": erh_pct_final.max(),
                "max_abs": erh_abs_final.max(),
            })

    df_gitter = pd.DataFrame(gitter_ergebnisse)

    # Score berechnen
    if "Minmax" in opt_modus:
        df_gitter["score"] = np.minimum(
            (max_pct_vorher - df_gitter["max_pct"]) / norm_pct_range,
            (max_abs_vorher - df_gitter["max_abs"]) / norm_abs_range,
        )
    else:
        w_pct = opt_gewicht_pct
        w_abs = 1.0 - w_pct
        df_gitter["score"] = (
            w_pct * (max_pct_vorher - df_gitter["max_pct"]) / norm_pct_range
            + w_abs * (max_abs_vorher - df_gitter["max_abs"]) / norm_abs_range
        )

    meta = {
        "max_pct_vorher": max_pct_vorher,
        "max_abs_vorher": max_abs_vorher,
        "norm_pct_range": norm_pct_range,
        "norm_abs_range": norm_abs_range,
        "umrechnungsfaktor": umrechnungsfaktor,
    }
    return df_gitter, meta


def berechne_optimale_budgetstufen(
    df_gitter: pd.DataFrame,
    n_versicherte: int,
    budget_max: float,
    schrittweite_mio: float,
) -> pd.DataFrame:
    """
    Findet für jede Budget-Stufe die Deckel-Kombination mit dem höchsten Score.

    Args:
        df_gitter: Gitter-DataFrame aus berechne_gitter().
        n_versicherte: Anzahl Versicherte (für Anteilsberechnung).
        budget_max: Maximales Budget in Euro.
        schrittweite_mio: Schrittweite in Mio. Euro.

    Returns:
        DataFrame mit einer Zeile pro Budget-Stufe.
    """
    budget_stufen = np.arange(
        schrittweite_mio * 1e6,
        budget_max + 1,
        schrittweite_mio * 1e6,
    )

    opt_ergebnisse = []
    for b in budget_stufen:
        machbar = df_gitter[df_gitter["rfb"] <= b]
        if len(machbar) == 0:
            continue
        best = machbar.loc[machbar["score"].idxmax()]
        opt_ergebnisse.append({
            "Budget (Mio. €)": b / 1e6,
            "Opt. %-Deckel": best["pct_cap"],
            "Opt. €-Deckel": best["abs_cap"],
            "Max nachher (%)": best["max_pct"],
            "Max nachher (€)": best["max_abs"],
            "Limitierte": int(best["n_lim"]),
            "Anteil lim. (%)": best["n_lim"] / n_versicherte * 100,
            "RfB-Bedarf (Mio. €)": best["rfb"] / 1e6,
            "score": best["score"],
        })

    return pd.DataFrame(opt_ergebnisse)


def finde_knickpunkt(df_opt: pd.DataFrame) -> tuple[pd.Series | None, bool]:
    """
    Identifiziert den Knickpunkt der Score-Budget-Kurve per Krümmungsanalyse.

    Args:
        df_opt: Ergebnis-DataFrame aus berechne_optimale_budgetstufen().

    Returns:
        (knick_row, knick_gefunden):
            knick_row: Zeile des Knickpunkts (oder letzte Zeile als Fallback).
            knick_gefunden: True wenn ein echter Knickpunkt identifiziert wurde.
    """
    if len(df_opt) < 1:
        return None, False

    if len(df_opt) >= 5:
        scores = df_opt["score"].values
        budgets = df_opt["Budget (Mio. €)"].values

        delta_score = np.diff(scores)
        delta_budget = np.diff(budgets)
        grenznutzen = np.where(delta_budget > 0, delta_score / delta_budget, 0)
        df_opt["grenznutzen"] = np.append(grenznutzen[0], grenznutzen)

        if len(grenznutzen) >= 3:
            gn_smooth = uniform_filter1d(grenznutzen.astype(float), size=3)
            kruemmung = np.abs(np.diff(gn_smooth))

            max_gn = gn_smooth.max()
            min_gn = gn_smooth.min()
            gn_spread = max_gn - min_gn

            if gn_spread > max_gn * 0.3:
                knick_pos = kruemmung.argmax() + 1
                knick_pos = min(knick_pos + 1, len(df_opt) - 1)
                return df_opt.iloc[knick_pos], True
            else:
                return df_opt.iloc[-1], False
        else:
            return df_opt.iloc[-1], False
    else:
        df_opt["grenznutzen"] = 0
        return df_opt.iloc[-1], False


def berechne_pareto_front(
    df_gitter: pd.DataFrame,
    budget_eur: float,
) -> pd.DataFrame:
    """
    Extrahiert die Pareto-Front aus dem Gitter für ein gegebenes Budget.

    Args:
        df_gitter: Gitter-DataFrame aus berechne_gitter().
        budget_eur: Budget in Euro.

    Returns:
        DataFrame mit Pareto-optimalen Kombinationen.
    """
    tol = budget_eur * 0.05
    to_data = df_gitter[
        (df_gitter["rfb"] >= budget_eur - tol) & (df_gitter["rfb"] <= budget_eur + tol)
    ].copy()

    if len(to_data) < 5:
        machbar = df_gitter[df_gitter["rfb"] <= budget_eur].copy()
        if len(machbar) > 0:
            sw = machbar["rfb"].quantile(0.92)
            to_data = machbar[machbar["rfb"] >= sw]

    if len(to_data) == 0:
        return pd.DataFrame()

    # Pareto-Filter: sortiert nach pct_cap aufsteigend, behalte nur wenn abs_cap sinkt
    to_s = to_data.sort_values("pct_cap").reset_index(drop=True)
    pareto = []
    min_abs = float("inf")
    for _, r in to_s.iterrows():
        if r["abs_cap"] < min_abs:
            pareto.append(r)
            min_abs = r["abs_cap"]

    return pd.DataFrame(pareto)
