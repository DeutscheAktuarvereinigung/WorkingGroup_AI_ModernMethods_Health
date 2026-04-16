#!/usr/bin/env python3
"""
PKV-Limitierungstool — Streamlit App
=====================================
Tab 1: Bestandsanalyse
Tab 2: Limitierungsrechnung

Nutzung:
  streamlit run app.py
"""

import logging
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ── Logging-Konfiguration ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from ui.theme import (
    DAV_BLAU_AKZENT,
    DAV_BLAU_DUNKEL,
    DAV_GRUEN,
    DAV_ORANGE,
    PALETTE_GROSS,
    PLOTLY_LAYOUT,
    apply_theme,
    get_logo_src,
)
from services.data_loader import lade_csv as lade_csv_service
from services.bestandsanalyse import (
    berechne_hist_daten as berechne_hist_daten_service,
    berechne_interaktive_statistik as berechne_interaktive_statistik_service,
    berechne_kpis as berechne_kpis_service,
    berechne_treemap_daten as berechne_treemap_daten_service,
    df_hash,
    farb_map_dynamisch as farb_map_dynamisch_service,
    formatiere_euro,
    geschlecht_label,
)
from services.limitierung import (
    berechne_barwertfaktoren as berechne_barwertfaktoren_service,
    berechne_barwertfaktoren_befristet as berechne_barwertfaktoren_befristet_service,
    berechne_limitierung as berechne_limitierung_service,
    berechne_sensitivitaet as berechne_sensitivitaet_service,
)
from services.optimierung import (
    berechne_gitter as berechne_gitter_service,
    berechne_optimale_budgetstufen as berechne_optimale_budgetstufen_service,
    finde_knickpunkt as finde_knickpunkt_service,
    berechne_pareto_front as berechne_pareto_front_service,
)
from app.pages import bestandsanalyse, limitierung



# =============================================================================
# SEITENKONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="PKV-Limitierungstool",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()
DAV_LOGO_SRC = get_logo_src("dav_logo.svg")

GRUPPIER_DIMENSIONEN = {
    "Tarifwerk": "tarifwerk",
    "Tarifart": "tarifart",
    "Tarif": "tarif_id",
    "Geschlecht": "geschlecht",
    "Altersgruppe": "altersgruppe",
    "Hist. Belastung": "hist_belastung",
}

def _geschlecht_label(code):
    return geschlecht_label(code)

def _farb_map_dynamisch(df, spalte):
    return farb_map_dynamisch_service(df, spalte, PALETTE_GROSS)

@st.cache_data(show_spinner="Lade Daten …")
def lade_csv(datei, name: str):
    try:
        df, warnungen = lade_csv_service(datei, name)
        return df, warnungen
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

@st.cache_data(show_spinner=False)
def berechne_kpis(_hash, df):
    return berechne_kpis_service(df)

@st.cache_data(show_spinner=False)
def berechne_treemap_daten(_hash, df, farb_spalte):
    return berechne_treemap_daten_service(df, farb_spalte)

@st.cache_data(show_spinner=False)
def berechne_interaktive_statistik(_hash, df, gruppen_spalten_tuple):
    return berechne_interaktive_statistik_service(df, gruppen_spalten_tuple)

