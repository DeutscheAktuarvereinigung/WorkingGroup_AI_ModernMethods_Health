#!/usr/bin/env python3
"""
Mock-Daten-Generator für PKV-Limitierungstool — v4
====================================================
Erzeugt realistische Testdaten mit:
  - Starke Differenzierung nach Tarif, Alter, Geschlecht, Versicherungsdauer
  - Breite Streuung mit echten Extremfällen (bis >100% Erhöhung)
  - Historische kumulierte Anpassungen (letzte 3 Jahre)
  - Korrelation zwischen historischer und aktueller Anpassung

Nutzung:
  python mock_daten_erzeugen.py [--ausgabeverzeichnis PFAD] [--mittlere_anpassung 0.30]
"""

import argparse
import os
import time
import numpy as np
import pandas as pd
from datetime import date, timedelta

# =============================================================================
# KONFIGURATION
# =============================================================================

ANZAHL_VERSICHERTE = 1_000_000
MITTLERE_PRAEMIENANPASSUNG = 0.30
STICHTAG = date(2026, 1, 1)
ENDALTER = 100
SEED = 42

# Tarife: anpassungs_faktor steuert die mittlere Erhöhung relativ zur Gesamtmitte.
# Große Spreizung: CL-VOLL 1.80 (alte Vollversicherung, kaum angepasst) vs PR-ZAHN 0.55
TARIFE = [
    # Classic — altes, geschlossenes Tarifwerk, lange nicht angepasst → hohe Erhöhungen
    {"tarif_id": "CL-AMB",  "bezeichnung": "Classic Ambulant",         "tarifwerk": "Classic",  "tarifart": "ambulant",    "rechnungszins": 0.025,  "geschlossen": True,  "anpassungs_faktor": 1.30},
    {"tarif_id": "CL-STAT", "bezeichnung": "Classic Stationär",        "tarifwerk": "Classic",  "tarifart": "stationaer",  "rechnungszins": 0.025,  "geschlossen": True,  "anpassungs_faktor": 1.20},
    {"tarif_id": "CL-ZAHN", "bezeichnung": "Classic Zahn",             "tarifwerk": "Classic",  "tarifart": "zahn",        "rechnungszins": 0.025,  "geschlossen": True,  "anpassungs_faktor": 1.05},
    {"tarif_id": "CL-VOLL", "bezeichnung": "Classic Vollversicherung",  "tarifwerk": "Classic", "tarifart": "voll",        "rechnungszins": 0.025,  "geschlossen": True,  "anpassungs_faktor": 1.45},

    # Komfort — mittleres Tarifwerk, moderate Spreizung
    {"tarif_id": "KO-AMB",  "bezeichnung": "Komfort Ambulant",         "tarifwerk": "Komfort",  "tarifart": "ambulant",    "rechnungszins": 0.0175, "geschlossen": False, "anpassungs_faktor": 1.00},
    {"tarif_id": "KO-STAT", "bezeichnung": "Komfort Stationär",        "tarifwerk": "Komfort",  "tarifart": "stationaer",  "rechnungszins": 0.0175, "geschlossen": False, "anpassungs_faktor": 0.90},
    {"tarif_id": "KO-ZAHN", "bezeichnung": "Komfort Zahn",             "tarifwerk": "Komfort",  "tarifart": "zahn",        "rechnungszins": 0.0175, "geschlossen": False, "anpassungs_faktor": 0.75},
    {"tarif_id": "KO-VOLL", "bezeichnung": "Komfort Vollversicherung",  "tarifwerk": "Komfort", "tarifart": "voll",        "rechnungszins": 0.0175, "geschlossen": False, "anpassungs_faktor": 1.10},

    # Premium — neuestes Tarifwerk, regelmäßig angepasst → niedrige Erhöhungen
    {"tarif_id": "PR-AMB",  "bezeichnung": "Premium Ambulant",         "tarifwerk": "Premium",  "tarifart": "ambulant",    "rechnungszins": 0.01,   "geschlossen": False, "anpassungs_faktor": 0.65},
    {"tarif_id": "PR-STAT", "bezeichnung": "Premium Stationär",        "tarifwerk": "Premium",  "tarifart": "stationaer",  "rechnungszins": 0.01,   "geschlossen": False, "anpassungs_faktor": 0.60},
    {"tarif_id": "PR-ZAHN", "bezeichnung": "Premium Zahn",             "tarifwerk": "Premium",  "tarifart": "zahn",        "rechnungszins": 0.01,   "geschlossen": False, "anpassungs_faktor": 0.50},
    {"tarif_id": "PR-VOLL", "bezeichnung": "Premium Vollversicherung",  "tarifwerk": "Premium", "tarifart": "voll",        "rechnungszins": 0.01,   "geschlossen": False, "anpassungs_faktor": 0.70},
]


