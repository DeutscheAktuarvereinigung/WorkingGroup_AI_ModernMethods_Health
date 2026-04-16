import numpy as np
import pandas as pd


def berechne_barwertfaktoren(df_ao: pd.DataFrame, df_tarife: pd.DataFrame) -> pd.DataFrame:
    """
    Berechnet Barwertfaktoren (Annuitätenfaktoren) für jede Tarifart, Geschlecht und Alter.
    
    Die Barwertfaktoren werden anhand der Ausscheideordnung (Sterbewahrscheinlichkeiten und
    Stornowahrscheinlichkeiten) sowie des Rechnungszinses pro Tarif ermittelt. Sie stellen die
    Diskontierungsfaktoren dar, um monatliche Beträge in Einmaleinlagen umzuwandeln.
    
    Args:
        df_ao (pd.DataFrame): Ausscheideordnung mit Spalten:
            - tarif_id: Tarifidentifikator
            - geschlecht: Geschlecht ('M' oder 'W')
            - alter: Eintrittsalter 
            - qx: Sterbewahrscheinlichkeit
            - storno: Stornowahrscheinlichkeit
        
        df_tarife (pd.DataFrame): Tarifstammdaten mit Spalten:
            - tarif_id: Tarifidentifikator
            - rechnungszins: Rechnungszinssatz (z.B. 0.025 für 2.5%)
    
    Returns:
        pd.DataFrame: DataFrame mit berechneten Barwertfaktoren, Spalten:
            - tarif_id: Tarifidentifikator
            - geschlecht: Geschlecht
            - alter: Eintrittsalter
            - barwertfaktor: Berechneter Barwertfaktor (auf 6 Dezimalstellen gerundet)
    
    Mathematik:
        Für jedes Alter x wird der Barwertfaktor ax als Summe über alle Versorgungsjahre t
        berechnet: ax = Σ v^t * Π(1 - q_x+t)
        wobei v = 1 / (1 + Rechnungszins) der Diskontfaktor ist.
    """
    ergebnisse = []

    # Iteriere über alle Tarife
    for _, tarif in df_tarife.iterrows():
        tid = tarif["tarif_id"]
        i = tarif["rechnungszins"]  # Rechnungszins als Dezimalzahl (z.B. 0.025)
        v = 1.0 / (1.0 + i)  # Diskontierungsfaktor für zukünftige Zahlungsströme

        # Berechne Barwertfaktoren für beide Geschlechter separat
        for geschl in ["M", "W"]:
            # Hole alle Ausscheidedaten für diesen Tarif und dieses Geschlecht, sortiert nach Alter
            ao_teil = df_ao[(df_ao["tarif_id"] == tid) & (df_ao["geschlecht"] == geschl)].sort_values("alter")
            
            # Überspringe, wenn keine Daten für diese Kombination vorhanden sind
            if len(ao_teil) == 0:
                continue

            # Extrahiere Sterbe- und Stornowahrscheinlichkeiten als Arrays
            qx_arr = ao_teil["qx"].values
            wx_arr = ao_teil["storno"].values
            max_alter = len(qx_arr)  # Maximales Alter in der Ausscheideordnung

            # Berechne Barwertfaktor für jedes Eintrittsalter
            for x in range(max_alter):
                ax = 0.0  # Akkumulator für den Barwertfaktor
                tp = 1.0  # Überlebenwahrscheinlichkeit vom Eintrittsalter bis Jahr t
                
                # Summiere über alle zukünftigen Jahre
                for t in range(1, max_alter - x):
                    alter_idx = x + t - 1
                    if alter_idx >= max_alter:
                        break
                    
                    # Kombinierte Ausscheidewahrscheinlichkeit (Sterbe- + Stornowahrscheinlichkeit)
                    ausch = min(qx_arr[alter_idx] + wx_arr[alter_idx], 1.0)
                    
                    # Aktualisiere die kumulierte Überlebenwahrscheinlichkeit
                    tp *= (1.0 - ausch)
                    
                    # Abbruchbedingung: wenn weitere Beiträge zu negligabel sind
                    if tp < 1e-10:
                        break
                    
                    # Addiere den abgezinsten Überlebenanteil
                    ax += (v ** t) * tp

                # Speichere Ergebnis für dieses Tarif-Geschlecht-Alter-Tripel
                ergebnisse.append({
                    "tarif_id": tid,
                    "geschlecht": geschl,
                    "alter": x,
                    "barwertfaktor": round(ax, 6),
                })

    return pd.DataFrame(ergebnisse)


