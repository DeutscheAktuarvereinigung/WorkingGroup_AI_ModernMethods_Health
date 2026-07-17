import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from services.bestandsanalyse import (
    berechne_hist_daten,
    berechne_interaktive_statistik,
    berechne_kpis,
    berechne_treemap_daten,
    df_hash,
    formatiere_euro,
)
from ui.theme import (
    DAV_BLAU_AKZENT,
    DAV_GRUEN,
    DAV_ORANGE,
    PALETTE_GROSS,
    PLOTLY_LAYOUT,
)


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


def render_bestandsanalyse(df_gefiltert, _farb_map_dynamisch, _geschlecht_label, GRUPPIER_DIMENSIONEN,
                             berechne_kpis, berechne_treemap_daten, berechne_interaktive_statistik,
                             berechne_hist_daten):
    df = df_gefiltert
    h = df_hash(df)
    kpis = berechne_kpis(h, df)

    farb_dimensionen = {
        "Keine Differenzierung": (None, None),
        "Tarifwerk": ("tarifwerk", _farb_map_dynamisch(df, "tarifwerk")),
        "Tarifart": ("tarifart", _farb_map_dynamisch(df, "tarifart")),
        "Tarif (einzeln)": ("tarif_id", _farb_map_dynamisch(df, "tarif_id")),
        "Geschlecht": ("geschlecht", _farb_map_dynamisch(df, "geschlecht")),
        "Altersgruppe": ("altersgruppe", _farb_map_dynamisch(df, "altersgruppe")),
    }

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
    st.markdown("### Verteilung der Prämienerhöhung")

    ctrl1, ctrl2, ctrl3 = st.columns([1, 2, 1])
    with ctrl1:
        wert_perspektive = st.radio("Wertperspektive", ["Prozentual (%)", "Absolut (€/Monat)"], horizontal=True)
    with ctrl2:
        farb_wahl = st.selectbox("Farbliche Differenzierung", list(farb_dimensionen.keys()), index=0)
    with ctrl3:
        ausreisser_ausblenden = st.checkbox("Ausreißer ausblenden", value=False,
            help="Blendet Werte oberhalb des 95. Percentils aus den Plots aus.")

    ist_prozent = "%" in wert_perspektive
    wert_spalte = "erhoehung_prozent" if ist_prozent else "erhoehung_absolut"
    einheit = "%" if ist_prozent else "€"
    mw = kpis["erh_pct_mean"] if ist_prozent else kpis["erh_abs_mean"]
    md = kpis["erh_pct_median"] if ist_prozent else kpis["erh_abs_median"]

    df_plot = df
    if ausreisser_ausblenden:
        p95 = df[wert_spalte].quantile(0.95)
        df_plot = df[df[wert_spalte] <= p95]
        st.caption(f"Ausreißer ausgeblendet: zeige Werte ≤ {p95:.1f} {einheit} (P95). {len(df) - len(df_plot):,} Versicherte ausgeblendet.")

    farb_spalte, farb_map = farb_dimensionen[farb_wahl]
    hist_daten = berechne_hist_daten(h if not ausreisser_ausblenden else df_hash(df_plot), df_plot, farb_spalte, wert_spalte)

    col_hist, col_box = st.columns([3, 2])
    with col_hist:
        st.plotly_chart(erstelle_histogramm(hist_daten, farb_spalte, farb_map, mw, md, einheit), use_container_width=True)
    with col_box:
        st.plotly_chart(erstelle_boxplot(hist_daten, farb_spalte, farb_map, einheit), use_container_width=True)

    st.markdown("---")
    st.markdown("### Bestandsstruktur")
    treemap_farb_spalte = wert_spalte
    treemap_df = berechne_treemap_daten(h, df, treemap_farb_spalte)
    st.plotly_chart(erstelle_treemap(treemap_df, einheit), use_container_width=True)

    st.markdown("---")
    st.markdown("### Statistische Übersicht")
    st.caption("Wählen Sie eine oder mehrere Dimensionen, nach denen die Statistiken gruppiert werden sollen.")

    # Nur Dimensionen anbieten, deren Spalte im DataFrame vorhanden ist
    verfuegbare_dims = {k: v for k, v in GRUPPIER_DIMENSIONEN.items() if v in df.columns}
    gew_gruppierung = st.multiselect("Gruppieren nach", list(verfuegbare_dims.keys()), default=["Tarifwerk"], key="stat_gruppierung")
    gruppen_spalten = tuple(verfuegbare_dims[g] for g in gew_gruppierung)

    stat_df = berechne_interaktive_statistik(h, df, gruppen_spalten)

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

    st.dataframe(stat_df, hide_index=True, use_container_width=True, height=min(400, 40 + len(stat_df) * 35), column_config=col_config)
    st.download_button("📥 Statistik-Tabelle als CSV", data=stat_df.to_csv(index=False, sep=";").encode("utf-8"),
        file_name="statistik_gruppiert.csv", mime="text/csv", key="dl_stat")

    st.markdown("---")
    st.markdown("### Einzeldaten")
    ansicht = st.radio("Ansicht", ["Top 100 höchste Erhöhungen (%)", "Top 100 höchste Erhöhungen (€)", "Top 100 höchste Prämien", "Zufällige Stichprobe"], horizontal=True)

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

    st.dataframe(df_anzeige, hide_index=True, use_container_width=True, height=400,
        column_config={
            "Prämie alt (€)": st.column_config.NumberColumn(format="%.2f"),
            "Prämie neu (€)": st.column_config.NumberColumn(format="%.2f"),
            "Erhöhung (€)": st.column_config.NumberColumn(format="%.2f"),
            "Erhöhung (%)": st.column_config.NumberColumn(format="%.1f"),
            "Alter.-Rückst. (€)": st.column_config.NumberColumn(format="%.2f"),
        })

    with st.expander("📥 CSV-Export Gesamtbestand"):
        st.info(f"Der gefilterte Bestand umfasst {len(df):,} Zeilen.")
        if st.button("CSV erzeugen"):
            csv_bytes = df.to_csv(index=False, sep=";").encode("utf-8")
            st.download_button(label="⬇️ Herunterladen", data=csv_bytes, file_name="bestand_gefiltert.csv", mime="text/csv")