# =============================================================================
# STERBETAFEL — PKV-2026 Approximation (kalibriert an BaFin-Stützpunkten)
# =============================================================================

def erzeuge_pkv_sterbetafel():
    A_m, B_m, c_m = 0.0002461254, 0.0000004204, 1.165858
    A_f, B_f, c_f = 0.000086413324, 0.000003352459, 1.11574556
    alter = np.arange(0, ENDALTER + 1)
    qx_m = 1.0 - np.exp(-(A_m + B_m * np.power(c_m, alter)))
    qx_f = 1.0 - np.exp(-(A_f + B_f * np.power(c_f, alter)))
    kind_m = [0.003,0.00025,0.00018,0.00015,0.00012,0.0001,0.00009,0.00009,0.00008,0.00008,0.00008]
    kind_f = [0.0025,0.0002,0.00014,0.00012,0.0001,0.00008,0.00007,0.00007,0.00007,0.00006,0.00006]
    for i in range(11):
        qx_m[i] = max(qx_m[i], kind_m[i])
        qx_f[i] = max(qx_f[i], kind_f[i])
    qx_m[ENDALTER] = 1.0
    qx_f[ENDALTER] = 1.0
    df_m = pd.DataFrame({"alter": alter, "geschlecht": "M", "qx": np.clip(qx_m, 0, 1)})
    df_f = pd.DataFrame({"alter": alter, "geschlecht": "W", "qx": np.clip(qx_f, 0, 1)})
    return pd.concat([df_m, df_f], ignore_index=True)


# =============================================================================
# AUSSCHEIDEORDNUNG — tarifabhängig
# =============================================================================

def erzeuge_ausscheideordnung(df_tarife, sterbetafel):
    zeilen = []
    for _, tarif in df_tarife.iterrows():
        tid = tarif["tarif_id"]
        tw = tarif["tarifwerk"]
        geschl = tarif["geschlossen"]
        sf = {"Classic": 1.05, "Komfort": 1.00, "Premium": 0.97}[tw]

        for _, z in sterbetafel.iterrows():
            a, g, qx = z["alter"], z["geschlecht"], min(z["qx"] * sf, 1.0)
            if geschl:
                storno = max(0.001, 0.005 * np.exp(-0.03 * a))
            else:
                if a < 25: storno = 0.06
                elif a < 35: storno = 0.04
                elif a < 45: storno = 0.025
                elif a < 55: storno = 0.012
                elif a < 65: storno = 0.005
                else: storno = 0.002
            zeilen.append({"tarif_id": tid, "alter": a, "geschlecht": g,
                           "qx": round(qx, 8), "storno": round(storno, 6)})
    return pd.DataFrame(zeilen)


# =============================================================================
# BESTAND — 1 Mio. Versicherte mit breiter Streuung
# =============================================================================

