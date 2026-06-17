#!/usr/bin/env python3
"""
PKV-Limitierungstool — Streamlit App
=====================================
Tab 1: Bestandsanalyse
Tab 2: Mittelkonfiguration
Tab 3: Limitierungsrechnung

Nutzung:
  streamlit run app.py
"""

import logging
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

# ── Logging-Konfiguration ───────────────────────────────────────────────────
# Ausgabe auf INFO-Level mit Zeitstempel, Level, Modulname und Meldung
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── UI-Theme und Farbpalette der DAV ────────────────────────────────────────
from ui.theme import (
    DAV_BLAU_AKZENT,    # Akzentfarbe (hellblau)
    DAV_BLAU_DUNKEL,    # Dunkles DAV-Blau (Hintergrund/Header)
    DAV_GRUEN,          # Grün für positive Kennzahlen
    DAV_ORANGE,         # Orange für Warnhinweise
    PALETTE_GROSS,      # Erweiterte Farbpalette für Diagramme
    PLOTLY_LAYOUT,      # Standardlayout für alle Plotly-Charts
    apply_theme,        # Wendet globales CSS-Theme auf Streamlit an
    get_logo_src,       # Gibt das DAV-Logo als Base64-Data-URI zurück
)

# ── Service-Importe (Business-Logik, von UI getrennt) ───────────────────────
from services.data_loader import lade_csv as lade_csv_service   # CSV-Parsing und Validierung
from services.snowflake_loader import lade_snowflake_schema as lade_snowflake_schema_service

from services.bestandsanalyse import (
    berechne_hist_daten as berechne_hist_daten_service,                         # Histogramm-Rohdaten
    berechne_interaktive_statistik as berechne_interaktive_statistik_service,   # Gruppenstatistiken
    berechne_kpis as berechne_kpis_service,                                     # Kennzahlen (KPIs)
    berechne_treemap_daten as berechne_treemap_daten_service,                   # Daten für Treemap-Chart
    df_hash,            # Erzeugt Hash-Wert eines DataFrames für st.cache_data
    farb_map_dynamisch as farb_map_dynamisch_service,   # Dynamische Farb-Zuweisung je Spalte
    formatiere_euro,    # Hilfsfunktion: Zahl → "1.234,56 €"
    geschlecht_label,   # Hilfsfunktion: Codierwert → lesbarer Text (z. B. "1" → "Männlich")
)

from services.limitierung import (
    berechne_barwertfaktoren as berechne_barwertfaktoren_service,                       # Leibrentenbarwerte (unbefristet)
    berechne_barwertfaktoren_befristet as berechne_barwertfaktoren_befristet_service,   # Barwerte mit festem Zeithorizont
    berechne_limitierung as berechne_limitierung_service,       # Kernrechnung der Limitierung
    berechne_limitierung_person as berechne_limitierung_person_service,   # Limitierung mit Personenebene
    berechne_sensitivitaet as berechne_sensitivitaet_service,   # Sensitivitätsanalyse über Parameterbereich
)

from services.optimierung import (
    berechne_gitter as berechne_gitter_service,                                 # 2-D Parametergitter (Erhöhung % × €)
    berechne_optimale_budgetstufen as berechne_optimale_budgetstufen_service,   # Pareto-optimale Budgetstufen
    finde_knickpunkt as finde_knickpunkt_service,       # Knickpunkt auf der Pareto-Front
    berechne_pareto_front as berechne_pareto_front_service,     # Pareto-Front für gegebenes Budget
)

# ── Seiten-Module (UI-Rendering) ─────────────────────────────────────────────
from app.pages import bestandsanalyse, limitierung, mittelkonfiguration



# =============================================================================
# SEITENKONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="PKV-Limitierungstool",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()  # Globales CSS-Styling (Farben, Schriftarten) aktivieren
DAV_LOGO_SRC = get_logo_src("dav_logo.svg")  # Logo als eingebettete Base64-URI laden

