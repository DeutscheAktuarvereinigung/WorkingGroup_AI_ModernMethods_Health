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
    """Lade echte PKV-Sterbetafel aus CSV-Datei.
    
    Liest die offizielle PKV-Sterbetafel 2026 aus der lokalen CSV-Datei,
    validiert die Daten und konvertiert sie in das interne Format.
    Trennt die Daten nach Geschlecht (M/W) und clippt Sterbewahrscheinlichkeiten
    auf den zulässigen Bereich [0, 1].
    
    Returns:
        pd.DataFrame: Sterbetafel mit Spalten:
            - alter: Alter (0-100+)
            - geschlecht: 'M' (Männer, qx) oder 'W' (Frauen, qy)
            - qx: Sterbewahrscheinlichkeit, clipped auf [0, 1]
    
    Raises:
        FileNotFoundError: Falls pkv_sterbetafel.csv nicht im Arbeitsverzeichnis liegt
        ValueError: Falls erforderliche Spalten (Alter, qx, qy) fehlen oder
                   nicht numerisch konvertiert werden können
    
    Notes:
        - qx: Alter- und geschlechtsspezifische Sterbewahrscheinlichkeit (Männer)
        - qy: Alter- und geschlechtsspezifische Sterbewahrscheinlichkeit (Frauen)
        - Format: CSV mit Header, Separator ","
    """
    # Lade echte PKV-Sterbetafel aus CSV
    tafel_pfad = "pkv_sterbetafel.csv"
    df = pd.read_csv(tafel_pfad, sep=",", skiprows=1)
    
    # Bereinige Spalten: entferne Leerzeichen aus Spaltennamen
    df.columns = df.columns.str.strip()
    # Entferne unbenannte Spalten (entstehen durch Trailing-Komma in CSV)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.dropna()
    
    # Konvertiere zu numerisch (fehlerhafte Werte werden NaN)
    df["Alter"] = pd.to_numeric(df["Alter"], errors="coerce")
    df["qx"] = pd.to_numeric(df["qx"], errors="coerce")
    df["qy"] = pd.to_numeric(df["qy"], errors="coerce")
    
    # Entferne Zeilen mit NaN (nach Konvertierung)
    df = df.dropna()
    alter_values = df["Alter"].values.astype(int)
    
    # Splitte Daten nach Geschlecht:
    # - qx = Sterbewahrscheinlichkeit Männer
    # - qy = Sterbewahrscheinlichkeit Frauen
    df_m = pd.DataFrame({
        "alter": alter_values,
        "geschlecht": "M",
        "qx": np.clip(df["qx"].values, 0, 1)  # Clippe auf [0, 1] zur Sicherheit
    })
    
    df_f = pd.DataFrame({
        "alter": alter_values,
        "geschlecht": "W",
        "qx": np.clip(df["qy"].values, 0, 1)  # Clippe auf [0, 1] zur Sicherheit
    })
    
    return pd.concat([df_m, df_f], ignore_index=True)


# =============================================================================
# AUSSCHEIDEORDNUNG — tarifabhängig
# =============================================================================

