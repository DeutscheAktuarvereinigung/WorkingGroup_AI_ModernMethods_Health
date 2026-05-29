import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def erzeuge_altersgruppen(df: pd.DataFrame, schritt: int = 10):
    alter_min = int(np.floor(df["alter"].min() / schritt) * schritt)
    alter_max = int(np.ceil((df["alter"].max() + 1) / schritt) * schritt)
    grenzen = list(range(alter_min, alter_max + schritt, schritt))
    labels = [f"{i}-{i + schritt - 1}" for i in range(alter_min, alter_max, schritt)]
    return grenzen, labels


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
    for spalte in numerische_spalten:
        if not pd.api.types.is_numeric_dtype(df[spalte]):
            raise ValueError(
                f"Spalte '{spalte}' muss numerisch sein, ist aber '{df[spalte].dtype}'."
            )

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

    if not pd.api.types.is_numeric_dtype(df["rechnungszins"]):
        raise ValueError(
            f"Tarife: 'rechnungszins' muss numerisch sein, ist aber '{df['rechnungszins'].dtype}'."
        )

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

    for spalte in ["qx", "storno"]:
        if not pd.api.types.is_numeric_dtype(df[spalte]):
            raise ValueError(
                f"Ausscheideordnung: '{spalte}' muss numerisch sein, "
                f"ist aber '{df[spalte].dtype}'."
            )
        if df[spalte].isna().any():
            raise ValueError(f"Ausscheideordnung: '{spalte}' enthält fehlende Werte.")
        if (df[spalte] < 0).any() or (df[spalte] > 1).any():
            warnungen.append(f"Ausscheideordnung: '{spalte}' enthält Werte außerhalb [0, 1].")

    for w in warnungen:
        logger.warning("AO-Validierung: %s", w)
    return warnungen


def lade_csv(datei, name: str) -> tuple[pd.DataFrame, list[str]]:
    """Lädt eine CSV-Datei und validiert sie.

    Returns:
        Tuple aus (DataFrame, Liste von Warnungen).
    """
    logger.info("Lade CSV: name=%s", name)
    df = pd.read_csv(datei, sep=";", low_memory=False)
    logger.info("CSV geladen: %d Zeilen, %d Spalten", len(df), len(df.columns))
    warnungen: list[str] = []

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

    return df, warnungen
