import numpy as np
import pandas as pd
import streamlit as st

from services.data_loader import validiere_mittelquellen_config
from services.bestandsanalyse import formatiere_euro


CONFIG_SPALTEN = [
    "quelle_id", "name", "aktiv", "prioritaet", "typ", "betrag_euro",
    "betrag_spalte", "betrag_einheit", "unterliegt_limitierungsregeln",
    "einsatzmodus", "anwendungsphase", "filter_spalten", "filter_operatoren",
    "filter_werte", "fallback_erlaubt",
]


def _ist_numerische_spalte(df: pd.DataFrame, spalte: str) -> bool:
    return spalte in df.columns and pd.api.types.is_numeric_dtype(df[spalte])


def _default_mittelquellen_config(df_bestand: pd.DataFrame) -> pd.DataFrame:
    """Erzeugt die Phase-A/D-Default-Konfiguration fuer die UI."""
    hat_ueberzins = _ist_numerische_spalte(df_bestand, "ueberzins_mittel_euro")
    hat_zu10 = _ist_numerische_spalte(df_bestand, "zu10_mittel_euro")

    return pd.DataFrame([
        {
            "quelle_id": "ueberzins",
            "name": "Ueberzins kunden-/tarifindividuell",
            "aktiv": hat_ueberzins,
            "prioritaet": 1,
            "typ": "zeilenindividuell",
            "betrag_euro": np.nan,
            "betrag_spalte": "ueberzins_mittel_euro" if hat_ueberzins else "",
            "betrag_einheit": "einmaleinlage",
            "unterliegt_limitierungsregeln": False,
            "einsatzmodus": "pflicht_vollstaendig",
            "anwendungsphase": "vor_regeln",
            "filter_spalten": "",
            "filter_operatoren": "",
            "filter_werte": "",
            "fallback_erlaubt": True,
        },
        {
            "quelle_id": "zu10",
            "name": "ZU10-Mittel Vollversicherung ab 65",
            "aktiv": hat_zu10,
            "prioritaet": 2,
            "typ": "zeilenindividuell",
            "betrag_euro": np.nan,
            "betrag_spalte": "zu10_mittel_euro" if hat_zu10 else "",
            "betrag_einheit": "einmaleinlage",
            "unterliegt_limitierungsregeln": True,
            "einsatzmodus": "nur_bedarf_finanzieren",
            "anwendungsphase": "nach_regeln",
            "filter_spalten": "tarifart|alter",
            "filter_operatoren": "==|>=",
            "filter_werte": "voll|65",
            "fallback_erlaubt": True,
        },
        {
            "quelle_id": "rfb_frei",
            "name": "Freie RfB",
            "aktiv": True,
            "prioritaet": 3,
            "typ": "global",
            "betrag_euro": float(st.session_state.get("default_budget", 100_000_000)),
            "betrag_spalte": "",
            "betrag_einheit": "einmaleinlage",
            "unterliegt_limitierungsregeln": True,
            "einsatzmodus": "nur_bedarf_finanzieren",
            "anwendungsphase": "nach_regeln",
            "filter_spalten": "",
            "filter_operatoren": "",
            "filter_werte": "",
            "fallback_erlaubt": True,
        },
    ])


def _normalisiere_config(df_config: pd.DataFrame) -> pd.DataFrame:
    """Ergaenzt fehlende Konfigurationsspalten und synchronisiert die Anwendungsphase."""
    config = df_config.copy()
    for spalte in CONFIG_SPALTEN:
        if spalte not in config.columns:
            if spalte in {"aktiv", "unterliegt_limitierungsregeln", "fallback_erlaubt"}:
                config[spalte] = False
            elif spalte == "prioritaet":
                config[spalte] = np.arange(1, len(config) + 1)
            else:
                config[spalte] = ""

    config = config[CONFIG_SPALTEN]
    for spalte in ["aktiv", "unterliegt_limitierungsregeln", "fallback_erlaubt"]:
        config[spalte] = config[spalte].map(lambda x: str(x).strip().lower() in {"true", "1", "ja", "yes"} if not isinstance(x, bool) else x)

    config["prioritaet"] = pd.to_numeric(config["prioritaet"], errors="coerce").fillna(1).astype(int)
    config["betrag_euro"] = pd.to_numeric(config["betrag_euro"], errors="coerce")
    config["anwendungsphase"] = np.where(
        config["unterliegt_limitierungsregeln"], "nach_regeln", "vor_regeln"
    )
    return config


def _initialisiere_config(df_bestand: pd.DataFrame, df_mittelquellen_geladen: pd.DataFrame | None) -> None:
    if "mittelquellen_config" in st.session_state:
        return
    if df_mittelquellen_geladen is not None:
        st.session_state["mittelquellen_config"] = _normalisiere_config(df_mittelquellen_geladen)
    else:
        st.session_state["mittelquellen_config"] = _default_mittelquellen_config(df_bestand)