def erzeuge_bestand(df_tarife, mittlere_anpassung, rng):
    n = ANZAHL_VERSICHERTE
    print(f"\n  Erzeuge {n:,} Versicherte ...")

    # --- 1. Tarif-Zuweisung ---
    tarifwerk_wahl = rng.choice(["Classic", "Komfort", "Premium"], size=n, p=[0.25, 0.45, 0.30])
    tarifart_wahl = rng.choice(["voll", "ambulant", "stationaer", "zahn"], size=n, p=[0.50, 0.20, 0.15, 0.15])
    prefix_map = {"Classic": "CL", "Komfort": "KO", "Premium": "PR"}
    art_map = {"voll": "VOLL", "ambulant": "AMB", "stationaer": "STAT", "zahn": "ZAHN"}
    tarif_ids = np.array([f"{prefix_map[tw]}-{art_map[ta]}" for tw, ta in zip(tarifwerk_wahl, tarifart_wahl)])

    # --- 2. Alter — breitere Verteilung mit mehr Extremen ---
    alter_raw = rng.beta(4.0, 2.8, size=n)  # etwas flacher → mehr Ältere
    alter = np.round(18 + alter_raw * 77).astype(int)  # 18 bis 95
    alter = np.clip(alter, 18, 95)

    # Geburtsdatum
    geburtsjahre = STICHTAG.year - alter
    geburtsdaten = np.array([
        date(int(j), 1, 1) + timedelta(days=int(t))
        for j, t in zip(geburtsjahre, rng.integers(0, 365, size=n))
    ])

    # --- 3. Geschlecht ---
    geschlecht = rng.choice(["M", "W"], size=n, p=[0.55, 0.45])

    # --- 4. Versicherungsdauer ---
    mc = tarifwerk_wahl == "Classic"
    mk = tarifwerk_wahl == "Komfort"
    mp = tarifwerk_wahl == "Premium"
    vd = np.zeros(n, dtype=int)
    vd[mc] = rng.integers(15, 40, size=mc.sum())  # bis 40 Jahre
    vd[mk] = rng.integers(5, 25, size=mk.sum())   # bis 25 Jahre
    vd[mp] = rng.integers(1, 12, size=mp.sum())
    vd = np.minimum(vd, np.maximum(alter - 18, 1))
    vb_j = STICHTAG.year - vd
    versicherungsbeginn = np.array([
        date(int(j), 1, 1) + timedelta(days=int(rng.integers(0, 365)))
        for j in vb_j
    ])

    # --- 5. Bisherige Monatsprämie — stärkere Differenzierung ---
    # Basis je Tarifart
    bp_map = {"voll": 380.0, "ambulant": 190.0, "stationaer": 130.0, "zahn": 55.0}
    bp = np.array([bp_map[ta] for ta in tarifart_wahl])

    # Altersfaktor: exponentieller als vorher
    af = 0.6 + 0.4 * np.exp(0.018 * (alter - 30))
    af = np.clip(af, 0.6, 3.5)

    # Tarifwerk-Faktor
    twf = np.ones(n)
    twf[mc] = 1.20  # Classic ist teurer geworden
    twf[mk] = 1.05

    # Geschlecht-Faktor (leicht, realistisch)
    gf = np.ones(n)
    gf[(geschlecht == "M") & (tarifart_wahl == "voll")] = 1.04
    gf[(geschlecht == "W") & (tarifart_wahl == "ambulant")] = 1.06

    # Versicherungsdauer-Effekt: längere Dauer → Prämie schon mehrfach angepasst
    df_eff = 1.0 + 0.005 * vd
    df_eff = np.clip(df_eff, 1.0, 1.25)

    bp = bp * af * twf * gf * df_eff

    # Individuelles Rauschen (±20%, breiter als vorher)
    rauschen = np.clip(1.0 + rng.normal(0, 0.12, size=n), 0.6, 1.5)
    praemie_alt = np.maximum(np.round(bp * rauschen, 2), 25.0)

    # --- 6. Prämienanpassung — Skalierte Beta-Verteilung ---
    # Die Beta-Verteilung lebt auf [0,1] und wird auf ein tarifabhängiges Intervall
    # [min_anp, max_anp] skaliert. Das ergibt eine natürliche Obergrenze ohne Kappung.
    # Der kombinierte Faktor (Alter, Dauer, Geschlecht) verschiebt das Intervall.
    print("  Berechne Anpassungen (Beta-Verteilung) ...")

    # Tarif-spezifische Beta-Parameter und Intervallgrenzen
    # alpha, beta: steuern die Form (alpha < beta → rechtsschief)
    # basis_min, basis_max: Basis-Intervall in Dezimal (0.05 = 5%)
    TARIF_BETA_PARAMS = {
        # Tarif-ID:      (alpha, beta, basis_min, basis_max)
        # Classic — breit, rechtsschief, hohe Anpassungen
        "CL-VOLL": (2.0, 3.0, 0.10, 0.75),
        "CL-AMB":  (2.2, 3.3, 0.08, 0.70),
        "CL-STAT": (2.3, 3.5, 0.07, 0.65),
        "CL-ZAHN": (2.5, 4.0, 0.05, 0.55),
        # Komfort — moderater
        "KO-VOLL": (2.3, 3.5, 0.06, 0.62),
        "KO-AMB":  (2.5, 4.0, 0.05, 0.55),
        "KO-STAT": (2.8, 4.2, 0.04, 0.50),
        "KO-ZAHN": (3.0, 5.0, 0.03, 0.42),
        # Premium — konzentriert, niedrig
        "PR-VOLL": (2.8, 5.0, 0.03, 0.40),
        "PR-AMB":  (3.0, 5.5, 0.02, 0.35),
        "PR-STAT": (3.0, 6.0, 0.02, 0.32),
        "PR-ZAHN": (3.5, 7.0, 0.01, 0.25),
    }

    # Alters-Faktor: verschiebt das Intervall nach oben/unten
    alter_f = np.ones(n)
    alter_f[alter < 30] = 0.80
    alter_f[(alter >= 30) & (alter < 40)] = 0.90
    alter_f[(alter >= 40) & (alter < 50)] = 0.95
    alter_f[(alter >= 50) & (alter < 60)] = 1.05
    alter_f[(alter >= 60) & (alter < 70)] = 1.15
    alter_f[(alter >= 70) & (alter < 80)] = 1.25
    alter_f[(alter >= 80) & (alter < 90)] = 1.35
    alter_f[alter >= 90] = 1.45

    # Versicherungsdauer-Effekt
    dauer_f = np.ones(n)
    dauer_f[mc & (vd >= 30)] = 1.15
    dauer_f[mc & (vd >= 20) & (vd < 30)] = 1.08
    dauer_f[mk & (vd >= 15)] = 1.05

    # Geschlecht × Tarifart Interaktion
    ga_f = np.ones(n)
    ga_f[(geschlecht == "W") & (tarifart_wahl == "ambulant")] = 1.06
    ga_f[(geschlecht == "M") & (tarifart_wahl == "stationaer")] = 1.04
    ga_f[(geschlecht == "W") & (tarifart_wahl == "voll")] = 1.03

    # Kombinierter Skalierungsfaktor
    kf = alter_f * dauer_f * ga_f

    # Mittlere Anpassung als globaler Skalierungsfaktor
    # (die Tarif-Parameter sind auf ~26% kalibriert, skaliere relativ dazu)
    global_skala = mittlere_anpassung / 0.26

    # Anpassung per skalierter Beta-Verteilung, tarifweise
    anp = np.zeros(n)
    for tid, (alpha, beta_p, b_min, b_max) in TARIF_BETA_PARAMS.items():
        maske = tarif_ids == tid
        n_tid = maske.sum()
        if n_tid == 0:
            continue

        kf_tid = kf[maske] * global_skala

        # Intervall skalieren mit kombiniertem Faktor
        vmin = np.clip(b_min * np.power(kf_tid, 0.5), 0.01, 0.50)
        vmax = np.clip(b_max * np.power(kf_tid, 0.7), 0.05, 0.80)
        vmax = np.maximum(vmax, vmin + 0.03)  # mindestens 3pp Spread

        # Beta-Verteilung ziehen und skalieren
        raw = rng.beta(alpha, beta_p, size=n_tid)
        anp[maske] = vmin + (vmax - vmin) * raw

    # Sicherstellen: mindestens 1%, maximal 80%
    anp = np.clip(anp, 0.01, 0.80)

    praemie_neu = np.round(praemie_alt * (1.0 + anp), 2)
    erh_abs = np.round(praemie_neu - praemie_alt, 2)
    erh_pct = np.round(anp * 100, 2)

    # --- 7. Alterungsrückstellung ---
    arf = np.clip((alter - 18) / 50.0, 0.02, 1.8)
    # Stärkerer Versicherungsdauer-Effekt
    ar = np.maximum(np.round(praemie_alt * 12 * vd * arf * rng.uniform(0.7, 1.3, size=n), 2), 0.0)

    # --- 8. Historische kumulierte Anpassung (letzte 3 Jahre) ---
    print("  Erzeuge historische Anpassungen ...")

    # Basis je Tarifwerk
    hist_basis = np.zeros(n)
    hist_basis[mc] = 40.0  # Classic: Ø 40% kumuliert über 3 Jahre
    hist_basis[mk] = 22.0  # Komfort: Ø 22%
    hist_basis[mp] = 8.0   # Premium: Ø 8%

    # Alters-Effekt auf Historie
    hist_af = np.ones(n)
    hist_af[alter < 35] = 0.70
    hist_af[(alter >= 35) & (alter < 50)] = 0.90
    hist_af[(alter >= 60) & (alter < 70)] = 1.15
    hist_af[(alter >= 70) & (alter < 80)] = 1.30
    hist_af[alter >= 80] = 1.50

    # Tarif-Effekt: Voll-Tarife historisch stärker betroffen
    hist_tf = np.ones(n)
    hist_tf[tarifart_wahl == "voll"] = 1.20
    hist_tf[tarifart_wahl == "zahn"] = 0.75

    # Korrelation mit aktueller Anpassung (~0.55)
    korrelation = 0.55
    akt_norm = (anp - anp.min()) / (anp.max() - anp.min() + 1e-10)
    hist_zuf = rng.lognormal(0, 0.55, size=n)
    hist_zuf_norm = (hist_zuf - hist_zuf.min()) / (hist_zuf.max() - hist_zuf.min() + 1e-10)
    hist_score = korrelation * akt_norm + (1 - korrelation) * hist_zuf_norm

    erh_hist = hist_basis * hist_af * hist_tf * (0.2 + 1.6 * hist_score)

    # Versicherungsdauer < 3 Jahre: weniger Historie
    kurz = vd < 3
    erh_hist[kurz] *= (vd[kurz] / 3.0)

    # Top-Anpassungen: auch historisch stärker betroffen
    top_anp = anp >= np.percentile(anp, 95)
    erh_hist[top_anp] *= 1.3

    erh_hist = np.clip(np.round(erh_hist, 1), 0.0, 80.0)

    # --- 9. DataFrame ---
    print("  Baue DataFrame ...")
    return pd.DataFrame({
        "versicherten_id": [f"V{i:07d}" for i in range(1, n + 1)],
        "geburtsdatum": geburtsdaten,
        "alter": alter,
        "geschlecht": geschlecht,
        "tarifwerk": tarifwerk_wahl,
        "tarif_id": tarif_ids,
        "tarifart": tarifart_wahl,
        "versicherungsbeginn": versicherungsbeginn,
        "versicherungsdauer_jahre": vd,
        "praemie_alt_monatlich": praemie_alt,
        "praemie_neu_monatlich": praemie_neu,
        "erhoehung_absolut": erh_abs,
        "erhoehung_prozent": erh_pct,
        "erhoehung_historisch_kumuliert": erh_hist,
        "alterungsrueckstellung": ar,
    })