# Mapping: Anzeigename → DataFrame-Spaltenname für alle Gruppierungsoptionen
GRUPPIER_DIMENSIONEN = {
    "Tarifwerk": "tarifwerk",
    "Tarifart": "tarifart",
    "Tarif": "tarif_id",
    "Geschlecht": "geschlecht",
    "Altersgruppe": "altersgruppe",
    "Hist. Belastung": "hist_belastung",
    "Person": "person_id",
}

# ── Adapter-Funktionen (leiten an Service-Schicht weiter) ───────────────────

def _geschlecht_label(code):
    # Konvertiert numerischen Geschlechtscode in lesbaren Label (für Multiselect)
    return geschlecht_label(code)

def _farb_map_dynamisch(df, spalte):
    # Weist jeder eindeutigen Ausprägung in `spalte` eine Farbe aus PALETTE_GROSS zu
    return farb_map_dynamisch_service(df, spalte, PALETTE_GROSS)

# ── Gecachte Wrapper: Ergebnisse werden bei gleichem Input wiederverwendet ──

@st.cache_data(show_spinner="Lade Daten …")
def lade_csv(datei, name: str):
    # Liest CSV ein und validiert Pflichtfelder; stoppt die App bei Formatfehlern
    try:
        df, warnungen = lade_csv_service(datei, name)
        return df, warnungen
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

@st.cache_data(show_spinner="Lade Daten aus Snowflake …", ttl=600)
def lade_snowflake_schema(database, schema, bestand_tabelle, tarife_tabelle, ao_tabelle, mittelquellen_tabelle):
    # Laedt Tabellen aus einem Snowflake-Schema und validiert den bestehenden Datenvertrag
    try:
        return lade_snowflake_schema_service(
            database=database,
            schema=schema,
            bestand_tabelle=bestand_tabelle,
            tarife_tabelle=tarife_tabelle,
            ao_tabelle=ao_tabelle,
            mittelquellen_tabelle=mittelquellen_tabelle,
        )
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

def speichere_geladene_daten(df_b, df_t, df_a, df_m):
    # DataFrames im Session-State speichern (app-weite Datenhaltung)
    st.session_state["df_bestand"] = df_b
    st.session_state["df_tarife"] = df_t
    st.session_state["df_ao"] = df_a
    st.session_state["df_mittelquellen_config_geladen"] = df_m
    # Gefilterten Bestand zurücksetzen, damit kein veralteter Filter verbleibt
    st.session_state.pop("df_gefiltert", None)
    st.session_state.pop("mittelquellen_config", None)

@st.cache_data(show_spinner=False)
def berechne_kpis(_hash, df):
    # _hash dient nur als Cache-Key (df selbst ist nicht hashbar)
    return berechne_kpis_service(df)

@st.cache_data(show_spinner=False)
def berechne_treemap_daten(_hash, df, farb_spalte):
    return berechne_treemap_daten_service(df, farb_spalte)

@st.cache_data(show_spinner=False)
def berechne_interaktive_statistik(_hash, df, gruppen_spalten_tuple):
    # gruppen_spalten_tuple muss ein Tuple sein (Listen sind nicht hashbar für st.cache_data)
    return berechne_interaktive_statistik_service(df, gruppen_spalten_tuple)

@st.cache_data(show_spinner=False)
def berechne_hist_daten(_hash, df, farb_spalte, wert_spalte):
    return berechne_hist_daten_service(df, farb_spalte, wert_spalte)


# =============================================================================
# SIDEBAR
# =============================================================================

