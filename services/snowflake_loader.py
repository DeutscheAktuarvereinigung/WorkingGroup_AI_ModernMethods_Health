"""Snowflake-Datenimport fuer das PKV-Limitierungstool."""

from __future__ import annotations

import logging
import re
from importlib import import_module
from typing import Any

import pandas as pd

from services.data_loader import validiere_dataframe, validiere_mittelquellen_config

logger = logging.getLogger(__name__)

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class SnowflakeImportFehler(ValueError):
    """Fachlicher Fehler beim Import aus Snowflake."""


def _validiere_identifier(wert: str, feldname: str) -> str:
    """Validiert einfache Snowflake-Identifier ohne Freitext-SQL."""
    wert = str(wert or "").strip()
    if not wert:
        raise SnowflakeImportFehler(f"Snowflake: '{feldname}' darf nicht leer sein.")
    if not _IDENTIFIER_PATTERN.fullmatch(wert):
        raise SnowflakeImportFehler(
            f"Snowflake: '{feldname}' enthält einen unzulässigen Identifier: {wert!r}. "
            "Erlaubt sind Buchstaben, Ziffern, Unterstrich und Dollarzeichen; "
            "der erste Buchstabe muss ein Buchstabe oder Unterstrich sein."
        )
    return wert


def _baue_tabellenreferenz(database: str | None, schema: str, tabelle: str) -> str:
    """Erzeugt eine sichere, qualifizierte Snowflake-Tabellenreferenz."""
    schema = _validiere_identifier(schema, "Schema")
    tabelle = _validiere_identifier(tabelle, "Tabelle")
    if database and str(database).strip():
        database = _validiere_identifier(database, "Datenbank")
        return f"{database}.{schema}.{tabelle}"
    return f"{schema}.{tabelle}"


def _hole_aktive_session() -> Any:
    """Liest die aktive Snowpark-Session in Streamlit-in-Snowflake."""
    try:
        snowflake_context = import_module("snowflake.snowpark.context")
        get_active_session = snowflake_context.get_active_session
    except ImportError as exc:
        raise SnowflakeImportFehler(
            "Snowflake: snowflake-snowpark-python ist nicht verfügbar. "
            "In Streamlit in Snowflake ist die aktive Session normalerweise vorhanden; "
            "lokal muss das Paket installiert und eine Session übergeben werden."
        ) from exc

    try:
        return get_active_session()
    except Exception as exc:  # pragma: no cover - haengt von Snowflake-Laufzeit ab
        raise SnowflakeImportFehler(
            "Snowflake: Es wurde keine aktive Snowflake-Session gefunden. "
            "Bitte die App in einer Snowflake-Streamlit-Umgebung ausführen."
        ) from exc


def _lade_tabelle_als_dataframe(
    session: Any,
    database: str | None,
    schema: str,
    tabelle: str,
    name: str,
    optional: bool = False,
) -> tuple[pd.DataFrame | None, list[str]]:
    """Laedt eine Snowflake-Tabelle nach Pandas und validiert den Datenvertrag."""
    warnungen: list[str] = []
    if optional and not str(tabelle or "").strip():
        return None, warnungen

    referenz = _baue_tabellenreferenz(database, schema, tabelle)
    logger.info("Lade Snowflake-Tabelle: name=%s, referenz=%s", name, referenz)
    try:
        df_roh = session.table(referenz).to_pandas()
    except Exception as exc:
        if optional:
            warnungen.append(
                f"Optionale Snowflake-Tabelle '{referenz}' konnte nicht geladen werden: {exc}"
            )
            logger.warning("Optionale Snowflake-Tabelle nicht geladen: %s", referenz, exc_info=True)
            return None, warnungen
        raise SnowflakeImportFehler(
            f"Snowflake: Tabelle '{referenz}' konnte nicht geladen werden: {exc}"
        ) from exc

    logger.info("Snowflake-Tabelle geladen: name=%s, zeilen=%d, spalten=%d", name, len(df_roh), len(df_roh.columns))
    df, validierungs_warnungen = validiere_dataframe(df_roh, name)
    warnungen.extend(validierungs_warnungen)
    return df, warnungen


def lade_snowflake_schema(
    database: str | None,
    schema: str,
    bestand_tabelle: str = "BESTAND",
    tarife_tabelle: str = "TARIFE",
    ao_tabelle: str = "AUSSCHEIDEORDNUNG",
    mittelquellen_tabelle: str | None = "MITTELQUELLEN_CONFIG",
    session: Any | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame | None, list[str]]:
    """Laedt Bestand, Tarife, Ausscheideordnung und optionale Mittelquellen aus einem Snowflake-Schema.

    Die Funktion verwendet dieselben Datenvertraege wie der CSV-Import. Snowflake-
    Spaltennamen werden vor der Validierung auf Kleinschreibung normalisiert, damit
    typische Snowflake-Tabellen mit gross geschriebenen Spalten funktionieren.
    """
    session = session or _hole_aktive_session()
    warnungen: list[str] = []

    df_bestand, w_bestand = _lade_tabelle_als_dataframe(
        session, database, schema, bestand_tabelle, "bestand"
    )
    df_tarife, w_tarife = _lade_tabelle_als_dataframe(
        session, database, schema, tarife_tabelle, "tarife"
    )
    df_ao, w_ao = _lade_tabelle_als_dataframe(
        session, database, schema, ao_tabelle, "ao"
    )
    df_mittel, w_mittel = _lade_tabelle_als_dataframe(
        session, database, schema, mittelquellen_tabelle or "", "mittelquellen", optional=True
    )

    warnungen.extend(w_bestand)
    warnungen.extend(w_tarife)
    warnungen.extend(w_ao)
    warnungen.extend(w_mittel)

    if df_mittel is not None:
        warnungen.extend(validiere_mittelquellen_config(df_mittel, df_bestand))

    return df_bestand, df_tarife, df_ao, df_mittel, warnungen
