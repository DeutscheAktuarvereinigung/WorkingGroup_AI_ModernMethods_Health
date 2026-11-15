"""
TB-Validierung – Oberfläche für die Live-Vorführung
====================================================

Streamlit-App für die DAV/DGVFM-Herbsttagung. Sie zeigt, wie die
automatisierte Prüfung einer Technischen Berechnungsgrundlage (TB) abläuft –
Schritt für Schritt, mit Statusfarben UND Piktogrammen.

Prozesskette oben:
    Prüfkatalog – alle Checks (feste Regeln und Sprachmodell) zum Auswählen
    Prüflauf    – die ausgewählten Checks laufen sichtbar nacheinander
    Befunde     – jeder Befund mit der markierten Passage aus der TB, auf
                  Wunsch neben derselben Stelle der jeweils anderen TB
    Abgleich    – Vergleich mit dem Fehlerprotokoll (F01–F13) bzw. Ergebnis
                  der Gegenprobe auf der fehlerfreien TB

Darstellung: feste Grundschrift (16 px × Faktor aus der Seitenleiste), alle
Maße in rem. Für die Leinwand vergrößert der Vortragende mit dem Browser-Zoom
(Strg +); bei 150 % und 200 % bleibt alles lesbar, notfalls wird senkrecht
gescrollt. Schrift Roboto (lokal unter static/fonts, siehe config.toml),
Piktogramme aus der Schrift „Material Symbols Rounded“, die Streamlit
mitliefert (beides ohne Internet). Keine abgerundeten Ecken außer bei den
kreisrunden Status-Symbolen.

Zustand: Einstellungen und Ergebnisse liegen zusätzlich in einem Speicher im
Serverprozess (st.cache_resource) und überstehen ein Neuladen der Seite.
Während eines Prüflaufs sind Dokument-Umschalter, Prozesskette und Regler
gesperrt; ein abgebrochener Lauf wird beim nächsten Aufbau gemeldet.

Die Prüflogik steckt in engine.py (führt die Zellen des Validierungsnotebooks
aus), die Fundstellen-Suche in fundstellen.py und der Abgleich mit dem
Fehlerprotokoll in fehlerprotokoll.py.

Start (im Ordner gui):   python -m streamlit run app.py
"""
from __future__ import annotations

import html
import re
import sys
import threading
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True        # keine __pycache__-Ordner im (Drive-)Repo
GUI_ORDNER = Path(__file__).resolve().parent
if str(GUI_ORDNER) not in sys.path:
    sys.path.insert(0, str(GUI_ORDNER))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="TB-Validierung", layout="wide",
                   initial_sidebar_state="collapsed")

try:
    import engine            # noqa: E402
    import fehlerprotokoll   # noqa: E402
    import fundstellen       # noqa: E402
except Exception:            # z. B. fehlendes Paket auf dem Vorführrechner
    print(traceback.format_exc(), file=sys.stderr)
    st.error("Die Prüfmodule konnten nicht geladen werden. Bitte die Installation "
             "prüfen (siehe README; Einzelheiten in der Konsole).")
    st.stop()


# =============================================================================
# Konstanten
# =============================================================================
DOK_TITEL = {
    "fehlerhaft": "TB mit 13 eingebauten Fehlern",
    "fehlerfrei": "Fehlerfreie TB (Gegenprobe)",
}
SCHRITTE = {1: "Prüfkatalog", 2: "Prüflauf", 3: "Befunde", 4: "Abgleich"}
METHODE = {"deterministisch": "feste Regel", "LLM": "Sprachmodell"}

# Piktogramme: Namen aus „Material Symbols Rounded“ (eine Familie für alles –
# in eigenem HTML über icon(), in Streamlit-Beschriftungen als ":material/…:")
ICON = {
    "schritt": {1: "checklist", 2: "play_arrow", 3: "find_in_page", 4: "fact_check"},
    "dokument": {"fehlerhaft": "bug_report", "fehlerfrei": "verified"},
    "regeln": "rule", "ki": "psychology", "vergleich": "compare", "seite": "description",
    "start": "play_arrow", "weiter": "arrow_forward", "zurueck_pfeil": "chevron_left",
    "vor_pfeil": "chevron_right", "zeigen": "arrow_forward",
}


def mat(name: str) -> str:
    """Piktogramm für Streamlit-Beschriftungen (Knöpfe, Checkboxen, Umschalter)."""
    return f":material/{name}:"


# Status eines Checks: (Piktogramm, Anzeigetext, CSS-Klasse). Die Piktogramme
# stehen weiß in einem farbigen Kreis (sym_html) – wie gefüllte Symbole.
STATUS = {
    "BESTANDEN": ("check", "bestanden", "ok"),
    "WARNUNG": ("priority_high", "Warnung", "warn"),
    "FEHLER": ("close", "Fehler", "fehler"),
    "ÜBERSPRUNGEN": ("remove", "übersprungen", "skip"),
    "FEHLGESCHLAGEN": ("bolt", "fehlgeschlagen", "kaputt"),
}
# Schwere eines Befunds: (Piktogramm, Anzeigetext, CSS-Klasse)
SCHWERE = {
    "FEHLER": ("close", "Fehler", "fehler"),
    "WARNUNG": ("priority_high", "Warnung", "warn"),
}
# Fester Satz für fehlgeschlagene Checks auf der Leinwand (der technische Grund
# steht nur in der Seitenleiste und in der Konsole)
FEHLGESCHLAGEN_TEXT = "Check konnte nicht ausgeführt werden."
ABBRUCH_TEXT = "Prüfung wurde abgebrochen – bitte neu starten."


def _live_tempo_moeglich() -> bool:
    """Kann die Prüfmaschine den Notfallmodus im Tempo eines Live-Laufs
    abspielen (notfall_verzoegerung_s="live")? Ältere Stände kennen nur Zahlen."""
    plan = getattr(engine, "_verzoegerungsplan", None)
    if plan is None:
        return False
    try:
        plan("live")
        return True
    except Exception:
        return False


# Simulierte Antwortzeit im Notfallmodus: "live" = gemessene Antwortzeiten
# eines echten Laufs je Check (der Notfall ist am Tempo nicht zu erkennen).
NOTFALL_TEMPO_STANDARD = "live" if _live_tempo_moeglich() else 6.0
NOTFALL_TEMPI = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0]
if NOTFALL_TEMPO_STANDARD == "live":
    NOTFALL_TEMPI.append("live")
else:
    NOTFALL_TEMPI = sorted(set(NOTFALL_TEMPI) | {NOTFALL_TEMPO_STANDARD})

# Startwerte der Einstellungen (Seitenleiste). Tests können sie vor dem ersten
# Aufbau über st.session_state überschreiben. Nach einem Neuladen der Seite
# gelten die zuletzt eingestellten Werte (Vorführstand, siehe unten).
VORGABEN = {
    "modell": engine.STANDARDMODELL,
    "notfall": False,                  # Notfallschalter: gespeicherte Antworten
    "pause_s": 0.5,                    # Mindestdauer je Check in der Anzeige
    "max_parallel": int(getattr(engine, "MAX_PARALLEL_STANDARD", 24)),
    "schrift_faktor": 1.0,             # Faktor auf die Grundschrift (16 px)
    "notfall_verzoegerung_s": NOTFALL_TEMPO_STANDARD,
}
MAX_PARALLEL_HOECHSTENS = 64           # Obergrenze in der Seitenleiste
# Stufen der Regler in der Seitenleiste (Pause je Check, Schriftfaktor)
PAUSEN = [round(i / 10, 1) for i in range(31)]                 # 0,0 … 3,0 s
SCHRIFT_FAKTOREN = [round(0.6 + i * 0.05, 2) for i in range(21)]   # 0,60 … 1,60
BILDBREITE_PX = 1800                   # Breite der gerenderten Passagen

# Sitzungswerte, die ein Neuladen der Seite überstehen (Einstellungen,
# Ergebnisse je Dokument, Auswahl und Ansicht). Ein laufender Prüflauf gehört
# nicht dazu – er wird nach dem Neuladen als abgebrochen gemeldet.
GEMERKT = ("modell", "notfall", "pause_s", "max_parallel", "schrift_faktor",
           "notfall_verzoegerung_s", "laeufe", "befund_idx", "auswahl", "dok_wahl",
           "schritt", "_dauer_vergleich")


