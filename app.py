#!/usr/bin/env python3
"""
PKV-Limitierungstool — Streamlit App
=====================================
Tab 1: Bestandsanalyse
Tab 2: Limitierungsrechnung (folgt)

Nutzung:
  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import hashlib
import base64
from pathlib import Path



# =============================================================================
# SEITENKONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="PKV-Limitierungstool",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _lade_svg_als_data_uri(pfad: str) -> str:
    try:
        svg_bytes = Path(pfad).read_bytes()
        svg_b64 = base64.b64encode(svg_bytes).decode("ascii")
        return f"data:image/svg+xml;base64,{svg_b64}"
    except Exception:
        # Fallback auf externe Quelle, falls lokale Datei fehlt.
        return "https://aktuar.de/_assets/87d17a42edc6aa4486ad37cc027da99c/Images/Design/logo.svg"


DAV_LOGO_SRC = _lade_svg_als_data_uri("dav_logo.svg")

st.markdown("""
<style>
    /* === DAV Corporate Design === */
    /* Primär: Dunkelblau #003056, Akzent-Blau #0078C8, Grün #78BE20 */
    /* Sekundär: Orange #E87722, Hellgrau #F0F2F5, Dunkelgrau #3C3C3C */

    @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Source Sans 3', 'Source Sans Pro', Calibri, sans-serif !important;
    }

    /* ===== GLOBAL STREAMLIT PRIMARY COLOR OVERRIDE ===== */
    /* This catches ALL default red/primary elements */
    :root {
        --primary-color: #0078C8 !important;
    }

    /* Metriken im DAV-Stil */
    div[data-testid="stMetric"] {
        background: #FFFFFF;
        border-left: 4px solid #0078C8;
        border-top: none; border-right: 1px solid #E8ECF0; border-bottom: 1px solid #E8ECF0;
        border-radius: 4px;
        padding: 14px 16px;
        box-shadow: 0 1px 4px rgba(0,48,86,0.06);
    }
    div[data-testid="stMetric"] label {
        font-size: 0.72rem !important; color: #5A7184 !important;
        font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.8px;
        font-family: 'Source Sans 3', sans-serif !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 1.45rem !important; font-weight: 700 !important; color: #003056 !important;
        font-family: 'Source Sans 3', sans-serif !important;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0px;
        border-bottom: 2px solid #E8ECF0;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 24px; font-weight: 600; color: #5A7184;
        border-bottom: 3px solid transparent;
        font-family: 'Source Sans 3', sans-serif;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #003056 !important;
        border-bottom: 3px solid #0078C8 !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #F0F2F5;
        border-right: 1px solid #E8ECF0;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2 {
        color: #003056 !important;
        font-family: 'Source Sans 3', sans-serif !important;
    }

    /* ===== BUTTONS — aggressive override of Streamlit red ===== */
    button[kind="primary"],
    button[kind="primaryFormSubmit"],
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button,
    .stButton > button:focus,
    div[data-testid="stForm"] button[type="submit"],
    div[data-testid="stForm"] button {
        background-color: #0078C8 !important;
        color: white !important;
        border: none !important;
        border-color: #0078C8 !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        font-family: 'Source Sans 3', sans-serif !important;
    }
    button[kind="primary"]:hover,
    button[kind="primaryFormSubmit"]:hover,
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover,
    div[data-testid="stForm"] button:hover {
        background-color: #005FA0 !important;
        border-color: #005FA0 !important;
    }
    button[kind="primary"]:active,
    .stFormSubmitButton > button:active {
        background-color: #004A80 !important;
    }

    /* Sekundäre Buttons */
    .stButton > button:not([kind="primary"]) {
        color: #003056 !important;
        border: 1px solid #0078C8 !important;
        font-family: 'Source Sans 3', sans-serif !important;
        font-weight: 600 !important;
    }

    /* Download Buttons */
    .stDownloadButton > button {
        background-color: #FFFFFF !important;
        color: #003056 !important;
        border: 1px solid #0078C8 !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
    }
    .stDownloadButton > button:hover {
        background-color: #EBF5FF !important;
        border-color: #005FA0 !important;
    }

    /* ===== SLIDER — override red track and thumb ===== */
    div[data-testid="stSlider"] [role="slider"] {
        background-color: #0078C8 !important;
    }
    div[data-testid="stSlider"] [data-testid="stTickBar"] > div {
        background-color: #0078C8 !important;
    }
    /* Slider track (filled portion) */
    div[data-testid="stSlider"] div[role="slider"] ~ div {
        background: #0078C8 !important;
    }

    /* ===== MULTISELECT TAGS — override red pills ===== */
    span[data-baseweb="tag"] {
        background-color: #0078C8 !important;
        color: white !important;
        border-color: #0078C8 !important;
    }
    span[data-baseweb="tag"]:hover {
        background-color: #005FA0 !important;
    }
    span[data-baseweb="tag"] > span:last-child {
        color: white !important;
    }

    /* ===== RADIO BUTTONS ===== */
    div[role="radiogroup"] label[data-baseweb="radio"] div:first-child div {
        border-color: #0078C8 !important;
    }
    div[role="radiogroup"] label[data-baseweb="radio"][aria-checked="true"] div:first-child div {
        background-color: #0078C8 !important;
    }

    /* ===== SELECT / MULTISELECT focus ring ===== */
    div[data-baseweb="select"] {
        font-family: 'Source Sans 3', sans-serif !important;
    }
    div[data-baseweb="select"] > div:focus-within {
        border-color: #0078C8 !important;
        box-shadow: 0 0 0 1px #0078C8 !important;
    }
    /* Dropdown highlight */
    li[role="option"][aria-selected="true"],
    li[role="option"]:hover {
        background-color: #EBF5FF !important;
    }

    /* ===== CHECKBOX ===== */
    input[type="checkbox"]:checked + div {
        background-color: #0078C8 !important;
        border-color: #0078C8 !important;
    }

    /* ===== TOGGLE / SWITCH ===== */
    div[data-baseweb="toggle"] input:checked ~ div {
        background-color: #0078C8 !important;
    }

    /* ===== PROGRESS / SPINNER ===== */
    .stSpinner > div > div {
        border-top-color: #0078C8 !important;
    }

    /* ===== LINKS ===== */
    a {
        color: #0078C8 !important;
    }
    a:hover {
        color: #005FA0 !important;
    }

    /* Markdown Headers */
    h1, h2, h3, h4 {
        color: #003056 !important;
        font-family: 'Source Sans 3', sans-serif !important;
    }

    /* Info boxes */
    div[data-testid="stAlert"] {
        border-left-color: #0078C8 !important;
    }

    /* Dividers */
    hr {
        border-color: #E8ECF0 !important;
    }

    /* ===== EXPANDER ===== */
    details[data-testid="stExpander"] summary:hover {
        color: #0078C8 !important;
    }
    details[data-testid="stExpander"] svg {
        color: #0078C8 !important;
    }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# KONSTANTEN & FARBPALETTEN — DAV Corporate Design
# =============================================================================

# DAV-Farbpalette: Dunkelblau, Akzent-Blau, Grün, Orange + Abstufungen
DAV_BLAU_DUNKEL = "#003056"
DAV_BLAU_AKZENT = "#0078C8"
DAV_GRUEN = "#78BE20"
DAV_ORANGE = "#E87722"
DAV_GRAU_DUNKEL = "#3C3C3C"
DAV_GRAU_HELL = "#F0F2F5"

PALETTE_GROSS = [
    "#0078C8",  # DAV Blau
    "#E87722",  # DAV Orange
    "#78BE20",  # DAV Grün
    "#003056",  # DAV Dunkelblau
    "#5CB8E6",  # Helles Blau
    "#F5A623",  # Helles Orange
    "#4A9E2F",  # Dunkleres Grün
    "#8B572A",  # Braun
    "#7B61A1",  # Violett
    "#2AABB3",  # Teal
    "#D0021B",  # Rot
    "#3C7A3C",  # Waldgrün
    "#B8860B",  # Dunkelgold
    "#4A90D9",  # Mittelblau
    "#C85000",  # Dunkelorange
    "#5A7184",  # Blaugrau
    "#9B9B9B",  # Mittelgrau
    "#006B54",  # Dunkelgrün
    "#8E44AD",  # Lila
    "#2C3E50",  # Anthrazit
]

PLOTLY_LAYOUT = dict(
    font=dict(family="Source Sans 3, Source Sans Pro, Calibri, sans-serif", size=13, color=DAV_GRAU_DUNKEL),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=50, b=40),
    hoverlabel=dict(bgcolor="white", font_size=12, bordercolor=DAV_BLAU_AKZENT),
    title_font=dict(color=DAV_BLAU_DUNKEL, size=15),
)

# Dimensionen für Gruppierung in der interaktiven Tabelle
GRUPPIER_DIMENSIONEN = {
    "Tarifwerk": "tarifwerk",
    "Tarifart": "tarifart",
    "Tarif": "tarif_id",
    "Geschlecht": "geschlecht",
    "Altersgruppe": "altersgruppe",
    "Hist. Belastung": "hist_belastung",
}


def _farb_map_dynamisch(df, spalte):
    """Erzeugt dynamische Farbzuordnung für beliebige Kategorien in einer Spalte."""
    kategorien = sorted(df[spalte].unique())
    return {k: PALETTE_GROSS[i % len(PALETTE_GROSS)] for i, k in enumerate(kategorien)}


def _erzeuge_altersgruppen(df, schritt=10):
    """Erzeugt Altersgruppen basierend auf tatsächlichem Altersbereich in den Daten."""
    alter_min = int(np.floor(df["alter"].min() / schritt) * schritt)
    alter_max = int(np.ceil((df["alter"].max() + 1) / schritt) * schritt)
    grenzen = list(range(alter_min, alter_max + schritt, schritt))
    labels = [f"{i}-{i + schritt - 1}" for i in range(alter_min, alter_max, schritt)]
    return grenzen, labels


def _geschlecht_label(code):
    """Menschenlesbares Label für Geschlechtscode — mit Fallback."""
    mapping = {"M": "Männlich", "W": "Weiblich", "D": "Divers"}
    return mapping.get(code, code)


def formatiere_euro(wert):
    if abs(wert) >= 1_000_000:
        return f"{wert / 1_000_000:,.1f} Mio. €"
    elif abs(wert) >= 1_000:
        return f"{wert:,.0f} €"
    return f"{wert:.2f} €"


def df_hash(df):
    n = len(df)
    if n == 0:
        return "empty"
    key = f"{n}_{list(df.columns)}"
    key += f"_{df.iloc[0].values.tobytes().hex()[:32]}"
    key += f"_{df.iloc[-1].values.tobytes().hex()[:32]}"
    key += f"_{df.iloc[n // 2].values.tobytes().hex()[:32]}"
    return hashlib.md5(key.encode()).hexdigest()


# =============================================================================
# DATEN LADEN
# =============================================================================

@st.cache_data(show_spinner="Lade Daten …")
def lade_csv(datei, name: str) -> pd.DataFrame:
    df = pd.read_csv(datei, sep=";", low_memory=False)
    if name == "bestand":
        erwartete = [
            "versicherten_id", "alter", "geschlecht", "tarifwerk", "tarif_id",
            "tarifart", "praemie_alt_monatlich", "praemie_neu_monatlich",
            "erhoehung_absolut", "erhoehung_prozent", "alterungsrueckstellung",
            "versicherungsdauer_jahre",
        ]
        fehlende = [s for s in erwartete if s not in df.columns]
        if fehlende:
            st.error(f"Fehlende Spalten: {fehlende}")
            st.stop()
        grenzen, labels = _erzeuge_altersgruppen(df)
        df["altersgruppe"] = pd.cut(
            df["alter"], bins=grenzen,
            right=False, labels=labels,
        ).astype(str)
    return df


