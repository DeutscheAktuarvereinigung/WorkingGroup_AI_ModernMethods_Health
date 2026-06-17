"""Tests fuer services/snowflake_loader.py"""

import numpy as np
import pandas as pd
import pytest

from services.snowflake_loader import SnowflakeImportFehler, lade_snowflake_schema


class FakeSnowparkDataFrame:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def to_pandas(self):
        return self._df.copy()


class FakeSession:
    def __init__(self, tabellen: dict[str, pd.DataFrame]):
        self.tabellen = tabellen

    def table(self, referenz: str):
        if referenz not in self.tabellen:
            raise RuntimeError(f"Tabelle nicht gefunden: {referenz}")
        return FakeSnowparkDataFrame(self.tabellen[referenz])


def _bestand_df():
    return pd.DataFrame({
        "VERSICHERTEN_ID": ["V1", "V2"],
        "ALTER": [66, 62],
        "GESCHLECHT": ["M", "W"],
        "TARIFWERK": ["Classic", "Komfort"],
        "TARIF_ID": ["CL-VOLL", "KO-AMB"],
        "TARIFART": ["voll", "ambulant"],
        "PRAEMIE_ALT_MONATLICH": [500.0, 200.0],
        "PRAEMIE_NEU_MONATLICH": [600.0, 230.0],
        "ERHOEHUNG_ABSOLUT": [100.0, 30.0],
        "ERHOEHUNG_PROZENT": [20.0, 15.0],
        "ALTERUNGSRUECKSTELLUNG": [30000.0, 10000.0],
        "VERSICHERUNGSDAUER_JAHRE": [20, 8],
        "UEBERZINS_MITTEL_EURO": [900.0, 200.0],
        "ZU10_MITTEL_EURO": [1500.0, 0.0],
    })


def _tarife_df():
    return pd.DataFrame({
        "TARIF_ID": ["CL-VOLL", "KO-AMB"],
        "RECHNUNGSZINS": [0.025, 0.0175],
    })


def _ao_df():
    return pd.DataFrame({
        "TARIF_ID": ["CL-VOLL", "KO-AMB"],
        "ALTER": [66, 62],
        "GESCHLECHT": ["M", "W"],
        "QX": [0.01, 0.008],
        "STORNO": [0.002, 0.002],
    })


def _mittelquellen_df():
    return pd.DataFrame({
        "QUELLE_ID": ["UEBERZINS", "ZU10", "RFB_FREI"],
        "NAME": ["Ueberzins", "ZU10", "Freie RfB"],
        "AKTIV": [True, True, True],
        "PRIORITAET": ["1", "2", "3"],
        "TYP": ["ZEILENINDIVIDUELL", "ZEILENINDIVIDUELL", "GLOBAL"],
        "BETRAG_EURO": [np.nan, np.nan, 1_000_000.0],
        "BETRAG_SPALTE": ["UEBERZINS_MITTEL_EURO", "ZU10_MITTEL_EURO", ""],
        "BETRAG_EINHEIT": ["EINMALEINLAGE", "EINMALEINLAGE", "EINMALEINLAGE"],
        "UNTERLIEGT_LIMITIERUNGSREGELN": [False, True, True],
        "EINSATZMODUS": ["PFLICHT_VOLLSTAENDIG", "NUR_BEDARF_FINANZIEREN", "NUR_BEDARF_FINANZIEREN"],
        "ANWENDUNGSPHASE": ["VOR_REGELN", "NACH_REGELN", "NACH_REGELN"],
        "FILTER_SPALTEN": ["", "TARIFART|ALTER", ""],
        "FILTER_OPERATOREN": ["", "==|>=", ""],
        "FILTER_WERTE": ["", "voll|65", ""],
        "FALLBACK_ERLAUBT": [True, True, True],
    })


def _session_mit_tabellen(mit_mittelquellen: bool = True):
    tabellen = {
        "PKV_DB.PKV_LIMITIERUNG.BESTAND": _bestand_df(),
        "PKV_DB.PKV_LIMITIERUNG.TARIFE": _tarife_df(),
        "PKV_DB.PKV_LIMITIERUNG.AUSSCHEIDEORDNUNG": _ao_df(),
    }
    if mit_mittelquellen:
        tabellen["PKV_DB.PKV_LIMITIERUNG.MITTELQUELLEN_CONFIG"] = _mittelquellen_df()
    return FakeSession(tabellen)


def test_lade_snowflake_schema_normalisiert_uppercase_spalten_und_config_referenzen():
    df_bestand, df_tarife, df_ao, df_mittel, warnungen = lade_snowflake_schema(
        database="PKV_DB",
        schema="PKV_LIMITIERUNG",
        session=_session_mit_tabellen(),
    )

    assert warnungen == []
    assert "versicherten_id" in df_bestand.columns
    assert "altersgruppe" in df_bestand.columns
    assert "rechnungszins" in df_tarife.columns
    assert "qx" in df_ao.columns
    assert df_mittel is not None
    assert df_mittel.loc[0, "betrag_spalte"] == "ueberzins_mittel_euro"
    assert df_mittel.loc[1, "filter_spalten"] == "tarifart|alter"


def test_lade_snowflake_schema_optionale_mittelquellen_tabelle_darf_fehlen():
    df_bestand, _, _, df_mittel, warnungen = lade_snowflake_schema(
        database="PKV_DB",
        schema="PKV_LIMITIERUNG",
        session=_session_mit_tabellen(mit_mittelquellen=False),
    )

    assert len(df_bestand) == 2
    assert df_mittel is None
    assert any("Optionale Snowflake-Tabelle" in warnung for warnung in warnungen)


def test_lade_snowflake_schema_lehnt_unsicheren_identifier_ab():
    with pytest.raises(SnowflakeImportFehler, match="Identifier"):
        lade_snowflake_schema(
            database="PKV_DB;DROP",
            schema="PKV_LIMITIERUNG",
            session=_session_mit_tabellen(),
        )