# =============================================================================
# Darstellung (CSS) – ein Gestaltungssystem: Farb- und Abstands-Tokens als
# CSS-Variablen, Schrift Roboto, Piktogramme über icon()/sym_html()
# =============================================================================
# Feste Grundschrift 16 px × Faktor (Seitenleiste); alle Maße in rem. Der
# Browser-Zoom (Strg +) vergrößert damit die ganze Oberfläche. Untergrenze für
# Nebenzeilen: .85rem. Keine abgerundeten Ecken (theme.baseRadius = "none"
# plus border-radius: 0 für den Rest) – nur die Status-Symbole sind kreisrund.
CSS_VORLAGE = """<style>
:root {
  --schrift-faktor: __FAKTOR__;
  --schrift: Roboto, "Segoe UI", system-ui, sans-serif;
  --icons: "Material Symbols Rounded";
  /* Farben */
  --blau: #00539F; --blau-dunkel: #003B73; --blau-hell: #E3ECF6; --blau-hover: #D2E0F0;
  --ok: #1B7F3B; --ok-hell: #E5F2E9;
  --warn: #E0A200; --warn-text: #5A4200; --warn-hell: #FFF3D1;
  --fehler: #C62828; --fehler-hell: #FBE8E7;
  --skip: #66707D; --skip-hell: #ECEFF2;
  --kaputt: #7B1FA2; --kaputt-hell: #F3E6F7;
  --text: #1A2433; --text-2: #4E5A6B; --text-3: #8A95A5; --titel: #000000;
  --seite: #F3F5F8; --flaeche: #FFFFFF; --linie: #D5DCE5; --linie-fein: #E8EDF2;
  --gesperrt: #E6E9ED; --gesperrt-text: #98A1AD;
  /* Abstände */
  --a1: .25rem; --a2: .5rem; --a3: .75rem; --a4: 1rem; --a5: 1.5rem;
  --pfeil: .85rem;                 /* Tiefe der Pfeilspitze in der Prozesskette */
}
html { font-size: calc(var(--schrift-faktor) * 16px) !important; }
body, [data-testid="stApp"] { font-family: var(--schrift); background: var(--seite); }

/* ---- Keine abgerundeten Ecken (Ausnahme: kreisrunde Status-Symbole) ---- */
*, *::before, *::after { border-radius: 0 !important; }
.sym, [data-testid="stSpinner"] i,
.st-key-befundliste [data-testid="stIconMaterial"] { border-radius: 50% !important; }

/* ---- Piktogramme (Material Symbols Rounded, von Streamlit mitgeliefert) ---- */
.ic { font-family: var(--icons); font-weight: 400; font-style: normal; font-size: 1.25em;
  line-height: 1; letter-spacing: normal; text-transform: none; white-space: nowrap;
  direction: ltr; font-feature-settings: "liga"; -webkit-font-smoothing: antialiased;
  display: inline-block; width: 1em; height: 1em; overflow: hidden; flex: none;
  user-select: none; }
/* Status-Symbol: weißes Piktogramm im farbigen Kreis (wirkt wie gefüllt) */
.sym { display: inline-flex; align-items: center; justify-content: center; width: 1.5rem;
  height: 1.5rem; color: #fff; flex: none; line-height: 1; }
.sym .ic { font-size: 1.05rem; }
.sym.ok { background: var(--ok); } .sym.warn { background: var(--warn); color: #2E2200; }
.sym.fehler { background: var(--fehler); } .sym.skip { background: var(--skip); }
.sym.kaputt { background: var(--kaputt); }
.sym.wartet { background: var(--gesperrt); color: var(--text-3); }
.sym.laeuft { background: transparent; border: .2rem solid #B9CCE6;
  border-top-color: var(--blau); animation: drehen .8s linear infinite; box-sizing: border-box; }
.sym.gross { width: 2rem; height: 2rem; } .sym.gross .ic { font-size: 1.35rem; }
.sym.klein { width: 1.2rem; height: 1.2rem; } .sym.klein .ic { font-size: .85rem; }
@keyframes drehen { to { transform: rotate(360deg); } }
/* Zahlen mit gleich breiten Ziffern (Zähler springen nicht) */
.num, .k-zahl, .zaehler, .lauf-zaehler, .lauf-block-info, .block-zahl, .z-unter,
.abgleich-zahl, .liste-kopf, .fnr { font-variant-numeric: tabular-nums; }

/* ---- Seitenleiste: nur für die Vortragenden, normale Bildschirmschrift ---- */
section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] code,
section[data-testid="stSidebar"] li,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { font-size: 15px !important; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
section[data-testid="stSidebar"] li { font-size: 13.5px !important; }
section[data-testid="stSidebar"] .stButton button p { font-size: 15px !important;
  white-space: normal !important; }

/* ---- Streamlit-Bedienelemente für das Publikum ausblenden ---- */
/* Die Kopfleiste bleibt nur als Träger des Seitenleisten-Knopfs erhalten. */
header[data-testid="stHeader"] { background: transparent !important; pointer-events: none; }
header[data-testid="stHeader"] button { pointer-events: auto; }
/* Die unsichtbare Werkzeugleiste liegt über dem oberen Seitenrand und würde
   sonst Mausklicks auf die hochgescrollte Navigationszeile abfangen. */
[data-testid="stToolbar"], [data-testid="stToolbar"] * { pointer-events: none !important; }
[data-testid="stExpandSidebarButton"], [data-testid="stExpandSidebarButton"] *
{ pointer-events: auto !important; }
[data-testid="stDecoration"], [data-testid="stStatusWidget"], [data-testid="stAppDeployButton"],
[data-testid="stMainMenu"], #MainMenu, footer, [data-testid="stToolbarActions"]
{ display: none !important; }
/* Knopf zum Öffnen der Seitenleiste: unsichtbar oben links, erscheint beim
   Darüberfahren – für die Vortragenden erreichbar, für das Publikum kein Zeichen */
[data-testid="stExpandSidebarButton"] { opacity: 0; transition: opacity .2s; }
[data-testid="stExpandSidebarButton"]:hover,
[data-testid="stExpandSidebarButton"]:focus-visible { opacity: 1; }
/* Regler „Antwortzeit“: Min/Max-Beschriftung entfällt (Wert steht am Griff) */
.st-key-notfall_verzoegerung_s [data-testid="stSliderTickBar"] { display: none !important; }
[data-testid="stMainBlockContainer"], .block-container {
  padding: .9rem 1.5rem 1.5rem 2.6rem !important; max-width: 100% !important; }
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] { gap: var(--a2); }
/* Unsichtbare Behälter für Skripte (Scrollen, Einpassen, Seitenleiste) – samt
   Streamlit-Hülle, sonst entstünde je Behälter ein zusätzlicher Zwischenraum */
.st-key-skript_seite, .st-key-skript_scroll, .st-key-skript_passen,
[data-testid="stLayoutWrapper"]:has(> .st-key-skript_seite),
[data-testid="stLayoutWrapper"]:has(> .st-key-skript_scroll),
[data-testid="stLayoutWrapper"]:has(> .st-key-skript_passen) { display: none !important; }

/* ---- Grundtypografie, Titel ---- */
[data-testid="stMarkdownContainer"] p { font-size: 1rem; }
.kopf { display: flex; align-items: baseline; gap: .55rem; margin: 0; color: var(--titel);
  line-height: 1.2; white-space: nowrap; }
.kopf-titel { font-size: 1.6rem; font-weight: 700; letter-spacing: -.005em; }
.kopf-zusatz { font-size: 1.6rem; font-weight: 400; }
.st-key-kopfleiste { flex-wrap: wrap !important; justify-content: space-between !important;
  row-gap: .4rem !important; }
.dok-label { display: flex; align-items: center; gap: .35rem; font-size: .95rem;
  font-weight: 500; color: var(--text-2); white-space: nowrap; }

/* ---- Knöpfe allgemein ---- */
.stButton button { min-height: 2.4rem; padding: .3rem 1rem; font-weight: 500; box-shadow: none; }
.stButton button p { font-size: 1rem !important; font-weight: 500; white-space: nowrap;
  font-variant-numeric: tabular-nums; }
.stButton button[kind="primary"] { background: var(--blau); border-color: var(--blau); }
.stButton button[kind="primary"]:hover:not(:disabled) { background: var(--blau-dunkel);
  border-color: var(--blau-dunkel); }
/* Gesperrt (z. B. „Prüfung starten“ ohne Auswahl): klar grau, beim Darüberfahren unverändert */
.stButton button[kind="primary"]:disabled,
.stButton button[kind="primary"]:disabled:hover { background: var(--gesperrt);
  border-color: var(--gesperrt); color: var(--gesperrt-text); opacity: 1; }
.stButton button[kind="primary"]:disabled * { color: var(--gesperrt-text); }
.stButton button[kind="secondary"] { background: var(--flaeche); }
[data-testid="stMain"] .stButton [data-testid="stIconMaterial"] { font-size: 1.25em; }

/* ---- Dokument-Umschalter: gewähltes Dokument hellblau gefüllt mit blauem Rand,
   das andere weiß; beim Darüberfahren ändert sich nur die Randfarbe ---- */
.st-key-dok_wahl button { padding: .3rem 1rem !important; min-height: 2.4rem; }
.st-key-dok_wahl button p, .st-key-dok_wahl button div { font-size: 1rem !important;
  font-weight: 500; white-space: nowrap; }
.st-key-dok_wahl [data-testid="stBaseButton-segmented_control"],
.st-key-dok_wahl [data-testid="stBaseButton-segmented_control"]:focus,
.st-key-dok_wahl [data-testid="stBaseButton-segmented_control"]:active {
  background: var(--flaeche) !important; border-color: var(--linie) !important;
  color: var(--text) !important; }
.st-key-dok_wahl [data-testid="stBaseButton-segmented_control"]:hover:not(:disabled) {
  background: var(--flaeche) !important; border-color: var(--blau) !important; }
.st-key-dok_wahl [data-testid="stBaseButton-segmented_controlActive"],
.st-key-dok_wahl [data-testid="stBaseButton-segmented_controlActive"]:hover,
.st-key-dok_wahl [data-testid="stBaseButton-segmented_controlActive"]:focus,
.st-key-dok_wahl [data-testid="stBaseButton-segmented_controlActive"]:active {
  background: var(--blau-hell) !important; border-color: var(--blau) !important;
  color: var(--blau-dunkel) !important; z-index: 1; }
.st-key-dok_wahl [data-testid="stBaseButton-segmented_controlActive"] p { font-weight: 600; }

/* ---- Prozesskette (Schritte als Pfeilboxen, per clip-path) ---- */
.st-key-schrittleiste { margin: .1rem 0 .35rem 0; }
.st-key-schrittleiste [data-testid="stHorizontalBlock"] { gap: 0 !important; }
.st-key-schrittleiste [data-testid="stColumn"] { flex: 1 1 0 !important; min-width: 0; }
.st-key-schrittleiste [data-testid="stColumn"]:not(:first-child)
{ margin-left: calc(.3rem - var(--pfeil)); }
/* Die Spalten überlappen die Pfeilspitzen: nur die (per clip-path geformten)
   Knöpfe nehmen Mausklicks an, ein Klick auf die Spitze trifft ihren Schritt */
.st-key-schrittleiste [data-testid="stHorizontalBlock"] * { pointer-events: none; }
.st-key-schrittleiste .stButton button, .st-key-schrittleiste .stButton button *
{ pointer-events: auto; }
.st-key-schrittleiste .stButton button { min-height: 2.75rem; border: none !important;
  background: var(--blau-hell); color: var(--blau-dunkel); box-shadow: none !important;
  padding: .3rem calc(var(--pfeil) + .75rem);
  clip-path: polygon(0 0, calc(100% - var(--pfeil)) 0, 100% 50%, calc(100% - var(--pfeil)) 100%,
                     0 100%, var(--pfeil) 50%); }
.st-key-schritt_1 button { clip-path: polygon(0 0, calc(100% - var(--pfeil)) 0, 100% 50%,
                                              calc(100% - var(--pfeil)) 100%, 0 100%) !important; }
.st-key-schritt_4 button { clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%,
                                              var(--pfeil) 50%) !important; }
.st-key-schrittleiste .stButton button p { font-size: 1.05rem !important; font-weight: 600; }
.st-key-schrittleiste .stButton button:hover:not(:disabled) { background: var(--blau-hover);
  color: var(--blau-dunkel); }
.st-key-schrittleiste .stButton button[kind="primary"],
.st-key-schrittleiste .stButton button[kind="primary"]:hover { background: var(--blau);
  color: #fff; }
.st-key-schrittleiste .stButton button:disabled { background: var(--gesperrt);
  color: var(--gesperrt-text); opacity: 1; }
/* Während eines Prüflaufs ist alles gesperrt – der aktive Schritt bleibt kräftig */
.st-key-schrittleiste .stButton button[kind="primary"]:disabled { background: var(--blau);
  color: #fff; }

/* ---- Meldungen ---- */
.meldung { display: flex; align-items: center; gap: .7rem; font-size: 1.05rem; font-weight: 600;
  color: var(--warn-text); background: var(--warn-hell); border: 1px solid var(--warn);
  padding: .5rem .9rem; }
.meldung.neutral { color: var(--text); background: var(--skip-hell); border-color: var(--skip); }

/* ---- Flächen: weiß mit 1px-Rand auf hellgrauem Seitengrund ---- */
.st-key-block_regeln, .st-key-block_ki, .st-key-befundliste, .st-key-abgleich_tabelle,
.st-key-ohne_tabelle { background: var(--flaeche); border: 1px solid var(--linie) !important; }

/* ---- Schritt Prüfkatalog ---- */
.st-key-block_regeln, .st-key-block_ki { padding: .7rem 1rem .8rem !important;
  gap: .35rem !important; }
.st-key-block_regeln [data-testid="stVerticalBlock"],
.st-key-block_ki [data-testid="stVerticalBlock"] { gap: .3rem; }
/* Beide Blöcke gleich hoch (gemeinsame Unterkante) */
[data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-block_regeln)
{ align-items: stretch !important; }
[data-testid="stColumn"]:has(.st-key-block_regeln) > [data-testid="stVerticalBlock"],
[data-testid="stColumn"]:has(.st-key-block_ki) > [data-testid="stVerticalBlock"]
{ height: 100%; }
[data-testid="stColumn"]:has(.st-key-block_regeln) [data-testid="stLayoutWrapper"]:has(> .st-key-block_regeln),
[data-testid="stColumn"]:has(.st-key-block_ki) [data-testid="stLayoutWrapper"]:has(> .st-key-block_ki),
.st-key-block_regeln, .st-key-block_ki { flex: 1 1 auto; }
/* Kopf des Blocks: Kategorie-Checkbox links, Anzahl rechts auf derselben Linie;
   darunter eine feine Trennlinie (ohne Erklärtext – der steht im Tooltip) */
.st-key-kopf_regeln, .st-key-kopf_ki { flex-wrap: nowrap !important; padding-bottom: .45rem;
  margin-bottom: .2rem; border-bottom: 1px solid var(--linie-fein); }
.st-key-kat_regeln label p, .st-key-kat_ki label p { font-size: 1.15rem !important;
  font-weight: 700; color: var(--blau-dunkel); line-height: 1.3; white-space: nowrap; }
.st-key-kat_regeln span[role="img"], .st-key-kat_ki span[role="img"] { font-size: 1.3rem;
  vertical-align: -.25rem !important; margin-right: .15rem; }
.st-key-kat_regeln [data-testid="stTooltipHoverTarget"], .st-key-kat_ki [data-testid="stTooltipHoverTarget"],
.st-key-kat_regeln [data-testid="stTooltipIcon"], .st-key-kat_ki [data-testid="stTooltipIcon"]
{ opacity: 0; transition: opacity .15s; }
.st-key-kopf_regeln:hover [data-testid="stTooltipHoverTarget"], .st-key-kopf_ki:hover [data-testid="stTooltipHoverTarget"],
.st-key-kopf_regeln:hover [data-testid="stTooltipIcon"], .st-key-kopf_ki:hover [data-testid="stTooltipIcon"]
{ opacity: .75; }
.block-zahl { font-size: .9rem; color: var(--text-2); text-align: right; line-height: 1.3;
  white-space: nowrap; }
.block-warnung { color: var(--warn-text); background: var(--warn-hell); font-weight: 600;
  font-size: .9rem; line-height: 1.3; border: 1px solid var(--warn); padding: .2rem .5rem;
  display: flex; gap: .45rem; align-items: center; margin-bottom: .2rem; }
/* Check-Titel nur an Wortgrenzen umbrechen */
.st-key-block_regeln label p, .st-key-block_ki label p { overflow-wrap: normal; word-break: normal; }
[class*="st-key-check_"] .stCheckbox { margin-top: 0 !important; }
.stCheckbox label { align-items: flex-start; gap: .55rem; }
.stCheckbox label > span:first-child { width: 1.15rem !important; height: 1.15rem !important;
  margin-top: .12rem; border-width: 2px; }
.stCheckbox label [data-testid="stMarkdownContainer"] p { font-size: 1rem; line-height: 1.35; }
/* Erklärung je Check nur als Tooltip: das Fragezeichen erscheint beim Darüberfahren */
[class*="st-key-check_"] [data-testid="stTooltipHoverTarget"],
[class*="st-key-check_"] [data-testid="stTooltipIcon"] { opacity: 0; transition: opacity .15s; }
[class*="st-key-check_"]:hover [data-testid="stTooltipHoverTarget"],
[class*="st-key-check_"]:hover [data-testid="stTooltipIcon"] { opacity: .75; }
/* Knopf zum nächsten Schritt: unten rechts, nach dem Inhalt */
.st-key-startleiste, .st-key-weiterleiste { margin-top: .4rem; }
.st-key-start button, .st-key-zu_befunden button { min-height: 2.75rem !important;
  padding: .3rem 1.4rem !important; }
.st-key-start button p, .st-key-zu_befunden button p { font-size: 1.1rem !important;
  font-weight: 600; }

/* ---- Schritt Prüflauf ---- */
.lauf-kopf { background: var(--flaeche); border: 1px solid var(--linie); padding: .55rem 1rem .6rem; }
.lauf-titel { display: flex; align-items: center; gap: .7rem; font-size: 1.15rem;
  font-weight: 600; color: var(--blau-dunkel); }
.lauf-zaehler { margin-left: auto; font-size: 1rem; font-weight: 500; color: var(--text-2); }
.balken { height: .5rem; background: var(--blau-hell); margin: .45rem 0 .35rem; overflow: hidden; }
.balken-fuell { height: 100%; background: var(--blau); transition: width .3s; }
.lauf-info { font-size: .9rem; color: var(--text-2); }
/* Raster: feste Regeln (zwei Spalten) links, Sprachmodell rechts – alles auf einen Blick */
/* Beide Blöcke teilen sich per subgrid die Zeile der Blockköpfe: Bricht ein
   Kopf um, wird der andere gleich hoch und die Zeilen bleiben auf einer Höhe */
.lauf-raster { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  column-gap: 1rem; row-gap: 0; align-items: stretch; }
.lauf-raster.einspaltig { grid-template-columns: minmax(0, 1fr); }
.lauf-raster.einspaltig .lauf-block + .lauf-block { margin-top: 1rem; }
.lauf-block { background: var(--flaeche); border: 1px solid var(--linie); padding: .3rem .9rem .4rem;
  min-width: 0; display: grid; grid-row: span 2; grid-template-rows: subgrid; row-gap: 0;
  align-content: start; }
.lauf-block > .zeilen { align-self: start; }
.lauf-block-kopf { display: flex; justify-content: space-between; align-items: center;
  gap: .3rem .8rem; border-bottom: 1px solid var(--linie); padding: .3rem 0 .4rem; flex-wrap: wrap; }
.lauf-block-titel { display: inline-flex; align-items: center; gap: .45rem; font-size: 1.1rem;
  font-weight: 700; color: var(--blau-dunkel); white-space: nowrap; }
.lauf-block-info { font-size: .9rem; color: var(--text-2); white-space: nowrap; }
.zeilen.zweispaltig { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  grid-auto-flow: column; grid-template-rows: repeat(var(--reihen), auto); column-gap: 1.4rem; }
/* Zeile: Symbol | ID | Titel + Nebenzeile (Zahlen bzw. Grund) | Status-Wort */
.zeile { display: grid; grid-template-columns: 1.5rem 2.7rem minmax(0, 1fr) auto;
  gap: .5rem; align-items: center; padding: .3rem .2rem; min-height: 3.2rem;
  border-bottom: 1px solid var(--linie-fein); }
.zeile.laeuft { background: var(--blau-hell); }
.zeile.wartet .z-titel, .zeile.wartet .z-id { color: var(--text-3); }
/* Wartende Checks haben keine Nebenzeile: Titel mittig zu ID und Symbol */
.zeile.wartet .z-unter { display: none; }
.z-id { font-weight: 700; color: var(--blau-dunkel); font-size: .95rem; }
.z-mitte { min-width: 0; }
.z-titel { font-weight: 500; font-size: .95rem; line-height: 1.25; overflow-wrap: break-word; }
.z-unter { font-size: .85rem; color: var(--text-2); line-height: 1.3; }
.z-status { font-weight: 600; font-size: .9rem; line-height: 1.2; text-align: right;
  white-space: nowrap; }
.z-status.ok { color: var(--ok); } .z-status.warn { color: var(--warn-text); }
.z-status.fehler { color: var(--fehler); } .z-status.skip { color: var(--skip); }
.z-status.kaputt { color: var(--kaputt); } .z-status.laeuft { color: var(--blau); }
.z-status.wartet { color: var(--text-3); font-weight: 500; }

/* Ergebnis-Kacheln: weiße Fläche, Statusfarbe nur als linker Balken, im
   Symbol und in der Zahl */
.kacheln { display: flex; gap: .75rem; flex-wrap: wrap; align-items: stretch; }
.kachel { display: flex; align-items: center; gap: .65rem; padding: .55rem 1.1rem .55rem .9rem;
  background: var(--flaeche); border: 1px solid var(--linie); border-left: .25rem solid var(--linie); }
.kachel .k-zahl { font-size: 1.75rem; font-weight: 700; line-height: 1; }
.kachel .k-text { font-size: 1rem; font-weight: 500; color: var(--text); }
.kachel.fehler { border-left-color: var(--fehler); } .kachel.fehler .k-zahl { color: var(--fehler); }
.kachel.warn { border-left-color: var(--warn); } .kachel.warn .k-zahl { color: var(--warn-text); }
.kachel.ok { border-left-color: var(--ok); } .kachel.ok .k-zahl { color: var(--ok); }
.kachel.skip { border-left-color: var(--skip); } .kachel.skip .k-zahl { color: var(--skip); }
.kachel.kaputt { border-left-color: var(--kaputt); } .kachel.kaputt .k-zahl { color: var(--kaputt); }

/* ---- Schritt Befunde ---- */
.liste-kopf { font-size: .9rem; color: var(--text-2); font-weight: 500; margin-bottom: .1rem;
  line-height: 1.35; }
.liste-kopf .nw { white-space: nowrap; }
.liste-kopf .nw:first-child { color: var(--text); font-weight: 600; }
/* Höhe der Liste: per Skript bis zum unteren Bildrand (Ersatzwert ohne Skript) */
.st-key-befundliste { padding: .3rem; box-sizing: border-box;
  height: var(--liste-hoehe, 66vh) !important; overflow-y: auto !important;
  flex: 0 0 auto !important; flex-wrap: nowrap !important; }
.st-key-befundliste > * { flex-shrink: 0; }
.st-key-befundliste [data-testid="stVerticalBlock"] { gap: .15rem; }
.st-key-befundliste .stButton button { justify-content: flex-start; text-align: left;
  align-items: flex-start; min-height: 0; padding: .4rem .55rem; border: 1px solid transparent;
  background: transparent; gap: .5rem; }
.st-key-befundliste .stButton button:hover { background: var(--blau-hell); color: var(--text); }
.st-key-befundliste .stButton button[kind="primary"] { background: var(--blau-hell);
  border-color: var(--blau); color: var(--text); }
/* Gewählter Befund unter der Maus: dunkelblau (Regel für primäre Knöpfe), Schrift
   deshalb weiß; das Schwere-Symbol behält seine Farben */
.st-key-befundliste .stButton button[kind="primary"]:hover:not(:disabled),
.st-key-befundliste .stButton button[kind="primary"]:hover:not(:disabled) p,
.st-key-befundliste .stButton button[kind="primary"]:hover:not(:disabled) p * {
  color: #fff !important; }
.st-key-befundliste .stButton button > div,
.st-key-befundliste .stButton button > div > span { justify-content: flex-start;
  align-items: flex-start !important; }
.st-key-befundliste .stButton button p { font-size: .9rem !important; font-weight: 400;
  text-align: left; line-height: 1.35; white-space: normal; }
/* Schwere-Symbol im Listeneintrag: weiß im farbigen Kreis (Farbe je Eintrag,
   siehe Liste) – gleiches Verhältnis Zeichen zu Kreis (0,7) wie .sym */
[data-testid="stMain"] .st-key-befundliste .stButton [data-testid="stIconMaterial"] {
  display: inline-flex; align-items: center; justify-content: center; width: 1.4rem;
  height: 1.4rem; font-size: .98rem !important; line-height: 1; color: #fff;
  background: var(--fehler); flex: none; margin-top: 0; overflow: hidden; }
/* Navigationszeile: Pfeile mit Zähler links, Gegenüberstellung rechts; bei
   schmaler Fläche rückt die Gegenüberstellung in eine eigene Zeile */
.st-key-befund_nav { flex-wrap: wrap !important; justify-content: space-between !important;
  row-gap: .3rem !important; }
.st-key-befund_nav .stButton button { min-height: 2.5rem; min-width: 3rem; padding: .2rem .6rem; }
.st-key-befund_nav .stButton button span[role="img"] { font-size: 1.7rem; line-height: 1;
  vertical-align: middle !important; }
/* Tastenkürzel (← →) funktionieren, der Hinweis im Knopf wäre doppelt zum Pfeil */
.st-key-befund_nav kbd { display: none !important; }
.st-key-vergleich_umschalter label p { font-size: 1rem !important; font-weight: 500;
  line-height: 1.3; white-space: nowrap; }
.zaehler { text-align: center; font-size: 1rem; font-weight: 600; color: var(--text-2);
  white-space: nowrap; min-width: 9rem; }
/* Befundkarte: Kopfleiste in der Schwere-Farbe getönt; Typografie in beiden
   Ansichten (mit/ohne Gegenüberstellung) identisch */
.befund-karte { background: var(--flaeche); border: 1px solid var(--linie); margin: 0 0 .25rem; }
.befund-kopf { display: flex; flex-wrap: nowrap; align-items: center; gap: .35rem 1rem;
  padding: .45rem .9rem; background: var(--fehler-hell); border-bottom: 1px solid var(--linie);
  font-size: .95rem; color: var(--text); }
.befund-karte.warn .befund-kopf { background: var(--warn-hell); }
.befund-schwere { display: inline-flex; align-items: center; gap: .45rem; font-weight: 700;
  color: var(--fehler); flex: none; white-space: nowrap; }
.befund-karte.warn .befund-schwere { color: var(--warn-text); }
.befund-check { flex: 0 1 auto; min-width: 0; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.meta-stark { font-weight: 700; color: var(--text); }
.befund-seite { margin-left: auto; display: inline-flex; align-items: center; gap: .3rem;
  font-weight: 600; white-space: nowrap; flex: none; }
.befund-seite .ic { color: var(--text-2); }
.befund-koerper { padding: .6rem .9rem .65rem; }
/* Aussage höchstens drei Zeilen (Volltext im Tooltip), damit die markierte
   Passage sichtbar bleibt – in beiden Ansichten gleich */
.befund-text { font-size: 1.2rem; line-height: 1.35; font-weight: 500; color: var(--text);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.befund-rest { font-size: .95rem; line-height: 1.4; color: var(--text-2); margin-top: .35rem;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.fp-zeile { margin-top: .45rem; font-size: .9rem; display: flex; align-items: center; gap: .45rem; }
.fp-treffer { color: var(--ok); font-weight: 600; }
.fp-ohne { color: var(--skip); font-weight: 500; }
/* Methode (feste Regel / Sprachmodell): neutrale Chips, unterschieden durch das
   Piktogramm – Farben bleiben dem Status vorbehalten */
.chip { display: inline-flex; align-items: center; gap: .3rem; font-size: .85rem; font-weight: 600;
  padding: .1rem .5rem; background: var(--flaeche); border: 1px solid var(--linie);
  color: var(--text); white-space: nowrap; flex: none; }
.chip .ic { font-size: 1.1rem; color: var(--text-2); }
.bild-label { display: flex; align-items: center; gap: .55rem; font-size: .95rem; font-weight: 600;
  padding: .3rem .75rem; background: var(--flaeche); border: 1px solid var(--linie);
  border-bottom: none; margin-top: 0; }
.bild-label .links { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bild-label.fehler .links { color: var(--fehler); }
.bild-label.warn .links { color: var(--warn-text); }
.bild-label.neutral { color: var(--blau-dunkel); }
.bild-label > .ic { color: var(--blau); }
.bild-label .rechts { margin-left: auto; font-weight: 500; font-size: .85rem; color: var(--text-2);
  white-space: nowrap; }
[class*="st-key-passagen"] { gap: 0 !important; }
[class*="st-key-passagen"] [data-testid="stElementContainer"]:not(:first-child) .bild-label
{ margin-top: .6rem; }
[class*="st-key-passagen"] [data-testid="stHorizontalBlock"] .bild-label { margin-top: 0 !important; }
[data-testid="stImage"] img { border: 1px solid var(--linie); background: var(--flaeche); }
/* Passagen: weiße Fläche immer über die volle Breite, bündig mit der
   Beschriftung; ein in der Höhe begrenztes Bild steht mittig darin */
[class*="st-key-passagen"] [data-testid="stElementContainer"]:has([data-testid="stImage"]),
[class*="st-key-passagen"] [data-testid="stFullScreenFrame"] > div,
[class*="st-key-passagen"] [data-testid="stImage"] { width: 100% !important; }
[class*="st-key-passagen"] [data-testid="stImage"] { background: var(--flaeche);
  border: 1px solid var(--linie); box-sizing: border-box; display: flex !important;
  justify-content: center; }
[class*="st-key-passagen"] [data-testid="stImage"] > div { display: flex; justify-content: center;
  width: 100%; }
[class*="st-key-passagen"] [data-testid="stImage"] img { border: none; display: block;
  margin: 0 auto; }
/* Grafiken nebeneinander – bei schmaler Fläche (starker Zoom) untereinander */
.st-key-passagen_nebeneinander { container-type: inline-size; }
@container (max-width: 44rem) {
  .st-key-passagen_nebeneinander [data-testid="stHorizontalBlock"] { flex-direction: column !important;
    flex-wrap: nowrap !important; height: auto !important; gap: .6rem !important; }
  .st-key-passagen_nebeneinander [data-testid="stColumn"] { width: 100% !important;
    flex: 1 1 100% !important; }
}
/* Passagen werden per Skript so begrenzt, dass alles möglichst ohne Scrollen
   ins Fenster passt (--bild-max); Ersatzwerte, falls das Skript nicht läuft */
.st-key-passagen [data-testid="stImage"] img { max-height: var(--bild-max, 56vh); }
.st-key-passagen_vergleich [data-testid="stImage"] img,
.st-key-passagen_nebeneinander [data-testid="stImage"] img { max-height: var(--bild-max, 24vh); }
[class*="st-key-passagen"] [data-testid="stImage"] img { width: auto !important;
  max-width: 100%; object-fit: contain; }
.hinweis-klein { font-size: .9rem; color: var(--text-2); margin-top: .2rem; }

/* ---- Schritt Abgleich ---- */
.abgleich-kopf { display: flex; align-items: baseline; gap: .9rem; flex-wrap: wrap; }
.abgleich-zahl { font-size: 2.4rem; font-weight: 700; line-height: 1.1; }
.abgleich-zahl.ok { color: var(--ok); } .abgleich-zahl.teil { color: var(--blau); }
.abgleich-zahl.fehler { color: var(--fehler); } .abgleich-zahl.skip { color: var(--skip); }
.abgleich-text { font-size: 1.4rem; font-weight: 500; color: var(--text); }
.abgleich-text .warn-zahl { color: var(--warn-text); font-weight: 600; }
.abgleich-unter { font-size: .9rem; color: var(--text-2); margin: .1rem 0 .25rem; line-height: 1.4; }
.legende { font-size: .9rem; color: var(--text-2); display: flex; gap: .6rem; align-items: center;
  flex-wrap: wrap; }
.st-key-abgleich_tabelle, .st-key-ohne_tabelle { padding: .3rem 1rem .4rem !important; gap: 0 !important; }
.tabkopf { font-size: .85rem; font-weight: 600; color: var(--text-2); padding: .3rem 0; }
[class*="st-key-fzeile_"], [class*="st-key-bzeile_"] { border-top: 1px solid var(--linie-fein);
  padding: .35rem 0; }
/* Tabelle ohne Kopfzeile: über der ersten Zeile keine zweite Linie (Rahmen reicht) */
.st-key-ohne_tabelle > :first-child [class*="st-key-bzeile_"],
.st-key-ohne_tabelle > [class*="st-key-bzeile_"]:first-child { border-top: none; }
.fnr { font-size: 1rem; font-weight: 700; color: var(--blau-dunkel); }
.fkurz { font-size: 1rem; font-weight: 600; line-height: 1.25; }
.fort { font-size: .85rem; color: var(--text-2); line-height: 1.3; }
.gefunden { display: inline-flex; align-items: center; gap: .45rem; font-weight: 600;
  font-size: .95rem; white-space: nowrap; }
.gefunden.ok { color: var(--ok); } .gefunden.fehler { color: var(--fehler); }
.chips { display: flex; flex-wrap: wrap; gap: .3rem; }
.btext { font-size: .9rem; line-height: 1.35; }
.bseite { display: inline-flex; align-items: center; gap: .25rem; font-size: .9rem; white-space: nowrap; }
.bseite .ic { color: var(--text-2); }
/* „Zeigen“: ruhiger Textknopf rechtsbündig (kein Kasten je Zeile) */
[data-testid="stColumn"]:has([class*="st-key-zeige_"]) > [data-testid="stVerticalBlock"]
{ align-items: flex-end !important; }
[class*="st-key-zeige_"] button { min-height: 2rem; padding: .15rem .6rem; border: none !important;
  background: transparent !important; color: var(--blau); }
[class*="st-key-zeige_"] button:hover:not(:disabled) { background: var(--blau-hell) !important;
  color: var(--blau-dunkel); }
[class*="st-key-zeige_"] button:disabled { color: var(--gesperrt-text); }
[class*="st-key-zeige_"] button p { font-size: .9rem !important; font-weight: 600; }
.aussage { display: flex; align-items: center; gap: .6rem; font-size: 1.05rem; font-weight: 500;
  margin: .2rem 0 .3rem; line-height: 1.35; color: var(--text); }
.leer { display: flex; align-items: center; gap: .7rem; font-size: 1.3rem; font-weight: 600;
  color: var(--ok); padding: 1rem 0; }
.leer.skip { color: var(--text); }
.info-text { font-size: 1.05rem; color: var(--text-2); padding: .6rem 0; }
.abschnitt { font-size: 1.15rem; font-weight: 700; color: var(--blau-dunkel); margin: .9rem 0 .1rem; }
/* Werkzeugleiste über Bildern (Vollbild-Knopf) ausblenden */
[data-testid="stMain"] [data-testid="stElementToolbar"] { display: none !important; }

/* ---- Schmale Hauptfläche (starker Browser-Zoom, Seitenleiste offen) ----
   Gemessen an der Breite der Hauptfläche, unabhängig von der Fensterbreite */
[data-testid="stMainBlockContainer"] { container-type: inline-size; }
@container (max-width: 60rem) {
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-block_regeln) {
    flex-direction: column !important; flex-wrap: nowrap !important; }
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-block_regeln)
    > [data-testid="stColumn"] { width: 100% !important; flex: 1 1 100% !important; }
}
@container (max-width: 37.5rem) {
  .st-key-block_regeln [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]) {
    flex-direction: column !important; flex-wrap: nowrap !important;
    gap: .3rem !important; }
  .st-key-block_regeln [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 100% !important; }
}

/* ---- Schmale Fenster (starker Browser-Zoom, z. B. 200 %) ---- */
@media (max-width: 1100px) {
  .dok-label { display: none !important; }
  .lauf-raster { grid-template-columns: minmax(0, 1fr) !important; }
  .lauf-raster .lauf-block + .lauf-block { margin-top: 1rem; }
}
</style>"""