# =============================================================================
# GECACHTE BERECHNUNGEN
# =============================================================================

@st.cache_data(show_spinner=False)
def berechne_kpis(_hash, df):
    return {
        "n": len(df),
        "praemie_alt_mean": df["praemie_alt_monatlich"].mean(),
        "praemie_neu_mean": df["praemie_neu_monatlich"].mean(),
        "erh_pct_mean": df["erhoehung_prozent"].mean(),
        "erh_pct_median": df["erhoehung_prozent"].median(),
        "erh_abs_mean": df["erhoehung_absolut"].mean(),
        "erh_abs_median": df["erhoehung_absolut"].median(),
        "jahres_vol": (df["erhoehung_absolut"] * 12).sum(),
    }


@st.cache_data(show_spinner=False)
def berechne_treemap_daten(_hash, df, farb_spalte):
    """Treemap mit Farbspalte: erhoehung_prozent oder erhoehung_absolut."""

    s4 = (df.groupby(["tarifwerk", "tarifart", "geschlecht", "altersgruppe"], observed=True)
          .agg(anzahl=("versicherten_id", "count"), erh=(farb_spalte, "mean"))
          .reset_index())
    s4["id"] = s4["tarifwerk"] + "/" + s4["tarifart"] + "/" + s4["geschlecht"] + "/" + s4["altersgruppe"]
    s4["parent"] = s4["tarifwerk"] + "/" + s4["tarifart"] + "/" + s4["geschlecht"]
    s4["label"] = s4["altersgruppe"]

    s3 = (df.groupby(["tarifwerk", "tarifart", "geschlecht"], observed=True)
          .agg(anzahl=("versicherten_id", "count"), erh=(farb_spalte, "mean"))
          .reset_index())
    s3["id"] = s3["tarifwerk"] + "/" + s3["tarifart"] + "/" + s3["geschlecht"]
    s3["parent"] = s3["tarifwerk"] + "/" + s3["tarifart"]
    s3["label"] = s3["geschlecht"].map(_geschlecht_label)

    s2 = (df.groupby(["tarifwerk", "tarifart"], observed=True)
          .agg(anzahl=("versicherten_id", "count"), erh=(farb_spalte, "mean"))
          .reset_index())
    s2["id"] = s2["tarifwerk"] + "/" + s2["tarifart"]
    s2["parent"] = s2["tarifwerk"]
    s2["label"] = s2["tarifart"].str.capitalize()

    s1 = (df.groupby("tarifwerk", observed=True)
          .agg(anzahl=("versicherten_id", "count"), erh=(farb_spalte, "mean"))
          .reset_index())
    s1["id"] = s1["tarifwerk"]
    s1["parent"] = ""
    s1["label"] = s1["tarifwerk"]

    spalten = ["id", "parent", "label", "anzahl", "erh"]
    return pd.concat([s1[spalten], s2[spalten], s3[spalten], s4[spalten]], ignore_index=True)


@st.cache_data(show_spinner=False)
def berechne_interaktive_statistik(_hash, df, gruppen_spalten_tuple):
    """
    Dynamische Gruppierungstabelle.
    gruppen_spalten_tuple: tuple von Spaltennamen (als tuple für Hashbarkeit).
    """
    gruppen_spalten = list(gruppen_spalten_tuple)

    if not gruppen_spalten:
        # Keine Gruppierung: Gesamtzeile
        row = {
            "Versicherte": len(df),
            "Ø Prämie alt (€)": round(df["praemie_alt_monatlich"].mean(), 0),
            "Ø Prämie neu (€)": round(df["praemie_neu_monatlich"].mean(), 0),
            "Ø Erhöhung (%)": round(df["erhoehung_prozent"].mean(), 1),
            "Median Erhöhung (%)": round(df["erhoehung_prozent"].median(), 1),
            "Ø Erhöhung (€)": round(df["erhoehung_absolut"].mean(), 0),
            "Median Erhöhung (€)": round(df["erhoehung_absolut"].median(), 0),
            "P95 Erhöhung (%)": round(df["erhoehung_prozent"].quantile(0.95), 1),
            "P95 Erhöhung (€)": round(df["erhoehung_absolut"].quantile(0.95), 0),
            "Ø Alter.-Rückst. (€)": round(df["alterungsrueckstellung"].mean(), 0),
            "Volumen p.a. (€)": round((df["erhoehung_absolut"] * 12).sum(), 0),
        }
        return pd.DataFrame([row])

    agg = df.groupby(gruppen_spalten, observed=True).agg(
        Versicherte=("versicherten_id", "count"),
        praemie_alt_mean=("praemie_alt_monatlich", "mean"),
        praemie_neu_mean=("praemie_neu_monatlich", "mean"),
        erh_pct_mean=("erhoehung_prozent", "mean"),
        erh_pct_median=("erhoehung_prozent", "median"),
        erh_abs_mean=("erhoehung_absolut", "mean"),
        erh_abs_median=("erhoehung_absolut", "median"),
        erh_pct_p95=("erhoehung_prozent", lambda x: x.quantile(0.95)),
        erh_abs_p95=("erhoehung_absolut", lambda x: x.quantile(0.95)),
        ar_mean=("alterungsrueckstellung", "mean"),
        erh_abs_sum=("erhoehung_absolut", "sum"),
    ).reset_index()

    # Spalten umbenennen
    agg = agg.rename(columns={
        "praemie_alt_mean": "Ø Prämie alt (€)",
        "praemie_neu_mean": "Ø Prämie neu (€)",
        "erh_pct_mean": "Ø Erhöhung (%)",
        "erh_pct_median": "Median Erhöhung (%)",
        "erh_abs_mean": "Ø Erhöhung (€)",
        "erh_abs_median": "Median Erhöhung (€)",
        "erh_pct_p95": "P95 Erhöhung (%)",
        "erh_abs_p95": "P95 Erhöhung (€)",
        "ar_mean": "Ø Alter.-Rückst. (€)",
        "erh_abs_sum": "erh_abs_sum_raw",
    })

    # Volumen = Summe × 12
    agg["Volumen p.a. (€)"] = (agg["erh_abs_sum_raw"] * 12).round(0)
    agg = agg.drop(columns=["erh_abs_sum_raw"])

    # Runden
    for col in agg.columns:
        if agg[col].dtype in [np.float64, np.float32]:
            if "(%)" in col:
                agg[col] = agg[col].round(1)
            else:
                agg[col] = agg[col].round(0)

    # Gruppierungsspalten umbenennen für Anzeige
    rename_map = {
        "tarifwerk": "Tarifwerk", "tarifart": "Tarifart", "tarif_id": "Tarif",
        "geschlecht": "Geschlecht", "altersgruppe": "Altersgruppe",
    }
    agg = agg.rename(columns={k: v for k, v in rename_map.items() if k in agg.columns})

    return agg.sort_values("Versicherte", ascending=False).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def berechne_hist_daten(_hash, df, farb_spalte, wert_spalte):
    if farb_spalte and farb_spalte in df.columns:
        return {kat: df.loc[df[farb_spalte] == kat, wert_spalte].values
                for kat in sorted(df[farb_spalte].unique())}
    return {"_gesamt": df[wert_spalte].values}


# =============================================================================
# PLOT-FUNKTIONEN
# =============================================================================

def _farbe_fuer(kat, farb_map, idx):
    if isinstance(farb_map, dict) and kat in farb_map:
        return farb_map[kat]
    return PALETTE_GROSS[idx % len(PALETTE_GROSS)]


def erstelle_histogramm(hist_daten, farb_spalte, farb_map, mw, md, einheit):
    fig = go.Figure()
    x_title = f"Erhöhung ({einheit})"

    if farb_spalte:
        for i, (kat, werte) in enumerate(hist_daten.items()):
            if len(werte) == 0:
                continue
            farbe = _farbe_fuer(kat, farb_map, i)
            fmt = ":.1f" if einheit == "%" else ":.0f"
            fig.add_trace(go.Histogram(
                x=werte, nbinsx=60, name=str(kat),
                marker=dict(color=farbe, line=dict(color=farbe, width=0.3)),
                opacity=0.75,
                hovertemplate=f"{kat}<br>{x_title}: %{{x{fmt}}}<br>Anzahl: %{{y:,}}<extra></extra>",
            ))
        fig.update_layout(barmode="overlay")
    else:
        werte = hist_daten["_gesamt"]
        fmt = ":.1f" if einheit == "%" else ":.0f"
        fig.add_trace(go.Histogram(
            x=werte, nbinsx=80,
            marker=dict(color="rgba(0,120,200,0.7)", line=dict(color="rgba(0,120,200,1)", width=0.5)),
            hovertemplate=f"{x_title}: %{{x{fmt}}}<br>Anzahl: %{{y:,}}<extra></extra>",
        ))

    mw_txt = f"Ø {mw:.1f}%" if einheit == "%" else f"Ø {mw:.0f} €"
    md_txt = f"Median {md:.1f}%" if einheit == "%" else f"Median {md:.0f} €"

    fig.add_vline(x=mw, line_dash="dash", line_color=DAV_ORANGE, line_width=2,
                  annotation_text=mw_txt, annotation_position="top right",
                  annotation_font=dict(color=DAV_ORANGE, size=11))
    fig.add_vline(x=md, line_dash="dot", line_color=DAV_GRUEN, line_width=2,
                  annotation_text=md_txt, annotation_position="top left",
                  annotation_font=dict(color=DAV_GRUEN, size=11))

    fig.update_layout(
        **PLOTLY_LAYOUT, title=f"Histogramm — Prämienerhöhung ({einheit})",
        xaxis_title=x_title, yaxis_title="Anzahl Versicherte", height=440,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
        showlegend=bool(farb_spalte),
    )
    fig.update_xaxes(gridcolor="#eee", zeroline=False)
    fig.update_yaxes(gridcolor="#eee", zeroline=False)
    return fig


def erstelle_boxplot(hist_daten, farb_spalte, farb_map, einheit):
    fig = go.Figure()

    if farb_spalte:
        for i, (kat, werte) in enumerate(hist_daten.items()):
            if len(werte) == 0:
                continue
            farbe = _farbe_fuer(kat, farb_map, i)
            fig.add_trace(go.Box(
                y=werte, name=str(kat), marker_color=farbe,
                boxmean=True, hoverinfo="y+name",
            ))
    else:
        fig.add_trace(go.Box(
            y=hist_daten["_gesamt"], name="Gesamt",
            marker_color=DAV_BLAU_AKZENT, boxmean=True, hoverinfo="y",
        ))

    fig.update_layout(
        **PLOTLY_LAYOUT, title=f"Boxplot — Erhöhung ({einheit})",
        yaxis_title=f"Erhöhung ({einheit})", showlegend=False, height=440,
    )
    fig.update_yaxes(gridcolor="#eee", zeroline=False)
    return fig