def _summen_je_quelle(df_bestand: pd.DataFrame, config: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for quelle in config.itertuples(index=False):
        if not bool(quelle.aktiv):
            continue
        betrag_spalte = str(quelle.betrag_spalte).strip()
        if betrag_spalte and betrag_spalte in df_bestand.columns:
            verfuegbar = float(df_bestand[betrag_spalte].sum())
        elif pd.notna(quelle.betrag_euro):
            verfuegbar = float(quelle.betrag_euro)
        else:
            verfuegbar = 0.0
        rows.append({
            "Quelle": quelle.name,
            "Prioritaet": int(quelle.prioritaet),
            "Regelbindung": "regelgebunden" if bool(quelle.unterliegt_limitierungsregeln) else "regelunabhaengig",
            "Phase": quelle.anwendungsphase,
            "Verfuegbar (konfig.)": formatiere_euro(verfuegbar),
            "Betragsspalte": betrag_spalte or "-",
            "Filter": str(quelle.filter_spalten) if str(quelle.filter_spalten).strip() else "-",
        })
    return pd.DataFrame(rows)


def render_mittelkonfiguration(
    df_bestand: pd.DataFrame,
    df_mittelquellen_geladen: pd.DataFrame | None = None,
) -> None:
    """Rendert den Tab fuer Mittelquellen- und Topfkonfiguration."""
    st.markdown("### 💶 Mittelkonfiguration")
    st.caption(
        "Konfigurieren Sie, welche Mittelquellen in welcher Reihenfolge eingesetzt werden "
        "und ob sie den UI-Limitierungsregeln unterliegen."
    )

    _initialisiere_config(df_bestand, df_mittelquellen_geladen)

    numeric_cols = [c for c in df_bestand.columns if pd.api.types.is_numeric_dtype(df_bestand[c])]
    betragsspalten = [""] + numeric_cols
    filter_spalten = ["alter", "tarifart", "tarifwerk", "tarif_id", "geschlecht", "altersgruppe"]
    filter_spalten = [s for s in filter_spalten if s in df_bestand.columns]

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("↩️ Defaults wiederherstellen", use_container_width=True):
            st.session_state["mittelquellen_config"] = _default_mittelquellen_config(df_bestand)
            st.rerun()
    with c2:
        if df_mittelquellen_geladen is not None:
            if st.button("📄 Geladene CSV verwenden", use_container_width=True):
                st.session_state["mittelquellen_config"] = _normalisiere_config(df_mittelquellen_geladen)
                st.rerun()
        else:
            st.info("Keine mittelquellen_config.csv geladen.")
    with c3:
        st.metric("Mittelspalten", len([c for c in ["ueberzins_mittel_euro", "zu10_mittel_euro"] if c in df_bestand.columns]))

    st.markdown("#### Quellen bearbeiten")
    st.caption(
        "Die Phase wird automatisch aus der Regelbindung abgeleitet: "
        "regelunabhängig = vor_regeln, regelgebunden = nach_regeln. "
        f"Verfügbare Filterspalten: {', '.join(filter_spalten) if filter_spalten else 'keine'}"
    )

    config = _normalisiere_config(st.session_state["mittelquellen_config"])
    editor = st.data_editor(
        config,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "aktiv": st.column_config.CheckboxColumn("Aktiv"),
            "prioritaet": st.column_config.NumberColumn("Priorität", min_value=1, step=1),
            "typ": st.column_config.SelectboxColumn("Typ", options=["global", "zeilenindividuell", "segmentiert"]),
            "betrag_spalte": st.column_config.SelectboxColumn("Betragsspalte", options=betragsspalten),
            "betrag_einheit": st.column_config.SelectboxColumn("Einheit", options=["einmaleinlage", "monatlich"]),
            "unterliegt_limitierungsregeln": st.column_config.CheckboxColumn("Unterliegt Regeln"),
            "einsatzmodus": st.column_config.SelectboxColumn(
                "Einsatzmodus", options=["pflicht_vollstaendig", "nur_bedarf_finanzieren", "optional"]
            ),
            "anwendungsphase": st.column_config.SelectboxColumn("Phase", options=["vor_regeln", "nach_regeln"], disabled=True),
            "fallback_erlaubt": st.column_config.CheckboxColumn("Fallback"),
        },
        key="mittelquellen_editor",
    )
    editor = _normalisiere_config(editor)

    v1, v2 = st.columns([1, 2])
    with v1:
        if st.button("✅ Konfiguration übernehmen", type="primary", use_container_width=True):
            try:
                validiere_mittelquellen_config(editor, df_bestand)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["mittelquellen_config"] = editor
                st.success("Mittelquellen-Konfiguration übernommen und validiert.")
    with v2:
        try:
            validiere_mittelquellen_config(editor, df_bestand)
            st.success("Aktueller Entwurf ist valide.")
        except ValueError as exc:
            st.warning(f"Aktueller Entwurf ist noch nicht valide: {exc}")

    st.markdown("#### Aktive Quellen")
    summary = _summen_je_quelle(df_bestand, editor)
    if len(summary) == 0:
        st.info("Keine aktive Mittelquelle konfiguriert.")
    else:
        st.dataframe(summary.sort_values("Prioritaet"), hide_index=True, use_container_width=True)

    with st.expander("Hinweise zur Filterdefinition"):
        st.markdown(
            """
- Mehrere Filter werden pipe-getrennt definiert, z. B. `tarifart|alter`, `==|>=`, `voll|65`.
- Unterstützte Operatoren: `==`, `!=`, `>=`, `>`, `<=`, `<`, `in`, `not in`.
- Beispiel ZU10: `filter_spalten=tarifart|alter`, `filter_operatoren` mit Wert `==|>=`, `filter_werte=voll|65`.
- Fehlende Betragsspalten oder Filterspalten werden als fachliche Fehler behandelt.
            """
        )

    st.session_state["mittelquellen_config_entwurf"] = editor