def css(faktor: float) -> str:
    """Stylesheet mit dem Schriftgrößen-Faktor der Seitenleiste."""
    try:
        faktor = max(0.5, min(2.0, float(faktor)))
    except (TypeError, ValueError):
        faktor = 1.0
    return CSS_VORLAGE.replace("__FAKTOR__", f"{faktor:.2f}")


# =============================================================================
# Kleine Helfer
# =============================================================================
def esc(text) -> str:
    """Text für HTML entschärfen."""
    return html.escape(str(text), quote=True)


def md_esc(text: str) -> str:
    """Text für Markdown-Beschriftungen (Buttons, Checkboxen) entschärfen."""
    return re.sub(r"([\\`*_\[\]<>$~:#|])", r"\\\1", str(text))


def de_zahl(wert: float, stellen: int = 1) -> str:
    """Zahl im deutschen Format (Komma als Dezimaltrenner)."""
    return f"{wert:.{stellen}f}".replace(".", ",")


def anzahl(n: int, einzahl: str, mehrzahl: str) -> str:
    return f"{n} {einzahl if n == 1 else mehrzahl}"


def kuerzen(text: str, laenge: int) -> str:
    """Kürzt an einer Wortgrenze und hängt „…“ an."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= laenge:
        return text
    schnitt = text.rfind(" ", 0, laenge)
    if schnitt < laenge * 0.6:
        schnitt = laenge
    return text[:schnitt].rstrip(" ,;:–-") + " …"


def anzeige(beschreibung: str) -> str:
    """Befundtext für die Leinwand (unsichtbare Zeichen entfernt, zerlegte
    Formelauszüge gekürzt – fundstellen.anzeige_text). Der Abgleich mit dem
    Fehlerprotokoll arbeitet weiter auf dem Originaltext."""
    try:
        return fundstellen.anzeige_text(beschreibung)
    except Exception:            # Anzeige darf nie an der Aufbereitung scheitern
        return re.sub(r"\s+", " ", str(beschreibung or "")).strip()


def hinweis_neutral(text: str) -> str:
    """Hinweistext eines Checks für die Leinwand: Modellnamen werden neutral
    als „Sprachmodell“ dargestellt (Live- und Notfallmodus sehen gleich aus),
    technische Präfixe von Fehlermeldungen entfallen."""
    text = re.sub(r"^\s*SprachmodellFehler:\s*", "", str(text or ""))
    modelle = {engine.STANDARDMODELL, engine.REFERENZMODELL,
               str(st.session_state.get("modell") or "").strip()}
    for m in sorted((m for m in modelle if len(m) >= 6), key=len, reverse=True):
        text = (text.replace(f"mit {m}", "mit dem Sprachmodell")
                    .replace(f"({m})", "(Sprachmodell)")
                    .replace(m, "Sprachmodell"))
    return text


# Merkmale technischer Texte, die nicht auf die Leinwand gehören
_TECHNISCH = re.compile(r"Error\b|Exception|Traceback|Errno|\b[A-Z]:[\\/]|https?://|\\\\")


def grund_fuer_leinwand(ergebnis) -> str:
    """Kurzer deutscher Satz, warum ein Check nicht (vollständig) lief.
    Fehlgeschlagen: fester Satz. Übersprungen: der Grund des Checks ohne
    Dateipfade; wirkt er technisch, ein allgemeiner Satz."""
    if ergebnis.status == "FEHLGESCHLAGEN":
        return FEHLGESCHLAGEN_TEXT
    text = hinweis_neutral(ergebnis.hinweis)
    text = re.split(r":\s*(?=[A-Za-z]:[\\/]|/|\\\\)", text)[0].strip()   # Pfade abschneiden
    if not text or _TECHNISCH.search(text):
        return "Check wurde übersprungen."
    return kuerzen(text, 110)


def zaehle(ergebnisse) -> tuple[int, int]:
    """(Fehler, Warnungen) über alle Befunde."""
    befunde = [b for r in ergebnisse for b in r.befunde]
    return (sum(b.schwere == "FEHLER" for b in befunde),
            sum(b.schwere == "WARNUNG" for b in befunde))


def nicht_gelaufen(lauf: dict) -> tuple[int, int]:
    """(übersprungene, fehlgeschlagene) Checks eines Laufs."""
    ergebnisse = lauf["ergebnisse"]
    return (sum(r.status == "ÜBERSPRUNGEN" for r in ergebnisse),
            sum(r.status == "FEHLGESCHLAGEN" for r in ergebnisse))


def nicht_gelaufen_text(lauf: dict) -> str:
    """z. B. „6 Checks übersprungen“ oder „2 Checks übersprungen, 1 fehlgeschlagen“;
    leer, wenn alle Checks ausgeführt wurden."""
    n_skip, n_kaputt = nicht_gelaufen(lauf)
    teile = []
    if n_skip:
        teile.append(f"{anzahl(n_skip, 'Check', 'Checks')} übersprungen")
    if n_kaputt:
        teile.append(f"{n_kaputt} fehlgeschlagen" if teile
                     else f"{anzahl(n_kaputt, 'Check', 'Checks')} fehlgeschlagen")
    return ", ".join(teile)


def alle_befunde(lauf: dict) -> list:
    """Alle Befunde eines Laufs in Check-Reihenfolge."""
    return [b for r in lauf["ergebnisse"] for b in r.befunde]


def teile_beschreibung(text: str) -> tuple[str, str]:
    """Teilt lange Befundtexte (v. a. der Sprachmodell-Checks) in einen
    Kernsatz für die große Anzeige und die Einzelheiten (Begründung)."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= 280:
        return text, ""
    i = text.find(" – ", 30)
    kern, rest = (text[:i], text[i + 3:]) if i > 0 else (text, "")
    if len(kern) > 420:                       # sehr langer Kern: nur das Thema groß
        j = kern.find("“: ")
        if 0 < j < 200:
            rest = kern[j + 3:] + (" – " + rest if rest else "")
            kern = kern[:j + 1]
    return kern, rest