def erstelle_treemap(treemap_df, einheit):
    erh_vals = treemap_df["erh"].values
    einheit_kurz = "%" if einheit == "%" else "€"
    fmt = ".1f" if einheit == "%" else ".0f"

    fig = go.Figure(go.Treemap(
        ids=treemap_df["id"].values,
        labels=treemap_df["label"].values,
        parents=treemap_df["parent"].values,
        values=treemap_df["anzahl"].values,
        branchvalues="total",
        marker=dict(
            colors=erh_vals,
            colorscale=[[0, DAV_GRUEN], [0.5, DAV_ORANGE], [1, "#D0021B"]],
            cmin=np.nanmin(erh_vals), cmax=np.nanmax(erh_vals),
            colorbar=dict(title=f"Ø Erhöhung ({einheit_kurz})"),
        ),
        customdata=np.column_stack([
            np.where(np.isnan(erh_vals), 0, np.round(erh_vals, 1 if einheit == "%" else 0)),
            treemap_df["anzahl"].values,
        ]),
        hovertemplate=(
            "<b>%{label}</b><br>Anzahl: %{customdata[1]:,}<br>"
            f"Ø Erhöhung: %{{customdata[0]:{fmt}}}{einheit_kurz}"
            "<extra></extra>"
        ),
        texttemplate=(
            f"<b>%{{label}}</b><br>n=%{{customdata[1]:,}}<br>"
            f"Ø %{{customdata[0]:{fmt}}}{einheit_kurz}"
        ),
        maxdepth=2,
    ))

    fig.update_layout(
        **PLOTLY_LAYOUT,
        title=f"Treemap — Ø Erhöhung ({einheit_kurz}), Klick zum Drilldown",
        height=540,
    )
    return fig


# =============================================================================
# SIDEBAR
# =============================================================================


