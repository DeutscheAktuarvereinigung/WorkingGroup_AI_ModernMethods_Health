import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

OPTIONALE_MITTELSPALTEN = ["ueberzins_mittel_euro", "zu10_mittel_euro"]
ERLAUBTE_MITTEL_TYPEN = {"global", "zeilenindividuell", "segmentiert"}
ERLAUBTE_BETRAG_EINHEITEN = {"einmaleinlage", "monatlich"}
ERLAUBTE_EINSATZMODI = {"pflicht_vollstaendig", "nur_bedarf_finanzieren", "optional"}
ERLAUBTE_ANWENDUNGSPHASEN = {"vor_regeln", "nach_regeln"}


def normalisiere_spaltennamen(df: pd.DataFrame) -> pd.DataFrame:
    """Normalisiert technische Spaltennamen fuer CSV- und Snowflake-Quellen."""
    df = df.copy()
    normalisierte_spalten = [str(spalte).strip().lower() for spalte in df.columns]
    doppelte_spalten = pd.Index(normalisierte_spalten)[pd.Index(normalisierte_spalten).duplicated()].unique().tolist()
    if doppelte_spalten:
        raise ValueError(
            "Doppelte Spalten nach Normalisierung gefunden: "
            f"{doppelte_spalten}"
        )
    df.columns = normalisierte_spalten
    return df


def _stelle_numerische_spalten_sicher(df: pd.DataFrame, spalten: list[str], kontext: str = "Spalte") -> None:
    """Konvertiert fachlich numerische Spalten defensiv, ohne ungueltige Werte zu dulden."""
    for spalte in spalten:
        if pd.api.types.is_numeric_dtype(df[spalte]):
            continue
        try:
            df[spalte] = pd.to_numeric(df[spalte], errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{kontext} '{spalte}' muss numerisch sein, ist aber '{df[spalte].dtype}'."
            ) from exc


def erzeuge_altersgruppen(df: pd.DataFrame, schritt: int = 10):
    alter_min = int(np.floor(df["alter"].min() / schritt) * schritt)
    alter_max = int(np.ceil((df["alter"].max() + 1) / schritt) * schritt)
    grenzen = list(range(alter_min, alter_max + schritt, schritt))
    labels = [f"{i}-{i + schritt - 1}" for i in range(alter_min, alter_max, schritt)]
    return grenzen, labels


def _ist_gesetzt(wert) -> bool:
    """Prueft, ob ein optionales CSV-Feld fachlich befuellt ist."""
    if wert is None or pd.isna(wert):
        return False
    return str(wert).strip() != ""


def _split_filter_spalten(wert) -> list[str]:
    """Liest pipe-getrennte Filterspalten aus der Mittelquellen-Konfiguration."""
    if not _ist_gesetzt(wert):
        return []
    return [teil.strip() for teil in str(wert).split("|") if teil.strip()]


def _normalisiere_pipe_referenzen(wert):
    """Normalisiert pipe-getrennte Spaltenreferenzen auf den technischen Datenvertrag."""
    if not _ist_gesetzt(wert):
        return wert
    return "|".join(teil.strip().lower() for teil in str(wert).split("|"))