def icon(name: str, klasse: str = "") -> str:
    """Ein Piktogramm (Material Symbols Rounded, Ligatur-Name) für eigenes HTML.
    Die einzige Stelle, an der Piktogramme als HTML entstehen."""
    zusatz = f" {klasse}" if klasse else ""
    return f"<span class='ic{zusatz}' aria-hidden='true'>{esc(name)}</span>"


def sym_html(klasse: str, name: str, groesse: str = "") -> str:
    """Status-Symbol: weißes Piktogramm im farbigen Kreis (Klasse = Farbe)."""
    zusatz = f" {groesse}" if groesse else ""
    return f"<span class='sym {klasse}{zusatz}'>{icon(name)}</span>"


def methode_chip(methode: str, text: str) -> str:
    """Neutraler Chip; die Methode zeigt das Piktogramm (rule bzw. psychology)."""
    name = ICON["ki"] if methode == "LLM" else ICON["regeln"]
    return f"<span class='chip'>{icon(name)}{esc(text)}</span>"


def chip_html(check_id: str, methoden: dict) -> str:
    return methode_chip(methoden.get(check_id, ""), check_id)


def meldung_html(text: str, klasse: str = "", name: str = "priority_high") -> str:
    sym = sym_html("skip" if klasse == "neutral" else "warn", name)
    return f"<div class='meldung {klasse}'>{sym}<span>{esc(text)}</span></div>"


def melde_fehler(text: str, fehler: BaseException) -> None:
    """Verständliche deutsche Meldung auf der Leinwand; technische
    Einzelheiten nur in der Konsole und in der Seitenleiste."""
    details = "".join(traceback.format_exception(fehler))
    st.session_state["letzter_fehler"] = details
    print(details, file=sys.stderr)
    st.error(text)


# =============================================================================
# Vorführstand: Speicher im Serverprozess, der ein Neuladen übersteht
# =============================================================================
@st.cache_resource(show_spinner=False)
def vorfuehrstand() -> dict:
    """Speicher im Serverprozess (nur Arbeitsspeicher, nichts auf der Platte).

    Streamlit beginnt nach einem Neuladen der Seite (F5, Browser-Absturz,
    WLAN-Wackler) eine neue Sitzung. Ohne diesen Speicher wären alle
    Ergebnisse weg und der Notfallschalter stünde wieder auf AUS – der nächste
    Start liefe live und kostete erneut. Gilt für alle Browser-Tabs dieses
    Servers (Einzelplatz-Vorführung) und verschwindet mit dem Server.

    werte: gemerkte Sitzungswerte (GEMERKT)
    lauf:  Dokument eines begonnenen, nicht beendeten Prüflaufs (oder None)
    """
    return {"sperre": threading.Lock(), "werte": {}, "lauf": None}


def _kopie(wert):
    """Flache Kopie veränderlicher Behälter (Sitzungen teilen keine Objekte)."""
    if isinstance(wert, dict):
        return dict(wert)
    if isinstance(wert, set):
        return set(wert)
    return wert


def stand_merken() -> None:
    """Übernimmt die Werte aus GEMERKT in den Vorführstand."""
    ss = st.session_state
    speicher = vorfuehrstand()
    with speicher["sperre"]:
        for schluessel in GEMERKT:
            if schluessel in ss:
                speicher["werte"][schluessel] = _kopie(ss[schluessel])


def stand_vergessen(nur_ergebnisse: bool = False) -> None:
    """Leert den Vorführstand (ganz oder nur die Ergebnisse)."""
    speicher = vorfuehrstand()
    with speicher["sperre"]:
        if nur_ergebnisse:
            for schluessel in ("laeufe", "befund_idx"):
                speicher["werte"].pop(schluessel, None)
        else:
            speicher["werte"].clear()
        speicher["lauf"] = None


def neue_sitzung_vorbelegen() -> None:
    """Erster Aufbau einer Sitzung: gemerkten Stand übernehmen (vorhandene
    Werte – z. B. aus Tests – haben Vorrang). Mit „?neu=1“ in der Adresse
    beginnt die Vorführung ohne alte Ergebnisse und mit Standardwerten.
    Wurde beim Neuladen gerade geprüft, wird der Abbruch gemeldet."""
    ss = st.session_state
    if "neu" in st.query_params:
        stand_vergessen()
        try:
            del st.query_params["neu"]      # ein späteres Neuladen setzt nicht zurück
        except Exception:
            pass
        return
    speicher = vorfuehrstand()
    with speicher["sperre"]:
        for schluessel, wert in speicher["werte"].items():
            if schluessel not in ss:
                ss[schluessel] = _kopie(wert)
        unterbrochen, speicher["lauf"] = speicher["lauf"], None
    if unterbrochen:
        ss["abbruch_meldung"] = unterbrochen


def lauf_beginnt(dokument: str) -> None:
    st.session_state["lauf_laeuft"] = dokument
    speicher = vorfuehrstand()
    with speicher["sperre"]:
        speicher["lauf"] = dokument


def lauf_endet() -> None:
    st.session_state["lauf_laeuft"] = None
    speicher = vorfuehrstand()
    with speicher["sperre"]:
        speicher["lauf"] = None


# =============================================================================
# Sitzungszustand
# =============================================================================
def zustand_vorbereiten() -> None:
    ss = st.session_state
    if not ss.get("_sitzung_bekannt"):
        ss["_sitzung_bekannt"] = True
        ss["_seitenleiste_einklappen"] = True
        neue_sitzung_vorbelegen()
    for schluessel, wert in VORGABEN.items():
        ss.setdefault(schluessel, wert)
    if ss["notfall_verzoegerung_s"] not in NOTFALL_TEMPI:   # z. B. alter gemerkter Wert
        ss["notfall_verzoegerung_s"] = NOTFALL_TEMPO_STANDARD
    ss["max_parallel"] = max(1, min(MAX_PARALLEL_HOECHSTENS, int(ss["max_parallel"])))
    # Regler-Werte auf die nächste Stufe setzen (z. B. alter gemerkter Wert)
    for schluessel, stufen in (("pause_s", PAUSEN), ("schrift_faktor", SCHRIFT_FAKTOREN)):
        try:
            wert = float(ss[schluessel])
        except (TypeError, ValueError):
            wert = float(VORGABEN[schluessel])
        if wert not in stufen:
            ss[schluessel] = min(stufen, key=lambda s: abs(s - wert))
    ss.setdefault("dok_wahl", "fehlerhaft")   # Widget-Schlüssel des Umschalters
    ss.setdefault("schritt", 1)
    ss.setdefault("laeufe", {})               # Dokument -> abgeschlossener Prüflauf
    ss.setdefault("befund_idx", {})           # Dokument -> gewählter Befund
    ss.setdefault("auswahl", None)            # Menge der ausgewählten Check-IDs
    ss.setdefault("lauf_anstehend", None)     # {"dokument", "ids"} nach „Prüfung starten“
    ss.setdefault("lauf_laeuft", None)        # Dokument eines begonnenen Prüflaufs
    ss.setdefault("abbruch_meldung", None)    # Dokument, dessen Lauf abgebrochen wurde
    ss.setdefault("_dauer_vergleich", False)  # Gegenüberstellung an/aus
    ss.setdefault("_scroll", None)            # angeforderte Scrollposition (siehe unten)
    ss.setdefault("_skript_nr", 0)
    # Wurde der letzte Prüflauf dieser Sitzung nicht zu Ende geführt (z. B. durch
    # Umschalten des Notfallschalters während des Laufs), wird das gemeldet –
    # außer es wurde gerade neu gestartet (etwa durch einen Doppelklick).
    if ss["lauf_laeuft"] and not ss["lauf_anstehend"]:
        ss["abbruch_meldung"] = ss["lauf_laeuft"]
        lauf_endet()


def laeuft_gerade() -> bool:
    """Wird in diesem Aufbau ein Prüflauf ausgeführt? Dann sind Umschalter,
    Prozesskette und Regler gesperrt (jede Bedienung bräche den Lauf ab)."""
    return bool(st.session_state.get("lauf_anstehend"))


def scroll_anfordern(ziel: str | None = "oben") -> None:
    """Merkt vor, wohin die Hauptfläche nach dem nächsten Aufbau scrollt:
    "oben" (Seitenanfang) oder "vergleich" (Befund samt beiden Passagen).
    Streamlit behält sonst die alte Scrollposition – nach einem Sprung aus
    Schritt 4 sähe das Publikum z. B. nur das Ende einer Grafik."""
    st.session_state["_scroll"] = ziel


def gehe_zu(schritt: int) -> None:
    st.session_state["schritt"] = schritt
    scroll_anfordern("oben")


def waehle_befund(dokument: str, index: int, schritt: int | None = None) -> None:
    ss = st.session_state
    ss["befund_idx"][dokument] = max(0, index)
    if schritt:
        ss["schritt"] = schritt
    scroll_anfordern("vergleich" if ss.get("_dauer_vergleich") else "oben")


def dokument_gewechselt() -> None:
    """Beim Dokumentwechsel ohne vorhandenes Ergebnis zurück zum Prüfkatalog."""
    ss = st.session_state
    ss["lauf_anstehend"] = None
    if ss.get("dok_wahl") not in ss["laeufe"]:
        ss["schritt"] = 1
    scroll_anfordern("oben")


def kategorie_geaendert(schluessel: str, ids: list[str]) -> None:
    """Kategorie-Checkbox (feste Regeln bzw. Sprachmodell): wählt alle Checks
    dieser Kategorie aus oder ab; die übrigen bleiben, wie sie sind."""
    ss = st.session_state
    an = bool(ss.get(schluessel))
    for cid in ids:
        ss[f"cb_{cid}"] = an
        if an:
            ss["auswahl"].add(cid)
        else:
            ss["auswahl"].discard(cid)


def checkbox_geaendert(cid: str) -> None:
    """Einzelner Check an/aus. Der Haken der Kategorie-Checkbox folgt beim
    nächsten Aufbau (schritt_katalog)."""
    ss = st.session_state
    if ss.get(f"cb_{cid}"):
        ss["auswahl"].add(cid)
    else:
        ss["auswahl"].discard(cid)


def vergleich_gemerkt() -> None:
    """Checkbox „Gegenüberstellung“: merken (übersteht Neuladen) und scrollen."""
    an = bool(st.session_state["vergleich_umschalter"])
    st.session_state["_dauer_vergleich"] = an
    scroll_anfordern("vergleich" if an else "oben")