with st.sidebar:
    st.markdown(f"""
    <div style="text-align:center; padding:8px 0 12px 0; border-bottom:2px solid #0078C8; margin-bottom:16px;">
        <div style="display:inline-block; background:#003056; padding:8px 12px; border-radius:8px;">
            <img src="{DAV_LOGO_SRC}"
                 alt="DAV" style="height:40px; width:auto; display:block;">
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("## 📂 Datenimport")

    upload_modus = st.radio("Datenquelle", ["Mock-Daten (lokaler Pfad)", "CSV-Upload"], index=0)

    if upload_modus == "Mock-Daten (lokaler Pfad)":
        pfad = st.text_input("Verzeichnis", value="./output_daten")
        if st.button("Daten laden", type="primary", use_container_width=True):
            try:
                st.session_state["df_bestand"] = lade_csv(f"{pfad}/bestand.csv", "bestand")
                st.session_state["df_tarife"] = lade_csv(f"{pfad}/tarife.csv", "tarife")
                st.session_state["df_ao"] = lade_csv(f"{pfad}/ausscheideordnung.csv", "ao")
                st.session_state.pop("df_gefiltert", None)
                st.success(f"✓ {len(st.session_state['df_bestand']):,} Versicherte geladen")
            except FileNotFoundError as e:
                st.error(f"Datei nicht gefunden: {e}")
            except Exception as e:
                st.error(f"Fehler: {e}")
    else:
        f_b = st.file_uploader("bestand.csv", type="csv", key="up_b")
        f_t = st.file_uploader("tarife.csv", type="csv", key="up_t")
        f_a = st.file_uploader("ausscheideordnung.csv", type="csv", key="up_a")
        if f_b and f_t and f_a:
            st.session_state["df_bestand"] = lade_csv(f_b, "bestand")
            st.session_state["df_tarife"] = lade_csv(f_t, "tarife")
            st.session_state["df_ao"] = lade_csv(f_a, "ao")
            st.session_state.pop("df_gefiltert", None)
            st.success(f"✓ {len(st.session_state['df_bestand']):,} Versicherte geladen")

    df_bestand = st.session_state.get("df_bestand")

    if df_bestand is not None:
        st.markdown("---")
        st.markdown("## 🔍 Filter")

        with st.form("filter_form"):
            alle_tw = sorted(df_bestand["tarifwerk"].unique())
            gew_tw = st.multiselect("Tarifwerk", alle_tw, default=alle_tw)

            alle_ta = sorted(df_bestand["tarifart"].unique())
            gew_ta = st.multiselect("Tarifart", alle_ta, default=alle_ta)

            alle_tarife = sorted(df_bestand["tarif_id"].unique())
            gew_tarife = st.multiselect("Tarif (einzeln)", alle_tarife, default=alle_tarife)

            alle_geschl = sorted(df_bestand["geschlecht"].unique())
            gew_geschl = st.multiselect(
                "Geschlecht", alle_geschl, default=alle_geschl,
                format_func=_geschlecht_label,
            )

            a_min, a_max = int(df_bestand["alter"].min()), int(df_bestand["alter"].max())
            gew_alter = st.slider("Altersbereich", a_min, a_max, (a_min, a_max))

            st.markdown("**Erhöhungsfilter**")
            e_pct_max = float(np.ceil(df_bestand["erhoehung_prozent"].max()))
            gew_erh_pct = st.slider("Erhöhung (%)", 0.0, e_pct_max, (0.0, e_pct_max), step=1.0, format="%.0f%%")

            e_abs_max = float(np.ceil(df_bestand["erhoehung_absolut"].max() / 10) * 10)  # auf 10er runden
            gew_erh_abs = st.slider("Erhöhung (€/Monat)", 0.0, e_abs_max,
                                    (0.0, e_abs_max), step=5.0, format="%.0f €")

            erh_logik = st.radio("Verknüpfung % und €",
                                 ["UND (beide müssen zutreffen)", "ODER (eine reicht)"],
                                 index=0, horizontal=True)

            filter_btn = st.form_submit_button("🔍 Filter anwenden", use_container_width=True, type="primary")

        if filter_btn:
            maske_basis = (
                df_bestand["tarifwerk"].isin(gew_tw if gew_tw else alle_tw)
                & df_bestand["tarifart"].isin(gew_ta if gew_ta else alle_ta)
                & df_bestand["tarif_id"].isin(gew_tarife if gew_tarife else alle_tarife)
                & df_bestand["geschlecht"].isin(gew_geschl if gew_geschl else alle_geschl)
                & df_bestand["alter"].between(gew_alter[0], gew_alter[1])
            )
            maske_pct = df_bestand["erhoehung_prozent"].between(gew_erh_pct[0], gew_erh_pct[1])
            maske_abs = df_bestand["erhoehung_absolut"].between(gew_erh_abs[0], gew_erh_abs[1])
            maske_erh = (maske_pct & maske_abs) if "UND" in erh_logik else (maske_pct | maske_abs)
            st.session_state["df_gefiltert"] = df_bestand[maske_basis & maske_erh]

        if "df_gefiltert" not in st.session_state and df_bestand is not None:
            st.session_state["df_gefiltert"] = df_bestand

        df_gef = st.session_state.get("df_gefiltert")
        if df_gef is not None:
            st.markdown("---")
            st.metric("Gefiltert", f"{len(df_gef):,} / {len(df_bestand):,}")


# =============================================================================
# HAUPTBEREICH
# =============================================================================

st.markdown(f"""
<div style="display:flex; align-items:center; gap:20px; margin-bottom:12px; padding-bottom:12px; border-bottom:2px solid #E8ECF0;">
    <div style="flex-shrink:0;">
        <div style="background:#003056; padding:10px 14px; border-radius:10px; display:inline-block;">
            <img src="{DAV_LOGO_SRC}"
                 alt="DAV" style="height:56px; width:auto; display:block;">
        </div>
    </div>
    <div>
        <h1 style="margin:0; padding:0; font-size:1.8rem; color:#003056 !important;
                    font-family:'Source Sans 3', sans-serif !important; font-weight:700; line-height:1.2;">
            PKV-Limitierungstool
        </h1>
        <p style="margin:2px 0 0 0; padding:0; font-size:0.88rem; color:#5A7184;
                  font-family:'Source Sans 3', sans-serif; font-weight:400;">
            Deutsche Aktuarvereinigung e.V. — Analyse und Simulation von Beitragsanpassungen
        </p>
    </div>
</div>
""", unsafe_allow_html=True)


df_gefiltert = st.session_state.get("df_gefiltert")
df_bestand = st.session_state.get("df_bestand")


if df_gefiltert is None or df_bestand is None:
    st.info("Bitte laden Sie die Daten über die Sidebar (links).")
    st.stop()


tab_bestand, tab_limitierung = st.tabs(["📊 Bestandsanalyse", "⚖️ Limitierungsrechnung"])


# =============================================================================
# TAB 1: BESTANDSANALYSE
# =============================================================================

with tab_bestand:
    df = df_gefiltert
    h = df_hash(df)
    kpis = berechne_kpis(h, df)

    # Alle Farbmaps dynamisch aus den Daten erzeugen
    farb_dimensionen = {
        "Keine Differenzierung": (None, None),
        "Tarifwerk": ("tarifwerk", _farb_map_dynamisch(df, "tarifwerk")),
        "Tarifart": ("tarifart", _farb_map_dynamisch(df, "tarifart")),
        "Tarif (einzeln)": ("tarif_id", _farb_map_dynamisch(df, "tarif_id")),
        "Geschlecht": ("geschlecht", _farb_map_dynamisch(df, "geschlecht")),
        "Altersgruppe": ("altersgruppe", _farb_map_dynamisch(df, "altersgruppe")),
    }

    # --- KPIs ---
    st.markdown("### Kennzahlen")
    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    with k1:
        st.metric("Versicherte", f"{kpis['n']:,}")
    with k2:
        st.metric("Ø Prämie alt", f"{kpis['praemie_alt_mean']:.0f} €/Mon.")
    with k3:
        st.metric("Ø Prämie neu", f"{kpis['praemie_neu_mean']:.0f} €/Mon.")
    with k4:
        st.metric("Ø Erhöhung (%)", f"{kpis['erh_pct_mean']:.1f} %")
    with k5:
        st.metric("Median Erh. (%)", f"{kpis['erh_pct_median']:.1f} %")
    with k6:
        st.metric("Ø Erhöhung (€)", f"{kpis['erh_abs_mean']:.0f} €/Mon.")
    with k7:
        st.metric("Volumen p.a.", formatiere_euro(kpis["jahres_vol"]))

    st.markdown("---")

    # --- Wertperspektive (global für diesen Tab) ---
    st.markdown("### Verteilung der Prämienerhöhung")

    ctrl1, ctrl2, ctrl3 = st.columns([1, 2, 1])
    with ctrl1:
        wert_perspektive = st.radio("Wertperspektive", ["Prozentual (%)", "Absolut (€/Monat)"], horizontal=True)
    with ctrl2:
        farb_wahl = st.selectbox("Farbliche Differenzierung", list(farb_dimensionen.keys()), index=0)
    with ctrl3:
        ausreisser_ausblenden = st.checkbox(
            "Ausreißer ausblenden",
            value=False,
            help="Blendet Werte oberhalb des 95. Percentils aus den Plots aus.",
        )

    ist_prozent = "%" in wert_perspektive
    wert_spalte = "erhoehung_prozent" if ist_prozent else "erhoehung_absolut"
    einheit = "%" if ist_prozent else "€"
    mw = kpis["erh_pct_mean"] if ist_prozent else kpis["erh_abs_mean"]
    md = kpis["erh_pct_median"] if ist_prozent else kpis["erh_abs_median"]

    # Ausreißer filtern für Plots (nicht für KPIs/Tabellen)
    df_plot = df
    if ausreisser_ausblenden:
        p95 = df[wert_spalte].quantile(0.95)
        df_plot = df[df[wert_spalte] <= p95]
        st.caption(f"Ausreißer ausgeblendet: zeige Werte ≤ {p95:.1f} {einheit} (P95). "
                   f"{len(df) - len(df_plot):,} Versicherte ausgeblendet.")

    farb_spalte, farb_map = farb_dimensionen[farb_wahl]
    hist_daten = berechne_hist_daten(h if not ausreisser_ausblenden else df_hash(df_plot),
                                     df_plot, farb_spalte, wert_spalte)

    col_hist, col_box = st.columns([3, 2])
    with col_hist:
        st.plotly_chart(erstelle_histogramm(hist_daten, farb_spalte, farb_map, mw, md, einheit),
                        use_container_width=True)
    with col_box:
        st.plotly_chart(erstelle_boxplot(hist_daten, farb_spalte, farb_map, einheit),
                        use_container_width=True)

    st.markdown("---")

    # --- Treemap mit %/€ Toggle ---
    st.markdown("### Bestandsstruktur")

    treemap_farb_spalte = wert_spalte  # folgt dem globalen Toggle
    treemap_df = berechne_treemap_daten(h, df, treemap_farb_spalte)
    st.plotly_chart(erstelle_treemap(treemap_df, einheit), use_container_width=True)

    st.markdown("---")

    # --- Interaktive Statistik-Tabelle ---
    st.markdown("### Statistische Übersicht")
    st.caption("Wählen Sie eine oder mehrere Dimensionen, nach denen die Statistiken gruppiert werden sollen.")

    gew_gruppierung = st.multiselect(
        "Gruppieren nach",
        list(GRUPPIER_DIMENSIONEN.keys()),
        default=["Tarifwerk"],
        key="stat_gruppierung",
    )

    # Spaltennamen auflösen
    gruppen_spalten = tuple(GRUPPIER_DIMENSIONEN[g] for g in gew_gruppierung)

    stat_df = berechne_interaktive_statistik(h, df, gruppen_spalten)

    # Spalten-Konfiguration für schöne Anzeige
    col_config = {}
    for col in stat_df.columns:
        if col == "Versicherte":
            col_config[col] = st.column_config.NumberColumn(format="%d")
        elif "(%)" in col:
            col_config[col] = st.column_config.NumberColumn(format="%.1f")
        elif "(€)" in col and "Volumen" not in col:
            col_config[col] = st.column_config.NumberColumn(format="%.0f")
        elif "Volumen" in col:
            col_config[col] = st.column_config.NumberColumn(format="%.0f")

    st.dataframe(
        stat_df, hide_index=True, use_container_width=True,
        height=min(400, 40 + len(stat_df) * 35),
        column_config=col_config,
    )

    # CSV-Export der Statistik-Tabelle
    st.download_button(
        label="📥 Statistik-Tabelle als CSV",
        data=stat_df.to_csv(index=False, sep=";").encode("utf-8"),
        file_name="statistik_gruppiert.csv",
        mime="text/csv",
        key="dl_stat",
    )

    st.markdown("---")

    # --- Detailtabelle ---
    st.markdown("### Einzeldaten")
    ansicht = st.radio(
        "Ansicht",
        ["Top 100 höchste Erhöhungen (%)", "Top 100 höchste Erhöhungen (€)",
         "Top 100 höchste Prämien", "Zufällige Stichprobe"],
        horizontal=True,
    )

    if "(%)" in ansicht:
        df_detail = df.nlargest(100, "erhoehung_prozent")
    elif "(€)" in ansicht:
        df_detail = df.nlargest(100, "erhoehung_absolut")
    elif "Prämien" in ansicht:
        df_detail = df.nlargest(100, "praemie_neu_monatlich")
    else:
        df_detail = df.sample(n=min(100, len(df)), random_state=42)

    spalten_map = {
        "versicherten_id": "ID", "alter": "Alter", "geschlecht": "Geschl.",
        "tarifwerk": "Tarifwerk", "tarif_id": "Tarif", "tarifart": "Tarifart",
        "versicherungsdauer_jahre": "Dauer (J.)",
        "praemie_alt_monatlich": "Prämie alt (€)", "praemie_neu_monatlich": "Prämie neu (€)",
        "erhoehung_absolut": "Erhöhung (€)", "erhoehung_prozent": "Erhöhung (%)",
        "alterungsrueckstellung": "Alter.-Rückst. (€)",
    }
    df_anzeige = df_detail[list(spalten_map.keys())].rename(columns=spalten_map)

    st.dataframe(
        df_anzeige, hide_index=True, use_container_width=True, height=400,
        column_config={
            "Prämie alt (€)": st.column_config.NumberColumn(format="%.2f"),
            "Prämie neu (€)": st.column_config.NumberColumn(format="%.2f"),
            "Erhöhung (€)": st.column_config.NumberColumn(format="%.2f"),
            "Erhöhung (%)": st.column_config.NumberColumn(format="%.1f"),
            "Alter.-Rückst. (€)": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    with st.expander("📥 CSV-Export Gesamtbestand"):
        st.info(f"Der gefilterte Bestand umfasst {len(df):,} Zeilen.")
        if st.button("CSV erzeugen"):
            csv_bytes = df.to_csv(index=False, sep=";").encode("utf-8")
            st.download_button(label="⬇️ Herunterladen", data=csv_bytes,
                               file_name="bestand_gefiltert.csv", mime="text/csv")

# =============================================================================
# TAB 2: LIMITIERUNGSRECHNUNG
# =============================================================================

# --- Barwert-Kern (vorberechnet, gecacht) ---

@st.cache_data(show_spinner="Berechne Leibrentenbarwerte …")
def berechne_barwertfaktoren(_ao_hash, df_ao, df_tarife):
    """
    Vorberechnung der Leibrentenbarwerte a_x für jede Kombination
    aus Tarif × Geschlecht × Alter. Einmal berechnen, dann nur noch Lookup.

    a_x = Summe über t=1..omega-x von: v^t * t_p_x
    wobei v = 1/(1+i), t_p_x = Produkt der (1-q_{x+s}-w_{x+s}) für s=0..t-1
    """
    ergebnisse = []

    for _, tarif in df_tarife.iterrows():
        tid = tarif["tarif_id"]
        i = tarif["rechnungszins"]
        v = 1.0 / (1.0 + i)

        for geschl in ["M", "W"]:
            ao_teil = df_ao[(df_ao["tarif_id"] == tid) & (df_ao["geschlecht"] == geschl)].sort_values("alter")
            if len(ao_teil) == 0:
                continue

            qx_arr = ao_teil["qx"].values
            wx_arr = ao_teil["storno"].values
            max_alter = len(qx_arr)

            for x in range(max_alter):
                # Barwert einer lebenslangen Rente ab Alter x
                ax = 0.0
                tp = 1.0  # t_p_x: Verbleibewahrscheinlichkeit
                for t in range(1, max_alter - x):
                    alter_idx = x + t - 1
                    if alter_idx >= max_alter:
                        break
                    # Ausscheidewahrscheinlichkeit = Sterben + Storno
                    ausch = min(qx_arr[alter_idx] + wx_arr[alter_idx], 1.0)
                    tp *= (1.0 - ausch)
                    if tp < 1e-10:
                        break
                    ax += (v ** t) * tp

                ergebnisse.append({
                    "tarif_id": tid,
                    "geschlecht": geschl,
                    "alter": x,
                    "barwertfaktor": round(ax, 6),
                })

    return pd.DataFrame(ergebnisse)


@st.cache_data(show_spinner=False)
def berechne_limitierung(_hash, df, df_bwf, regeln, modus, laufzeit_jahre):
    """
    Wendet Regelkaskade an und berechnet Einmaleinlagen.

    regeln: Liste von dicts mit keys:
        ziel_pct (float|None), ziel_abs (float|None),
        scope_spalte (str|None), scope_werte (list|None)

    Rückgabe: DataFrame mit zusätzlichen Spalten:
        erhoehung_limitiert_pct, erhoehung_limitiert_abs, praemie_limitiert,
        einmaleinlage, limitiert (bool)
    """
    n = len(df)
    erh_pct_orig = df["erhoehung_prozent"].values.copy()
    erh_abs_orig = df["erhoehung_absolut"].values.copy()
    praemie_alt = df["praemie_alt_monatlich"].values

    # Starte mit der ungedeckelten Erhöhung
    erh_pct_lim = erh_pct_orig.copy()
    erh_abs_lim = erh_abs_orig.copy()

    # Regelkaskade: jede Regel verschärft den Deckel
    for regel in regeln:
        ziel_pct = regel.get("ziel_pct")
        ziel_abs = regel.get("ziel_abs")
        scope_spalte = regel.get("scope_spalte")
        scope_werte = regel.get("scope_werte")

        if ziel_pct is None and ziel_abs is None:
            continue

        # Scope bestimmen: welche Versicherten sind betroffen?
        if scope_spalte and scope_werte:
            maske = df[scope_spalte].isin(scope_werte).values
        else:
            maske = np.ones(n, dtype=bool)

        # Deckel anwenden
        if ziel_pct is not None:
            cap_pct = np.where(maske & (erh_pct_lim > ziel_pct), ziel_pct, erh_pct_lim)
            erh_pct_lim = np.minimum(erh_pct_lim, cap_pct)

        if ziel_abs is not None:
            cap_abs = np.where(maske & (erh_abs_lim > ziel_abs), ziel_abs, erh_abs_lim)
            erh_abs_lim = np.minimum(erh_abs_lim, cap_abs)

    # Konsistenz: abs und pct müssen zusammenpassen
    # Die strengere Begrenzung gewinnt
    erh_abs_aus_pct = praemie_alt * erh_pct_lim / 100.0
    erh_abs_lim = np.minimum(erh_abs_lim, erh_abs_aus_pct)
    erh_pct_lim = np.where(praemie_alt > 0, erh_abs_lim / praemie_alt * 100.0, 0.0)

    praemie_lim = np.round(praemie_alt + erh_abs_lim, 2)

    # Differenz zur Finanzierung
    diff_monatlich = erh_abs_orig - erh_abs_lim  # was durch RfB finanziert wird
    diff_monatlich = np.maximum(diff_monatlich, 0.0)

    # Barwertfaktor per Merge-Lookup (60x schneller als List-Comprehension)
    bwf_merged = df[["tarif_id", "geschlecht", "alter"]].merge(
        df_bwf, on=["tarif_id", "geschlecht", "alter"], how="left"
    )
    bwf_werte = bwf_merged["barwertfaktor"].fillna(0).values

    # Einmaleinlage berechnen (dauerhafte Limitierung)
    einmaleinlage = np.round(diff_monatlich * 12 * bwf_werte, 2)

    limitiert = diff_monatlich > 0.01

    return pd.DataFrame({
        "erhoehung_limitiert_pct": np.round(erh_pct_lim, 2),
        "erhoehung_limitiert_abs": np.round(erh_abs_lim, 2),
        "praemie_limitiert": praemie_lim,
        "differenz_monatlich": np.round(diff_monatlich, 2),
        "einmaleinlage": einmaleinlage,
        "limitiert": limitiert,
    })


@st.cache_data(show_spinner=False)
def berechne_sensitivitaet(_hash, df, df_bwf, regeln_basis, modus, laufzeit):
    """Berechnet RfB-Bedarf für verschiedene Limitierungsziele."""
    ergebnisse = []
    # Finde die erste Regel ohne Scope (= die globale Regel)
    global_idx = None
    for i, r in enumerate(regeln_basis):
        if not r.get("scope_spalte"):
            global_idx = i
            break

    if global_idx is None:
        return pd.DataFrame()

    basis_pct = regeln_basis[global_idx].get("ziel_pct", 30)
    schritte = np.arange(max(5, basis_pct - 20), min(basis_pct + 25, 100), 2.5)

    for ziel in schritte:
        regeln_var = [r.copy() for r in regeln_basis]
        regeln_var[global_idx] = {**regeln_var[global_idx], "ziel_pct": float(ziel)}
        res = berechne_limitierung(_hash, df, df_bwf, regeln_var, modus, laufzeit)
        ergebnisse.append({
            "Limitierungsziel (%)": ziel,
            "RfB-Bedarf (Mio. €)": res["einmaleinlage"].sum() / 1e6,
            "Anzahl limitiert": res["limitiert"].sum(),
            "Ø Entlastung (€/Mon)": res.loc[res["limitiert"], "differenz_monatlich"].mean()
            if res["limitiert"].any() else 0,
        })

    return pd.DataFrame(ergebnisse)


@st.cache_data(show_spinner=False)
def berechne_optimierungsvorschlaege(_hash, df, df_bwf, regeln, modus, laufzeit, budget):
    """
    Erzeugt Optimierungsvorschläge als konkrete Regeländerungen.
    Analysiert: Wo ist der Grenznutzen pro € RfB am höchsten/niedrigsten?
    """
    vorschlaege = []
    aktuell = berechne_limitierung(_hash, df, df_bwf, regeln, modus, laufzeit)
    bedarf_aktuell = aktuell["einmaleinlage"].sum()

    # --- Einsparvorschläge: Regeln lockern ---
    for i, regel in enumerate(regeln):
        ziel_pct = regel.get("ziel_pct")
        if ziel_pct is None:
            continue

        for delta in [2, 5, 10]:
            neue_regeln = [r.copy() for r in regeln]
            neue_regeln[i] = {**neue_regeln[i], "ziel_pct": ziel_pct + delta}
            res_neu = berechne_limitierung(_hash, df, df_bwf, neue_regeln, modus, laufzeit)
            bedarf_neu = res_neu["einmaleinlage"].sum()
            einsparung = bedarf_aktuell - bedarf_neu

            if einsparung > 10000:  # Mindestens 10k € Einsparung
                # Wie viele Versicherte sind stärker belastet?
                mehr_belastet = (res_neu["erhoehung_limitiert_pct"] > aktuell["erhoehung_limitiert_pct"] + 0.1).sum()
                scope_text = f"{regel.get('scope_spalte', 'Alle')}: {regel.get('scope_werte', 'Alle')}" if regel.get("scope_spalte") else "Global"

                vorschlaege.append({
                    "typ": "einsparung",
                    "beschreibung": f"Regel '{scope_text}' von {ziel_pct:.0f}% auf {ziel_pct + delta:.0f}% lockern",
                    "einsparung_eur": einsparung,
                    "betroffene": mehr_belastet,
                    "regel_index": i,
                    "neue_regel": neue_regeln[i],
                })

    # --- Verbesserungsvorschläge: Regeln verschärfen ---
    for i, regel in enumerate(regeln):
        ziel_pct = regel.get("ziel_pct")
        if ziel_pct is None or ziel_pct <= 5:
            continue

        for delta in [2, 5]:
            neues_ziel = max(ziel_pct - delta, 0)
            neue_regeln = [r.copy() for r in regeln]
            neue_regeln[i] = {**neue_regeln[i], "ziel_pct": neues_ziel}
            res_neu = berechne_limitierung(_hash, df, df_bwf, neue_regeln, modus, laufzeit)
            bedarf_neu = res_neu["einmaleinlage"].sum()
            mehrkosten = bedarf_neu - bedarf_aktuell

            if mehrkosten > 0 and mehrkosten < (budget - bedarf_aktuell) * 1.5:
                entlastet = (res_neu["erhoehung_limitiert_pct"] < aktuell["erhoehung_limitiert_pct"] - 0.1).sum()
                scope_text = f"{regel.get('scope_spalte', 'Alle')}: {regel.get('scope_werte', 'Alle')}" if regel.get("scope_spalte") else "Global"

                vorschlaege.append({
                    "typ": "verbesserung",
                    "beschreibung": f"Regel '{scope_text}' von {ziel_pct:.0f}% auf {neues_ziel:.0f}% verschärfen",
                    "einsparung_eur": -mehrkosten,
                    "betroffene": entlastet,
                    "regel_index": i,
                    "neue_regel": neue_regeln[i],
                })

    # Sortieren: Einsparungen nach Größe, Verbesserungen nach Kosten-Nutzen
    vorschlaege.sort(key=lambda x: -abs(x["einsparung_eur"]))
    return vorschlaege


@st.cache_data(show_spinner=False)
def berechne_teilbestand_vorschlaege(_hash, df, df_bwf, regeln, modus, laufzeit, budget):
    """
    Generiert Vorschläge für neue Regeln auf Teilbeständen.
    Prüft für jede Tarifart und jeden Tarif, ob eine spezifische Regel sinnvoll wäre.
    """
    vorschlaege = []
    aktuell = berechne_limitierung(_hash, df, df_bwf, regeln, modus, laufzeit)
    bedarf_aktuell = aktuell["einmaleinlage"].sum()

    # Finde die globale Regel (für Referenz-Zielwert)
    global_ziel = None
    for r in regeln:
        if not r.get("scope_spalte") and r.get("ziel_pct"):
            global_ziel = r["ziel_pct"]
            break
    if global_ziel is None:
        return vorschlaege

    # Teste Teilbestände: Tarifart, Tarif, Tarifwerk
    segmente = []
    for spalte, label in [("tarifart", "Tarifart"), ("tarif_id", "Tarif"), ("tarifwerk", "Tarifwerk")]:
        for wert in sorted(df[spalte].unique()):
            segmente.append((spalte, label, wert))

    for spalte, label, wert in segmente:
        n_segment = (df[spalte] == wert).sum()
        if n_segment < 100:  # Zu klein für sinnvolle Vorschläge
            continue

        # Prüfe ob für dieses Segment bereits eine Regel existiert
        bereits_geregelt = False
        for r in regeln:
            if r.get("scope_spalte") == spalte and wert in (r.get("scope_werte") or []):
                bereits_geregelt = True
                break
        if bereits_geregelt:
            continue

        # Ø Erhöhung in diesem Segment nach aktueller Limitierung
        maske = df[spalte] == wert
        erh_segment = aktuell.loc[maske.values, "erhoehung_limitiert_pct"]
        erh_mean = erh_segment.mean()

        # Vorschlag 1: Segment lockern (wenn es nahe am Deckel ist → viel gespart)
        for ziel_lockerer in [global_ziel + 5, global_ziel + 10]:
            neue_regeln = [r.copy() for r in regeln]
            neue_regeln.append({
                "ziel_pct": ziel_lockerer, "ziel_abs": None,
                "scope_spalte": spalte, "scope_werte": [wert],
            })
            # Da die Regelkaskade nur verschärft, funktioniert eine lockere Regel
            # nur wenn wir die globale Regel für dieses Segment ersetzen
            # → Simuliere: globale Regel bleibt, aber wir entfernen dieses Segment davon
            # Einfacher: Berechne was passiert wenn dieses Segment komplett von der
            # Limitierung ausgenommen wird
            pass  # Lockern geht nicht mit Kaskadenlogik — überspringe

        # Vorschlag 2: Segment verschärfen (niedrigerer Deckel als global)
        for delta in [5, 10]:
            neues_ziel = max(global_ziel - delta, 0)
            neue_regel = {
                "ziel_pct": float(neues_ziel), "ziel_abs": None,
                "scope_spalte": spalte, "scope_werte": [wert],
            }
            neue_regeln = [r.copy() for r in regeln] + [neue_regel]
            res_neu = berechne_limitierung(_hash, df, df_bwf, neue_regeln, modus, laufzeit)
            bedarf_neu = res_neu["einmaleinlage"].sum()
            mehrkosten = bedarf_neu - bedarf_aktuell

            if mehrkosten > 10000:
                entlastet = (res_neu.loc[maske.values, "erhoehung_limitiert_pct"]
                             < aktuell.loc[maske.values, "erhoehung_limitiert_pct"] - 0.1).sum()
                if entlastet > 0:
                    vorschlaege.append({
                        "typ": "teilbestand",
                        "beschreibung": f"{label} '{wert}' zusätzlich auf {neues_ziel:.0f}% begrenzen",
                        "einsparung_eur": -mehrkosten,
                        "betroffene": entlastet,
                        "regel_index": len(regeln),  # Wird angehängt
                        "neue_regel": neue_regel,
                    })

    # Sortieren nach Anzahl entlasteter Versicherter pro € Mehrkosten
    vorschlaege.sort(key=lambda x: x["betroffene"] / (abs(x["einsparung_eur"]) + 1), reverse=True)
    return vorschlaege[:10]  # Max 10 Vorschläge


# --- UI ---

with tab_limitierung:
    st.markdown("### ⚖️ Limitierungsrechnung")

    df_ao = st.session_state.get("df_ao")
    df_tarife = st.session_state.get("df_tarife")

    if df_ao is None or df_tarife is None or df_bestand is None:
        st.info("Bitte laden Sie zuerst die Daten (inkl. Ausscheideordnung und Tarife).")
    else:
        # Welcher Bestand? Gefiltert oder gesamt
        verwende_filter = st.checkbox(
            "Limitierung nur auf gefilterten Bestand anwenden",
            value=False,
            help="Wenn aktiv, wird nur der in Tab 1 gefilterte Bestand limitiert.",
        )
        df_lim = df_gefiltert if verwende_filter else df_bestand

        # Historische Belastung als binäre Gruppierung hinzufügen
        if "erhoehung_historisch_kumuliert" in df_lim.columns:
            schwelle = st.session_state.get("hist_schwelle", 30.0)
            df_lim = df_lim.copy()
            df_lim["hist_belastung"] = np.where(
                df_lim["erhoehung_historisch_kumuliert"] >= schwelle,
                f"Hist. ≥ {schwelle:.0f}%", f"Hist. < {schwelle:.0f}%"
            )

        st.caption(f"Bestand: {len(df_lim):,} Versicherte")

        # === BESTANDSKENNZAHLEN (Orientierung für Limitierung) ===
        st.markdown("### 📋 Bestandskennzahlen vor Limitierung")
        st.caption("Überblick über die aktuelle Anpassungssituation — als Basis für die Festlegung der Regeln.")

        bk1, bk2, bk3, bk4 = st.columns(4)
        with bk1:
            st.metric("Versicherte", f"{len(df_lim):,}")
        with bk2:
            st.metric("Ø Erhöhung", f"{df_lim['erhoehung_prozent'].mean():.1f} %")
        with bk3:
            st.metric("Ø Erhöhung (€)", f"{df_lim['erhoehung_absolut'].mean():.0f} €/Mon")
        with bk4:
            vol_pa = df_lim["erhoehung_absolut"].sum() * 12
            st.metric("Erhöhungsvolumen p.a.", formatiere_euro(vol_pa))

        st.markdown("**Percentile und Maxima**")
        perc_col1, perc_col2 = st.columns(2)
        with perc_col1:
            st.markdown("*Prozentual (%)*")
            pp1, pp2, pp3, pp4 = st.columns(4)
            with pp1:
                st.metric("P90", f"{df_lim['erhoehung_prozent'].quantile(0.90):.1f} %")
            with pp2:
                st.metric("P95", f"{df_lim['erhoehung_prozent'].quantile(0.95):.1f} %")
            with pp3:
                st.metric("P99", f"{df_lim['erhoehung_prozent'].quantile(0.99):.1f} %")
            with pp4:
                st.metric("Maximum", f"{df_lim['erhoehung_prozent'].max():.1f} %")
        with perc_col2:
            st.markdown("*Absolut (€/Mon)*")
            pa1, pa2, pa3, pa4 = st.columns(4)
            with pa1:
                st.metric("P90", f"{df_lim['erhoehung_absolut'].quantile(0.90):.0f} €")
            with pa2:
                st.metric("P95", f"{df_lim['erhoehung_absolut'].quantile(0.95):.0f} €")
            with pa3:
                st.metric("P99", f"{df_lim['erhoehung_absolut'].quantile(0.99):.0f} €")
            with pa4:
                st.metric("Maximum", f"{df_lim['erhoehung_absolut'].max():.0f} €")

        # Kompakte Tarifwerk-Übersicht
        with st.expander("📊 Aufschlüsselung nach Tarifwerk", expanded=False):
            tw_rows = []
            for tw in sorted(df_lim["tarifwerk"].unique()):
                d = df_lim[df_lim["tarifwerk"] == tw]
                tw_rows.append({
                    "Tarifwerk": tw,
                    "Versicherte": f"{len(d):,}",
                    "Ø Erh. (%)": f"{d['erhoehung_prozent'].mean():.1f}",
                    "P90 (%)": f"{d['erhoehung_prozent'].quantile(0.90):.1f}",
                    "P95 (%)": f"{d['erhoehung_prozent'].quantile(0.95):.1f}",
                    "Max (%)": f"{d['erhoehung_prozent'].max():.1f}",
                    "Ø Erh. (€)": f"{d['erhoehung_absolut'].mean():.0f}",
                    "Max (€)": f"{d['erhoehung_absolut'].max():.0f}",
                })
            st.dataframe(pd.DataFrame(tw_rows), hide_index=True, use_container_width=True)

        # Barwertfaktoren: erst berechnen wenn nötig (lazy, aber gecacht)
        if "df_bwf" not in st.session_state:
            with st.spinner("Berechne Leibrentenbarwerte (einmalig) …"):
                ao_hash = df_hash(df_ao)
                st.session_state["df_bwf"] = berechne_barwertfaktoren(ao_hash, df_ao, df_tarife)
        df_bwf = st.session_state["df_bwf"]

        st.markdown("---")

        # === INPUTS ===
        col_cfg1, col_cfg2 = st.columns(2)

        with col_cfg1:
            st.markdown("#### Konfiguration")

            # Default-Budget: basierend auf einer groben Schätzung
            # (wird beim ersten Laden aus den Daten abgeleitet)
            budget = st.number_input(
                "Verfügbares RfB-Budget (€)",
                min_value=0, value=st.session_state.get("default_budget", 100_000_000),
                step=1_000_000, format="%d",
                help="Gesamtbetrag in Euro, der für Limitierung zur Verfügung steht.",
            )
            modus_key = "dauerhaft"
            laufzeit = 1

            # Historische Belastung als Gruppierung verfügbar machen
            if "hist_belastung" not in df_lim.columns and "erhoehung_historisch_kumuliert" in df_lim.columns:
                hist_schwelle = st.number_input(
                    "Schwelle historische Belastung (%)",
                    min_value=0.0, max_value=100.0, value=30.0, step=5.0,
                    help="Versicherte mit kumulierter historischer Anpassung über diesem Wert "
                         "gelten als 'historisch stark belastet' und können per Regel bevorzugt werden.",
                )
                st.session_state["hist_schwelle"] = hist_schwelle

        with col_cfg2:
            st.markdown("#### Regeln definieren")
            st.caption("Regeln werden von oben nach unten angewendet. Spätere Regeln können nur verschärfen.")

            # Default-Regel: P99 der prozentualen und absoluten Erhöhung, sinnvoll gerundet
            if "regeln" not in st.session_state:
                p99_pct = df_lim["erhoehung_prozent"].quantile(0.99)
                p99_abs = df_lim["erhoehung_absolut"].quantile(0.99)
                # Runden: % auf 5er, € auf 50er
                default_pct = float(np.ceil(p99_pct / 5) * 5)
                default_abs = float(np.ceil(p99_abs / 50) * 50)
                st.session_state["regeln"] = [
                    {"ziel_pct": default_pct, "ziel_abs": default_abs,
                     "scope_spalte": None, "scope_werte": None},
                ]

            regeln = st.session_state["regeln"]

            # Anzeige und Bearbeitung der Regeln
            for idx, regel in enumerate(regeln):
                with st.container():
                    rc1, rc2, rc3, rc4, rc5 = st.columns([1.5, 1.5, 1.5, 2, 0.8])
                    with rc1:
                        regeln[idx]["ziel_pct"] = st.number_input(
                            "Max %", value=regel.get("ziel_pct") or 0.0,
                            min_value=0.0, max_value=200.0, step=1.0,
                            key=f"r_pct_{idx}", format="%.1f",
                        )
                        if regeln[idx]["ziel_pct"] == 0.0:
                            regeln[idx]["ziel_pct"] = None
                    with rc2:
                        abs_val = st.number_input(
                            "Max €/Mon", value=regel.get("ziel_abs") or 0.0,
                            min_value=0.0, max_value=5000.0, step=10.0,
                            key=f"r_abs_{idx}", format="%.0f",
                        )
                        regeln[idx]["ziel_abs"] = abs_val if abs_val > 0 else None
                    with rc3:
                        scope_optionen = ["Alle"] + list(GRUPPIER_DIMENSIONEN.keys())
                        scope_wahl = st.selectbox(
                            "Scope", scope_optionen, index=0, key=f"r_scope_{idx}",
                        )
                        if scope_wahl == "Alle":
                            regeln[idx]["scope_spalte"] = None
                            regeln[idx]["scope_werte"] = None
                    with rc4:
                        if scope_wahl != "Alle":
                            spalte = GRUPPIER_DIMENSIONEN[scope_wahl]
                            regeln[idx]["scope_spalte"] = spalte
                            alle_werte = sorted(df_lim[spalte].unique())
                            regeln[idx]["scope_werte"] = st.multiselect(
                                "Werte", alle_werte, default=alle_werte[:1], key=f"r_werte_{idx}",
                            )
                        else:
                            st.markdown(" ")
                    with rc5:
                        if len(regeln) > 1:
                            if st.button("🗑", key=f"r_del_{idx}"):
                                regeln.pop(idx)
                                st.session_state["regeln"] = regeln
                                st.rerun()

            # Neue Regel hinzufügen
            if st.button("➕ Regel hinzufügen"):
                regeln.append({"ziel_pct": 20.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None})
                st.session_state["regeln"] = regeln
                st.rerun()

        st.markdown("---")

        # === SENSITIVITÄTSANALYSE (vor Berechnung, für Größenordnung) ===
        st.markdown("### 📈 Sensitivitätsanalyse")
        st.caption("Zeigt den RfB-Bedarf für verschiedene Limitierungsziele.")

        if st.button("📈 Sensitivität berechnen", key="sens_btn"):
            aktive_regeln_fuer_sens = [r for r in regeln if r.get("ziel_pct") or r.get("ziel_abs")]
            if aktive_regeln_fuer_sens:
                lim_hash = df_hash(df_lim)
                sens = berechne_sensitivitaet(
                    lim_hash, df_lim, df_bwf, aktive_regeln_fuer_sens,
                    modus_key, laufzeit,
                )
                st.session_state["lim_sens"] = sens
            else:
                st.warning("Definieren Sie mindestens eine Regel.")

        sens = st.session_state.get("lim_sens")
        if sens is not None and len(sens) > 0:
                fig_sens = go.Figure()
                fig_sens.add_trace(go.Scatter(
                    x=sens["Limitierungsziel (%)"], y=sens["RfB-Bedarf (Mio. €)"],
                    mode="lines+markers", name="RfB-Bedarf",
                    line=dict(color=DAV_BLAU_AKZENT, width=3),
                    marker=dict(size=6),
                    hovertemplate="Ziel: %{x:.0f}%<br>Bedarf: %{y:.1f} Mio. €<extra></extra>",
                ))
                fig_sens.add_hline(y=budget / 1e6, line_dash="dash", line_color=DAV_ORANGE,
                                   annotation_text=f"Budget: {budget / 1e6:.0f} Mio. €")
                # Zweite Y-Achse: Anzahl Limitierte
                fig_sens.add_trace(go.Scatter(
                    x=sens["Limitierungsziel (%)"], y=sens["Anzahl limitiert"],
                    mode="lines+markers", name="Anzahl limitiert",
                    line=dict(color=DAV_GRUEN, width=2, dash="dot"),
                    marker=dict(size=4),
                    yaxis="y2",
                    hovertemplate="Ziel: %{x:.0f}%<br>Limitierte: %{y:,}<extra></extra>",
                ))
                fig_sens.update_layout(
                    **PLOTLY_LAYOUT, title="Sensitivität: Limitierungsziel vs. RfB-Bedarf",
                    xaxis_title="Limitierungsziel (%)", yaxis_title="RfB-Bedarf (Mio. €)",
                    yaxis2=dict(title="Anzahl limitiert", overlaying="y", side="right",
                                showgrid=False, tickformat=","),
                    height=400,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
                )
                fig_sens.update_xaxes(gridcolor="#eee")
                fig_sens.update_yaxes(gridcolor="#eee")
                st.plotly_chart(fig_sens, use_container_width=True)

        st.markdown("---")

        # === BERECHNUNG ===
        if st.button("🔄 Limitierung berechnen", type="primary", use_container_width=True):
            aktive_regeln = [r for r in regeln if r.get("ziel_pct") or r.get("ziel_abs")]

            if not aktive_regeln:
                st.warning("Bitte definieren Sie mindestens eine Regel.")
            else:
                lim_hash = df_hash(df_lim)
                res = berechne_limitierung(lim_hash, df_lim, df_bwf, aktive_regeln, modus_key, laufzeit)
                st.session_state["lim_result"] = res
                st.session_state["lim_regeln_snapshot"] = aktive_regeln
                st.session_state["lim_budget"] = budget
                st.session_state["lim_modus"] = modus_key
                st.session_state["lim_laufzeit"] = laufzeit

        # === ERGEBNISSE ===
        res = st.session_state.get("lim_result")

        if res is not None:
            df_lim_aktuell = df_lim
            bedarf = res["einmaleinlage"].sum()
            n_limitiert = res["limitiert"].sum()
            n_gesamt = len(res)
            budget_val = st.session_state.get("lim_budget", budget)

            # --- KPI-Karten ---
            st.markdown("### Ergebnis")
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("RfB-Bedarf", formatiere_euro(bedarf))
            with m2:
                st.metric("RfB-Budget", formatiere_euro(budget_val))
            with m3:
                diff_budget = budget_val - bedarf
                st.metric("Differenz", formatiere_euro(diff_budget),
                           delta=f"{'Über' if diff_budget >= 0 else 'Unter'}deckung")
            with m4:
                st.metric("Limitierte", f"{n_limitiert:,} ({n_limitiert / n_gesamt:.1%})")

            m5, m6, m7, m8 = st.columns(4)
            with m5:
                mehrbetrag_pa = res["erhoehung_limitiert_abs"].sum() * 12
                st.metric("Mehrbetrag p.a. nachher", formatiere_euro(mehrbetrag_pa))
            with m6:
                st.metric("Max. Erhöhung nachher (%)", f"{res['erhoehung_limitiert_pct'].max():.1f} %")
            with m7:
                st.metric("Max. Erhöhung nachher (€)", f"{res['erhoehung_limitiert_abs'].max():.0f} €/Mon")
            with m8:
                st.metric("Ø Erhöhung nachher (€)", f"{res['erhoehung_limitiert_abs'].mean():.0f} €/Mon")

            st.markdown("---")

            # --- Treemap: Verwendete RfB-Mittel ---
            st.markdown("### Verteilung der RfB-Mittel")

            # Hierarchie-Reihenfolge wählbar
            TREEMAP_EBENEN = {
                "Tarifwerk": "tarifwerk",
                "Tarifart": "tarifart",
                "Geschlecht": "geschlecht",
                "Altersgruppe": "altersgruppe",
            }
            treemap_reihenfolge = st.multiselect(
                "Hierarchie-Ebenen (Reihenfolge = Verschachtelung)",
                list(TREEMAP_EBENEN.keys()),
                default=["Tarifwerk", "Tarifart", "Geschlecht", "Altersgruppe"],
                key="lim_treemap_hierarchie",
            )

            if len(treemap_reihenfolge) == 0:
                st.warning("Bitte mindestens eine Ebene wählen.")
            else:
                hierarchie_spalten = [TREEMAP_EBENEN[e] for e in treemap_reihenfolge]

                df_tree_src = df_lim_aktuell[list(set(hierarchie_spalten + ["versicherten_id"]))].copy()
                df_tree_src["einmaleinlage"] = res["einmaleinlage"].values

                label_fn = {
                    "geschlecht": _geschlecht_label,
                    "tarifart": lambda x: str(x).capitalize(),
                }

                # Dynamisch alle Stufen der Hierarchie aufbauen
                alle_stufen = []
                for tiefe in range(1, len(hierarchie_spalten) + 1):
                    grp_cols = hierarchie_spalten[:tiefe]
                    agg = df_tree_src.groupby(grp_cols, observed=True).agg(
                        anzahl=("versicherten_id", "count"),
                        rfb_summe=("einmaleinlage", "sum"),
                        rfb_mean=("einmaleinlage", "mean"),
                    ).reset_index()
                    agg["rfb_summe_mio"] = agg["rfb_summe"] / 1e6
                    agg["id"] = agg[grp_cols].astype(str).agg("/".join, axis=1)
                    if tiefe == 1:
                        agg["parent"] = ""
                    else:
                        parent_cols = grp_cols[:-1]
                        agg["parent"] = agg[parent_cols].astype(str).agg("/".join, axis=1)

                    # Label = letzte Spalte, ggf. mit Mapping
                    letzte_spalte = grp_cols[-1]
                    if letzte_spalte in label_fn:
                        agg["label"] = agg[letzte_spalte].map(label_fn[letzte_spalte])
                    else:
                        agg["label"] = agg[letzte_spalte].astype(str)

                    alle_stufen.append(agg[["id", "parent", "label", "anzahl", "rfb_summe_mio", "rfb_mean"]])

                alle_t = pd.concat(alle_stufen, ignore_index=True)

                fig_tm = go.Figure(go.Treemap(
                    ids=alle_t["id"].values, labels=alle_t["label"].values,
                    parents=alle_t["parent"].values, values=alle_t["anzahl"].values,
                    branchvalues="total",
                    marker=dict(
                        colors=alle_t["rfb_summe_mio"].values,
                        colorscale=[[0, "#EBF5FF"], [0.3, DAV_BLAU_AKZENT], [0.7, DAV_ORANGE], [1, "#D0021B"]],
                        cmin=0, cmax=alle_t["rfb_summe_mio"].max(),
                        colorbar=dict(title="RfB-Mittel (Mio. €)"),
                    ),
                    customdata=np.column_stack([
                        alle_t["rfb_summe_mio"].round(1).values,
                        alle_t["anzahl"].values,
                        alle_t["rfb_mean"].round(0).values,
                    ]),
                    hovertemplate=(
                        "<b>%{label}</b><br>"
                        "Anzahl: %{customdata[1]:,}<br>"
                        "RfB-Mittel: %{customdata[0]:.1f} Mio. €<br>"
                        "Ø Einmaleinlage: %{customdata[2]:.0f} €"
                        "<extra></extra>"
                    ),
                    texttemplate="<b>%{label}</b><br>n=%{customdata[1]:,}<br>%{customdata[0]:.1f} Mio. €",
                    maxdepth=2,
                ))
                hierarchie_text = " → ".join(treemap_reihenfolge)
                fig_tm.update_layout(
                    **PLOTLY_LAYOUT,
                    title=f"Treemap — RfB-Mittel ({hierarchie_text})",
                    height=520,
                )
                st.plotly_chart(fig_tm, use_container_width=True)

            st.markdown("---")

            # --- Spitzenreduktion nach Alter (Zumutbarkeitsprüfung) ---
            st.markdown("### Spitzenreduktion nach Alter")
            st.caption("Zeigt die oberen Quantile der Erhöhung pro Alter — vorher vs. nachher. "
                       "Relevant für die Zumutbarkeitsprüfung gem. § 155 Abs. 2 VAG.")

            sp_col1, sp_col2 = st.columns([1, 1])
            with sp_col1:
                sp_quantil = st.selectbox(
                    "Quantil", ["P90", "P95", "P99", "Maximum"],
                    index=2, key="sp_quantil",
                )
            with sp_col2:
                sp_wert = st.radio("Wert", ["Prozentual (%)", "Absolut (€/Mon)"], horizontal=True, key="sp_wert")

            sp_q_map = {"P90": 0.90, "P95": 0.95, "P99": 0.99, "Maximum": None}
            sp_q = sp_q_map[sp_quantil]
            sp_ist_pct = "%" in sp_wert

            vorher_col = "erhoehung_prozent" if sp_ist_pct else "erhoehung_absolut"
            nachher_col_vals = res["erhoehung_limitiert_pct"].values if sp_ist_pct else res["erhoehung_limitiert_abs"].values
            einheit_sp = "%" if sp_ist_pct else "€/Mon"

            df_sp = df_lim_aktuell[["alter", vorher_col, "versicherten_id"]].copy()
            df_sp["nachher"] = nachher_col_vals
            df_sp["limitiert"] = res["limitiert"].values

            alter_werte = sorted(df_sp["alter"].unique())
            sp_vorher, sp_nachher, sp_max_v, sp_max_n, sp_n, sp_n_lim = [], [], [], [], [], []

            for a in alter_werte:
                mask = df_sp["alter"] == a
                v = df_sp.loc[mask, vorher_col]
                n_val = df_sp.loc[mask, "nachher"]

                if sp_q is not None:
                    sp_vorher.append(v.quantile(sp_q))
                    sp_nachher.append(n_val.quantile(sp_q))
                else:
                    sp_vorher.append(v.max())
                    sp_nachher.append(n_val.max())

                sp_max_v.append(v.max())
                sp_max_n.append(n_val.max())
                sp_n.append(mask.sum())
                sp_n_lim.append(df_sp.loc[mask, "limitiert"].sum())

            sp_vorher = np.array(sp_vorher)
            sp_nachher = np.array(sp_nachher)

            fig_sp = go.Figure()

            # Vorher-Linie (gestrichelt)
            fig_sp.add_trace(go.Scatter(
                x=alter_werte, y=sp_vorher,
                mode="lines", name=f"{sp_quantil} vorher",
                line=dict(color=DAV_BLAU_AKZENT, width=2, dash="dash"),
                customdata=np.column_stack([sp_n, sp_n_lim, sp_max_v]),
                hovertemplate=(
                    f"Alter: %{{x}}<br>{sp_quantil} vorher: %{{y:.1f}} {einheit_sp}<br>"
                    "Max vorher: %{customdata[2]:.1f}<br>"
                    "n: %{customdata[0]:,}<extra></extra>"
                ),
            ))

            # Nachher-Linie (durchgezogen)
            fig_sp.add_trace(go.Scatter(
                x=alter_werte, y=sp_nachher,
                mode="lines", name=f"{sp_quantil} nachher",
                line=dict(color=DAV_BLAU_AKZENT, width=3),
                customdata=np.column_stack([sp_n, sp_n_lim, sp_max_n]),
                hovertemplate=(
                    f"Alter: %{{x}}<br>{sp_quantil} nachher: %{{y:.1f}} {einheit_sp}<br>"
                    "Max nachher: %{customdata[2]:.1f}<br>"
                    "Limitierte: %{customdata[1]:,} von %{customdata[0]:,}<extra></extra>"
                ),
            ))

            # Maximum vorher/nachher als dünne Linien
            if sp_q is not None:  # Nur wenn nicht schon Maximum gewählt
                fig_sp.add_trace(go.Scatter(
                    x=alter_werte, y=sp_max_v,
                    mode="lines", name="Max vorher",
                    line=dict(color=DAV_ORANGE, width=1, dash="dot"),
                    hovertemplate=f"Alter: %{{x}}<br>Max vorher: %{{y:.1f}} {einheit_sp}<extra></extra>",
                ))
                fig_sp.add_trace(go.Scatter(
                    x=alter_werte, y=sp_max_n,
                    mode="lines", name="Max nachher",
                    line=dict(color=DAV_ORANGE, width=1.5),
                    hovertemplate=f"Alter: %{{x}}<br>Max nachher: %{{y:.1f}} {einheit_sp}<extra></extra>",
                ))

            # Markierung "Ältere Versicherte" ab 60
            fig_sp.add_vrect(
                x0=60, x1=max(alter_werte),
                fillcolor="rgba(232,119,34,0.06)", line_width=0,
                annotation_text="§ 155 VAG: Ältere Versicherte",
                annotation_position="top left",
                annotation_font=dict(size=10, color=DAV_ORANGE),
            )

            fig_sp.update_layout(
                **PLOTLY_LAYOUT,
                title=f"Spitzenreduktion nach Alter — {sp_quantil} ({einheit_sp})",
                xaxis_title="Alter",
                yaxis_title=f"Erhöhung ({einheit_sp})",
                height=460,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center"),
            )
            fig_sp.update_xaxes(gridcolor="#eee")
            fig_sp.update_yaxes(gridcolor="#eee", rangemode="tozero")
            st.plotly_chart(fig_sp, use_container_width=True)

            st.markdown("---")

            # --- Bubble-Chart: Effizienz des RfB-Einsatzes ---
            st.markdown("### Effizienz des RfB-Einsatzes")
            st.caption("Jede Bubble = ein Segment. Zeigt wo wenige stark gekappt werden vs. viele leicht entlastet.")

            bc_col1, bc_col2 = st.columns([1, 1])
            with bc_col1:
                bubble_dim = st.selectbox(
                    "Segmentierung", list(GRUPPIER_DIMENSIONEN.keys()),
                    index=list(GRUPPIER_DIMENSIONEN.keys()).index("Altersgruppe")
                    if "Altersgruppe" in GRUPPIER_DIMENSIONEN else 0,
                    key="bubble_dim",
                )
            with bc_col2:
                bubble_y_wahl = st.radio(
                    "Y-Achse", ["Absolut (€/Mon)", "Relativ (%)"],
                    horizontal=True, key="bubble_y",
                )
            bubble_spalte = GRUPPIER_DIMENSIONEN[bubble_dim]
            bubble_y_ist_abs = "Absolut" in bubble_y_wahl

            # Daten aufbereiten
            df_bubble = df_lim_aktuell[[bubble_spalte, "versicherten_id", "erhoehung_prozent", "erhoehung_absolut"]].copy()
            df_bubble["erh_nachher_pct"] = res["erhoehung_limitiert_pct"].values
            df_bubble["erh_nachher_abs"] = res["erhoehung_limitiert_abs"].values
            df_bubble["einmaleinlage"] = res["einmaleinlage"].values
            df_bubble["limitiert"] = res["limitiert"].values
            df_bubble["differenz"] = res["differenz_monatlich"].values
            df_bubble["differenz_pct"] = df_lim_aktuell["erhoehung_prozent"].values - res["erhoehung_limitiert_pct"].values

            bubble_agg = df_bubble.groupby(bubble_spalte, observed=True).agg(
                n_gesamt=("versicherten_id", "count"),
                n_limitiert=("limitiert", "sum"),
                rfb_summe=("einmaleinlage", "sum"),
                erh_vorher_mean=("erhoehung_prozent", "mean"),
                erh_vorher_max=("erhoehung_prozent", "max"),
                erh_nachher_max_lim=("erh_nachher_pct", "max"),
                # Nur für Limitierte: Ø Entlastung und Ø Erhöhung nachher
                entlastung_sum=("differenz", "sum"),
            ).reset_index()

            # Ø Entlastung der Limitierten (nicht aller)
            entlastung_limitierte = df_bubble[df_bubble["limitiert"]].groupby(bubble_spalte, observed=True).agg(
                entlastung_mean_lim=("differenz", "mean"),
                entlastung_pct_mean_lim=("differenz_pct", "mean"),
                erh_vorher_mean_lim=("erhoehung_prozent", "mean"),
                erh_nachher_mean_lim=("erh_nachher_pct", "mean"),
            ).reset_index()

            bubble_agg = bubble_agg.merge(entlastung_limitierte, on=bubble_spalte, how="left")
            bubble_agg["entlastung_mean_lim"] = bubble_agg["entlastung_mean_lim"].fillna(0)
            bubble_agg["entlastung_pct_mean_lim"] = bubble_agg["entlastung_pct_mean_lim"].fillna(0)
            bubble_agg["anteil_limitiert"] = (bubble_agg["n_limitiert"] / bubble_agg["n_gesamt"] * 100)
            bubble_agg["rfb_mio"] = bubble_agg["rfb_summe"] / 1e6
            bubble_agg["rfb_pro_kopf"] = np.where(
                bubble_agg["n_limitiert"] > 0,
                bubble_agg["rfb_summe"] / bubble_agg["n_limitiert"],
                0,
            )

            if len(bubble_agg) > 0 and bubble_agg["n_limitiert"].sum() > 0:
                fig_bubble = go.Figure()

                # Y-Achse je nach Wahl
                if bubble_y_ist_abs:
                    y_vals = bubble_agg["entlastung_mean_lim"]
                    y_label = "Ø Entlastung der Limitierten (€/Mon)"
                    y_fmt = ":.0f"
                    y_einheit = "€/Mon"
                else:
                    y_vals = bubble_agg["entlastung_pct_mean_lim"]
                    y_label = "Ø Entlastung der Limitierten (pp)"
                    y_fmt = ":.1f"
                    y_einheit = "pp"

                # Bubble-Größe: proportional zu RfB-Summe
                max_rfb = bubble_agg["rfb_mio"].max()
                bubble_sizes = np.clip(bubble_agg["rfb_mio"] / (max_rfb + 1e-10) * 60, 8, 60)

                fig_bubble.add_trace(go.Scatter(
                    x=bubble_agg["anteil_limitiert"],
                    y=y_vals,
                    mode="markers+text",
                    text=bubble_agg[bubble_spalte],
                    textposition="top center",
                    textfont=dict(size=11, color=DAV_BLAU_DUNKEL),
                    marker=dict(
                        size=bubble_sizes,
                        color=bubble_agg["erh_vorher_mean"],
                        colorscale=[[0, DAV_GRUEN], [0.5, DAV_ORANGE], [1, "#D0021B"]],
                        colorbar=dict(title="Ø Erh. vorher (%)"),
                        line=dict(width=1, color="white"),
                        opacity=0.85,
                    ),
                    customdata=np.column_stack([
                        bubble_agg["n_gesamt"].values,
                        bubble_agg["n_limitiert"].values.astype(int),
                        bubble_agg["rfb_mio"].round(1).values,
                        bubble_agg["rfb_pro_kopf"].round(0).values,
                        bubble_agg["erh_vorher_mean"].round(1).values,
                        bubble_agg["erh_vorher_max"].round(1).values,
                        bubble_agg.get("erh_vorher_mean_lim", pd.Series(0, index=bubble_agg.index)).round(1).values,
                        bubble_agg.get("erh_nachher_mean_lim", pd.Series(0, index=bubble_agg.index)).round(1).values,
                        bubble_agg["erh_nachher_max_lim"].round(1).values,
                        bubble_agg["entlastung_mean_lim"].round(0).values,
                        bubble_agg["entlastung_pct_mean_lim"].round(1).values,
                    ]),
                    hovertemplate=(
                        "<b>%{text}</b><br><br>"
                        "Versicherte gesamt: %{customdata[0]:,}<br>"
                        "Davon limitiert: %{customdata[1]:,} (%{x:.1f}%)<br><br>"
                        "<b>RfB-Einsatz</b><br>"
                        "Σ RfB: %{customdata[2]:.1f} Mio. €<br>"
                        "RfB pro limitiertem Kopf: %{customdata[3]:,.0f} €<br><br>"
                        "<b>Limitierte Versicherte</b><br>"
                        "Ø Erhöhung vorher: %{customdata[6]:.1f}%<br>"
                        "Ø Erhöhung nachher: %{customdata[7]:.1f}%<br>"
                        "Ø Entlastung: %{customdata[9]:.0f} €/Mon / %{customdata[10]:.1f} pp<br><br>"
                        "<b>Gesamtsegment</b><br>"
                        "Ø Erhöhung vorher: %{customdata[4]:.1f}%<br>"
                        "Max vorher: %{customdata[5]:.1f}%<br>"
                        "Max nachher: %{customdata[8]:.1f}%"
                        "<extra></extra>"
                    ),
                ))

                fig_bubble.update_layout(
                    **PLOTLY_LAYOUT,
                    title=f"RfB-Effizienz: Anteil Limitierte vs. {y_label}<br>"
                          "<sub>Bubble-Größe = RfB-Summe, Farbe = Ø Erhöhung vorher</sub>",
                    xaxis_title="Anteil limitierte Versicherte (%)",
                    yaxis_title=y_label,
                    height=500,
                    showlegend=False,
                )
                fig_bubble.update_xaxes(gridcolor="#eee", zeroline=False)
                fig_bubble.update_yaxes(gridcolor="#eee", zeroline=False)
                st.plotly_chart(fig_bubble, use_container_width=True)
            else:
                st.info("Keine Versicherten limitiert — Bubble-Chart nicht darstellbar.")

            st.markdown("---")

            # --- Gruppierte Analyse ---
            st.markdown("### Detailanalyse nach Limitierung")

            gew_grp_lim = st.multiselect(
                "Gruppieren nach", list(GRUPPIER_DIMENSIONEN.keys()),
                default=["Tarifwerk"], key="lim_gruppierung",
            )
            grp_spalten = [GRUPPIER_DIMENSIONEN[g] for g in gew_grp_lim]

            if grp_spalten:
                df_detail_lim = df_lim_aktuell[grp_spalten + ["versicherten_id"]].copy()
                df_detail_lim["erh_vorher_pct"] = df_lim_aktuell["erhoehung_prozent"].values
                df_detail_lim["erh_nachher_pct"] = res["erhoehung_limitiert_pct"].values
                df_detail_lim["einmaleinlage"] = res["einmaleinlage"].values
                df_detail_lim["limitiert"] = res["limitiert"].values
                df_detail_lim["entlastung"] = res["differenz_monatlich"].values

                agg_lim = df_detail_lim.groupby(grp_spalten, observed=True).agg(
                    Versicherte=("versicherten_id", "count"),
                    Limitierte=("limitiert", "sum"),
                    erh_vorher=("erh_vorher_pct", "mean"),
                    erh_nachher=("erh_nachher_pct", "mean"),
                    einmaleinlage_sum=("einmaleinlage", "sum"),
                    einmaleinlage_mean=("einmaleinlage", "mean"),
                    entlastung_mean=("entlastung", "mean"),
                ).reset_index()

                agg_lim["Anteil limitiert"] = (agg_lim["Limitierte"] / agg_lim["Versicherte"] * 100).round(1)
                agg_lim = agg_lim.rename(columns={
                    "erh_vorher": "Ø Erh. vorher (%)",
                    "erh_nachher": "Ø Erh. nachher (%)",
                    "einmaleinlage_sum": "Σ Einmaleinlage (€)",
                    "einmaleinlage_mean": "Ø Einmaleinlage (€)",
                    "entlastung_mean": "Ø Entlastung (€/Mon)",
                })

                # Runden
                for c in agg_lim.columns:
                    if agg_lim[c].dtype in [np.float64, np.float32]:
                        agg_lim[c] = agg_lim[c].round(1 if "%" in c or "Anteil" in c else 0)

                # Gruppierungsspalten umbenennen
                rename = {"tarifwerk": "Tarifwerk", "tarifart": "Tarifart", "tarif_id": "Tarif",
                          "geschlecht": "Geschlecht", "altersgruppe": "Altersgruppe"}
                agg_lim = agg_lim.rename(columns={k: v for k, v in rename.items() if k in agg_lim.columns})

                st.dataframe(
                    agg_lim.sort_values("Σ Einmaleinlage (€)", ascending=False),
                    hide_index=True, use_container_width=True,
                    height=min(500, 40 + len(agg_lim) * 35),
                )

            st.markdown("---")

            # --- Export ---
            with st.expander("📥 Export"):
                df_export = df_lim_aktuell.copy()
                df_export["erhoehung_limitiert_pct"] = res["erhoehung_limitiert_pct"].values
                df_export["erhoehung_limitiert_abs"] = res["erhoehung_limitiert_abs"].values
                df_export["praemie_limitiert"] = res["praemie_limitiert"].values
                df_export["einmaleinlage"] = res["einmaleinlage"].values
                df_export["limitiert"] = res["limitiert"].values

                st.info(f"{len(df_export):,} Zeilen mit Limitierungsergebnis.")
                if st.button("CSV erzeugen", key="lim_csv"):
                    csv_bytes = df_export.to_csv(index=False, sep=";").encode("utf-8")
                    st.download_button("⬇️ Herunterladen", data=csv_bytes,
                                       file_name="bestand_limitiert.csv", mime="text/csv")