def _normalisiere_mittelquellen_config(df_config: pd.DataFrame) -> pd.DataFrame:
    """Normalisiert technische Referenzen in der Mittelquellen-Konfiguration."""
    df_config = df_config.copy()
    for spalte in ["typ", "betrag_einheit", "einsatzmodus", "anwendungsphase"]:
        if spalte in df_config.columns:
            df_config[spalte] = df_config[spalte].astype(str).str.strip().str.lower()
    if "betrag_euro" in df_config.columns:
        # Snowflake liefert gemischte/leere Konfigurationsspalten haeufig als VARCHAR.
        # Leere Werte bleiben fuer zeilenindividuelle Quellen erlaubt; befuellte Werte
        # muessen vor der fachlichen Validierung echte numerische Werte sein.
        betrag_euro = df_config["betrag_euro"].replace(r"^\s*$", np.nan, regex=True)
        try:
            df_config["betrag_euro"] = pd.to_numeric(betrag_euro, errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError("Mittelquellen: 'betrag_euro' muss numerisch sein, wenn befüllt.") from exc
    if "betrag_spalte" in df_config.columns:
        df_config["betrag_spalte"] = df_config["betrag_spalte"].apply(_normalisiere_pipe_referenzen)
    if "filter_spalten" in df_config.columns:
        df_config["filter_spalten"] = df_config["filter_spalten"].apply(_normalisiere_pipe_referenzen)
    return df_config


def _validiere_optionale_mittelspalten(df: pd.DataFrame, spalten: list[str] | None = None) -> None:
    """Validiert optionale Mittelspalten im Bestand, sofern sie vorhanden sind."""
    pruef_spalten = spalten if spalten is not None else OPTIONALE_MITTELSPALTEN
    for spalte in pruef_spalten:
        if spalte not in df.columns:
            continue
        _stelle_numerische_spalten_sicher(df, [spalte])
        if df[spalte].isna().any():
            raise ValueError(f"Spalte '{spalte}' enthält fehlende Werte (NaN).")
        if (df[spalte] < 0).any():
            raise ValueError(f"Spalte '{spalte}' enthält negative Werte.")


def validiere_mittelquellen_config(
    df_config: pd.DataFrame,
    df_bestand: pd.DataFrame | None = None,
) -> list[str]:
    """Validiert die Konfiguration der Mittelquellen.

    Die Funktion prueft das in Phase A definierte CSV-Schema. Wenn ein
    Bestands-DataFrame uebergeben wird, werden referenzierte Betragsspalten
    und Filterspalten gegen den Bestand validiert. Fehlende referenzierte
    Spalten sind fachliche Fehler und werden nicht still ignoriert.
    """
    warnungen: list[str] = []
    erwartete = [
        "quelle_id", "name", "aktiv", "prioritaet", "typ", "betrag_euro",
        "betrag_spalte", "betrag_einheit", "unterliegt_limitierungsregeln",
        "einsatzmodus", "anwendungsphase", "filter_spalten", "filter_operatoren",
        "filter_werte", "fallback_erlaubt",
    ]
    fehlende = [s for s in erwartete if s not in df_config.columns]
    if fehlende:
        raise ValueError(f"Mittelquellen: Fehlende Spalten: {fehlende}")

    if df_config["quelle_id"].isna().any() or (df_config["quelle_id"].astype(str).str.strip() == "").any():
        raise ValueError("Mittelquellen: quelle_id enthält fehlende Werte.")
    if df_config["quelle_id"].duplicated().any():
        raise ValueError("Mittelquellen: quelle_id muss eindeutig sein.")
    _stelle_numerische_spalten_sicher(df_config, ["prioritaet"], "Mittelquellen")
    if (df_config["prioritaet"] < 1).any():
        raise ValueError("Mittelquellen: 'prioritaet' muss >= 1 sein.")

    unbekannte_typen = set(df_config["typ"].dropna().astype(str)) - ERLAUBTE_MITTEL_TYPEN
    if unbekannte_typen:
        raise ValueError(f"Mittelquellen: Unbekannte typ-Werte: {unbekannte_typen}")
    unbekannte_einheiten = set(df_config["betrag_einheit"].dropna().astype(str)) - ERLAUBTE_BETRAG_EINHEITEN
    if unbekannte_einheiten:
        raise ValueError(f"Mittelquellen: Unbekannte betrag_einheit-Werte: {unbekannte_einheiten}")
    unbekannte_modi = set(df_config["einsatzmodus"].dropna().astype(str)) - ERLAUBTE_EINSATZMODI
    if unbekannte_modi:
        raise ValueError(f"Mittelquellen: Unbekannte einsatzmodus-Werte: {unbekannte_modi}")
    unbekannte_phasen = set(df_config["anwendungsphase"].dropna().astype(str)) - ERLAUBTE_ANWENDUNGSPHASEN
    if unbekannte_phasen:
        raise ValueError(f"Mittelquellen: Unbekannte anwendungsphase-Werte: {unbekannte_phasen}")

    aktive = df_config[df_config["aktiv"].astype(str).str.lower().isin(["true", "1", "ja", "yes"])]
    if aktive["prioritaet"].duplicated().any():
        raise ValueError("Mittelquellen: Aktive Quellen müssen eindeutige prioritaet-Werte haben.")

    for idx, row in df_config.iterrows():
        quelle = row["quelle_id"]
        typ = str(row["typ"])
        betrag_spalte = row["betrag_spalte"]
        betrag_euro = row["betrag_euro"]

        if typ == "zeilenindividuell" and not _ist_gesetzt(betrag_spalte):
            raise ValueError(
                f"Mittelquellen: Quelle '{quelle}' mit typ='zeilenindividuell' "
                "erfordert eine betrag_spalte."
            )
        if typ in {"global", "segmentiert"} and not _ist_gesetzt(betrag_spalte):
            if not pd.api.types.is_number(betrag_euro) or pd.isna(betrag_euro) or float(betrag_euro) < 0:
                raise ValueError(
                    f"Mittelquellen: Quelle '{quelle}' erfordert einen nicht-negativen betrag_euro."
                )

        regelgebunden = str(row["unterliegt_limitierungsregeln"]).lower() in ["true", "1", "ja", "yes"]
        phase = str(row["anwendungsphase"])
        if regelgebunden and phase != "nach_regeln":
            raise ValueError(
                f"Mittelquellen: Quelle '{quelle}' ist regelgebunden und muss anwendungsphase='nach_regeln' haben."
            )
        if not regelgebunden and phase != "vor_regeln":
            raise ValueError(
                f"Mittelquellen: Quelle '{quelle}' ist regelunabhaengig und muss anwendungsphase='vor_regeln' haben."
            )

        if df_bestand is not None:
            if _ist_gesetzt(betrag_spalte):
                if str(betrag_spalte) not in df_bestand.columns:
                    raise ValueError(
                        f"Mittelquellen: Quelle '{quelle}' referenziert fehlende Betragsspalte "
                        f"'{betrag_spalte}'."
                    )
                _validiere_optionale_mittelspalten(df_bestand, [str(betrag_spalte)])

            for filter_spalte in _split_filter_spalten(row["filter_spalten"]):
                if filter_spalte not in df_bestand.columns:
                    raise ValueError(
                        f"Mittelquellen: Quelle '{quelle}' referenziert fehlende Filterspalte "
                        f"'{filter_spalte}'."
                    )

        filter_spalten = _split_filter_spalten(row["filter_spalten"])
        filter_operatoren = _split_filter_spalten(row["filter_operatoren"])
        filter_werte = _split_filter_spalten(row["filter_werte"])
        if filter_spalten and not (
            len(filter_spalten) == len(filter_operatoren) == len(filter_werte)
        ):
            raise ValueError(
                f"Mittelquellen: Quelle '{quelle}' hat inkonsistente Filterdefinitionen."
            )

    for w in warnungen:
        logger.warning("Mittelquellen-Validierung: %s", w)
    return warnungen


def _validiere_bestand(df: pd.DataFrame) -> list[str]:
    """Validiert Datentypen, Wertebereiche und Konsistenz des Bestands-DataFrames.

    Returns:
        Liste von Warnungen (nicht-kritisch). Wirft ValueError bei kritischen Fehlern.
    """
    warnungen: list[str] = []

    # --- Datentypen numerischer Spalten prüfen ---
    numerische_spalten = [
        "alter", "praemie_alt_monatlich", "praemie_neu_monatlich",
        "erhoehung_absolut", "erhoehung_prozent", "alterungsrueckstellung",
        "versicherungsdauer_jahre",
    ]
    _stelle_numerische_spalten_sicher(df, numerische_spalten)

    # --- NaN-Prüfung ---
    kritische_spalten = [
        "versicherten_id", "alter", "geschlecht", "tarif_id",
        "praemie_alt_monatlich", "praemie_neu_monatlich",
        "erhoehung_absolut", "erhoehung_prozent",
    ]
    for spalte in kritische_spalten:
        nan_anzahl = int(df[spalte].isna().sum())
        if nan_anzahl > 0:
            raise ValueError(
                f"Spalte '{spalte}' enthält {nan_anzahl} fehlende Werte (NaN)."
            )

    # --- Wertebereiche ---
    if (df["alter"] < 0).any() or (df["alter"] > 120).any():
        raise ValueError("Spalte 'alter' enthält Werte außerhalb [0, 120].")

    if (df["praemie_alt_monatlich"] < 0).any():
        raise ValueError("Spalte 'praemie_alt_monatlich' enthält negative Werte.")

    if (df["praemie_neu_monatlich"] < 0).any():
        raise ValueError("Spalte 'praemie_neu_monatlich' enthält negative Werte.")

    if (df["versicherungsdauer_jahre"] < 0).any():
        raise ValueError("Spalte 'versicherungsdauer_jahre' enthält negative Werte.")

    if (df["alterungsrueckstellung"] < 0).any():
        warnungen.append(
            "Spalte 'alterungsrueckstellung' enthält negative Werte "
            f"({(df['alterungsrueckstellung'] < 0).sum()} Zeilen)."
        )

    _validiere_optionale_mittelspalten(df)

    # --- Duplikate ---
    dups = df["versicherten_id"].duplicated().sum()
    if dups > 0:
        warnungen.append(f"{dups} doppelte versicherten_id gefunden.")

    # --- person_id Konsistenzprüfung (optional) ---
    if "person_id" in df.columns:
        nan_pid = int(df["person_id"].isna().sum())
        if nan_pid > 0:
            warnungen.append(
                f"Spalte 'person_id' enthält {nan_pid} fehlende Werte (NaN). "
                "Personen-Limitierung ist für diese Zeilen nicht möglich."
            )
        # Prüfe Konsistenz: gleiche Demographie (alter, geschlecht) pro person_id
        pid_gruppen = df.dropna(subset=["person_id"]).groupby("person_id")
        demo_inkonsistent = 0
        for spalte in ["alter", "geschlecht"]:
            if spalte in df.columns:
                n_unique = pid_gruppen[spalte].nunique()
                inkonsistent = (n_unique > 1).sum()
                if inkonsistent > 0:
                    demo_inkonsistent += inkonsistent
        if demo_inkonsistent > 0:
            warnungen.append(
                f"{demo_inkonsistent} person_id-Gruppen haben inkonsistente Demographie "
                "(unterschiedliches Alter oder Geschlecht innerhalb einer Person)."
            )

    # --- Geschlecht ---
    erlaubte_geschlechter = {"M", "W", "D"}
    unbekannte = set(df["geschlecht"].unique()) - erlaubte_geschlechter
    if unbekannte:
        warnungen.append(f"Unbekannte Geschlechts-Codes: {unbekannte}")

    # --- Konsistenz: erhoehung_absolut vs. Prämien ---
    diff = (df["praemie_neu_monatlich"] - df["praemie_alt_monatlich"] - df["erhoehung_absolut"]).abs()
    inkonsistent = (diff > 0.05).sum()
    if inkonsistent > 0:
        warnungen.append(
            f"{inkonsistent} Zeilen: erhoehung_absolut passt nicht zu "
            "praemie_neu - praemie_alt (Abweichung > 0,05 €)."
        )

    for w in warnungen:
        logger.warning("Bestandsvalidierung: %s", w)

    return warnungen


def _validiere_tarife(df: pd.DataFrame) -> list[str]:
    """Validiert den Tarife-DataFrame."""
    warnungen: list[str] = []
    erwartete = ["tarif_id", "rechnungszins"]
    fehlende = [s for s in erwartete if s not in df.columns]
    if fehlende:
        raise ValueError(f"Tarife: Fehlende Spalten: {fehlende}")

    if df["tarif_id"].isna().any():
        raise ValueError("Tarife: tarif_id enthält fehlende Werte.")

    _stelle_numerische_spalten_sicher(df, ["rechnungszins"], "Tarife")

    if (df["rechnungszins"] < 0).any() or (df["rechnungszins"] > 0.10).any():
        warnungen.append("Tarife: rechnungszins außerhalb [0, 0.10] gefunden.")

    for w in warnungen:
        logger.warning("Tarifvalidierung: %s", w)
    return warnungen


def _validiere_ausscheideordnung(df: pd.DataFrame) -> list[str]:
    """Validiert den Ausscheideordnungs-DataFrame."""
    warnungen: list[str] = []
    erwartete = ["tarif_id", "alter", "geschlecht", "qx", "storno"]
    fehlende = [s for s in erwartete if s not in df.columns]
    if fehlende:
        raise ValueError(f"Ausscheideordnung: Fehlende Spalten: {fehlende}")

    _stelle_numerische_spalten_sicher(df, ["qx", "storno"], "Ausscheideordnung")
    for spalte in ["qx", "storno"]:
        if df[spalte].isna().any():
            raise ValueError(f"Ausscheideordnung: '{spalte}' enthält fehlende Werte.")
        if (df[spalte] < 0).any() or (df[spalte] > 1).any():
            warnungen.append(f"Ausscheideordnung: '{spalte}' enthält Werte außerhalb [0, 1].")

    for w in warnungen:
        logger.warning("AO-Validierung: %s", w)
    return warnungen


def validiere_dataframe(df: pd.DataFrame, name: str) -> tuple[pd.DataFrame, list[str]]:
    """Normalisiert und validiert einen fachlichen Daten-DataFrame.

    Returns:
        Tuple aus (DataFrame, Liste von Warnungen).
    """
    df = normalisiere_spaltennamen(df)
    warnungen: list[str] = []
    if name == "mittelquellen":
        df = _normalisiere_mittelquellen_config(df)

    if name == "bestand":
        erwartete = [
            "versicherten_id", "alter", "geschlecht", "tarifwerk", "tarif_id",
            "tarifart", "praemie_alt_monatlich", "praemie_neu_monatlich",
            "erhoehung_absolut", "erhoehung_prozent", "alterungsrueckstellung",
            "versicherungsdauer_jahre",
        ]
        fehlende = [s for s in erwartete if s not in df.columns]
        if fehlende:
            raise ValueError(f"Fehlende Spalten: {fehlende}")

        warnungen = _validiere_bestand(df)

        grenzen, labels = erzeuge_altersgruppen(df)
        df["altersgruppe"] = pd.cut(
            df["alter"], bins=grenzen,
            right=False, labels=labels,
        ).astype(str)

    elif name == "tarife":
        warnungen = _validiere_tarife(df)

    elif name == "ao":
        warnungen = _validiere_ausscheideordnung(df)

    elif name == "mittelquellen":
        warnungen = validiere_mittelquellen_config(df)

    return df, warnungen


def lade_csv(datei, name: str) -> tuple[pd.DataFrame, list[str]]:
    """Lädt eine CSV-Datei und validiert sie.

    Returns:
        Tuple aus (DataFrame, Liste von Warnungen).
    """
    logger.info("Lade CSV: name=%s", name)
    df = pd.read_csv(datei, sep=";", low_memory=False)
    logger.info("CSV geladen: %d Zeilen, %d Spalten", len(df), len(df.columns))
    return validiere_dataframe(df, name)