def starte_pruefung(dokument: str, alle: list[str]) -> None:
    """„Prüfung starten“: Der neue Lauf ersetzt das bisherige Ergebnis dieses
    Dokuments (das andere Dokument behält seines)."""
    ss = st.session_state
    ss["lauf_anstehend"] = {"dokument": dokument,
                            "ids": [c for c in alle if c in ss["auswahl"]]}
    ss["laeufe"].pop(dokument, None)
    ss["befund_idx"].pop(dokument, None)
    ss["abbruch_meldung"] = None
    ss["schritt"] = 2
    scroll_anfordern("oben")


def alles_zuruecksetzen() -> None:
    ss = st.session_state
    ss["laeufe"], ss["befund_idx"] = {}, {}
    ss["lauf_anstehend"], ss["abbruch_meldung"], ss["schritt"] = None, None, 1
    ss.pop("letzter_fehler", None)
    stand_vergessen(nur_ergebnisse=True)


# =============================================================================
# Daten laden und Passagen rendern (zwischengespeichert)
# =============================================================================
@st.cache_resource(show_spinner="Die TB wird eingelesen und die Prüfregeln werden geladen …")
def pruefstrecke(dokument: str) -> engine.Pruefstrecke:
    """Prüfstrecke je Dokument (führt die Notebook-Zellen aus, ca. 2 s)."""
    return engine.lade_pruefstrecke(dokument)


@st.cache_data(show_spinner=False)
def fehlerliste() -> list:
    return fehlerprotokoll.lade_fehlerprotokoll()


@st.cache_data(show_spinner=False, max_entries=500)
def fundstelle(dokument: str, check_id: str, beschreibung: str, seite: int | None):
    """Fundstelle eines Befunds im geprüften PDF (oder None)."""
    with engine.FITZ_SPERRE:     # PyMuPDF verträgt keine parallelen Zugriffe
        return fundstellen.finde_fundstelle(engine.DOKUMENTE[dokument], check_id,
                                            beschreibung, seite)


@st.cache_data(show_spinner=False, max_entries=500)
def gegenstellen(dokument: str, check_id: str, beschreibung: str, seite: int | None) -> list:
    """Weitere im Befund genannte Stellen auf anderen Seiten (z. B. die zweite
    Stelle eines Widerspruchs); leer, wenn es keine belastbaren gibt."""
    finder = getattr(fundstellen, "finde_gegenstellen", None)
    if finder is None:
        return []
    with engine.FITZ_SPERRE:
        return list(finder(engine.DOKUMENTE[dokument], check_id, beschreibung, seite) or [])


@st.cache_data(show_spinner=False, max_entries=300)
def passage_png(dokument: str, check_id: str, beschreibung: str, seite: int | None,
                pdf_dokument: str, farbe: str) -> bytes | None:
    """Markierte Passage als PNG. pdf_dokument = Dokument, auf dem gerendert
    wird – für die Gegenüberstellung das jeweils andere (Layout identisch).
    Gegenstellen erscheinen im selben Bild darunter, je mit Kopfbalken."""
    fund = fundstelle(dokument, check_id, beschreibung, seite)
    if fund is None:
        return None
    fund.weitere = gegenstellen(dokument, check_id, beschreibung, seite)
    with engine.FITZ_SPERRE:
        return fundstellen.rendere_ausschnitt(engine.DOKUMENTE[pdf_dokument], fund,
                                              markieren=True, farbe=farbe,
                                              breite_px=BILDBREITE_PX)


def fundstelle_sicher(dokument: str, befund):
    """Fundstelle oder None – Fehler der Suche landen nur in der Konsole."""
    try:
        return fundstelle(dokument, befund.check_id, befund.beschreibung, befund.seite)
    except Exception as fehler:
        print("".join(traceback.format_exception(fehler)), file=sys.stderr)
        return None


def befund_seite(dokument: str, befund) -> int | None:
    """Seite der gefundenen Passage (kann von der gemeldeten Seite abweichen,
    z. B. Symbolverzeichnis statt Verwendungsstelle)."""
    fund = fundstelle_sicher(dokument, befund)
    return fund.seite if fund is not None else befund.seite


# =============================================================================
# Seitenleiste (nur für die Vortragenden, standardmäßig eingeklappt)
# =============================================================================
def tempo_text(wert) -> str:
    if wert == "live":
        return "wie live"
    return "sofort" if not wert else f"{de_zahl(float(wert))} s"


def seitenleiste() -> None:
    ss = st.session_state
    gesperrt = laeuft_gerade()
    with st.sidebar:
        st.markdown("**Einstellungen für die Vorführung**")
        st.text_input("Sprachmodell (Live-Betrieb)", key="modell", disabled=gesperrt)
        vorhanden = engine.api_schluessel_vorhanden()   # nur ja/nein, nie der Wert
        st.markdown("API-Schlüssel: " + (f"**vorhanden** :green[{mat('check_circle')}]"
                                         if vorhanden else
                                         f"**nicht gesetzt** :red[{mat('cancel')}]"))
        # Der Notfallschalter (eckige Checkbox) bleibt auch während eines Laufs
        # bedienbar: Hängt ein Live-Lauf, bricht das Umschalten ihn ab.
        st.checkbox("Gespeicherte Antworten verwenden (Notfall)", key="notfall",
                    help="Umschalten während einer Prüfung bricht sie ab – danach im "
                         "Prüfkatalog neu starten.")
        if ss["notfall"]:
            st.caption("Notfallmodus aktiv: Die Sprachmodell-Checks spielen die "
                       "gespeicherten Antworten des Nachweis-Laufs ab "
                       f"({engine.REFERENZMODELL}) – ohne Internet und ohne Kosten.")
        # Regler mit deutscher Schreibweise (Komma) – daher select_slider
        st.select_slider("Pause je Check", options=PAUSEN, key="pause_s",
                         format_func=lambda v: f"{de_zahl(v)} s", disabled=gesperrt)
        st.number_input("Parallele Anfragen an das Sprachmodell", min_value=1,
                        max_value=MAX_PARALLEL_HOECHSTENS, step=1, key="max_parallel",
                        disabled=gesperrt)
        st.select_slider("Schriftgröße (Faktor)", options=SCHRIFT_FAKTOREN,
                         key="schrift_faktor", format_func=lambda v: de_zahl(v, 2),
                         disabled=gesperrt)
        st.caption("Befunde blättern: Pfeiltasten ← → (solange ein Regler den Fokus "
                   "hat, verstellen sie nur den Regler).")
        with st.expander("Weitere Einstellungen"):
            st.select_slider("Antwortzeit im Notfallmodus (je Anfrage)",
                             options=NOTFALL_TEMPI, format_func=tempo_text,
                             key="notfall_verzoegerung_s", disabled=gesperrt,
                             help="„wie live“ spielt die gemessenen Antwortzeiten eines "
                                  "echten Laufs nach – der Notfall ist am Tempo nicht zu "
                                  "erkennen.")
            st.button("Alle Ergebnisse zurücksetzen", key="zuruecksetzen",
                      on_click=alles_zuruecksetzen, disabled=gesperrt)
            st.caption("Einstellungen und Ergebnisse bleiben beim Neuladen der Seite "
                       "erhalten, solange der Server läuft. Neubeginn ohne alte "
                       "Ergebnisse: Adresse mit „?neu=1“ aufrufen.")


def technik_details() -> None:
    """Technische Gründe für übersprungene/fehlgeschlagene Checks und den
    letzten Fehler – nur in der Seitenleiste, nie auf der Leinwand. Wird am
    Ende des Aufbaus angehängt, damit auch ein Fehler dieses Aufbaus erscheint."""
    ss = st.session_state
    lauf = ss.get("laeufe", {}).get(ss.get("dok_wahl") or "fehlerhaft")
    zeilen = []
    if lauf:
        zeilen = [f"- **{r.id}** ({STATUS.get(r.status, ('', r.status, ''))[1]}): "
                  f"{md_esc(r.hinweis or 'ohne Angabe')}"
                  for r in lauf["ergebnisse"] if r.status in ("ÜBERSPRUNGEN", "FEHLGESCHLAGEN")]
    if not zeilen and not ss.get("letzter_fehler"):
        return
    with st.sidebar, st.expander("Technische Einzelheiten", expanded=False):
        if zeilen:
            st.markdown("\n".join(zeilen))
        if ss.get("letzter_fehler"):
            st.caption("Letzter Fehler:")
            st.code(ss["letzter_fehler"][-3000:], language=None)


# =============================================================================
# Kopfzeile, Prozesskette und Skripte
# =============================================================================
def dok_beschriftung(dokument: str) -> str:
    return f"{mat(ICON['dokument'][dokument])} {DOK_TITEL[dokument]}"


def kopfzeile() -> None:
    """Titel links (ruhig, schwarz), Dokument-Umschalter rechts in derselben
    Zeile; bei starkem Browser-Zoom rückt der Umschalter unter den Titel."""
    with st.container(horizontal=True, vertical_alignment="center", key="kopfleiste"):
        st.html("<div class='kopf'><span class='kopf-titel'>TB-Validierung</span>"
                "<span class='kopf-zusatz'>Live-Demo</span></div>", width="content")
        dok_leiste = st.container(horizontal=True, horizontal_alignment="right",
                                  vertical_alignment="center", key="dok_leiste",
                                  width="content")
    with dok_leiste:
        st.html("<div class='dok-label'>Dokument</div>", width="content")
        st.segmented_control("Dokument", options=list(DOK_TITEL),
                             format_func=dok_beschriftung, key="dok_wahl",
                             required=True, label_visibility="collapsed",
                             disabled=laeuft_gerade(), on_change=dokument_gewechselt)


def schrittleiste(dokument: str) -> None:
    ss = st.session_state
    hat_ergebnis = dokument in ss["laeufe"]
    gesperrt = laeuft_gerade()
    verfuegbar = {1: True, 2: hat_ergebnis or gesperrt, 3: hat_ergebnis, 4: hat_ergebnis}
    if not verfuegbar.get(ss["schritt"], False):
        ss["schritt"] = 1
    # Prozesskette: Pfeilboxen (Form per CSS clip-path), aktiver Schritt kräftig
    # blau, erreichbare hell, gesperrte grau – ohne Nummern, mit Piktogramm
    with st.container(key="schrittleiste"):
        spalten = st.columns(len(SCHRITTE), gap=None)
        for spalte, (nr, name) in zip(spalten, SCHRITTE.items()):
            spalte.button(name, key=f"schritt_{nr}", icon=mat(ICON["schritt"][nr]),
                          type="primary" if ss["schritt"] == nr else "secondary",
                          disabled=gesperrt or not verfuegbar[nr], width="stretch",
                          on_click=gehe_zu, args=(nr,))


def skripte_seite() -> None:
    """Skripte, die nur die Browser-Anzeige betreffen (ändern keine Daten).
    Der (unsichtbare) Behälter wird immer angelegt, damit die Elemente darunter
    bei jedem Aufbau an derselben Position stehen.

    - Seitenleiste beim ersten Aufbau einer Sitzung einklappen: Streamlit merkt
      sich ihren Zustand im Browser (localStorage „stSidebarCollapsed-…“), sonst
      wären nach einer Probe mit offener Seitenleiste Notfallschalter und
      Schlüsselstatus für das Publikum sichtbar.
    - Vorgemerkte Scrollposition umsetzen (scroll_anfordern): "oben" =
      Seitenanfang. "vergleich" (Befundansicht mit Gegenüberstellung)
      übernimmt einpassen(), weil die Scrollposition dort von der Größe der
      Passagen abhängt.
    """
    ss = st.session_state
    behaelter = st.container(key="skript_seite")
    if ss.pop("_seitenleiste_einklappen", False):
        with behaelter:
            st.html("""<script>
(function () {
  try {
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (k && k.indexOf('stSidebarCollapsed-') === 0) localStorage.setItem(k, 'true');
    }
    localStorage.setItem('stSidebarCollapsed-', 'true');
  } catch (e) {}
  var versuch = 0;
  function einklappen() {
    var leiste = document.querySelector('section[data-testid="stSidebar"]');
    if (!leiste) { if (versuch++ < 20) setTimeout(einklappen, 100); return; }
    if (leiste.getAttribute('aria-expanded') === 'true') {
      var knopf = document.querySelector('[data-testid="stSidebarCollapseButton"] button');
      if (knopf) knopf.click();
    }
  }
  setTimeout(einklappen, 50);
})();
</script>""", unsafe_allow_javascript=True)
    ziel = ss.get("_scroll")
    if not ziel:
        return
    ss["_scroll"] = None
    if ziel == "vergleich" and ss.get("schritt") == 3:
        return                   # scrollt einpassen() – erst nach dem Einpassen der Bilder
    ziel = "oben"
    ss["_skript_nr"] += 1
    with behaelter:
        st.html(f"""<script>
/* Scrollauftrag {ss["_skript_nr"]} */
(function () {{
  var ziel = "{ziel}", versuch = 0;
  function los() {{
    var main = document.querySelector('[data-testid="stMain"]');
    if (!main) {{ if (versuch++ < 30) setTimeout(los, 100); return; }}
    if (ziel === "oben") {{ main.scrollTo({{ top: 0 }}); return; }}
    var anker = document.querySelector('.st-key-befund_nav');
    if (!anker) {{ if (versuch++ < 30) setTimeout(los, 100); return; }}
    var soll = main.scrollTop + anker.getBoundingClientRect().top
               - main.getBoundingClientRect().top - 8;
    main.scrollTo({{ top: soll }});
    /* Bilder noch nicht geladen -> Seite zu kurz: kurz danach erneut versuchen */
    if (Math.abs(main.scrollTop - soll) > 4 && versuch++ < 30) setTimeout(los, 100);
  }}
  setTimeout(los, 80);
}})();
</script>""", unsafe_allow_javascript=True)


# =============================================================================
# Schritt 1: Prüfkatalog
# =============================================================================
# Kategorie-Checkboxen: Schlüssel -> (Titel, Piktogramm, Erklärung im Tooltip)
KATEGORIEN = {
    "kat_regeln": ("Feste Regeln", ICON["regeln"],
                   "Python prüft nach festen Regeln – nachvollziehbar und bei jedem Lauf "
                   "gleich. Ein Klick wählt alle Checks dieser Kategorie aus oder ab."),
    "kat_ki": ("Sprachmodell (KI)", ICON["ki"],
               "Ein KI-Sprachmodell liest mit, Python kontrolliert seine Antworten. Ein "
               "Klick wählt alle Checks dieser Kategorie aus oder ab."),
}