# =============================================================================
# STATISTIKEN
# =============================================================================

def zeige_statistiken(df, df_t, df_ao):
    print("\n" + "=" * 70)
    print("ZUSAMMENFASSUNG (v4)")
    print("=" * 70)
    print(f"\n  Versicherte:        {len(df):>12,}")
    print(f"  Ø Alter:            {df['alter'].mean():>12.1f}")
    print(f"  Altersbereich:      {df['alter'].min():>5} - {df['alter'].max()}")
    print(f"  Anteil männlich:    {(df['geschlecht'] == 'M').mean():>12.1%}")
    print(f"  Ø Prämie alt:       {df['praemie_alt_monatlich'].mean():>12.0f} €/Mon")
    print(f"  Ø Prämie neu:       {df['praemie_neu_monatlich'].mean():>12.0f} €/Mon")

    e = df["erhoehung_prozent"]
    print(f"\n  --- Erhöhung (%) ---")
    print(f"  Mittelwert:         {e.mean():>12.1f} %")
    print(f"  Median:             {e.median():>12.1f} %")
    print(f"  Standardabw.:       {e.std():>12.1f} %")
    print(f"  Min / Max:          {e.min():.1f}% / {e.max():.1f}%")
    for p in [5, 25, 75, 95, 99]:
        print(f"  P{p:02d}:                {e.quantile(p / 100):>12.1f} %")

    ea = df["erhoehung_absolut"]
    print(f"\n  --- Erhöhung (€/Mon) ---")
    print(f"  Mittelwert:         {ea.mean():>12.0f} €")
    print(f"  Max:                {ea.max():>12.0f} €")
    print(f"  Jahresvolumen:      {ea.sum() * 12:>14,.0f} €")

    h = df["erhoehung_historisch_kumuliert"]
    print(f"\n  --- Historische Anpassung (3J kumuliert) ---")
    print(f"  Ø: {h.mean():.1f}%, Median: {h.median():.1f}%, Std: {h.std():.1f}%")
    print(f"  Min/Max: {h.min():.1f}% / {h.max():.1f}%")
    print(f"  Korrelation mit aktuell: {df['erhoehung_prozent'].corr(h):.3f}")

    print(f"\n  --- Nach Tarifwerk ---")
    for tw in sorted(df["tarifwerk"].unique()):
        s = df[df["tarifwerk"] == tw]
        print(f"  {tw:>10}: n={len(s):>9,}, "
              f"Ø Erh={s['erhoehung_prozent'].mean():.1f}%, "
              f"Std={s['erhoehung_prozent'].std():.1f}%, "
              f"P95={s['erhoehung_prozent'].quantile(0.95):.1f}%, "
              f"Ø Hist={s['erhoehung_historisch_kumuliert'].mean():.1f}%")

    print(f"\n  --- Nach Tarif (Top 5 höchste Ø Erhöhung) ---")
    tarif_stats = df.groupby("tarif_id").agg(
        n=("versicherten_id", "count"),
        mean_erh=("erhoehung_prozent", "mean"),
        std_erh=("erhoehung_prozent", "std"),
        p95_erh=("erhoehung_prozent", lambda x: x.quantile(0.95)),
        max_erh=("erhoehung_prozent", "max"),
    ).sort_values("mean_erh", ascending=False)
    for tid, row in tarif_stats.head(5).iterrows():
        print(f"  {tid:>10}: n={row['n']:>9,}, Ø={row['mean_erh']:.1f}%, "
              f"Std={row['std_erh']:.1f}%, P95={row['p95_erh']:.1f}%, Max={row['max_erh']:.1f}%")

    print(f"\n  --- Extremfälle ---")
    for schwelle in [30, 40, 50, 60, 80, 100, 120]:
        anz = (df["erhoehung_prozent"] >= schwelle).sum()
        if anz > 0:
            print(f"  >= {schwelle:>3}%: {anz:>10,}  ({anz / len(df):.2%})")

    print(f"\n  --- Extremfälle absolut ---")
    for schwelle in [100, 200, 300, 500]:
        anz = (df["erhoehung_absolut"] >= schwelle).sum()
        if anz > 0:
            print(f"  >= {schwelle:>3} €: {anz:>10,}  ({anz / len(df):.2%})")

    print(f"\n  Tarife: {len(df_t)} | Ausscheideordnung: {len(df_ao):,} Zeilen")


