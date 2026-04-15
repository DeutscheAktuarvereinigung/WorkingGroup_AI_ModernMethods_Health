import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from services.bestandsanalyse import df_hash, formatiere_euro
from ui.theme import (
    DAV_BLAU_AKZENT,
    DAV_BLAU_DUNKEL,
    DAV_GRUEN,
    DAV_ORANGE,
    PLOTLY_LAYOUT,
)


def _geschlecht_label(code):
    """M/W/D → deutscher Label"""
    mapping = {"M": "Männlich", "W": "Weiblich", "D": "Divers"}
    return mapping.get(str(code), str(code))


def render_limitierung(
    df_bestand,
    df_gefiltert,
    df_ao,
    df_tarife,
    GRUPPIER_DIMENSIONEN,
    berechne_barwertfaktoren,
    berechne_limitierung,
    berechne_sensitivitaet,
    formatiere_euro,
):
    """
    Rendert den gesamten Tab "Limitierungsrechnung".
    Verwaltet session_state für Regeln, Ergebnisse, Sensitivitätsanalyse.
    """
    st.markdown("### ⚖️ Limitierungsrechnung")

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