def erzeuge_ausscheideordnung(df_tarife, sterbetafel):
    """Erzeuge tarifspezifische Ausscheideordnung.
    
    Kombiniert Sterbetafel und Stornoquoten für jeden Tarif und jede
    Alter-Geschlecht-Kombination. Berücksichtigt tarifwerk-spezifische
    Sterblichkeitsfaktoren und geschlossen vs. offene Tarife mit
    unterschiedlichen Stornoquoten-Profilen.
    
    Args:
        df_tarife (pd.DataFrame): Tarifseigenschaften mit Spalten:
            - tarif_id: Eindeutige Tarif-ID (z.B. 'CL-AMB')
            - tarifwerk: Tarifwerk-Kategorie ('Classic', 'Komfort', 'Premium')
            - geschlossen: bool, ob Tarifwerk geschlossen ist
        sterbetafel (pd.DataFrame): Sterbetafel mit Spalten:
            - alter: Lebensalter
            - geschlecht: 'M' oder 'W'
            - qx: Sterbewahrscheinlichkeit
    
    Returns:
        pd.DataFrame: Ausscheideordnung mit Spalten:
            - tarif_id: Tarif-Identifier
            - alter: Lebensalter (0-100+)
            - geschlecht: 'M' oder 'W'
            - qx: Tarifwerk-adjustierte Sterbwahrscheinlichkeit
            - storno: Stornoquote (relative Häufigkeit von Versicherungsauflösungen)
    
    Notes:
        Stornoquoten-Profile:
        - Geschlossene Tarife: exponentiell fallend mit Alter (0.5%-0.1%)
        - Offene Tarife: Age-Banded (6% bei <25J, fallend bis 0.2% bei >65J)
        - Klassische Annahme: Ältere reduzieren häufiger bei geschlossenen Tarifen
    """
    zeilen = []
    for _, tarif in df_tarife.iterrows():
        tid = tarif["tarif_id"]
        tw = tarif["tarifwerk"]
        geschl = tarif["geschlossen"]
        # Tarifwerk-spezifische Sterblichkeits-Adjustierung
        # Classic: höhere Mortalität (älteres Risikokollektiv)
        # Premium: niedrigere Mortalität (bessere Risikoselektion)
        sf = {"Classic": 1.05, "Komfort": 1.00, "Premium": 0.97}[tw]

        for _, z in sterbetafel.iterrows():
            a, g, qx = z["alter"], z["geschlecht"], min(z["qx"] * sf, 1.0)
            
            # Berechne Stornoquote basierend auf Tarifwerk und Alter
            if geschl:
                # Geschlossene Tarife: exponentiell fallend (Ältere weniger Storno)
                storno = max(0.001, 0.005 * np.exp(-0.03 * a))
            else:
                # Offene Tarife: altersgestaffelt (junge Menschen haben höhere Storno)
                if a < 25:
                    storno = 0.06      # 6% bei unter 25
                elif a < 35:
                    storno = 0.04      # 4% bei 25-34
                elif a < 45:
                    storno = 0.025     # 2.5% bei 35-44
                elif a < 55:
                    storno = 0.012     # 1.2% bei 45-54
                elif a < 65:
                    storno = 0.005     # 0.5% bei 55-64
                else:
                    storno = 0.002     # 0.2% bei 65+
            
            zeilen.append({
                "tarif_id": tid,
                "alter": a,
                "geschlecht": g,
                "qx": round(qx, 8),           # 8 Dezimalstellen für Genauigkeit
                "storno": round(storno, 6)   # 6 Dezimalstellen
            })
    return pd.DataFrame(zeilen)


# =============================================================================
# BESTAND — 1 Mio. Versicherte mit breiter Streuung
# =============================================================================