# =============================================================================
# HAUPTPROGRAMM
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Mock-Daten-Generator v4")
    parser.add_argument("--ausgabeverzeichnis", "-o", default=".")
    parser.add_argument("--mittlere_anpassung", "-m", type=float, default=MITTLERE_PRAEMIENANPASSUNG)
    parser.add_argument("--seed", "-s", type=int, default=SEED)
    args = parser.parse_args()

    ausgabe = args.ausgabeverzeichnis
    os.makedirs(ausgabe, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    print("=" * 70)
    print("PKV-LIMITIERUNG — Mock-Daten-Generator (v4)")
    print("=" * 70)
    print(f"  Mittlere Anpassung: {args.mittlere_anpassung:.0%}")
    print(f"  Versicherte:        {ANZAHL_VERSICHERTE:,}")
    print(f"  Seed:               {args.seed}")

    t0 = time.time()

    print("\n[1/4] Tarife ...")
    df_t = pd.DataFrame(TARIFE)[["tarif_id", "bezeichnung", "tarifwerk", "tarifart", "rechnungszins", "geschlossen"]]
    df_t.to_csv(os.path.join(ausgabe, "tarife.csv"), index=False, sep=";")

    print("[2/4] Sterbetafel ...")
    sterbe = erzeuge_pkv_sterbetafel()

    print("[3/4] Ausscheideordnung ...")
    df_ao = erzeuge_ausscheideordnung(df_t, sterbe)
    df_ao.to_csv(os.path.join(ausgabe, "ausscheideordnung.csv"), index=False, sep=";")

    print("[4/4] Bestand ...")
    df_b = erzeuge_bestand(df_t, args.mittlere_anpassung, rng)
    df_b.to_csv(os.path.join(ausgabe, "bestand.csv"), index=False, sep=";")

    zeige_statistiken(df_b, df_t, df_ao)

    print(f"\n  Dauer: {time.time() - t0:.1f}s")
    for name in ["tarife.csv", "ausscheideordnung.csv", "bestand.csv"]:
        p = os.path.join(ausgabe, name)
        print(f"  {name:.<35} {os.path.getsize(p) / (1024 * 1024):>6.1f} MB")
    print(f"\nFertig! → {os.path.abspath(ausgabe)}")


if __name__ == "__main__":
    main()