def berechne_barwertfaktoren_befristet(df_ao: pd.DataFrame, df_tarife: pd.DataFrame, laufzeit_jahre: int) -> pd.DataFrame:
    """
    Berechnet befristete Barwertfaktoren (temporäre Annuitätenfaktoren).

    Wie berechne_barwertfaktoren, aber die Summation ist auf laufzeit_jahre begrenzt.
    Nach Ablauf der Befristung trägt der Versicherte den vollen Mehrbeitrag.

    Args:
        df_ao: Ausscheideordnung (tarif_id, geschlecht, alter, qx, storno)
        df_tarife: Tarifstammdaten (tarif_id, rechnungszins)
        laufzeit_jahre: Befristungsdauer in Jahren

    Returns:
        DataFrame mit tarif_id, geschlecht, alter, barwertfaktor_befristet
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
                ax = 0.0
                tp = 1.0
                for t in range(1, min(laufzeit_jahre + 1, max_alter - x)):
                    alter_idx = x + t - 1
                    if alter_idx >= max_alter:
                        break
                    ausch = min(qx_arr[alter_idx] + wx_arr[alter_idx], 1.0)
                    tp *= (1.0 - ausch)
                    if tp < 1e-10:
                        break
                    ax += (v ** t) * tp

                ergebnisse.append({
                    "tarif_id": tid,
                    "geschlecht": geschl,
                    "alter": x,
                    "barwertfaktor_befristet": round(ax, 6),
                })

    return pd.DataFrame(ergebnisse)


def berechne_limitierung(df: pd.DataFrame, df_bwf: pd.DataFrame, regeln, modus, laufzeit_jahre) -> pd.DataFrame:
    """
    Berechnet limitierte (begrenzte) Prämiensteigerungen basierend auf definierten Limitierungsregeln.
    
    Diese Funktion wendet Limitierungsregeln auf ein Bestandsportfolio an. Jede Regel kann ein
    Ziel für prozentuale oder absolute Steigerungen festlegen, optional beschränkt auf bestimmte
    Segmente (z.B. spezifische Tarifarten). Die Ergebnisse enthalten die limitierten Steigerungen
    sowie die daraus resultierenden Einmaleinlagen zur Rückstellung von Entlastungen.
    
    Args:
        df (pd.DataFrame): Bestands-DataFrame mit Spalten:
            - tarif_id, geschlecht, alter, praemie_alt_monatlich: Zur Verknüpfung mit Barwertfaktoren
            - erhoehung_prozent: Prozentuale Steigerung (z.B. 3.0 für 3%)
            - erhoehung_absolut: Absolute Steigerung in €/Monat
        
        df_bwf (pd.DataFrame): Barwertfaktoren, Spalten:
            - tarif_id, geschlecht, alter, barwertfaktor: Für Umrechnung monatlicher in Einmalbeträge
        
        regeln (list): Liste von Limitierungsregeln. Jede Regel ist ein Dict mit:
            - ziel_pct (float, optional): Max. prozentuale Steigerung (z.B. 3.0%)
            - ziel_abs (float, optional): Max. absolute Steigerung in €/Monat
            - scope_spalte (str, optional): Spalte für Segmentierung (z.B. 'tarifart')
            - scope_werte (list, optional): Werte für Segmentierung (z.B. ['Risiko', 'Einkommen'])
        
        modus (str): Betriebsmodus (z.B. 'budget', 'full')
        laufzeit_jahre (int): Versorgungslaufzeit in Jahren
    
    Returns:
        pd.DataFrame: Limitierungsergebnisse mit Spalten:
            - erhoehung_limitiert_pct: Begrenzte prozentuale Steigerung
            - erhoehung_limitiert_abs: Begrenzte absolute Steigerung in €/Monat
            - praemie_limitiert: Neue limitierte Prämie
            - differenz_monatlich: Entlastung pro Monat (€)
            - einmaleinlage: Erforderliche Einmaleinlage (€)
            - limitiert: Boolean-Flag, ob Versicherte limitiert wurden
    """
    n = len(df)
    
    # Speichere ursprüngliche Steigerungen zur späteren Vergleichbarkeit
    erh_pct_orig = df["erhoehung_prozent"].values.copy()
    erh_abs_orig = df["erhoehung_absolut"].values.copy()
    praemie_alt = df["praemie_alt_monatlich"].values

    # Initialisiere limitierte Steigerungen mit den Original-Werten
    erh_pct_lim = erh_pct_orig.copy()
    erh_abs_lim = erh_abs_orig.copy()

    # Wende alle definierten Limitierungsregeln nacheinander an
    for regel in regeln:
        ziel_pct = regel.get("ziel_pct")  # Ziel für prozentuale Steigerung
        ziel_abs = regel.get("ziel_abs")  # Ziel für absolute Steigerung
        scope_spalte = regel.get("scope_spalte")  # Spalte für Segmentierung (None = global)
        scope_werte = regel.get("scope_werte")  # Werte in der Segmentierungsspalte

        # Überspringe Regeln ohne Zielwerte
        if ziel_pct is None and ziel_abs is None:
            continue

        # Bestimme Maske: Welche Versicherten sind von dieser Regel betroffen?
        if scope_spalte and scope_werte:
            # Segmentierte Regel: nur Versicherte mit Werten in scope_werte
            maske = df[scope_spalte].isin(scope_werte).values
        else:
            # Globale Regel: alle Versicherten
            maske = np.ones(n, dtype=bool)

        # Begrenzte prozentuale Steigerungen nach dem Ziel
        if ziel_pct is not None:
            cap_pct = np.where(maske & (erh_pct_lim > ziel_pct), ziel_pct, erh_pct_lim)
            erh_pct_lim = np.minimum(erh_pct_lim, cap_pct)

        # Begrenze absolute Steigerungen nach dem Ziel
        if ziel_abs is not None:
            cap_abs = np.where(maske & (erh_abs_lim > ziel_abs), ziel_abs, erh_abs_lim)
            erh_abs_lim = np.minimum(erh_abs_lim, cap_abs)

    # Konsistenzcheck: Stelle sicher, dass absolute und prozentuale Steigerungen kohärent sind
    erh_abs_aus_pct = praemie_alt * erh_pct_lim / 100.0  # Von prozentual abgeleiteter Betrag
    erh_abs_lim = np.minimum(erh_abs_lim, erh_abs_aus_pct)  # Nutze das kleinere der beiden
    erh_pct_lim = np.where(praemie_alt > 0, erh_abs_lim / praemie_alt * 100.0, 0.0)  # Passe prozentual an

    # Berechne limitierte neue Prämien
    praemie_lim = np.round(praemie_alt + erh_abs_lim, 2)

    # Berechne Entlastung (Differenz zwischen ursprünglicher und begrenzter Steigerung)
    diff_monatlich = erh_abs_orig - erh_abs_lim  # Negative Änderungen sind Entlastungen
    diff_monatlich = np.maximum(diff_monatlich, 0.0)  # Nur positive Entlastungen zählen

    # Verknüpfe Bestände mit Barwertfaktoren für die Umrechnung
    bwf_merged = df[["tarif_id", "geschlecht", "alter"]].merge(
        df_bwf, on=["tarif_id", "geschlecht", "alter"], how="left"
    )
    bwf_werte = bwf_merged["barwertfaktor"].fillna(0).values  # Fehlende Barwertfaktoren = 0

    # Konvertiere monatliche Entlastungen in Einmaleinlagen
    # Formel: Monatlich * 12 Monate * Barwertfaktor
    einmaleinlage = np.round(diff_monatlich * 12 * bwf_werte, 2)
    
    # Flag: War diese Versicherte limitiert (Entlastung > 0,01 €)?
    limitiert = diff_monatlich > 0.01

    return pd.DataFrame({
        "erhoehung_limitiert_pct": np.round(erh_pct_lim, 2),
        "erhoehung_limitiert_abs": np.round(erh_abs_lim, 2),
        "praemie_limitiert": praemie_lim,
        "differenz_monatlich": np.round(diff_monatlich, 2),
        "einmaleinlage": einmaleinlage,
        "limitiert": limitiert,
    })


def berechne_sensitivitaet(df: pd.DataFrame, df_bwf: pd.DataFrame, regeln_basis, modus, laufzeit) -> pd.DataFrame:
    """
    Führt eine Sensitivitätsanalyse durch, um die Auswirkungen verschiedener Limitierungsziele zu zeigen.
    
    Diese Funktion berechnet Limitierungsszenarien für ein Raster von Limitierungszielen (z.B. von 10% bis 50%)
    und zeigt, wie sich Rückstellungsbedarf, Anzahl der Limitierten und durchschnittliche Entlastung ändern.
    Sie ist besonders nützlich, um optimale Schwellwerte zu identifizieren.
    
    Args:
        df (pd.DataFrame): Bestands-DataFrame
        df_bwf (pd.DataFrame): Barwertfaktoren
        regeln_basis (list): Basis-Limitierungsregeln; die globale Regel (ohne scope_spalte)
                              wird variiert
        modus (str): Betriebsmodus
        laufzeit (int): Versorgungslaufzeit
    
    Returns:
        pd.DataFrame: Sensitivitätsergebnisse mit Spalten:
            - Limitierungsziel (%): Das getestete Ziel
            - RfB-Bedarf (Mio. €): Erforderliche Einmaleinlagen in Millionen Euro
            - Anzahl limitiert: Zahl der begrenzten Versicherten
            - Ø Entlastung (€/Mon): Durchschnittliche monatliche Entlastung der limitierten Versicherten
    
    Raises:
        Warnung: Wenn keine globale Regel ohne scope_spalte existiert
    """
    ergebnisse = []
    
    # Finde die globale Regel (ohne Segmentierung) für die Sensitivitätsanalyse
    global_idx = None
    for i, r in enumerate(regeln_basis):
        if not r.get("scope_spalte"):  # Globale Regel hat keine scope_spalte
            global_idx = i
            break

    # Abbruch, wenn keine globale Regel definiert ist
    if global_idx is None:
        return pd.DataFrame()

    # Hole das aktuelle Basis-Ziel und generiere ein Raster von Szenarien
    basis_pct = regeln_basis[global_idx].get("ziel_pct", 30)
    schritte = np.arange(max(5, basis_pct - 20), min(basis_pct + 25, 100), 2.5)  # 2,5%-Schritte

    # Berechne Limitierung für jeden Testpunkt
    for ziel in schritte:
        # Erstelle Regelvariante mit neuem Ziel
        regeln_var = [r.copy() for r in regeln_basis]
        regeln_var[global_idx] = {**regeln_var[global_idx], "ziel_pct": float(ziel)}
        
        # Berechne Limitierung mit dieser Regelvariation
        res = berechne_limitierung(df, df_bwf, regeln_var, modus, laufzeit)
        
        # Akkumuliere Kennzahlen
        ergebnisse.append({
            "Limitierungsziel (%)": ziel,
            "RfB-Bedarf (Mio. €)": res["einmaleinlage"].sum() / 1e6,  # In Mio. umrechnen
            "Anzahl limitiert": res["limitiert"].sum(),  # Zahl der betroffenen Versicherten
            "Ø Entlastung (€/Mon)": res.loc[res["limitiert"], "differenz_monatlich"].mean()
            if res["limitiert"].any() else 0,  # Durchschnitt nur für limitierte
        })

    return pd.DataFrame(ergebnisse)


def berechne_optimierungsvorschlaege(df: pd.DataFrame, df_bwf: pd.DataFrame, regeln, modus, laufzeit, budget):
    """
    Generiert automatische Optimierungsvorschläge durch Variation der Limitierungsregeln.
    
    Diese Funktion testet verschiedene Szenarien durch Lockerung oder Verschärfung der aktuellen
    Regeln und identifiziert umsetzbare Verbesserungen mit signifikanten Einsparpotentialen oder
    sozialen Verbesserungen. Nur Vorschläge mit mindestens 10.000 € Wirkung werden berücksichtigt.
    
    Args:
        df (pd.DataFrame): Bestands-DataFrame
        df_bwf (pd.DataFrame): Barwertfaktoren
        regeln (list): Aktuelle Limitierungsregeln
        modus (str): Betriebsmodus
        laufzeit (int): Versorgungslaufzeit
        budget (float): Verfügbares Budget (in €) als Obergrenze für Verbessungen
    
    Returns:
        list: Liste von Optimierungsvorschlägen, jeder mit:
            - typ: 'einsparung' (lockernde Regel) oder 'verbesserung' (strengere Regel)
            - beschreibung: Lesbare Beschreibung des Vorschlags
            - einsparung_eur: Ersparnis (positiv) oder Mehrkosten (negativ)
            - betroffene: Anzahl der zusätzlich limitierten/entlasteten Versicherten
            - regel_index: Index der modifizierten Regel
            - neue_regel: Die vorgeschlagene neue Regelkonfiguration
    """
    vorschlaege = []
    
    # Berechne Baseline für alle Vergleiche
    aktuell = berechne_limitierung(df, df_bwf, regeln, modus, laufzeit)
    bedarf_aktuell = aktuell["einmaleinlage"].sum()  # Aktueller Rückstellungsbedarf

    # === ERSTE PHASE: Teste Lockerung der Regeln (Kosteneinsparung) ===
    for i, regel in enumerate(regeln):
        ziel_pct = regel.get("ziel_pct")
        if ziel_pct is None:
            continue  # Überspringe Regeln ohne prozentuale Ziele

        # Teste verschiedene Lockerungsstufen (+2%, +5%, +10%)
        for delta in [2, 5, 10]:
            # Erstelle neue Regelversion mit gelockertere Ziel
            neue_regeln = [r.copy() for r in regeln]
            neue_regeln[i] = {**neue_regeln[i], "ziel_pct": ziel_pct + delta}
            
            # Berechne Limitierung mit der gelockerten Regel
            res_neu = berechne_limitierung(df, df_bwf, neue_regeln, modus, laufzeit)
            bedarf_neu = res_neu["einmaleinlage"].sum()
            einsparung = bedarf_aktuell - bedarf_neu  # Positive Werte = Ersparnisse

            # Nur signifikante Einsparungen (> 10k€) berücksichtigen
            if einsparung > 10000:
                # Zähle Versicherte, die durch die Lockerung mehr belastet werden
                mehr_belastet = (res_neu["erhoehung_limitiert_pct"] > aktuell["erhoehung_limitiert_pct"] + 0.1).sum()
                
                # Formatiere Regelbezeichnung (Global oder Segment)
                scope_text = f"{regel.get('scope_spalte', 'Alle')}: {regel.get('scope_werte', 'Alle')}" if regel.get("scope_spalte") else "Global"

                vorschlaege.append({
                    "typ": "einsparung",
                    "beschreibung": f"Regel '{scope_text}' von {ziel_pct:.0f}% auf {ziel_pct + delta:.0f}% lockern",
                    "einsparung_eur": einsparung,  # Positive Werte
                    "betroffene": mehr_belastet,  # Nachteil-Zahl
                    "regel_index": i,
                    "neue_regel": neue_regeln[i],
                })

    # === ZWEITE PHASE: Teste Verschärfung der Regeln (soziale Verbesserung) ===
    for i, regel in enumerate(regeln):
        ziel_pct = regel.get("ziel_pct")
        if ziel_pct is None or ziel_pct <= 5:
            continue  # Überspringe Regeln ohne Ziel oder mit sehr niedrigem Ziel

        # Teste verschiedene Verschärfungsstufen (-2%, -5%)
        for delta in [2, 5]:
            # Erstelle neue Regelversion mit strengerem Ziel
            neues_ziel = max(ziel_pct - delta, 0)  # Aber nicht unter 0%
            neue_regeln = [r.copy() for r in regeln]
            neue_regeln[i] = {**neue_regeln[i], "ziel_pct": neues_ziel}
            
            # Berechne Limitierung mit der strengeren Regel
            res_neu = berechne_limitierung(df, df_bwf, neue_regeln, modus, laufzeit)
            bedarf_neu = res_neu["einmaleinlage"].sum()
            mehrkosten = bedarf_neu - bedarf_aktuell  # Positive Werte = zusätzliche Kosten

            # Filter: Nur umsetzbar, wenn Mehrkosten < 1,5x verfügbares Budget und > 0
            if mehrkosten > 0 and mehrkosten < (budget - bedarf_aktuell) * 1.5:
                # Zähle Versicherte, die von der Verschärfung entlastet werden
                entlastet = (res_neu["erhoehung_limitiert_pct"] < aktuell["erhoehung_limitiert_pct"] - 0.1).sum()
                
                # Formatiere Regelbezeichnung
                scope_text = f"{regel.get('scope_spalte', 'Alle')}: {regel.get('scope_werte', 'Alle')}" if regel.get("scope_spalte") else "Global"

                vorschlaege.append({
                    "typ": "verbesserung",
                    "beschreibung": f"Regel '{scope_text}' von {ziel_pct:.0f}% auf {neues_ziel:.0f}% verschärfen",
                    "einsparung_eur": -mehrkosten,  # Negative Werte (Kosten)
                    "betroffene": entlastet,  # Vorteil-Zahl
                    "regel_index": i,
                    "neue_regel": neue_regeln[i],
                })

    # Sortiere Vorschläge nach Betrag (höchste Auswirkungen zuerst)
    vorschlaege.sort(key=lambda x: -abs(x["einsparung_eur"]))
    return vorschlaege



def berechne_teilbestand_vorschlaege(df: pd.DataFrame, df_bwf: pd.DataFrame, regeln, modus, laufzeit, budget):
    """
    Generiert Optimierungsvorschläge durch Hinzufügung von Regeln für einzelne Segmente (Tarifarten, Tarife).
    
    Diese Funktion identifiziert Segmente des Bestands, die stärker begrenzt werden könnten, um
    Versicherte dieser Segmente gezielt zu entlasten. Sie testet zunächst alle Kombinationen von
    Spalten (Tarifart, Tarif, Tarifwerk) und Werten, und schlägt nur Regeln für Segmente mit
    ausreichender Größe (>= 100 Versicherte) vor, die nicht bereits reguliert sind.
    
    Args:
        df (pd.DataFrame): Bestands-DataFrame mit Spalten tarifart, tarif_id, tarifwerk
        df_bwf (pd.DataFrame): Barwertfaktoren
        regeln (list): Aktuelle globale + segmentspezifische Regeln
        modus (str): Betriebsmodus
        laufzeit (int): Versorgungslaufzeit
        budget (float): Verfügbares Budget
    
    Returns:
        list: Bis zu 10 beste Teilbestand-Vorschläge (nach Effizienzv verhältnis sortiert), jeder mit:
            - typ: 'teilbestand'
            - beschreibung: Beschreibung der neuen Segmentregel
            - einsparung_eur: Mehrkosten (negative Werte)
            - betroffene: Anzahl entlasteter Versicherten im Segment
            - regel_index: Index der neuen Regel
            - neue_regel: Die vorgeschlagene Segmentregel
    """
    _ = budget  # Budget wird in dieser Heuristik aktuell nicht verwendet.
    vorschlaege = []

    # Berechne aktuelle Limitierung als Baseline
    aktuell = berechne_limitierung(df, df_bwf, regeln, modus, laufzeit)
    bedarf_aktuell = aktuell["einmaleinlage"].sum()

    # Finde das globale Ziel (Referenz für Segment-Verschaerfungen)
    global_ziel = None
    for r in regeln:
        if not r.get("scope_spalte") and r.get("ziel_pct") is not None:
            global_ziel = r["ziel_pct"]
            break

    # Abbruch, wenn kein globales Ziel definiert ist
    if global_ziel is None:
        return vorschlaege

    # Generiere alle moeglichen Segment-Kombinationen aus drei Dimensionen
    segmente = []
    for spalte, label in [("tarifart", "Tarifart"), ("tarif_id", "Tarif"), ("tarifwerk", "Tarifwerk")]:
        for wert in sorted(df[spalte].unique()):
            segmente.append((spalte, label, wert))

    # Evaluiere jedes Segment
    for spalte, label, wert in segmente:
        # Ueberspringe kleine Segmente (< 100 Versicherte)
        n_segment = (df[spalte] == wert).sum()
        if n_segment < 100:
            continue

        # Ueberspringe bereits regulierte Segmente
        bereits_geregelt = False
        for r in regeln:
            if r.get("scope_spalte") == spalte and wert in (r.get("scope_werte") or []):
                bereits_geregelt = True
                break
        if bereits_geregelt:
            continue

        # Erstelle eine Maske fuer dieses Segment
        maske = df[spalte] == wert

        # Testphase: Verschaerfende Regeln fuer bessere Entlastung des Segments
        for delta in [5, 10]:
            neues_ziel = max(global_ziel - delta, 0)

            neue_regel = {
                "ziel_pct": float(neues_ziel),
                "ziel_abs": None,
                "scope_spalte": spalte,
                "scope_werte": [wert],
            }

            neue_regeln = [r.copy() for r in regeln] + [neue_regel]
            res_neu = berechne_limitierung(df, df_bwf, neue_regeln, modus, laufzeit)
            bedarf_neu = res_neu["einmaleinlage"].sum()
            mehrkosten = bedarf_neu - bedarf_aktuell  # Positive Werte = zusaetzliche Kosten

            # Nur signifikante Mehrkosten (> 10kEUR) beruecksichtigen
            if mehrkosten > 10000:
                entlastet = (
                    res_neu.loc[maske.values, "erhoehung_limitiert_pct"]
                    < aktuell.loc[maske.values, "erhoehung_limitiert_pct"] - 0.1
                ).sum()

                # Nur Vorschlaege mit mindestens einer entlasteten Person
                if entlastet > 0:
                    vorschlaege.append({
                        "typ": "teilbestand",
                        "beschreibung": f"{label} '{wert}' zusaetzlich auf {neues_ziel:.0f}% begrenzen",
                        "einsparung_eur": -mehrkosten,
                        "betroffene": entlastet,
                        "regel_index": len(regeln),
                        "neue_regel": neue_regel,
                    })

    # Sortiere nach Effizienzquotient: Entlastete pro Kosten-Euro (descending)
    vorschlaege.sort(key=lambda x: x["betroffene"] / (abs(x["einsparung_eur"]) + 1), reverse=True)
    return vorschlaege[:10]