def erzeuge_bestand(df_tarife, mittlere_anpassung, rng):
    """Erzeuge 1 Mio. realistischer PKV-Versichertendaten mit Prämienanpassungen.
    
    Implementiert ein hochrealistisches Modell zur Simulation von PKV-Bestandsdaten
    mit starker Differenzierung nach Tarif, Alter, Geschlecht und Versicherungsdauer.
    Die Prämienanpassungen folgen einer tarifwerk-spezifischen skalierten Beta-Verteilung
    mit Alters-, Dauer- und Geschlechtseffekten.
    
    Args:
        df_tarife (pd.DataFrame): Tarifseigenschaften
        mittlere_anpassung (float): Zielwert für Ø Anpassung als Dezimal (z.B. 0.30)
        rng (np.random.Generator): Zufallsgenerator (für Reproduzierbarkeit)
    
    Returns:
        pd.DataFrame: Versichertendaten mit 16 Spalten:
            - person_id, versicherten_id, geburtsdatum, alter, geschlecht
            - tarifwerk, tarif_id, tarifart
            - versicherungsbeginn, versicherungsdauer_jahre
            - praemie_alt_monatlich, praemie_neu_monatlich
            - erhoehung_absolut, erhoehung_prozent
            - erhoehung_historisch_kumuliert, alterungsrueckstellung
    """
    n_ziel = ANZAHL_VERSICHERTE
    print("  Erzeuge Personen-Struktur (Voll + Modul) ...")

    # --- 1. Person-Struktur bestimmen ---
    # ~50% Voll-Tarif-Personen (genau 1 Tarif "voll" pro Person)
    # ~50% Modul-Tarif-Personen (2-4 Tarife aus ambulant/stationaer/zahn, ggf. +voll)
    n_voll_personen = n_ziel // 2
    n_modul_zeilen_ziel = n_ziel - n_voll_personen

    # Generiere Modul-Personen mit 2-4 Tarifen pro Person
    modul_counts = []
    total_modul = 0
    while total_modul < n_modul_zeilen_ziel:
        c = int(rng.choice([2, 3, 4], p=[0.40, 0.40, 0.20]))
        if total_modul + c > n_modul_zeilen_ziel:
            rest = n_modul_zeilen_ziel - total_modul
            if rest >= 2:
                modul_counts.append(rest)
            break
        modul_counts.append(c)
        total_modul += c
    modul_counts = np.array(modul_counts, dtype=int)
    n_modul_personen = len(modul_counts)
    n_personen_gesamt = n_voll_personen + n_modul_personen
    print(f"    {n_voll_personen:,} Voll-Personen + {n_modul_personen:,} Modul-Personen "
          f"({modul_counts.sum():,} Zeilen) = {n_voll_personen + modul_counts.sum():,} Zeilen gesamt")

    # --- 2. Personen-Demographie generieren (identisch pro Person) ---
    person_tarifwerk = rng.choice(["Classic", "Komfort", "Premium"],
                                  size=n_personen_gesamt, p=[0.25, 0.45, 0.30])
    alter_raw = rng.beta(4.0, 2.8, size=n_personen_gesamt)
    person_alter = np.round(18 + alter_raw * 77).astype(int)
    person_alter = np.clip(person_alter, 18, 95)
    person_geschlecht = rng.choice(["M", "W"], size=n_personen_gesamt, p=[0.55, 0.45])

    person_geburtsjahre = STICHTAG.year - person_alter
    person_geburtsdaten = np.array([
        date(int(j), 1, 1) + timedelta(days=int(t))
        for j, t in zip(person_geburtsjahre, rng.integers(0, 365, size=n_personen_gesamt))
    ])

    mc_p = person_tarifwerk == "Classic"
    mk_p = person_tarifwerk == "Komfort"
    mp_p = person_tarifwerk == "Premium"
    person_vd = np.zeros(n_personen_gesamt, dtype=int)
    person_vd[mc_p] = rng.integers(15, 40, size=mc_p.sum())
    person_vd[mk_p] = rng.integers(5, 25, size=mk_p.sum())
    person_vd[mp_p] = rng.integers(1, 12, size=mp_p.sum())
    person_vd = np.minimum(person_vd, np.maximum(person_alter - 18, 1))

    person_vb_j = STICHTAG.year - person_vd
    person_vb = np.array([
        date(int(j), 1, 1) + timedelta(days=int(rng.integers(0, 365)))
        for j in person_vb_j
    ])

    # --- 3. Expand Personen → Zeilen (np.repeat für Demographie) ---
    # Voll-Personen haben 1 Zeile, Modul-Personen haben modul_counts[k] Zeilen
    counts_per_person = np.concatenate([np.ones(n_voll_personen, dtype=int), modul_counts])
    n = int(counts_per_person.sum())

    person_id_labels = np.array([f"P{i:07d}" for i in range(1, n_personen_gesamt + 1)])
    person_id_expanded = np.repeat(person_id_labels, counts_per_person)

    tarifwerk_wahl = np.repeat(person_tarifwerk, counts_per_person)
    alter = np.repeat(person_alter, counts_per_person)
    geschlecht = np.repeat(person_geschlecht, counts_per_person)
    geburtsdaten = np.repeat(person_geburtsdaten, counts_per_person)
    vd = np.repeat(person_vd, counts_per_person)
    versicherungsbeginn = np.repeat(person_vb, counts_per_person)

    # --- 4. Tarifart-Zuweisung ---
    # Voll-Personen: tarifart = "voll"
    # Modul-Personen: 2-4 distinkte Tarifarten aus {ambulant, stationaer, zahn, voll}
    tarifart_wahl = np.empty(n, dtype=object)
    tarifart_wahl[:n_voll_personen] = "voll"

    modul_offsets = n_voll_personen + np.concatenate([[0], np.cumsum(modul_counts[:-1])])
    modul_arten = ["ambulant", "stationaer", "zahn"]
    for k, count in enumerate(modul_counts):
        o = modul_offsets[k]
        if count == 4:
            arts = list(rng.permutation(modul_arten + ["voll"]))
        elif count == 3:
            arts = list(rng.permutation(modul_arten))
        else:
            chosen = rng.choice(modul_arten, size=count, replace=False)
            arts = list(chosen)
        tarifart_wahl[o:o + count] = arts

    prefix_map = {"Classic": "CL", "Komfort": "KO", "Premium": "PR"}
    art_map = {"voll": "VOLL", "ambulant": "AMB", "stationaer": "STAT", "zahn": "ZAHN"}
    tarif_ids = np.array([f"{prefix_map[tw]}-{art_map[ta]}" for tw, ta in zip(tarifwerk_wahl, tarifart_wahl)])

    mc = tarifwerk_wahl == "Classic"
    mk = tarifwerk_wahl == "Komfort"
    mp = tarifwerk_wahl == "Premium"

    # --- 5. Bisherige Monatsprämie (komplexe Multiplikativ-Faktorenlogik) ---
    # Basis: je Tarifart (Ärztegebühren, Krankenhaus, Zahnersatz)
    bp_map = {"voll": 380.0, "ambulant": 190.0, "stationaer": 130.0, "zahn": 55.0}
    bp = np.array([bp_map[ta] for ta in tarifart_wahl])

    # Altersfaktor: exponentiell steigende Prämien mit Alter
    # Formel: 0.6 + 0.4 * exp(0.018 * (age - 30))
    # Effekt: Bei 30J: 1.0x, Bei 50J: 1.2x, Bei 70J: 1.6x
    af = 0.6 + 0.4 * np.exp(0.018 * (alter - 30))
    af = np.clip(af, 0.6, 3.5)  # Realistisches Spektrum

    # Tarifwerk-Faktor (Risiko- und Kostenstruktur)
    twf = np.ones(n)
    twf[mc] = 1.20  # Classic: Älteres Kollektiv, höhere Kosten
    twf[mk] = 1.05  # Komfort: Neuere Tarifgeneration
    # Premium bleibt auf 1.0 (Basis)

    # Geschlecht-Faktor (subtil, nur bei bestimmten Tarifarten)
    gf = np.ones(n)
    gf[(geschlecht == "M") & (tarifart_wahl == "voll")] = 1.04  # Männer zahlen mehr für Voll
    gf[(geschlecht == "W") & (tarifart_wahl == "ambulant")] = 1.06  # Frauen für Ambulant

    # Versicherungsdauer-Effekt: Längere Dauer → bereits mehrfach angepasst
    # +0.5% pro Versicherungsjahr (max. 25% Aufschlag)
    df_eff = 1.0 + 0.005 * vd
    df_eff = np.clip(df_eff, 1.0, 1.25)

    # Kombiniere alle Faktoren multiplikativ
    bp = bp * af * twf * gf * df_eff

    # Individuelles Rauschen (Basis-Prämie wird variiert)
    # Normal(0, 0.12) → ±12 Std.Abw., dann clippt auf [0.6, 1.5]
    rauschen = np.clip(1.0 + rng.normal(0, 0.12, size=n), 0.6, 1.5)
    # Minimum 25€ als physikalisches Limit
    praemie_alt = np.maximum(np.round(bp * rauschen, 2), 25.0)

    # --- 6. Prämienanpassung (Zentrale Modell-Komponente) ---
    # Methode: Skalierte Beta-Verteilung auf tarifabhängigem Intervall
    # Vorteil: Natürliche Obergrenze (keine unerwünschten Extreme), gute Schiefe
    # Workflow:
    #   1. Definiere tarifspezif. Basis-Intervall [min, max] in Dezimal
    #   2. Berechne Skalierungsfaktoren (Alter, Dauer, Geschlecht)
    #   3. Adaptiere Intervall mit Faktoren
    #   4. Ziehe Beta-Verteilte Werte und skaliere auf Intervall
    #   5. Globale Skalierung auf mittlere_anpassung
    print("  Berechne Anpassungen (Beta-Verteilung) ...")

    # Tarif-spezifische Beta-Parameter und Intervallgrenzen
    # Format: (alpha, beta, basis_min, basis_max)
    # alpha, beta: Beta-Verteilungsparameter (alpha < beta → rechtsschief)
    # basis_min, basis_max: Basis-Intervall in Dezimal (z.B. 0.10 = 10%)
    # Beobachtung: Classic > Komfort > Premium (ältere Tarife mehr Anpassung)
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

    # Alters-Faktor: Ältere Versicherte haben höhere Anpassungen
    # Logik: Höheres Alter → höhere Kosten → stärkere Anpassung notwendig
    # Range: 0.80 (jung) bis 1.45 (90+)
    alter_f = np.ones(n)
    alter_f[alter < 30] = 0.80      # Junge: -20% (niedrige Kosten)
    alter_f[(alter >= 30) & (alter < 40)] = 0.90
    alter_f[(alter >= 40) & (alter < 50)] = 0.95
    alter_f[(alter >= 50) & (alter < 60)] = 1.05
    alter_f[(alter >= 60) & (alter < 70)] = 1.15
    alter_f[(alter >= 70) & (alter < 80)] = 1.25
    alter_f[(alter >= 80) & (alter < 90)] = 1.35
    alter_f[alter >= 90] = 1.45      # Älteste: +45% (höchste Kosten)

    # Versicherungsdauer-Effekt: Langzeitversicherte haben mehr Anpassungen
    # Logik: Längerer Zeitraum → mehr kumulative Anpassungen bereits eingezahlt
    dauer_f = np.ones(n)
    dauer_f[mc & (vd >= 30)] = 1.15  # Classic 30+ Jahre: +15%
    dauer_f[mc & (vd >= 20) & (vd < 30)] = 1.08  # Classic 20-29 Jahre: +8%
    dauer_f[mk & (vd >= 15)] = 1.05  # Komfort 15+ Jahre: +5%

    # Geschlecht × Tarifart Interaktion Spezialeffekte
    # Subtile geschlechtsspezifische Effekte je Tarifart
    ga_f = np.ones(n)
    ga_f[(geschlecht == "W") & (tarifart_wahl == "ambulant")] = 1.06  # Frauen Ambulant
    ga_f[(geschlecht == "M") & (tarifart_wahl == "stationaer")] = 1.04  # Männer Stationär
    ga_f[(geschlecht == "W") & (tarifart_wahl == "voll")] = 1.03      # Frauen Vollvers.

    # Kombinierter Skalierungsfaktor (multiplikativ)
    kf = alter_f * dauer_f * ga_f

    # Globale Skalierung auf target mittlere_anpassung
    # Die Tarif-Parameter sind auf ~26% kalibriert, skaliere nun proportional
    # Beispiel: mittlere_anpassung=0.30 → global_skala ≈ 1.15
    global_skala = mittlere_anpassung / 0.26

    # Berechne Anpassung pro Tarif mit skalierter Beta-Verteilung
    anp = np.zeros(n)  # Array für alle Versicherten
    for tid, (alpha, beta_p, b_min, b_max) in TARIF_BETA_PARAMS.items():
        # Filtere Versicherte dieses Tarifs
        maske = tarif_ids == tid
        n_tid = maske.sum()
        if n_tid == 0:
            continue

        # Hole Skalierungsfaktoren für diese Versicherten
        kf_tid = kf[maske] * global_skala

        # Adaptiere Basis-Intervall [b_min, b_max] mit Skalierungsfaktoren
        # vmin: mit sqrt(kf) → moderater Aufstieg
        # vmax: mit 0.7*log(kf) → stärkerer Aufstieg (mehr Spread bei hohem kf)
        vmin = np.clip(b_min * np.power(kf_tid, 0.5), 0.01, 0.50)
        vmax = np.clip(b_max * np.power(kf_tid, 0.7), 0.05, 0.80)
        # Garantiere mindestens 3 Prozentpunkte Spread
        vmax = np.maximum(vmax, vmin + 0.03)

        # Ziehe Beta-verteilte Werte ∈ [0, 1] und skaliere auf [vmin, vmax]
        raw = rng.beta(alpha, beta_p, size=n_tid)
        anp[maske] = vmin + (vmax - vmin) * raw

    # Finales Clipping: Sicherstelle Gültigkeitsbereich
    # Min 1% (administrative Mindesterhöhung), Max 80% (Geschäftsmodell-Limit)
    anp = np.clip(anp, 0.01, 0.80)

    # Berechne neue Prämien und Erhöhungen
    praemie_neu = np.round(praemie_alt * (1.0 + anp), 2)  # Neue monatliche Prämie
    erh_abs = np.round(praemie_neu - praemie_alt, 2)      # €/Monat Erhöhung
    erh_pct = np.round(anp * 100, 2)                      # % Erhöhung

    # --- 7. Alterungsrückstellung (ALT: Vermögensreserve für Altersanpassung) ---
    # Formel: Annualisierte Prämie × Versicherungsdauer × Altersfaktor × Zufallsterm
    # Höheres Alter und längere Dauer → höhere Reserven
    arf = np.clip((alter - 18) / 50.0, 0.02, 1.8)  # Normalisierter Altersfaktor [0.02, 1.8]
    # Zufallsterm: Individuelle Abweichungen ±30% um erwartete Rückstellung
    ar = np.maximum(
        np.round(praemie_alt * 12 * vd * arf * rng.uniform(0.7, 1.3, size=n), 2),
        0.0  # Minimum 0€
    )

    # --- 8. Historische kumulierte Anpassung (letzte 3 Jahre) ---
    # Simuliere, dass aktuelle Anpassungen korrelieren mit historischen
    # Ziel: Realistische Darstellung von Versicherten, die bereits mehrfach erhöht wurden
    print("  Erzeuge historische Anpassungen ...")

    # Basis je Tarifwerk (Ø Kumulierung über 3 Jahre)
    hist_basis = np.zeros(n)
    hist_basis[mc] = 40.0  # Classic: ältere Tarife, häufigere Anpassungen → 40% Ø
    hist_basis[mk] = 22.0  # Komfort: moderates Tarifwerk → 22% Ø
    hist_basis[mp] = 8.0   # Premium: neuere Tarife → 8% Ø

    # Alters-Effekt auf historische Anpassungen
    # Ältere waren länger abhängig → mehr historische Anpassungen
    hist_af = np.ones(n)
    hist_af[alter < 35] = 0.70              # Junge: weniger Historie
    hist_af[(alter >= 35) & (alter < 50)] = 0.90
    hist_af[(alter >= 60) & (alter < 70)] = 1.15
    hist_af[(alter >= 70) & (alter < 80)] = 1.30
    hist_af[alter >= 80] = 1.50             # Älteste: maximale Historie

    # Tarifart-Effekt: Voll-Tarife waren historisch stärker betroffen
    hist_tf = np.ones(n)
    hist_tf[tarifart_wahl == "voll"] = 1.20  # Voll +20%
    hist_tf[tarifart_wahl == "zahn"] = 0.75  # Zahn -25%

    # Erzeuge Korrelation zwischen aktueller und historischer Anpassung
    # Korrelation: 0.55 → moderate positive Abhängigkeit
    korrelation = 0.55
    # Normalisiere aktuelle Anpassungen auf [0, 1]
    akt_norm = (anp - anp.min()) / (anp.max() - anp.min() + 1e-10)
    # Unabhängiger log-normal verteilter Zufallsterm
    hist_zuf = rng.lognormal(0, 0.55, size=n)
    hist_zuf_norm = (hist_zuf - hist_zuf.min()) / (hist_zuf.max() - hist_zuf.min() + 1e-10)
    # Kombiniere mit Gewichtung
    hist_score = korrelation * akt_norm + (1 - korrelation) * hist_zuf_norm

    # Berechne historische Erhöhung
    # Basis × Altersfaktor × Tarifartfaktor × Zufalls-Score (skaliert [0.2, 1.8])
    erh_hist = hist_basis * hist_af * hist_tf * (0.2 + 1.6 * hist_score)

    # Spezialbehandlung: Kurze Versicherungsdauern (<3 Jahre)
    # Neue Versicherte haben weniger historische Anpassungen
    kurz = vd < 3
    erh_hist[kurz] *= (vd[kurz] / 3.0)  # Proportionaler Abschlag

    # Spezialbehandlung: Top 5% aktuelle Anpassungen
    # Diese sind auch historisch besonders betroffen (Risikoverlauf)
    top_anp = anp >= np.percentile(anp, 95)
    erh_hist[top_anp] *= 1.3  # +30% Aufschlag

    # Finales Clipping: 0-80%
    erh_hist = np.clip(np.round(erh_hist, 1), 0.0, 80.0)

    # --- 9. Mittelquellen fuer spaetere Topfsteuerung ---
    # Ueberzins wird kunden-/tarifindividuell als externe Mittelspalte simuliert.
    # Die Werte liegen bewusst in Einmaleinlagen-/Kapitalwertbasis vor und koennen
    # in der spaeteren Limitierung regelunabhaengig vor den UI-Regeln verwendet werden.
    print("  Erzeuge Mittelquellen (Ueberzins, ZU10) ...")
    ueberzins_tarifwerk_faktor = np.ones(n)
    ueberzins_tarifwerk_faktor[mc] = 0.80
    ueberzins_tarifwerk_faktor[mk] = 1.00
    ueberzins_tarifwerk_faktor[mp] = 1.20
    ueberzins_streuung = np.clip(rng.lognormal(mean=0.0, sigma=0.35, size=n), 0.35, 2.25)
    ueberzins_mittel = np.round(
        np.maximum(erh_abs, 0.0) * 12 * ueberzins_tarifwerk_faktor * ueberzins_streuung,
        2,
    )

    # ZU10-Mittel werden als Beispiel nur fuer Vollversicherte ab 65 erzeugt.
    # Damit ist die Mockdatei bereits kompatibel mit dem Phase-A-Defaultfilter
    # tarifart == voll und alter >= 65; alle anderen Zeilen erhalten 0.
    zu10_berechtigt = (tarifart_wahl == "voll") & (alter >= 65)
    zu10_horizont_faktor = np.clip((100 - alter) / 10.0, 1.0, 4.0)
    zu10_streuung = rng.uniform(0.85, 1.15, size=n)
    zu10_mittel = np.zeros(n)
    zu10_mittel[zu10_berechtigt] = np.round(
        praemie_alt[zu10_berechtigt]
        * 12
        * 0.10
        * zu10_horizont_faktor[zu10_berechtigt]
        * zu10_streuung[zu10_berechtigt],
        2,
    )

    # --- 10. Konstruiere finales DataFrame mit allen Spalten ---
    # Kombiniere alle generierten Arrays in strukturiertes DataFrame
    # Rückgabeformat ist die zentrale Schnittstelle für alle Downstream-Analysen
    print("  Baue DataFrame ...")
    return pd.DataFrame({
        "person_id": person_id_expanded,
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
        "ueberzins_mittel_euro": ueberzins_mittel,
        "zu10_mittel_euro": zu10_mittel,
    })