with st.sidebar:
    # DAV-Logo als zentrierter Header mit dunklem Hintergrund
    st.markdown(f"""
    <div style="text-align:center; padding:8px 0 12px 0; border-bottom:2px solid #0078C8; margin-bottom:16px;">
        <div style="display:inline-block; background:#003056; padding:8px 12px; border-radius:8px;">
            <img src="{DAV_LOGO_SRC}"
                 alt="DAV" style="height:40px; width:auto; display:block;">
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("## 📂 Datenimport")

    # Auswahl: Demo-Daten aus lokalem Verzeichnis, manuelle CSV-Uploads oder Snowflake-Schema
    upload_modus = st.radio(
        "Datenquelle",
        ["Mock-Daten (lokaler Pfad)", "CSV-Upload", "Snowflake-Schema"],
        index=0,
    )

    if upload_modus == "Mock-Daten (lokaler Pfad)":
        pfad = st.text_input("Verzeichnis", value="./output_daten")
        if st.button("Daten laden", type="primary", use_container_width=True):
            try:
                # Alle drei Datendateien einlesen
                df_b, w_b = lade_csv(f"{pfad}/bestand.csv", "bestand")
                df_t, w_t = lade_csv(f"{pfad}/tarife.csv", "tarife")
                df_a, w_a = lade_csv(f"{pfad}/ausscheideordnung.csv", "ao")
                try:
                    df_m, w_m = lade_csv(f"{pfad}/mittelquellen_config.csv", "mittelquellen")
                except FileNotFoundError:
                    df_m, w_m = None, []
                speichere_geladene_daten(df_b, df_t, df_a, df_m)
                st.success(f"✓ {len(df_b):,} Versicherte geladen")
                alle_warnungen = w_b + w_t + w_a + w_m
                for w in alle_warnungen:
                    st.warning(f"⚠️ {w}")
                logger.info("Daten geladen: %d Versicherte, %d Warnungen", len(df_b), len(alle_warnungen))
            except FileNotFoundError as e:
                st.error(f"Datei nicht gefunden: {e}")
            except Exception as e:
                st.error(f"Fehler: {e}")
    elif upload_modus == "CSV-Upload":
        # Upload-Widgets für alle drei Pflichtdateien
        f_b = st.file_uploader("bestand.csv", type="csv", key="up_b")
        f_t = st.file_uploader("tarife.csv", type="csv", key="up_t")
        f_a = st.file_uploader("ausscheideordnung.csv", type="csv", key="up_a")
        f_m = st.file_uploader("mittelquellen_config.csv (optional)", type="csv", key="up_m")
        if f_b and f_t and f_a:  # Erst laden wenn alle drei Dateien vorhanden sind
            upload_signature = tuple(
                (getattr(f, "name", None), getattr(f, "size", None))
                for f in [f_b, f_t, f_a, f_m]
            )
            daten_geaendert = st.session_state.get("_upload_data_signature") != upload_signature
            df_b, w_b = lade_csv(f_b, "bestand")
            df_t, w_t = lade_csv(f_t, "tarife")
            df_a, w_a = lade_csv(f_a, "ao")
            if f_m:
                df_m, w_m = lade_csv(f_m, "mittelquellen")
            else:
                df_m, w_m = None, []
            if daten_geaendert:
                speichere_geladene_daten(df_b, df_t, df_a, df_m)
                st.session_state["_upload_data_signature"] = upload_signature
            else:
                st.session_state["df_bestand"] = df_b
                st.session_state["df_tarife"] = df_t
                st.session_state["df_ao"] = df_a
                st.session_state["df_mittelquellen_config_geladen"] = df_m
            st.success(f"✓ {len(df_b):,} Versicherte geladen")
            alle_warnungen = w_b + w_t + w_a + w_m
            for w in alle_warnungen:
                st.warning(f"⚠️ {w}")
            logger.info("Daten geladen (Upload): %d Versicherte, %d Warnungen", len(df_b), len(alle_warnungen))
    else:
        st.caption(
            "Lädt Tabellen über die aktive Snowflake-Session. "
            "Schema- und Tabellennamen werden als Identifier validiert."
        )
        sf_database = st.text_input("Datenbank (optional)", value="")
        sf_schema = st.text_input("Schema", value="PKV_LIMITIERUNG")
        sf_bestand = st.text_input("Tabelle Bestand", value="BESTAND")
        sf_tarife = st.text_input("Tabelle Tarife", value="TARIFE")
        sf_ao = st.text_input("Tabelle Ausscheideordnung", value="AUSSCHEIDEORDNUNG")
        sf_mittel = st.text_input("Tabelle Mittelquellen (optional)", value="MITTELQUELLEN_CONFIG")
        if st.button("Daten aus Snowflake laden", type="primary", use_container_width=True):
            df_b, df_t, df_a, df_m, alle_warnungen = lade_snowflake_schema(
                sf_database.strip() or None,
                sf_schema.strip(),
                sf_bestand.strip(),
                sf_tarife.strip(),
                sf_ao.strip(),
                sf_mittel.strip(),
            )
            speichere_geladene_daten(df_b, df_t, df_a, df_m)
            st.success(f"✓ {len(df_b):,} Versicherte aus Snowflake geladen")
            for w in alle_warnungen:
                st.warning(f"⚠️ {w}")
            logger.info("Daten geladen (Snowflake): %d Versicherte, %d Warnungen", len(df_b), len(alle_warnungen))

    df_bestand = st.session_state.get("df_bestand")  # Aktuell geladener Gesamtbestand

    if df_bestand is not None:
        st.markdown("---")
        st.markdown("## 🔍 Filter")

        # Filterformular: alle Änderungen werden erst bei "Filter anwenden" wirksam
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
                format_func=_geschlecht_label,  # Numerischer Code → lesbarer Text
            )

            a_min, a_max = int(df_bestand["alter"].min()), int(df_bestand["alter"].max())
            gew_alter = st.slider("Altersbereich", a_min, a_max, (a_min, a_max))

            st.markdown("**Erhöhungsfilter**")
            # Obergrenze dynamisch aus den Daten ableiten (auf ganze Zahl aufrunden)
            e_pct_max = float(np.ceil(df_bestand["erhoehung_prozent"].max()))
            gew_erh_pct = st.slider("Erhöhung (%)", 0.0, e_pct_max, (0.0, e_pct_max), step=1.0, format="%.0f%%")

            e_abs_max = float(np.ceil(df_bestand["erhoehung_absolut"].max() / 10) * 10)  # Auf 10 € aufrunden
            gew_erh_abs = st.slider("Erhöhung (€/Monat)", 0.0, e_abs_max,
                                    (0.0, e_abs_max), step=5.0, format="%.0f €")

            # Logik-Verknüpfung zwischen %-Filter und €-Filter wählbar
            erh_logik = st.radio("Verknüpfung % und €",
                                 ["UND (beide müssen zutreffen)", "ODER (eine reicht)"],
                                 index=0, horizontal=True)

            filter_btn = st.form_submit_button("🔍 Filter anwenden", use_container_width=True, type="primary")

        if filter_btn:
            # Basismaske: strukturelle Merkmale (Tarifwerk, -art, ID, Geschlecht, Alter)
            maske_basis = (
                df_bestand["tarifwerk"].isin(gew_tw if gew_tw else alle_tw)
                & df_bestand["tarifart"].isin(gew_ta if gew_ta else alle_ta)
                & df_bestand["tarif_id"].isin(gew_tarife if gew_tarife else alle_tarife)
                & df_bestand["geschlecht"].isin(gew_geschl if gew_geschl else alle_geschl)
                & df_bestand["alter"].between(gew_alter[0], gew_alter[1])
            )
            maske_pct = df_bestand["erhoehung_prozent"].between(gew_erh_pct[0], gew_erh_pct[1])
            maske_abs = df_bestand["erhoehung_absolut"].between(gew_erh_abs[0], gew_erh_abs[1])
            # Erhöhungsmasken je nach gewählter Logik kombinieren
            maske_erh = (maske_pct & maske_abs) if "UND" in erh_logik else (maske_pct | maske_abs)
            st.session_state["df_gefiltert"] = df_bestand[maske_basis & maske_erh]

        # Inizialisierung: beim ersten Laden ohne Filter den vollen Bestand verwenden
        if "df_gefiltert" not in st.session_state and df_bestand is not None:
            st.session_state["df_gefiltert"] = df_bestand

        df_gef = st.session_state.get("df_gefiltert")
        if df_gef is not None:
            st.markdown("---")
            # Zeigt an wie viele Datensätze den aktiven Filtern entsprechen
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

df_gefiltert = st.session_state.get("df_gefiltert")  # Aktuell gefilterter Bestand
df_bestand = st.session_state.get("df_bestand")     # Vollständiger Bestand (ungefiltert)

# Sicherheitsabfrage: App bricht mit Hinweis ab wenn noch keine Daten geladen wurden
if df_gefiltert is None or df_bestand is None:
    st.info("Bitte laden Sie die Daten über die Sidebar (links).")
    st.stop()

# Drei Haupt-Tabs: Bestandsübersicht, Mittelkonfiguration und Limitierungsrechnung
tab_bestand, tab_mittel, tab_limitierung = st.tabs([
    "📊 Bestandsanalyse",
    "💶 Mittelkonfiguration",
    "⚖️ Limitierungsrechnung",
])


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
# TAB 2: MITTELKONFIGURATION
# =============================================================================

with tab_mittel:
    mittelkonfiguration.render_mittelkonfiguration(
        df_bestand,
        st.session_state.get("df_mittelquellen_config_geladen"),
    )


# =============================================================================
# TAB 3: LIMITIERUNGSRECHNUNG
# =============================================================================

@st.cache_data(show_spinner="Berechne Leibrentenbarwerte …")
def berechne_barwertfaktoren(_ao_hash, df_ao, df_tarife):
    # Berechnet unbefristete Leibrentenbarwerte auf Basis der Ausscheideordnung
    return berechne_barwertfaktoren_service(df_ao, df_tarife)

@st.cache_data(show_spinner="Berechne befristete Barwerte …")
def berechne_barwertfaktoren_befristet(_ao_hash, df_ao, df_tarife, laufzeit_jahre):
    # Wie oben, jedoch mit festem Zeithorizont (z. B. für Rentengarantie)
    return berechne_barwertfaktoren_befristet_service(df_ao, df_tarife, laufzeit_jahre)

@st.cache_data(show_spinner=False)
def berechne_limitierung(_hash, df, df_bwf, regeln, modus, laufzeit_jahre):
    # Kernrechnung: wendet Limitierungsregeln auf jeden Versicherten an
    return berechne_limitierung_service(df, df_bwf, regeln, modus, laufzeit_jahre)

@st.cache_data(show_spinner="Berechne Personen-Limitierung …")
def berechne_limitierung_person(_hash, df, df_bwf, regeln, personen_regel, modus,
                               laufzeit_jahre, reihenfolge, verteilungsmodus):
    return berechne_limitierung_person_service(
        df, df_bwf, regeln, personen_regel, modus, laufzeit_jahre,
        reihenfolge=reihenfolge, verteilungsmodus=verteilungsmodus,
    )

@st.cache_data(show_spinner=False)
def berechne_sensitivitaet(_hash, df, df_bwf, regeln_basis, modus, laufzeit):
    # Variiert einen Parameter über einen Wertebereich und berechnet je eine Limitierung
    return berechne_sensitivitaet_service(df, df_bwf, regeln_basis, modus, laufzeit)

@st.cache_data(show_spinner="Berechne Optimierungsgitter …")
def berechne_gitter(erh_pct, erh_abs, praemie_alt, bwf_vals, opt_modus, opt_gewicht_pct):
    # Erzeugt ein 2-D Gitter über alle Kombinationen von %-Schwelle und €-Schwelle
    return berechne_gitter_service(erh_pct, erh_abs, praemie_alt, bwf_vals, opt_modus, opt_gewicht_pct)

def berechne_optimale_budgetstufen(df_gitter, n_versicherte, budget_max, schrittweite_mio):
    # Ermittelt für jede Budgetstufe die effizienteste Parameterkombination
    return berechne_optimale_budgetstufen_service(df_gitter, n_versicherte, budget_max, schrittweite_mio)

def finde_knickpunkt(df_opt):
    # Identifiziert den Knickpunkt (Elbow) auf der Pareto-Front
    return finde_knickpunkt_service(df_opt)

def berechne_pareto_front(df_gitter, budget_eur):
    # Filtert das Gitter auf Pareto-optimale Punkte für ein gegebenes Gesamtbudget
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
        berechne_limitierung_person,
        berechne_sensitivitaet,
        formatiere_euro,
        berechne_gitter,
        berechne_optimale_budgetstufen,
        finde_knickpunkt,
        berechne_pareto_front,
    )
