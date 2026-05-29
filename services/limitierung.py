import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


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
    logger.info("Berechne Barwertfaktoren: %d Tarife, %d AO-Einträge", len(df_tarife), len(df_ao))
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


def _erzeuge_regel_beschreibungen(regeln: list) -> list[str]:
    """Erzeugt lesbare Labels für jede Regel, z.B. 'Regel 1: Global ≤ 25% / ≤ 50 €'."""
    beschreibungen = []
    for i, regel in enumerate(regeln):
        ziel_pct = regel.get("ziel_pct")
        ziel_abs = regel.get("ziel_abs")
        scope_spalte = regel.get("scope_spalte")
        scope_werte = regel.get("scope_werte")

        teile = []
        if ziel_pct is not None:
            teile.append(f"≤ {ziel_pct:g}%")
        if ziel_abs is not None:
            teile.append(f"≤ {ziel_abs:g} €")
        ziel_text = " / ".join(teile) if teile else "–"

        if scope_spalte and scope_werte:
            werte_text = ", ".join(str(w) for w in scope_werte[:3])
            if len(scope_werte) > 3:
                werte_text += f" (+{len(scope_werte) - 3})"
            scope_text = f"{scope_spalte}={werte_text}"
        else:
            scope_text = "Global"

        beschreibungen.append(f"Regel {i + 1}: {scope_text} {ziel_text}")
    return beschreibungen


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
    logger.info(
        "Berechne Limitierung: %d Versicherte, %d Regeln, Modus=%s",
        len(df), len(regeln), modus,
    )
    n = len(df)
    
    # Speichere ursprüngliche Steigerungen zur späteren Vergleichbarkeit
    erh_pct_orig = df["erhoehung_prozent"].values.copy()
    erh_abs_orig = df["erhoehung_absolut"].values.copy()
    praemie_alt = df["praemie_alt_monatlich"].values

    # Initialisiere limitierte Steigerungen mit den Original-Werten
    erh_pct_lim = erh_pct_orig.copy()
    erh_abs_lim = erh_abs_orig.copy()

    # Regeltracing: Welche Regel hat die Limitierung ausgelöst?
    regel_index = np.full(n, -1, dtype=int)

    # Wende alle definierten Limitierungsregeln nacheinander an
    for ri, regel in enumerate(regeln):
        ziel_pct = regel.get("ziel_pct")  # Ziel für prozentuale Steigerung
        ziel_abs = regel.get("ziel_abs")  # Ziel für absolute Steigerung
        scope_spalte = regel.get("scope_spalte")  # Spalte für Segmentierung (None = global)
        scope_werte = regel.get("scope_werte")  # Werte in der Segmentierungsspalte

        # Überspringe Regeln ohne Zielwerte
        if ziel_pct is None and ziel_abs is None:
            continue

        # Snapshot vor Regelanwendung für Tracing
        erh_pct_vor = erh_pct_lim.copy()
        erh_abs_vor = erh_abs_lim.copy()

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

        # Tracing: Markiere Versicherte, deren Werte durch diese Regel gesenkt wurden
        wurde_gesenkt = (erh_pct_vor > erh_pct_lim + 0.001) | (erh_abs_vor > erh_abs_lim + 0.001)
        regel_index[wurde_gesenkt] = ri

    # Konsistenzcheck: Stelle sicher, dass absolute und prozentuale Steigerungen kohärent sind
    erh_abs_aus_pct = praemie_alt * erh_pct_lim / 100.0  # Von prozentual abgeleiteter Betrag
    erh_abs_lim = np.minimum(erh_abs_lim, erh_abs_aus_pct)  # Nutze das kleinere der beiden
    with np.errstate(divide="ignore", invalid="ignore"):
        erh_pct_lim = np.where(praemie_alt > 0, erh_abs_lim / praemie_alt * 100.0, 0.0)

    # Berechne limitierte neue Prämien
    praemie_lim = np.round(praemie_alt + erh_abs_lim, 2)

    # Berechne Entlastung (Differenz zwischen ursprünglicher und begrenzter Steigerung)
    diff_monatlich = erh_abs_orig - erh_abs_lim  # Negative Änderungen sind Entlastungen
    diff_monatlich = np.maximum(diff_monatlich, 0.0)  # Nur positive Entlastungen zählen

    # Verknüpfe Bestände mit Barwertfaktoren für die Umrechnung
    bwf_merged = df[["tarif_id", "geschlecht", "alter"]].merge(
        df_bwf, on=["tarif_id", "geschlecht", "alter"], how="left"
    )

    # Validierung: Fehlende Barwertfaktoren erkennen und warnen
    fehlende_bwf = bwf_merged["barwertfaktor"].isna()
    anzahl_fehlend = int(fehlende_bwf.sum())
    if anzahl_fehlend > 0:
        betroffene = df.loc[fehlende_bwf.values, ["tarif_id", "geschlecht", "alter"]].drop_duplicates()
        logger.warning(
            "Barwertfaktoren-Merge: %d von %d Versicherten (%d eindeutige Kombinationen) "
            "haben keinen passenden Barwertfaktor. "
            "Fehlende Kombinationen (tarif_id, geschlecht, alter): %s. "
            "Einmaleinlagen werden für diese Versicherten auf 0 gesetzt — "
            "der RfB-Bedarf wird dadurch systematisch unterschätzt!",
            anzahl_fehlend,
            len(df),
            len(betroffene),
            betroffene.head(10).to_dict("records"),
        )

    bwf_werte = bwf_merged["barwertfaktor"].fillna(0).values

    # Konvertiere monatliche Entlastungen in Einmaleinlagen
    # Formel: Monatlich * 12 Monate * Barwertfaktor
    einmaleinlage = np.round(diff_monatlich * 12 * bwf_werte, 2)
    
    # Flag: War diese Versicherte limitiert (Entlastung > 0,01 €)?
    limitiert = diff_monatlich > 0.01

    # Regeltracing: Lesbare Beschreibung erzeugen
    regel_beschreibungen = _erzeuge_regel_beschreibungen(regeln)
    regel_beschreibung = np.where(
        regel_index >= 0,
        np.array([regel_beschreibungen[i] if i >= 0 else "" for i in regel_index]),
        "",
    )

    logger.info(
        "Limitierung abgeschlossen: %d von %d Versicherten limitiert, "
        "RfB-Bedarf=%.2f Mio. €",
        int(limitiert.sum()), n, einmaleinlage.sum() / 1e6,
    )

    return pd.DataFrame({
        "erhoehung_limitiert_pct": np.round(erh_pct_lim, 2),
        "erhoehung_limitiert_abs": np.round(erh_abs_lim, 2),
        "praemie_limitiert": praemie_lim,
        "differenz_monatlich": np.round(diff_monatlich, 2),
        "einmaleinlage": einmaleinlage,
        "limitiert": limitiert,
        "regel_index": regel_index,
        "regel_beschreibung": regel_beschreibung,
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


def berechne_limitierung_person(
    df: pd.DataFrame,
    df_bwf: pd.DataFrame,
    regeln: list,
    personen_regel: dict,
    modus: str,
    laufzeit_jahre: int,
    reihenfolge: str = "tarif_zuerst",
    verteilungsmodus: str = "proportional",
) -> pd.DataFrame:
    """
    Berechnet Limitierung mit zusätzlicher Personenebene.

    Wendet Tarif-Limitierungsregeln und Personen-Caps an. Die Reihenfolge ist
    konfigurierbar: bei 'tarif_zuerst' werden erst Tarif-Caps angewendet, dann
    der Personen-Cap auf die bereits limitierten Werte. Bei 'person_zuerst' umgekehrt.

    Args:
        df: Bestands-DataFrame mit person_id-Spalte.
        df_bwf: Barwertfaktoren (tarif_id, geschlecht, alter, barwertfaktor).
        regeln: Liste von Tarif-Limitierungsregeln (wie bei berechne_limitierung).
        personen_regel: Dict mit Personen-Cap:
            - ziel_abs (float, optional): Max. Gesamterhöhung €/Monat pro Person
            - ziel_pct (float, optional): Max. Gesamterhöhung in % der Gesamtprämie
        modus: Betriebsmodus (wird an berechne_limitierung durchgereicht).
        laufzeit_jahre: Versorgungslaufzeit in Jahren.
        reihenfolge: 'tarif_zuerst' oder 'person_zuerst'.
        verteilungsmodus: 'proportional' oder 'groesster_zuerst'.

    Returns:
        pd.DataFrame: Alle Spalten von berechne_limitierung plus:
            - erhoehung_person_gesamt_vorher: Summe aller Tarif-Erhöhungen der Person vor Personen-Cap
            - erhoehung_person_gesamt_nachher: Summe nach Personen-Cap
            - person_limitiert: True wenn Personen-Cap gegriffen hat
    """
    if "person_id" not in df.columns:
        raise ValueError(
            "Personen-Limitierung erfordert Spalte 'person_id' im Bestand."
        )

    person_ziel_abs = personen_regel.get("ziel_abs")
    person_ziel_pct = personen_regel.get("ziel_pct")

    if person_ziel_abs is None and person_ziel_pct is None:
        logger.warning("Personen-Regel enthält weder ziel_abs noch ziel_pct. "
                        "Nur Tarif-Limitierung wird angewendet.")
        res_tarif = berechne_limitierung(df, df_bwf, regeln, modus, laufzeit_jahre)
        n = len(df)
        res_tarif["erhoehung_person_gesamt_vorher"] = np.nan
        res_tarif["erhoehung_person_gesamt_nachher"] = np.nan
        res_tarif["person_limitiert"] = False
        return res_tarif

    if reihenfolge == "tarif_zuerst":
        return _limitierung_tarif_dann_person(
            df, df_bwf, regeln, person_ziel_abs, person_ziel_pct,
            modus, laufzeit_jahre, verteilungsmodus,
        )
    elif reihenfolge == "person_zuerst":
        return _limitierung_person_dann_tarif(
            df, df_bwf, regeln, person_ziel_abs, person_ziel_pct,
            modus, laufzeit_jahre, verteilungsmodus,
        )
    else:
        raise ValueError(f"Unbekannte Reihenfolge: '{reihenfolge}'. "
                         "Erlaubt: 'tarif_zuerst', 'person_zuerst'.")


def _wende_personen_cap_an(
    person_ids: np.ndarray,
    erh_abs: np.ndarray,
    praemie_alt: np.ndarray,
    ziel_abs: float | None,
    ziel_pct: float | None,
    verteilungsmodus: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Wendet Personen-Cap auf Erhöhungen an und verteilt Überschuss auf Einzeltarife.

    Returns:
        Tuple aus (erh_abs_neu, erh_person_vorher, erh_person_nachher, person_limitiert)
        - erh_abs_neu: Adjustierte absolute Erhöhungen pro Tarif-Zeile
        - erh_person_vorher: Gesamt-Erhöhung der Person (vor Personen-Cap), pro Zeile broadcasted
        - erh_person_nachher: Gesamt-Erhöhung nach Personen-Cap, pro Zeile broadcasted
        - person_limitiert: Boolean pro Zeile, ob die Person limitiert wurde
    """
    n = len(person_ids)
    erh_abs_neu = erh_abs.copy()
    erh_person_vorher = np.zeros(n)
    erh_person_nachher = np.zeros(n)
    person_limitiert = np.zeros(n, dtype=bool)

    # Gruppiere nach person_id
    df_temp = pd.DataFrame({
        "person_id": person_ids,
        "erh_abs": erh_abs,
        "praemie_alt": praemie_alt,
        "_idx": np.arange(n),
    })

    for pid, grp in df_temp.groupby("person_id"):
        idx = grp["_idx"].values
        erh_gruppe = erh_abs_neu[idx]
        praemie_gruppe = grp["praemie_alt"].values

        gesamt_erh = erh_gruppe.sum()
        gesamt_praemie = praemie_gruppe.sum()
        erh_person_vorher[idx] = gesamt_erh

        # Bestimme effektiven Cap
        cap = np.inf
        if ziel_abs is not None:
            cap = min(cap, ziel_abs)
        if ziel_pct is not None and gesamt_praemie > 0:
            cap = min(cap, gesamt_praemie * ziel_pct / 100.0)

        if gesamt_erh <= cap or cap == np.inf:
            erh_person_nachher[idx] = gesamt_erh
            continue

        # Überschuss verteilen
        person_limitiert[idx] = True
        reduktion = gesamt_erh - cap

        if verteilungsmodus == "proportional":
            erh_abs_neu[idx] = _verteile_proportional(erh_gruppe, reduktion)
        elif verteilungsmodus == "groesster_zuerst":
            erh_abs_neu[idx] = _verteile_groesster_zuerst(erh_gruppe, reduktion)
        else:
            raise ValueError(f"Unbekannter Verteilungsmodus: '{verteilungsmodus}'.")

        erh_person_nachher[idx] = erh_abs_neu[idx].sum()

    return erh_abs_neu, erh_person_vorher, erh_person_nachher, person_limitiert


def _verteile_proportional(erh_gruppe: np.ndarray, reduktion: float) -> np.ndarray:
    """Verteilt die Reduktion proportional zur Einzeltarif-Erhöhung."""
    gesamt = erh_gruppe.sum()
    if gesamt <= 0:
        return erh_gruppe.copy()
    anteile = erh_gruppe / gesamt
    return np.maximum(erh_gruppe - reduktion * anteile, 0.0)


def _verteile_groesster_zuerst(erh_gruppe: np.ndarray, reduktion: float) -> np.ndarray:
    """Reduziert die größten Einzeltarif-Erhöhungen zuerst."""
    result = erh_gruppe.copy()
    sort_idx = np.argsort(-result)  # Absteigend sortiert, Indizes merken
    rest = reduktion

    for i in sort_idx:
        if rest <= 0:
            break
        # Maximal bis auf 0 reduzieren
        moegliche_reduktion = min(rest, result[i])
        result[i] -= moegliche_reduktion
        rest -= moegliche_reduktion

    return result


def _limitierung_tarif_dann_person(
    df, df_bwf, regeln, person_ziel_abs, person_ziel_pct,
    modus, laufzeit_jahre, verteilungsmodus,
) -> pd.DataFrame:
    """Erst Tarif-Limitierung, dann Personen-Cap auf limitierte Werte."""
    logger.info("Reihenfolge: Tarif-Limitierung → Personen-Cap")

    # Schritt 1: Tarif-Limitierung
    res_tarif = berechne_limitierung(df, df_bwf, regeln, modus, laufzeit_jahre)

    # Schritt 2: Personen-Cap auf die bereits limitierten Werte
    erh_nach_tarif = res_tarif["erhoehung_limitiert_abs"].values
    praemie_alt = df["praemie_alt_monatlich"].values
    person_ids = df["person_id"].values

    erh_abs_neu, erh_p_vorher, erh_p_nachher, p_lim = _wende_personen_cap_an(
        person_ids, erh_nach_tarif, praemie_alt,
        person_ziel_abs, person_ziel_pct, verteilungsmodus,
    )

    # Aktualisiere Ergebnis-Spalten
    res_tarif["erhoehung_limitiert_abs"] = np.round(erh_abs_neu, 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        res_tarif["erhoehung_limitiert_pct"] = np.round(
            np.where(praemie_alt > 0, erh_abs_neu / praemie_alt * 100.0, 0.0), 2
        )
    res_tarif["praemie_limitiert"] = np.round(praemie_alt + erh_abs_neu, 2)

    # Differenz und Einmaleinlage neu berechnen
    erh_abs_orig = df["erhoehung_absolut"].values
    diff_monatlich = np.maximum(erh_abs_orig - erh_abs_neu, 0.0)
    res_tarif["differenz_monatlich"] = np.round(diff_monatlich, 2)

    bwf_merged = df[["tarif_id", "geschlecht", "alter"]].merge(
        df_bwf, on=["tarif_id", "geschlecht", "alter"], how="left"
    )
    bwf_werte = bwf_merged["barwertfaktor"].fillna(0).values
    res_tarif["einmaleinlage"] = np.round(diff_monatlich * 12 * bwf_werte, 2)
    res_tarif["limitiert"] = diff_monatlich > 0.01

    # Personen-Level-Spalten
    res_tarif["erhoehung_person_gesamt_vorher"] = np.round(erh_p_vorher, 2)
    res_tarif["erhoehung_person_gesamt_nachher"] = np.round(erh_p_nachher, 2)
    res_tarif["person_limitiert"] = p_lim

    n_person_lim = len(set(person_ids[p_lim]))
    logger.info(
        "Personen-Limitierung abgeschlossen: %d Personen limitiert, "
        "RfB-Bedarf=%.2f Mio. €",
        n_person_lim, res_tarif["einmaleinlage"].sum() / 1e6,
    )

    return res_tarif


def _limitierung_person_dann_tarif(
    df, df_bwf, regeln, person_ziel_abs, person_ziel_pct,
    modus, laufzeit_jahre, verteilungsmodus,
) -> pd.DataFrame:
    """Erst Personen-Cap auf Original-Werte, dann Tarif-Limitierung."""
    logger.info("Reihenfolge: Personen-Cap → Tarif-Limitierung")

    # Schritt 1: Personen-Cap auf die Original-Erhöhungen
    erh_abs_orig = df["erhoehung_absolut"].values
    praemie_alt = df["praemie_alt_monatlich"].values
    person_ids = df["person_id"].values

    erh_abs_nach_person, erh_p_vorher, erh_p_nachher, p_lim = _wende_personen_cap_an(
        person_ids, erh_abs_orig, praemie_alt,
        person_ziel_abs, person_ziel_pct, verteilungsmodus,
    )

    # Schritt 2: Erstelle modifizierten Bestand mit Personen-adjustierten Erhöhungen
    df_mod = df.copy()
    df_mod["erhoehung_absolut"] = np.round(erh_abs_nach_person, 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        df_mod["erhoehung_prozent"] = np.round(
            np.where(praemie_alt > 0, erh_abs_nach_person / praemie_alt * 100.0, 0.0), 2
        )
    df_mod["praemie_neu_monatlich"] = np.round(praemie_alt + erh_abs_nach_person, 2)

    # Schritt 3: Tarif-Limitierung auf die personen-adjustierten Werte
    res_tarif = berechne_limitierung(df_mod, df_bwf, regeln, modus, laufzeit_jahre)

    # Einmaleinlage basiert auf Differenz zu den Original-Erhöhungen
    erh_abs_final = res_tarif["erhoehung_limitiert_abs"].values
    diff_monatlich = np.maximum(erh_abs_orig - erh_abs_final, 0.0)
    res_tarif["differenz_monatlich"] = np.round(diff_monatlich, 2)

    bwf_merged = df[["tarif_id", "geschlecht", "alter"]].merge(
        df_bwf, on=["tarif_id", "geschlecht", "alter"], how="left"
    )
    bwf_werte = bwf_merged["barwertfaktor"].fillna(0).values
    res_tarif["einmaleinlage"] = np.round(diff_monatlich * 12 * bwf_werte, 2)
    res_tarif["limitiert"] = diff_monatlich > 0.01

    # Personen-Level-Spalten
    res_tarif["erhoehung_person_gesamt_vorher"] = np.round(erh_p_vorher, 2)
    res_tarif["erhoehung_person_gesamt_nachher"] = np.round(erh_p_nachher, 2)
    res_tarif["person_limitiert"] = p_lim

    n_person_lim = len(set(person_ids[p_lim]))
    logger.info(
        "Personen-Limitierung (person_zuerst) abgeschlossen: %d Personen limitiert, "
        "RfB-Bedarf=%.2f Mio. €",
        n_person_lim, res_tarif["einmaleinlage"].sum() / 1e6,
    )

    return res_tarif