@st.cache_data(show_spinner=False)
def berechne_hist_daten(_hash, df, farb_spalte, wert_spalte):
    return berechne_hist_daten_service(df, farb_spalte, wert_spalte)


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
                df_b, w_b = lade_csv(f"{pfad}/bestand.csv", "bestand")
                df_t, w_t = lade_csv(f"{pfad}/tarife.csv", "tarife")
                df_a, w_a = lade_csv(f"{pfad}/ausscheideordnung.csv", "ao")
                st.session_state["df_bestand"] = df_b
                st.session_state["df_tarife"] = df_t
                st.session_state["df_ao"] = df_a
                st.session_state.pop("df_gefiltert", None)
                st.success(f"✓ {len(df_b):,} Versicherte geladen")
                alle_warnungen = w_b + w_t + w_a
                for w in alle_warnungen:
                    st.warning(f"⚠️ {w}")
                logger.info("Daten geladen: %d Versicherte, %d Warnungen", len(df_b), len(alle_warnungen))
            except FileNotFoundError as e:
                st.error(f"Datei nicht gefunden: {e}")
            except Exception as e:
                st.error(f"Fehler: {e}")
    else:
        f_b = st.file_uploader("bestand.csv", type="csv", key="up_b")
        f_t = st.file_uploader("tarife.csv", type="csv", key="up_t")
        f_a = st.file_uploader("ausscheideordnung.csv", type="csv", key="up_a")
        if f_b and f_t and f_a:
            df_b, w_b = lade_csv(f_b, "bestand")
            df_t, w_t = lade_csv(f_t, "tarife")
            df_a, w_a = lade_csv(f_a, "ao")
            st.session_state["df_bestand"] = df_b
            st.session_state["df_tarife"] = df_t
            st.session_state["df_ao"] = df_a
            st.session_state.pop("df_gefiltert", None)
            st.success(f"✓ {len(df_b):,} Versicherte geladen")
            alle_warnungen = w_b + w_t + w_a
            for w in alle_warnungen:
                st.warning(f"⚠️ {w}")
            logger.info("Daten geladen (Upload): %d Versicherte, %d Warnungen", len(df_b), len(alle_warnungen))

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

            e_abs_max = float(np.ceil(df_bestand["erhoehung_absolut"].max() / 10) * 10)
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
    bestandsanalyse.render_bestandsanalyse(
        df_gefiltert,
        _farb_map_dynamisch,
        _geschlecht_label,
        GRUPPIER_DIMENSIONEN,
        berechne_kpis,
        berechne_treemap_daten,
        berechne_interaktive_statistik,
        berechne_hist_daten,
    )


# =============================================================================
# TAB 2: LIMITIERUNGSRECHNUNG
# =============================================================================

@st.cache_data(show_spinner="Berechne Leibrentenbarwerte …")
def berechne_barwertfaktoren(_ao_hash, df_ao, df_tarife):
    return berechne_barwertfaktoren_service(df_ao, df_tarife)

@st.cache_data(show_spinner="Berechne befristete Barwerte …")
def berechne_barwertfaktoren_befristet(_ao_hash, df_ao, df_tarife, laufzeit_jahre):
    return berechne_barwertfaktoren_befristet_service(df_ao, df_tarife, laufzeit_jahre)

@st.cache_data(show_spinner=False)
def berechne_limitierung(_hash, df, df_bwf, regeln, modus, laufzeit_jahre):
    return berechne_limitierung_service(df, df_bwf, regeln, modus, laufzeit_jahre)

@st.cache_data(show_spinner=False)
def berechne_sensitivitaet(_hash, df, df_bwf, regeln_basis, modus, laufzeit):
    return berechne_sensitivitaet_service(df, df_bwf, regeln_basis, modus, laufzeit)

@st.cache_data(show_spinner="Berechne Optimierungsgitter …")
def berechne_gitter(erh_pct, erh_abs, praemie_alt, bwf_vals, opt_modus, opt_gewicht_pct):
    return berechne_gitter_service(erh_pct, erh_abs, praemie_alt, bwf_vals, opt_modus, opt_gewicht_pct)

def berechne_optimale_budgetstufen(df_gitter, n_versicherte, budget_max, schrittweite_mio):
    return berechne_optimale_budgetstufen_service(df_gitter, n_versicherte, budget_max, schrittweite_mio)

def finde_knickpunkt(df_opt):
    return finde_knickpunkt_service(df_opt)

def berechne_pareto_front(df_gitter, budget_eur):
    return berechne_pareto_front_service(df_gitter, budget_eur)


with tab_limitierung:
    limitierung.render_limitierung(
        df_bestand,
        df_gefiltert,
        st.session_state.get("df_ao"),
        st.session_state.get("df_tarife"),
        GRUPPIER_DIMENSIONEN,
        berechne_barwertfaktoren,
        berechne_barwertfaktoren_befristet,
        berechne_limitierung,
        berechne_sensitivitaet,
        formatiere_euro,
        berechne_gitter,
        berechne_optimale_budgetstufen,
        finde_knickpunkt,
        berechne_pareto_front,
    )