def schritt_katalog(strecke, checks) -> None:
    ss = st.session_state
    alle = [c.id for c in checks]
    regeln = [c for c in checks if c.methode != "LLM"]
    ki = [c for c in checks if c.methode == "LLM"]
    for c in checks:                      # Checkbox-Zustand aus der Auswahl herstellen
        ss.setdefault(f"cb_{c.id}", c.id in ss["auswahl"])
    # Haken der Kategorie-Checkboxen: gesetzt, wenn alle Checks der Kategorie
    # gewählt sind (folgt damit auch jeder Einzeländerung)
    ss["kat_regeln"] = all(c.id in ss["auswahl"] for c in regeln)
    ss["kat_ki"] = all(c.id in ss["auswahl"] for c in ki)
    n_auswahl = len(ss["auswahl"] & set(alle))

    # Feste Struktur: Meldung | Katalog | Startleiste – der Prüflauf legt an
    # dieselben Positionen seine drei Platzhalter (pruefung_ausfuehren), damit
    # beim Start nichts vom Katalog blass stehen bleibt.
    platz_meldung = st.empty()
    if ss.get("abbruch_meldung") == strecke.dokument:
        platz_meldung.html(meldung_html(ABBRUCH_TEXT))

    # Beide Blöcke gleich aufgebaut (Kopf mit Kategorie-Checkbox, dann die
    # Checks); nur wenn der API-Schlüssel fehlt, warnt der Sprachmodell-Block.
    llm_gewaehlt = any(c.id in ss["auswahl"] for c in ki)
    ohne_schluessel = (llm_gewaehlt and not ss["notfall"]
                       and not engine.api_schluessel_vorhanden())
    links, rechts = st.columns([2, 1], gap="medium")
    with links:
        katalog_block("kat_regeln", regeln, spalten=2, schluessel="block_regeln")
    with rechts:
        katalog_block("kat_ki", ki, spalten=1, schluessel="block_ki",
                      warnung=("Kein API-Schlüssel gesetzt – die Sprachmodell-Checks würden "
                               "übersprungen." if ohne_schluessel else ""))

    # Start unten rechts, nach dem Katalog
    with st.container(horizontal=True, horizontal_alignment="right", key="startleiste"):
        st.button(f"Prüfung starten ({n_auswahl} von {len(alle)} Checks)", key="start",
                  icon=mat(ICON["start"]), type="primary", disabled=n_auswahl == 0,
                  on_click=starte_pruefung, args=(strecke.dokument, alle))