def erzeuge_mittelquellen_config() -> pd.DataFrame:
    """Erzeugt eine Beispiel-Konfiguration fuer Mittelquellen.

    Die Datei dokumentiert die Phase-A-Defaults fuer spaetere UI- und
    Service-Implementierungen. Sie wird noch nicht automatisch in der
    Limitierungsrechnung verwendet.
    """
    return pd.DataFrame([
        {
            "quelle_id": "ueberzins",
            "name": "Ueberzins kunden-/tarifindividuell",
            "aktiv": True,
            "prioritaet": 1,
            "typ": "zeilenindividuell",
            "betrag_euro": "",
            "betrag_spalte": "ueberzins_mittel_euro",
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
            "aktiv": True,
            "prioritaet": 2,
            "typ": "zeilenindividuell",
            "betrag_euro": "",
            "betrag_spalte": "zu10_mittel_euro",
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
            "betrag_euro": 100_000_000,
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


# =============================================================================
# STATISTIKEN
# =============================================================================

def zeige_statistiken(df, df_t, df_ao):
    """Ausgabe detailliertes Statistik-Report für den Bestand.
    
    Präsentiert umfassende Analysen der generierten Versichertendaten:
    - Deskriptive Statistiken (Anzahl, Alter, Geschlechterverhältnis)
    - Verteilungskennung der Prämienanpassung (%) und absolut (€)
    - Historische Anpassungen und Korrelation zur aktuellen Anpassung
    - Aggregierte Metriken nach Tarifwerk und einzelnem Tarif
    - Extremfälle (hohe Anpassungen)
    - Volumen-Metriken (Jahresausgaben)
    
    Args:
        df (pd.DataFrame): Bestandsdaten mit folgenden Spalten:
            - alter, geschlecht, tarifwerk, erhoehung_prozent,
            - erhoehung_absolut, erhoehung_historisch_kumuliert,
            - praemie_alt_monatlich, praemie_neu_monatlich, tarif_id
        df_t (pd.DataFrame): Tarifstammdaten (wird nur für count verwendet)
        df_ao (pd.DataFrame): Ausscheideordnung (wird nur für count verwendet)
    
    Returns:
        None (nur Konsolenausgabe)
    
    Notes:
        - P05, P25, P75, P95, P99: Perzentile der Prämienanpassung
        - Korrelation: Maß für lineare Abhängigkeit (0=unabhängig, 1=perfekt)
        - Top-5 Tarife: nach durchschnittlicher Erhöhung sortiert
    """
    print("\n" + "=" * 70)
    print("ZUSAMMENFASSUNG (v4)")
    print("=" * 70)
    print(f"\n  Versicherte:        {len(df):>12,}")
    if "person_id" in df.columns:
        n_personen = df["person_id"].nunique()
        tarife_pro_person = df.groupby("person_id").size()
        print(f"  Personen:           {n_personen:>12,}")
        print(f"  Ø Tarife/Person:    {tarife_pro_person.mean():>12.2f}")
        print(f"  Personen 1 Tarif:   {(tarife_pro_person == 1).sum():>12,}")
        print(f"  Personen >1 Tarif:  {(tarife_pro_person > 1).sum():>12,}")
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

    print(f"\n  --- Mittelquellen (Einmaleinlagenbasis) ---")
    if "ueberzins_mittel_euro" in df.columns:
        print(f"  Ueberzins gesamt:   {df['ueberzins_mittel_euro'].sum():>14,.0f} €")
    if "zu10_mittel_euro" in df.columns:
        zu10_berechtigt = (df["tarifart"] == "voll") & (df["alter"] >= 65)
        print(f"  ZU10 gesamt:        {df['zu10_mittel_euro'].sum():>14,.0f} €")
        print(f"  ZU10-berechtigt:    {zu10_berechtigt.sum():>12,} Zeilen")

    print(f"\n  Tarife: {len(df_t)} | Ausscheideordnung: {len(df_ao):,} Zeilen")


# =============================================================================
# HAUPTPROGRAMM
# =============================================================================

def main():
    """Hauptprogramm: Orchestriert die Erzeugung aller Mock-Daten.
    
    Workflow:
    1. Parse Kommandozeilen-Argumente
    2. Initialisiere Zufallsgenerator mit determiniertem Seed
    3. Erzeuge alle vier Ausgabedateien:
       a) tarife.csv - Tarifstammdaten
       b) ausscheideordnung.csv - Sterblichkeit + Stornoquoten
       c) bestand.csv - 1 Mio. Versicherte mit allen Merkmalen
       d) mittelquellen_config.csv - Beispiel-Konfiguration fuer Mittelquellen
    4. Berechne und zeige aggregierte Statistik
    5. Messe und reporte Ausführungszeit und Dateigröße
    
    Kommandozeilen-Argumente:
        --ausgabeverzeichnis / -o: Zielverzeichnis (default: aktuelles Verzeichnis)
        --mittlere_anpassung / -m: Target-Durchschnitt für Anpassung in % 
                                   (default: 30%)
        --seed / -s: RNG-Seed für Reproduzierbarkeit (default: 42)
    
    Returns:
        None (schreibt CSV-Dateien und Konsolenausgaben)
    
    Example:
        python mock_daten_erzeugen.py -o ./output -m 0.25 -s 123
    """
    parser = argparse.ArgumentParser(description="Mock-Daten-Generator v4")
    parser.add_argument(
        "--ausgabeverzeichnis", "-o",
        default=".",
        help="Zielverzeichnis für CSV-Ausgabedateien (default: aktuelles Verzeichnis)"
    )
    parser.add_argument(
        "--mittlere_anpassung", "-m",
        type=float,
        default=MITTLERE_PRAEMIENANPASSUNG,
        help=f"Mittlere Prämienanpassung als Dezimal (default: {MITTLERE_PRAEMIENANPASSUNG:.1%})"
    )
    parser.add_argument(
        "--seed", "-s",
        type=int,
        default=SEED,
        help=f"RNG-Seed für Reproduzierbarkeit (default: {SEED})"
    )
    args = parser.parse_args()

    ausgabe = args.ausgabeverzeichnis
    os.makedirs(ausgabe, exist_ok=True)  # Erstelle Verzeichnis falls nicht vorhanden
    # Initialisiere Zufallsgenerator mit Seed für Reproduzierbarkeit
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

    print("      Mittelquellen-Konfiguration ...")
    df_mittel = erzeuge_mittelquellen_config()
    df_mittel.to_csv(os.path.join(ausgabe, "mittelquellen_config.csv"), index=False, sep=";")

    zeige_statistiken(df_b, df_t, df_ao)

    print(f"\n  Dauer: {time.time() - t0:.1f}s")
    for name in ["tarife.csv", "ausscheideordnung.csv", "bestand.csv", "mittelquellen_config.csv"]:
        p = os.path.join(ausgabe, name)
        print(f"  {name:.<35} {os.path.getsize(p) / (1024 * 1024):>6.1f} MB")
    print(f"\nFertig! → {os.path.abspath(ausgabe)}")


if __name__ == "__main__":
    main()