def katalog_block(kategorie: str, checks, spalten: int, schluessel: str,
                  warnung: str = "") -> None:
    """Block einer Kategorie: Kopf mit Kategorie-Checkbox (wählt alle Checks des
    Blocks aus oder ab) und Anzahl, dann die Checks. Erklärungen stehen nur in
    Tooltips; eine Warnung (fehlender API-Schlüssel) erscheint unter dem Kopf."""
    titel, piktogramm, erklaerung = KATEGORIEN[kategorie]
    ids = [c.id for c in checks]
    with st.container(border=True, key=schluessel):
        with st.container(horizontal=True, vertical_alignment="center", gap="small",
                          key=f"kopf_{schluessel.removeprefix('block_')}"):
            st.checkbox(f"{mat(piktogramm)} {titel}", key=kategorie, width="stretch",
                        help=erklaerung, on_change=kategorie_geaendert,
                        args=(kategorie, ids))
            st.html(f"<div class='block-zahl'>{len(checks)} Checks</div>", width="content")
        if warnung:
            st.html(f"<div class='block-warnung'>{sym_html('warn', 'priority_high', 'klein')}"
                    f"<span>{esc(warnung)}</span></div>")
        je_spalte = -(-len(checks) // spalten)          # aufrunden
        teile = [checks[i:i + je_spalte] for i in range(0, len(checks), je_spalte)]
        bereiche = st.columns(spalten, gap="medium") if spalten > 1 else [st.container()]
        for bereich, teil in zip(bereiche, teile):
            with bereich:
                for c in teil:
                    with st.container(key=f"check_{c.id}", gap=None):
                        st.checkbox(f"**{c.id}**  {md_esc(c.titel)}", key=f"cb_{c.id}",
                                    help=c.erklaerung,
                                    on_change=checkbox_geaendert, args=(c.id,))


# =============================================================================
# Schritt 2: Prüflauf
# =============================================================================
def zeile_html(c, z: dict, erwartet: int | None) -> str:
    """Eine Zeile der Ablaufliste: wartet → läuft … → Ergebnis.
    Titel und Nebenzeile (Zahlen, Dauer bzw. Grund) stehen untereinander in
    derselben Spalte – nichts kann sich überlappen."""
    phase = z["phase"]
    ergebnis = z.get("ergebnis") if phase == "fertig" else None
    if ergebnis:
        r = ergebnis
        zeichen, text, klasse = STATUS.get(r.status, ("question_mark", r.status, "skip"))
        if r.status in ("ÜBERSPRUNGEN", "FEHLGESCHLAGEN"):
            # Bei übersprungenen/fehlgeschlagenen Checks muss der Grund sichtbar sein
            unter = grund_fuer_leinwand(r)
            tooltip = unter
        else:
            n_f = sum(b.schwere == "FEHLER" for b in r.befunde)
            n_w = sum(b.schwere == "WARNUNG" for b in r.befunde)
            teile = []
            if n_f:
                teile.append(anzahl(n_f, "Fehler", "Fehler"))
            if n_w:
                teile.append(anzahl(n_w, "Warnung", "Warnungen"))
            if not teile:
                teile.append("keine Befunde")
            # Angezeigt wird die sichtbare Dauer (inkl. Mindestpause)
            dauer = z.get("dauer", r.dauer_s)
            teile.append(f"{de_zahl(dauer)} s")
            unter = " · ".join(teile)
            tooltip = hinweis_neutral(r.hinweis) or c.titel   # Prüfumfang, z. B. „93 Seiten …“
        status = f"<div class='z-status {klasse}'>{esc(text)}</div>"
        symbol = sym_html(klasse, zeichen)
    elif phase == "laeuft":
        sekunden = time.monotonic() - z["t0"]
        details = []
        stand = z.get("llm") or ((0, erwartet) if erwartet else None)
        if c.methode == "LLM" and stand:
            details.append(f"Antworten {stand[0]} von {stand[1]}")
        details.append(f"{sekunden:.0f} s")
        unter, tooltip = " · ".join(details), c.titel
        status = "<div class='z-status laeuft'>läuft …</div>"
        symbol = "<span class='sym laeuft'></span>"
    else:
        unter, tooltip = "", c.titel
        status = "<div class='z-status wartet'>wartet</div>"
        symbol = sym_html("wartet", "more_horiz")
    return (f"<div class='zeile {phase}'>{symbol}<span class='z-id'>{esc(c.id)}</span>"
            f"<div class='z-mitte' title='{esc(tooltip)}'><div class='z-titel'>{esc(c.titel)}"
            f"</div><div class='z-unter'>{esc(unter) or '&nbsp;'}</div></div>{status}</div>")


def lauf_tabelle_html(auswahl, zustand: dict, erwartet: dict, llm_stand: tuple[int, int]) -> str:
    """Ablaufliste: feste Regeln links (ab 7 Checks in zwei Spalten),
    Sprachmodell rechts – so passen alle 19 Checks auf eine Leinwand."""
    bloecke = []
    for ist_ki, kategorie in ((False, "kat_regeln"), (True, "kat_ki")):
        titel, piktogramm, _ = KATEGORIEN[kategorie]
        teil = [c for c in auswahl if (c.methode == "LLM") == ist_ki]
        if not teil:
            continue
        fertig = sum(zustand[c.id]["phase"] == "fertig" for c in teil)
        info = f"{fertig} von {len(teil)} fertig"
        if ist_ki and llm_stand[1]:
            info = f"Antworten: {llm_stand[0]} von {llm_stand[1]} · " + info
        zeilen = "".join(zeile_html(c, zustand[c.id], erwartet.get(c.id)) for c in teil)
        if not ist_ki and len(teil) >= 7:
            reihen = -(-len(teil) // 2)                      # aufrunden
            zeilen = (f"<div class='zeilen zweispaltig' style='--reihen:{reihen}'>"
                      f"{zeilen}</div>")
        else:
            zeilen = f"<div class='zeilen'>{zeilen}</div>"
        bloecke.append(
            f"<div class='lauf-block'><div class='lauf-block-kopf'>"
            f"<span class='lauf-block-titel'>{icon(piktogramm)}"
            f"{esc(titel)}</span>"
            f"<span class='lauf-block-info'>{esc(info)}</span></div>{zeilen}</div>")
    klasse = "lauf-raster" + (" einspaltig" if len(bloecke) == 1 else "")
    return f"<div class='{klasse}'>{''.join(bloecke)}</div>"


def lauf_kopf_html(erledigt: int, gesamt: int, info: str) -> str:
    anteil = 100 * erledigt / gesamt if gesamt else 0
    return (f"<div class='lauf-kopf'><div class='lauf-titel'><span class='sym laeuft'></span>"
            f"Prüfung läuft …<span class='lauf-zaehler'>{erledigt} von {gesamt} Checks fertig"
            f"</span></div><div class='balken'><div class='balken-fuell' "
            f"style='width:{anteil:.1f}%'></div></div>"
            f"<div class='lauf-info'>{esc(info) or '&nbsp;'}</div></div>")


def ohne_befund(lauf: dict) -> int:
    """Anzahl der Checks, die ohne Befund durchliefen (Status bestanden)."""
    return sum(r.status == "BESTANDEN" for r in lauf["ergebnisse"])


def kacheln_html(lauf: dict) -> str:
    """Ergebnis-Kacheln eines Prüflaufs: Fehler, Warnungen, Checks ohne Befund
    (grün) und ggf. übersprungene bzw. fehlgeschlagene Checks."""
    n_f, n_w = lauf["fehler"], lauf["warnungen"]
    n_skip, n_kaputt = nicht_gelaufen(lauf)
    n_ok = ohne_befund(lauf)
    kacheln = [
        (("fehler", STATUS["FEHLER"][0]) if n_f else ("ok", "check"), n_f,
         "Fehler"),
        (("warn", STATUS["WARNUNG"][0]) if n_w else ("ok", "check"), n_w,
         "Warnung" if n_w == 1 else "Warnungen"),
        (("ok", "check"), n_ok, "Check ohne Befund" if n_ok == 1 else "Checks ohne Befund"),
    ]
    if n_skip:
        kacheln.append((("skip", STATUS["ÜBERSPRUNGEN"][0]), n_skip, "übersprungen"))
    if n_kaputt:
        kacheln.append((("kaputt", STATUS["FEHLGESCHLAGEN"][0]), n_kaputt, "fehlgeschlagen"))
    teile = [f"<div class='kachel {k}'>{sym_html(k, name, 'gross')}"
             f"<span class='k-zahl'>{zahl}</span><span class='k-text'>{esc(text)}</span></div>"
             for (k, name), zahl, text in kacheln]
    return f"<div class='kacheln'>{''.join(teile)}</div>"


def schritt_lauf(strecke, checks) -> None:
    ss = st.session_state
    dokument = strecke.dokument
    auftrag = ss.get("lauf_anstehend")
    if auftrag and auftrag["dokument"] == dokument:
        ss["lauf_anstehend"] = None         # ein abgebrochener Lauf startet nicht neu
        pruefung_ausfuehren(strecke, checks, auftrag["ids"])
        return
    lauf = ss["laeufe"].get(dokument)
    if lauf is None:
        st.html("<div class='info-text'>Für dieses Dokument wurde noch keine Prüfung "
                "gestartet.</div>")
        st.button("Zum Prüfkatalog", key="zum_katalog", icon=mat(ICON["schritt"][1]),
                  on_click=gehe_zu, args=(1,))
        return
    # Gleiche Struktur wie während des Laufs (Platzhalter | Kopf | Liste), damit
    # die Zusammenfassung die Laufanzeige Element für Element ersetzt.
    st.empty()
    st.html(kacheln_html(lauf))
    ids = {r.id for r in lauf["ergebnisse"]}
    auswahl = [c for c in checks if c.id in ids]
    dauern = lauf.get("dauer_sichtbar", {})
    zustand = {r.id: {"phase": "fertig", "ergebnis": r,
                      **({"dauer": dauern[r.id]} if r.id in dauern else {})}
               for r in lauf["ergebnisse"]}
    st.html(lauf_tabelle_html(auswahl, zustand, {}, lauf.get("llm_stand", (0, 0))))
    # Weiter zu den Befunden: unten rechts, nach der Ablaufliste
    with st.container(horizontal=True, horizontal_alignment="right", key="weiterleiste"):
        st.button("Befunde ansehen", key="zu_befunden", icon=mat(ICON["weiter"]),
                  icon_position="right", type="primary", on_click=gehe_zu, args=(3,))


LAUF_TEXT = "Die Checks laufen nacheinander …"


def pruefung_ausfuehren(strecke, checks, ids: list[str]) -> None:
    """Führt die Checks aus und aktualisiert die Anzeige Ereignis für Ereignis."""
    ss = st.session_state
    dokument = strecke.dokument
    gewaehlt = set(ids)
    auswahl = [c for c in checks if c.id in gewaehlt]       # Notebook-Reihenfolge
    zustand = {c.id: {"phase": "wartet"} for c in auswahl}
    erwartet: dict[str, int] = {}                           # LLM-Check -> Anfragen
    notfall = bool(ss["notfall"])
    pause = max(0.0, float(ss["pause_s"]))
    stand = {"erledigt": 0, "info": "Prüfung wird vorbereitet …", "llm": (0, 0),
             "llm_info": ""}

    # Drei Platzhalter an den Positionen von Meldung, Katalog und Startleiste
    # (schritt_katalog) – so ersetzt der Lauf den Katalog vollständig.
    st.empty()
    platz_kopf = st.empty()
    platz_tabelle = st.empty()

    def zeichnen():
        platz_kopf.html(lauf_kopf_html(stand["erledigt"], len(auswahl), stand["info"]))
        platz_tabelle.html(lauf_tabelle_html(auswahl, zustand, erwartet, stand["llm"]))

    zeichnen()
    lauf_beginnt(dokument)
    stand_merken()                      # altes Ergebnis dieses Dokuments ist ersetzt
    beginn = time.monotonic()
    ergebnisse, dauern = [], {}
    ablauf = None
    try:
        ablauf = strecke.laufe(
            [c.id for c in auswahl], modus="notfall" if notfall else "live",
            modell=(ss["modell"] or engine.STANDARDMODELL).strip(),
            max_parallel=int(ss["max_parallel"]),
            notfall_verzoegerung_s=ss["notfall_verzoegerung_s"] if notfall else 0.0)
        for ereignis in ablauf:
            if ereignis.llm_gesamt:
                stand["llm"] = (ereignis.llm_beantwortet, ereignis.llm_gesamt)
            z = zustand.get(ereignis.check_id) if ereignis.check_id else None
            if ereignis.art == "prefetch":
                if ereignis.check_id:
                    treffer = re.search(r"(\d+)\s+Anfragen", ereignis.text)
                    if treffer:
                        erwartet[ereignis.check_id] = int(treffer.group(1))
                    stand["info"] = ("Anfragen an das Sprachmodell werden vorbereitet … "
                                     f"({ereignis.check_id})")
                else:
                    n = ereignis.llm_gesamt or sum(erwartet.values())
                    if n:
                        stand["llm_info"] = (f" Das Sprachmodell bearbeitet "
                                             f"{anzahl(n, 'Anfrage', 'Anfragen')} parallel "
                                             f"im Hintergrund.")
                    stand["info"] = LAUF_TEXT + stand["llm_info"]
            elif ereignis.art == "start" and z is not None:
                stand["info"] = LAUF_TEXT + stand["llm_info"]
                z.update(phase="laeuft", t0=time.monotonic())
            elif ereignis.art == "llm_fortschritt" and z is not None:
                z["llm"] = (ereignis.erledigt, ereignis.gesamt)
            elif ereignis.art == "ergebnis" and z is not None:
                # Mindestdauer je Check, damit das Publikum mitlesen kann
                t0 = z.get("t0", time.monotonic())
                while (rest := t0 + pause - time.monotonic()) > 0:
                    time.sleep(min(0.15, rest))
                    zeichnen()
                dauern[ereignis.check_id] = time.monotonic() - t0
                zustand[ereignis.check_id] = {"phase": "fertig", "ergebnis": ereignis.ergebnis,
                                              "dauer": dauern[ereignis.check_id]}
                ergebnisse.append(ereignis.ergebnis)
                stand["erledigt"] = ereignis.erledigt
            zeichnen()
    except Exception as fehler:
        lauf_endet()                    # kein Abbruch durch Bedienung, sondern ein Fehler
        platz_kopf.empty()
        platz_tabelle.empty()
        melde_fehler("Der Prüflauf wurde unerwartet unterbrochen. Bitte im Prüfkatalog "
                     "erneut starten.", fehler)
        return
    finally:
        if ablauf is not None:
            ablauf.close()        # beendet Hintergrund-Anfragen auch bei Abbruch

    n_f, n_w = zaehle(ergebnisse)
    lauf = {"ergebnisse": ergebnisse, "fehler": n_f, "warnungen": n_w,
            "dauer_s": time.monotonic() - beginn, "modus": "notfall" if notfall else "live",
            "llm_stand": stand["llm"], "dauer_sichtbar": dauern, "zeit": time.strftime("%H:%M")}
    ss["laeufe"][dokument] = lauf
    ss["befund_idx"][dokument] = 0
    lauf_endet()
    stand_merken()
    # Neu aufbauen: Die Prozesskette schaltet „Befunde“ und „Abgleich“ frei,
    # über der Ablaufliste erscheinen die Ergebnis-Kacheln (schritt_lauf).
    st.rerun()


# =============================================================================
# Schritt 3: Befunde
# =============================================================================
def listen_label(befund, seite: int | None) -> str:
    """Beschriftung eines Listeneintrags; das Schwere-Symbol kommt als
    Knopf-Piktogramm dazu (listen_icon, Kreisfarbe per CSS)."""
    ort = f" · S. {seite}" if seite else ""
    return (f"**{befund.check_id}**{ort} · "
            f"{md_esc(kuerzen(anzeige(befund.beschreibung), 46))}")


def listen_icon(befund) -> str:
    return mat(SCHWERE.get(befund.schwere, SCHWERE["WARNUNG"])[0])


def aktiven_befund_einblenden(index: int) -> None:
    """Scrollt die Befundliste so, dass der gewählte Befund sichtbar ist
    (nur Browser-Anzeige; ändert keine Daten)."""
    with st.container(key="skript_scroll"):
        st.html(f"""<script>
(function () {{
  var ziel = {int(index)}, versuch = 0;
  function einblenden() {{
    var knopf = document.querySelector('.st-key-befund_' + ziel + ' button');
    var box = document.querySelector('.st-key-befundliste');
    if (!knopf || !box) {{ if (versuch++ < 20) setTimeout(einblenden, 100); return; }}
    /* nur die Liste selbst scrollen, nie die ganze Seite (Höhe kommt per Skript) */
    if (box.scrollHeight <= box.clientHeight + 2) {{
      if (versuch++ < 20) setTimeout(einblenden, 100);
      return;
    }}
    var k = knopf.getBoundingClientRect(), b = box.getBoundingClientRect();
    if (k.top < b.top || k.bottom > b.bottom) {{
      box.scrollTop += (k.top - b.top) - (b.height - k.height) / 2;
    }}
  }}
  setTimeout(einblenden, 60);
}})();
</script>""", unsafe_allow_javascript=True)


def einpassen(vergleich: bool) -> None:
    """Begrenzt Befundliste und Passagen so, dass alles möglichst ohne Scrollen
    ins Fenster passt – gemessen im Browser in CSS-Pixeln, also unabhängig von
    Auflösung, Browser-Zoom und Textlänge. Bei starkem Zoom gilt eine
    Mindestgröße der Passagen; dann wird senkrecht gescrollt. Setzt nur die CSS-Variablen --bild-max und
    --liste-hoehe (Ersatzwerte im Stylesheet).

    Ohne Gegenüberstellung wird für den Seitenanfang gerechnet. Mit
    Gegenüberstellung gibt es zwei Möglichkeiten: Seitenanfang (Kopf und
    Prozesskette bleiben sichtbar) oder Navigationszeile oben (mehr Platz für
    die Passagen). Gewählt wird der Seitenanfang, solange die Passagen dort
    mindestens 70 % so groß sind; sonst scrollt das Skript zur
    Navigationszeile. So steht nie ein halb abgeschnittener Kopf oben.

    Außerdem (nur Bedienung im Browser):
    - Nach einem Klick auf die Gegenüberstellung verliert die Checkbox den
      Fokus, damit die Pfeiltasten sofort wieder blättern.
    - Hat ein Regler der Seitenleiste den Fokus, blättern die Pfeiltasten
      nicht mit (sie verstellen nur den Regler)."""
    ss = st.session_state
    ss["_skript_nr"] += 1
    modus = "vergleich" if vergleich else "oben"
    with st.container(key="skript_passen"):
        st.html(f"""<script>
/* Einpassen {ss["_skript_nr"]} */
(function () {{
  var modus = "{modus}", versuch = 0;
  var aktiv = document.activeElement;
  if (aktiv && aktiv.closest && aktiv.closest('.st-key-vergleich_umschalter')) aktiv.blur();
  var hk = window.hotkeys;
  if (hk && typeof hk.filter === 'function' && !hk.__tbRegler) {{
    var filterAlt = hk.filter;
    hk.filter = function (e) {{
      var z = e && e.target;
      if (z && z.closest && z.closest('[role="slider"]')) return false;
      return filterAlt.call(this, e);
    }};
    hk.__tbRegler = true;
  }}
  function rem(n) {{ return n * parseFloat(getComputedStyle(document.documentElement).fontSize); }}
  function summe(a) {{ return a.reduce(function (x, y) {{ return x + y; }}, 0); }}
  function passen() {{
    var main = document.querySelector('[data-testid="stMain"]');
    var nav = document.querySelector('.st-key-befund_nav');
    var box = document.querySelector('[class*="st-key-passagen"]');
    var liste = document.querySelector('.st-key-befundliste');
    if (!main || !nav) {{ if (versuch++ < 40) setTimeout(passen, 100); return; }}
    var rm = main.getBoundingClientRect();
    function y(el) {{ return el.getBoundingClientRect().top - rm.top + main.scrollTop; }}
    var reserve = rem(1.7);                                   /* unterer Seitenrand */
    var untenOben = main.clientHeight - reserve;              /* Sicht ab Seitenanfang */
    var navOben = Math.max(0, y(nav) - 8);
    var untenNav = navOben + main.clientHeight - reserve;     /* Sicht ab Navigationszeile */
    var wurzel = document.documentElement.style;
    function listeBis(unten) {{
      if (liste) wurzel.setProperty('--liste-hoehe', Math.max(rem(12), unten - y(liste)) + 'px');
    }}
    if (!box) {{ listeBis(untenOben); return; }}
    var bilder = Array.prototype.slice.call(box.querySelectorAll('[data-testid="stImage"] img'));
    if (!bilder.length) {{ if (versuch++ < 40) setTimeout(passen, 100); return; }}
    bilder.forEach(function (b) {{
      if (!b.complete && !b.dataset.tbPassen) {{
        b.dataset.tbPassen = '1';
        b.addEventListener('load', function () {{ setTimeout(passen, 30); }});
      }}
    }});
    /* nebeneinander nur, wenn die Bilder tatsächlich auf einer Höhe stehen
       (bei schmaler Fläche stellt das Stylesheet Grafiken untereinander) */
    var nebeneinander = box.className.indexOf('st-key-passagen_nebeneinander') >= 0
      && bilder.length > 1 && Math.abs(bilder[0].getBoundingClientRect().top
                                       - bilder[1].getBoundingClientRect().top) < 4;
    var hoehen = bilder.map(function (b) {{ return b.getBoundingClientRect().height; }});
    var reihen = nebeneinander ? 1 : bilder.length;
    var bildanteil = nebeneinander ? Math.max.apply(null, hoehen) : summe(hoehen);
    /* Beschriftungen und Abstände; je Bild 2 px Rahmen */
    var rest = box.getBoundingClientRect().height - bildanteil + 2 * reihen;
    /* Untergrenze je Passage: Bei starkem Browser-Zoom (kleines Fenster in
       CSS-Pixeln) bleibt die Passage lesbar groß, dann wird eben gescrollt. */
    var minBild = Math.min(window.innerHeight * 0.45, rem(16));
    function je(unten) {{
      return Math.max(minBild, (unten - y(box) - rest) / reihen); }}
    var jeOben = je(untenOben), jeNav = je(untenNav);
    if (modus !== "vergleich") {{
      wurzel.setProperty('--bild-max', Math.floor(jeOben) + 'px');
      listeBis(untenOben);
      return;
    }}
    var geladen = bilder.every(function (b) {{ return b.complete && b.naturalWidth > 0; }});
    if (!geladen) {{ return; }}                  /* entschieden wird nach dem Laden */
    /* Höhe jeder Passage bei voller Breite (ohne Höhenbegrenzung) */
    var voll = bilder.map(function (b) {{
      var c = b.closest('[data-testid="stElementContainer"]') || box;
      return b.naturalHeight * Math.max(1, c.clientWidth - 2) / b.naturalWidth; }});
    function groesse(j) {{
      var h = voll.map(function (v) {{ return Math.min(v, j); }});
      return nebeneinander ? Math.max.apply(null, h) : summe(h); }}
    var vonOben = groesse(jeOben) >= 0.7 * groesse(jeNav);
    wurzel.setProperty('--bild-max', Math.floor(vonOben ? jeOben : jeNav) + 'px');
    listeBis(vonOben ? untenOben : untenNav);
    var ziel = vonOben ? 0 : navOben, runde = 0;
    function scrollen() {{
      main.scrollTo({{ top: ziel }});
      /* Seite noch nicht neu umbrochen -> zu kurz: kurz danach erneut */
      if (Math.abs(main.scrollTop - ziel) > 4 && runde++ < 20) setTimeout(scrollen, 80);
    }}
    setTimeout(scrollen, 30);
  }}
  window.__tbPassen = passen;
  if (!window.__tbPassenResize) {{
    window.__tbPassenResize = true;
    window.addEventListener('resize', function () {{
      if (window.__tbPassen) setTimeout(window.__tbPassen, 60); }});
  }}
  setTimeout(passen, 40);
}})();
</script>""", unsafe_allow_javascript=True)


def schritt_befunde(strecke, checks) -> None:
    ss = st.session_state
    dokument = strecke.dokument
    lauf = ss["laeufe"][dokument]
    befunde = alle_befunde(lauf)
    if not befunde:
        offen = nicht_gelaufen_text(lauf)
        if offen:
            st.html(f"<div class='leer skip'>{sym_html('skip', 'remove', 'gross')}"
                    f"<span>Keine Befunde – aber das Ergebnis ist unvollständig: "
                    f"{esc(offen)}.</span></div>")
        else:
            st.html(f"<div class='leer'>{sym_html('ok', 'check', 'gross')}<span>Keine Befunde – "
                    "alle Checks sind bestanden.</span></div>")
        return
    index = min(max(0, ss["befund_idx"].get(dokument, 0)), len(befunde) - 1)
    ss["befund_idx"][dokument] = index
    infos = {c.id: c for c in checks}

    links, rechts = st.columns([0.27, 0.73], gap="medium")
    with links:
        # Kreisfarbe der Schwere-Symbole je Listeneintrag (Standard: Fehler-Rot)
        warn_regeln = ", ".join(f"[data-testid='stMain'] .st-key-befundliste .st-key-befund_{i} "
                                f".stButton [data-testid='stIconMaterial']"
                                for i, b in enumerate(befunde) if b.schwere != "FEHLER")
        stil = (f"<style>{warn_regeln} {{ background: var(--warn); color: #2E2200; }}</style>"
                if warn_regeln else "")
        # Umbruch nur zwischen den Teilen, nie innerhalb von „8 Warnungen“
        teile = [anzahl(len(befunde), "Befund", "Befunde"),
                 anzahl(lauf["fehler"], "Fehler", "Fehler"),
                 anzahl(lauf["warnungen"], "Warnung", "Warnungen")]
        st.html(f"{stil}<div class='liste-kopf'>"
                + " · ".join(f"<span class='nw'>{esc(t)}</span>" for t in teile) + "</div>")
        # Höhe und Scrollen per CSS/Skript (einpassen): bis zum unteren Bildrand
        with st.container(border=False, key="befundliste"):
            for i, b in enumerate(befunde):
                st.button(listen_label(b, befund_seite(dokument, b)), key=f"befund_{i}",
                          icon=listen_icon(b), width="stretch",
                          type="primary" if i == index else "secondary",
                          on_click=waehle_befund, args=(dokument, i))
        aktiven_befund_einblenden(index)

    with rechts:
        # Navigationszeile: Pfeile und Zähler links, Gegenüberstellung rechts (bei
        # schmaler Fläche darunter). Ohne Tooltips an den Pfeilen – sie lägen nach
        # einem Klick über der Prozesskette; die Tastenkürzel ← → nennt die Seitenleiste.
        with st.container(horizontal=True, vertical_alignment="center", key="befund_nav"):
            with st.container(horizontal=True, vertical_alignment="center", width="content",
                              gap="small", key="befund_blaettern"):
                st.button(mat(ICON["zurueck_pfeil"]), key="vorheriger", shortcut="Left",
                          disabled=index == 0, on_click=waehle_befund,
                          args=(dokument, index - 1))
                st.html(f"<div class='zaehler'>Befund {index + 1} von {len(befunde)}</div>",
                        width="content")
                st.button(mat(ICON["vor_pfeil"]), key="naechster", shortcut="Right",
                          disabled=index >= len(befunde) - 1,
                          on_click=waehle_befund, args=(dokument, index + 1))
            andere_tb = "fehlerfreier TB" if dokument == "fehlerhaft" else "fehlerhafter TB"
            ss.setdefault("vergleich_umschalter", ss["_dauer_vergleich"])
            st.checkbox(f"{mat(ICON['vergleich'])} Gegenüberstellung mit {andere_tb}",
                        key="vergleich_umschalter", on_change=vergleich_gemerkt,
                        width="content")
        befund_anzeigen(dokument, befunde[index], infos, ss["vergleich_umschalter"])
    einpassen(bool(ss["vergleich_umschalter"]))


def befund_anzeigen(dokument: str, befund, infos: dict, vergleich: bool) -> None:
    """Befundkarte: Kopfleiste (Schwere, Check, Methode, Seite) in der
    Schwere-Farbe getönt, darunter die Aussage. Typografie mit und ohne
    Gegenüberstellung identisch; danach die markierte(n) Passage(n)."""
    zeichen, text, klasse = SCHWERE.get(befund.schwere, SCHWERE["WARNUNG"])
    info = infos.get(befund.check_id)
    titel = info.titel if info else befund.check_id
    methode = METHODE.get(info.methode, info.methode) if info else ""
    fund = fundstelle_sicher(dokument, befund)
    seite = fund.seite if fund is not None else befund.seite

    kopf = [f"<span class='befund-schwere'>{sym_html(klasse, zeichen)}{esc(text)}</span>",
            f"<span class='befund-check' title='{esc(befund.check_id)} · {esc(titel)}'>Check "
            f"<span class='meta-stark'>{esc(befund.check_id)}</span> · {esc(titel)}</span>"]
    if methode:
        kopf.append(methode_chip(info.methode, methode))
    if seite:
        kopf.append(f"<span class='befund-seite'>{icon(ICON['seite'])}Seite {seite}</span>")
    kern, rest = teile_beschreibung(anzeige(befund.beschreibung))
    teile = [f"<div class='befund-karte {klasse}'><div class='befund-kopf'>{''.join(kopf)}</div>",
             f"<div class='befund-koerper'><div class='befund-text' title='{esc(kern)}'>"
             f"{esc(kern)}</div>"]
    if rest:
        teile.append(f"<div class='befund-rest' title='{esc(rest)}'>{esc(rest)}</div>")
    if dokument == "fehlerhaft":
        treffer = [f for f in fehlerliste() if fehlerprotokoll.passt_zu(befund, f)]
        if treffer:
            teile.append(f"<div class='fp-zeile'>{sym_html('ok', 'check', 'klein')}"
                         "<span class='fp-treffer'>Fehlerprotokoll: "
                         + esc(" · ".join(f"{f.nr} {f.kurz}" for f in treffer))
                         + "</span></div>")
        else:
            teile.append(f"<div class='fp-zeile'>{sym_html('skip', 'remove', 'klein')}"
                         "<span class='fp-ohne'>Ohne Bezug zum Fehlerprotokoll (Hinweis zum "
                         "Nachsehen oder Fehlalarm)</span></div>")
    else:
        teile.append(f"<div class='fp-zeile'>{sym_html('skip', 'remove', 'klein')}"
                     "<span class='fp-ohne'>Fehlerfreie TB: Hinweis zum Nachsehen oder "
                     "Fehlalarm – hier entscheidet der Mensch</span></div>")
    teile.append("</div></div>")
    st.html("".join(teile))
    passagen_anzeigen(dokument, befund, fund, seite, klasse, zeichen, vergleich)


def _png_sicher(*args) -> bytes | None:
    try:
        return passage_png(*args)
    except Exception as fehler:
        print("".join(traceback.format_exception(fehler)), file=sys.stderr)
        return None


def passagen_anzeigen(dokument: str, befund, fund, seite, klasse: str, zeichen: str,
                      vergleich: bool) -> None:
    """Markierte Passage im geprüften Dokument; bei Gegenüberstellung dieselbe
    Stelle im anderen Dokument (Layout identisch, blau markiert) – darunter,
    bei Grafiken daneben. Gegenstellen auf anderen Seiten stehen im selben
    Bild unter der Hauptstelle (je mit Kopfbalken)."""
    farbe = "fehler" if befund.schwere == "FEHLER" else "warnung"
    argumente = (dokument, befund.check_id, befund.beschreibung, befund.seite)
    png = _png_sicher(*argumente, dokument, farbe)
    if png is None:
        st.html("<div class='hinweis-klein'>Die Passage kann für diesen Befund nicht "
                "angezeigt werden.</div>")
        return
    weitere = []
    try:
        weitere = gegenstellen(*argumente)
    except Exception as fehler:
        print("".join(traceback.format_exception(fehler)), file=sys.stderr)
    seiten = list(dict.fromkeys([seite] + [g.seite for g in weitere if g.seite != seite]))
    ort = (f"Seite {seiten[0]}" if len(seiten) == 1
           else "Seiten " + ", ".join(map(str, seiten[:-1])) + f" und {seiten[-1]}")
    dok_name = "TB mit Fehlern" if dokument == "fehlerhaft" else "Fehlerfreie TB"
    zusatz = ("Genaue Stelle nicht gefunden – Seitenanfang"
              if fund is not None and fund.methode == "Seite" else "markiert")
    label_haupt = (f"<div class='bild-label {klasse}'>{sym_html(klasse, zeichen, 'klein')}"
                   f"<span class='links'>{esc(dok_name)} · {esc(ort)}</span>"
                   f"<span class='rechts'>{esc(zusatz)}</span></div>")

    if not vergleich:
        with st.container(key="passagen"):
            st.html(label_haupt)
            passage_bild(png)
        return

    andere = "fehlerfrei" if dokument == "fehlerhaft" else "fehlerhaft"
    png_vergleich = _png_sicher(*argumente, andere, "neutral")
    name = "Fehlerfreie TB" if andere == "fehlerfrei" else "TB mit Fehlern"
    symbol = icon(ICON["dokument"][andere])
    label_vergleich = (f"<div class='bild-label neutral'>{symbol}<span class='links'>Zum "
                       f"Vergleich: {esc(name)} · dieselbe Stelle ({esc(ort)})</span>"
                       "<span class='rechts'>gleiches Layout</span></div>")
    nebeneinander = fund is not None and fund.methode == "Grafik"
    if nebeneinander:
        # Grafiken sind hoch und schmal: nebeneinander statt untereinander
        # (halbe Breite – Beschriftung entsprechend kürzer)
        label_vergleich = (f"<div class='bild-label neutral'>{symbol}<span class='links'>Zum "
                           f"Vergleich: {esc(name)}</span><span class='rechts'>{esc(ort)}"
                           "</span></div>")
        with st.container(key="passagen_nebeneinander"):
            sp_links, sp_rechts = st.columns(2, gap="small")
            with sp_links:
                st.html(label_haupt)
                passage_bild(png)
            with sp_rechts:
                vergleichsbild(png_vergleich, label_vergleich)
        return
    with st.container(key="passagen_vergleich"):
        st.html(label_haupt)
        passage_bild(png)
        vergleichsbild(png_vergleich, label_vergleich)


def passage_bild(png: bytes) -> None:
    """Passage als verlustfreies PNG anzeigen (Streamlit würde sonst in JPEG
    umwandeln – unscharfe Ränder an Schrift und Markierungsrahmen)."""
    st.image(png, width="stretch", output_format="PNG")


def vergleichsbild(png: bytes | None, label: str) -> None:
    if png is None:
        st.html("<div class='hinweis-klein'>Die Vergleichsstelle kann nicht angezeigt "
                "werden.</div>")
        return
    st.html(label)
    passage_bild(png)


# =============================================================================
# Schritt 4: Abgleich mit dem Fehlerprotokoll bzw. Gegenprobe
# =============================================================================
def zeigen_knopf(spalte, schluessel: str, dokument: str, index: int | None) -> None:
    """Sprung vom Abgleich in die Befundansicht."""
    spalte.button("Zeigen", key=schluessel, icon=mat(ICON["zeigen"]), icon_position="right",
                  width="content", disabled=index is None, on_click=waehle_befund,
                  args=(dokument, index or 0, 3))


def schritt_abgleich(strecke, checks) -> None:
    ss = st.session_state
    dokument = strecke.dokument
    lauf = ss["laeufe"][dokument]
    befunde = alle_befunde(lauf)
    methoden = {c.id: c.methode for c in checks}
    if dokument == "fehlerfrei":
        gegenprobe_anzeigen(lauf, befunde, methoden, len(checks))
        return

    abgleich = fehlerprotokoll.gleiche_ab(befunde, fehlerliste())
    gruppen: dict[str, list[bool]] = {}
    for fehler, treffer in abgleich:
        gruppen.setdefault(fehler.gruppe, []).append(bool(treffer))
    n_gefunden = sum(all(werte) for werte in gruppen.values())
    n_gesamt = len(gruppen)
    klasse = "ok" if n_gefunden == n_gesamt else ("teil" if n_gefunden else "fehler")
    zugeordnet = {id(b) for _, treffer in abgleich for b in treffer}
    ohne = [b for b in befunde if id(b) not in zugeordnet]

    st.html(f"<div class='abgleich-kopf'><span class='abgleich-zahl {klasse}'>"
            f"{n_gefunden} von {n_gesamt}</span><span class='abgleich-text'>dokumentierten "
            f"Fehlern gefunden</span></div>")
    n_lauf = len(lauf["ergebnisse"])
    unter = f"Ausgewertet: {anzahl(len(befunde), 'Befund', 'Befunde')} aus {n_lauf} Checks"
    offen = nicht_gelaufen_text(lauf)
    unter += (f" – davon {offen}; nicht ausgeführte Checks können keine Fehler finden."
              if offen else ".")
    if n_lauf < len(checks):
        unter += f" Es liefen nur {n_lauf} von {len(checks)} Checks."
    unter += " F05 umfasst drei Tippfehler (F05a–c)."
    st.html(f"<div class='abgleich-unter'>{esc(unter)}</div>"
            "<div class='legende'>Gefunden durch: "
            f"{methode_chip('deterministisch', METHODE['deterministisch'])}"
            f"{methode_chip('LLM', METHODE['LLM'])}</div>")

    breiten = [0.75, 4.3, 1.55, 2.6, 1.25]
    with st.container(key="abgleich_tabelle"):
        kopf = st.columns(breiten, vertical_alignment="bottom")
        for spalte, text in zip(kopf, ["Nr.", "Eingebauter Fehler", "Ergebnis",
                                       "Gefunden durch", ""]):
            spalte.html(f"<div class='tabkopf'>{text}</div>")
        for fehler, treffer in abgleich:
            with st.container(key=f"fzeile_{fehler.nr}"):
                sp = st.columns(breiten, vertical_alignment="center")
                sp[0].html(f"<div class='fnr'>{esc(fehler.nr)}</div>")
                sp[1].html(f"<div class='fkurz'>{esc(fehler.kurz)}</div>"
                           f"<div class='fort' title='{esc(fehler.ort)}'>{esc(fehler.ort)}</div>")
                if treffer:
                    sp[2].html(f"<span class='gefunden ok'>{sym_html('ok', 'check')}"
                               "gefunden</span>")
                else:
                    sp[2].html(f"<span class='gefunden fehler'>{sym_html('fehler', 'close')}"
                               "nicht gefunden</span>")
                ids = list(dict.fromkeys(b.check_id for b in treffer))
                sp[3].html("<div class='chips'>" + "".join(chip_html(i, methoden) for i in ids)
                           + "</div>")
                # Sprungziel: bevorzugt ein Befund mit Schwere FEHLER (klarste Passage)
                ziel = next((b for b in treffer if b.schwere == "FEHLER"),
                            treffer[0] if treffer else None)
                erster = next((i for i, b in enumerate(befunde) if b is ziel), None)
                zeigen_knopf(sp[4], f"zeige_{fehler.nr}", dokument, erster)

    if ohne:
        st.html(f"<div class='abschnitt'>Befunde ohne Bezug zum Fehlerprotokoll "
                f"({len(ohne)})</div><div class='abgleich-unter'>Hinweise zum Nachsehen oder "
                "Fehlalarme – hier entscheidet der Mensch.</div>")
        befund_zeilen(dokument, befunde, ohne, methoden)


def gegenprobe_anzeigen(lauf: dict, befunde, methoden: dict, n_checks: int) -> None:
    dokument = "fehlerfrei"
    n_f, n_w = lauf["fehler"], lauf["warnungen"]
    offen = nicht_gelaufen_text(lauf)
    treffer = [b for f, liste in fehlerprotokoll.gleiche_ab(befunde, fehlerliste()) for b in liste]
    n_dokumentiert = len({f.gruppe for f in fehlerliste()})
    if n_f or treffer:
        klasse, zeichen = "fehler", "close"
        text = (f"Achtung: {anzahl(n_f, 'Fehler', 'Fehler')} gemeldet"
                + (f", {len(treffer)} Befunde ähneln Fehlern aus dem Fehlerprotokoll."
                   if treffer else "."))
        if offen:
            text += f" Außerdem {offen}."
    elif offen:
        # Nicht ausgeführte Checks: grau „unvollständig“, kein grünes „bestanden“
        klasse, zeichen = "skip", "remove"
        text = f"Gegenprobe unvollständig: {offen}."
    else:
        klasse, zeichen = "ok", "check"
        text = (f"Gegenprobe bestanden: Keiner der {n_dokumentiert} eingebauten Fehler wird "
                "gemeldet.")
    # Gleiches Muster wie im Abgleich: nur die Zahl in der Statusfarbe, die
    # Warnungen in Warnfarbe; darunter der Befund als ruhiger Satz
    warn = (f" · <span class='warn-zahl'>{anzahl(n_w, 'Warnung', 'Warnungen')}</span> zum "
            "Nachsehen" if n_w else "")
    st.html(f"<div class='abgleich-kopf'><span class='abgleich-zahl {klasse}'>"
            f"{anzahl(n_f, 'Fehler', 'Fehler')}</span><span class='abgleich-text'>in der "
            f"fehlerfreien TB{warn}</span></div>")
    st.html(f"<div class='aussage'>{sym_html(klasse, zeichen)}<span>{esc(text)}</span></div>")
    if len(lauf["ergebnisse"]) < n_checks:
        st.html(f"<div class='abgleich-unter'>Es liefen nur {len(lauf['ergebnisse'])} von "
                f"{n_checks} Checks.</div>")
    if befunde:
        titel = "Warnungen" if n_f == 0 else "Befunde"
        st.html(f"<div class='abschnitt'>{titel} ({len(befunde)})</div>")
        befund_zeilen(dokument, befunde, befunde, methoden)


def befund_zeilen(dokument: str, befunde, auswahl, methoden: dict) -> None:
    """Kompakte Befundliste mit Sprung in die Befundansicht."""
    breiten = [0.5, 0.9, 0.9, 7.1, 1.25]
    with st.container(key="ohne_tabelle"):
        for b in auswahl:
            index = next(i for i, x in enumerate(befunde) if x is b)
            zeichen, _, klasse = SCHWERE.get(b.schwere, SCHWERE["WARNUNG"])
            with st.container(key=f"bzeile_{index}"):
                sp = st.columns(breiten, vertical_alignment="center")
                sp[0].html(sym_html(klasse, zeichen))
                sp[1].html(f"<div class='chips'>{chip_html(b.check_id, methoden)}</div>")
                seite = befund_seite(dokument, b)
                sp[2].html(f"<span class='bseite'>{icon(ICON['seite'])}S. {seite}</span>"
                           if seite else "")
                sp[3].html(f"<div class='btext'>{esc(kuerzen(anzeige(b.beschreibung), 150))}"
                           "</div>")
                zeigen_knopf(sp[4], f"zeige_b{index}", dokument, index)


# =============================================================================
# Hauptablauf
# =============================================================================
def main() -> None:
    ss = st.session_state
    zustand_vorbereiten()
    seitenleiste()
    st.html(css(ss["schrift_faktor"]))
    kopfzeile()
    dokument = ss.get("dok_wahl") or "fehlerhaft"
    try:
        strecke = pruefstrecke(dokument)
    except Exception as fehler:
        melde_fehler(f"„{DOK_TITEL[dokument]}“ konnte nicht eingelesen werden.", fehler)
        return
    checks = strecke.checks()
    if ss["auswahl"] is None:                       # Start: alle Checks ausgewählt
        ss["auswahl"] = {c.id for c in checks}
    schrittleiste(dokument)
    # Vor der Ansicht: Ein laufender Prüflauf blockiert den Skriptlauf, das
    # Scrollen nach oben soll aber schon zu Beginn des Laufs passieren.
    skripte_seite()
    stand_merken()
    ansicht = {1: schritt_katalog, 2: schritt_lauf, 3: schritt_befunde, 4: schritt_abgleich}
    ansicht[ss["schritt"]](strecke, checks)
    stand_merken()


try:
    main()
except Exception as _fehler:      # nie ein Traceback auf der Leinwand
    melde_fehler("Hier ist etwas schiefgegangen. Bitte den Schritt erneut aufrufen.", _fehler)
try:
    technik_details()
except Exception:                 # Zusatzanzeige für die Vortragenden, nie kritisch
    print(traceback.format_exc(), file=sys.stderr)
