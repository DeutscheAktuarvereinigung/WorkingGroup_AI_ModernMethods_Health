"""Tests für services/limitierung.py"""

import logging

import numpy as np
import pandas as pd
import pytest

from services.limitierung import (
    berechne_barwertfaktoren,
    berechne_barwertfaktoren_befristet,
    berechne_limitierung,
    berechne_limitierung_person,
    berechne_sensitivitaet,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Barwertfaktoren
# ═══════════════════════════════════════════════════════════════════════════════


class TestBerechneBarwertfaktoren:

    def test_ergebnis_spalten(self, ausscheideordnung, tarife):
        bwf = berechne_barwertfaktoren(ausscheideordnung, tarife)
        assert set(bwf.columns) == {"tarif_id", "geschlecht", "alter", "barwertfaktor"}

    def test_barwertfaktoren_positiv(self, ausscheideordnung, tarife):
        bwf = berechne_barwertfaktoren(ausscheideordnung, tarife)
        assert (bwf["barwertfaktor"] >= 0).all()

    def test_barwertfaktoren_fallend_mit_alter(self, ausscheideordnung, tarife):
        """Barwertfaktoren sollten tendenziell mit steigendem Alter sinken."""
        bwf = berechne_barwertfaktoren(ausscheideordnung, tarife)
        subset = bwf[(bwf["tarif_id"] == "CL-AMB") & (bwf["geschlecht"] == "M")]
        # Alter 20 sollte > Alter 80
        bwf_20 = subset.loc[subset["alter"] == 20, "barwertfaktor"].values[0]
        bwf_80 = subset.loc[subset["alter"] == 80, "barwertfaktor"].values[0]
        assert bwf_20 > bwf_80

    def test_hoeherer_zins_kleinere_barwertfaktoren(self, ausscheideordnung, tarife):
        """Höherer Rechnungszins → kleinere Barwertfaktoren."""
        bwf = berechne_barwertfaktoren(ausscheideordnung, tarife)
        # CL-AMB hat 2.5%, PR-AMB hat 1.0%
        cl = bwf[(bwf["tarif_id"] == "CL-AMB") & (bwf["geschlecht"] == "M") & (bwf["alter"] == 40)]
        pr = bwf[(bwf["tarif_id"] == "PR-AMB") & (bwf["geschlecht"] == "M") & (bwf["alter"] == 40)]
        assert cl["barwertfaktor"].values[0] < pr["barwertfaktor"].values[0]

    def test_leere_ausscheideordnung(self, tarife):
        ao_leer = pd.DataFrame(columns=["tarif_id", "geschlecht", "alter", "qx", "storno"])
        bwf = berechne_barwertfaktoren(ao_leer, tarife)
        assert len(bwf) == 0

    def test_maximales_alter_barwertfaktor_null(self, ausscheideordnung, tarife):
        """Barwertfaktor beim höchsten Alter sollte 0 sein (keine Zukunft)."""
        bwf = berechne_barwertfaktoren(ausscheideordnung, tarife)
        subset = bwf[(bwf["tarif_id"] == "CL-AMB") & (bwf["geschlecht"] == "M")]
        max_alter = subset["alter"].max()
        bwf_max = subset.loc[subset["alter"] == max_alter, "barwertfaktor"].values[0]
        assert bwf_max == pytest.approx(0.0, abs=0.01)

    def test_alle_tarife_vorhanden(self, ausscheideordnung, tarife):
        bwf = berechne_barwertfaktoren(ausscheideordnung, tarife)
        for tid in tarife["tarif_id"]:
            assert tid in bwf["tarif_id"].values

    def test_beide_geschlechter(self, ausscheideordnung, tarife):
        bwf = berechne_barwertfaktoren(ausscheideordnung, tarife)
        assert set(bwf["geschlecht"].unique()) == {"M", "W"}


class TestBerechneBarwertfaktorenBefristet:

    def test_ergebnis_spalten(self, ausscheideordnung, tarife):
        bwf = berechne_barwertfaktoren_befristet(ausscheideordnung, tarife, laufzeit_jahre=10)
        assert "barwertfaktor_befristet" in bwf.columns

    def test_befristet_kleiner_unbefristet(self, ausscheideordnung, tarife):
        """Befristete Barwertfaktoren müssen <= unbefristete sein."""
        bwf_unbef = berechne_barwertfaktoren(ausscheideordnung, tarife)
        bwf_bef = berechne_barwertfaktoren_befristet(ausscheideordnung, tarife, laufzeit_jahre=10)
        merged = bwf_unbef.merge(bwf_bef, on=["tarif_id", "geschlecht", "alter"])
        assert (merged["barwertfaktor_befristet"] <= merged["barwertfaktor"] + 1e-6).all()

    def test_laengere_laufzeit_groesserer_faktor(self, ausscheideordnung, tarife):
        bwf_5 = berechne_barwertfaktoren_befristet(ausscheideordnung, tarife, laufzeit_jahre=5)
        bwf_20 = berechne_barwertfaktoren_befristet(ausscheideordnung, tarife, laufzeit_jahre=20)
        merged = bwf_5.merge(bwf_20, on=["tarif_id", "geschlecht", "alter"], suffixes=("_5", "_20"))
        # 20 Jahre sollte >= 5 Jahre sein
        assert (merged["barwertfaktor_befristet_20"] >= merged["barwertfaktor_befristet_5"] - 1e-6).all()

    def test_laufzeit_1_jahr(self, ausscheideordnung, tarife):
        bwf = berechne_barwertfaktoren_befristet(ausscheideordnung, tarife, laufzeit_jahre=1)
        # Bei 1 Jahr Laufzeit sollten alle Faktoren sehr klein sein
        assert (bwf["barwertfaktor_befristet"] < 2.0).all()

    def test_positiv(self, ausscheideordnung, tarife):
        bwf = berechne_barwertfaktoren_befristet(ausscheideordnung, tarife, laufzeit_jahre=10)
        assert (bwf["barwertfaktor_befristet"] >= 0).all()


# ═══════════════════════════════════════════════════════════════════════════════
# Limitierungsberechnung
# ═══════════════════════════════════════════════════════════════════════════════


class TestBerechneLimitierung:

    @pytest.fixture
    def regeln_global_30(self):
        return [{"ziel_pct": 30.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]

    @pytest.fixture
    def regeln_global_15(self):
        return [{"ziel_pct": 15.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]

    def test_ergebnis_spalten(self, bestand_klein, barwertfaktoren, regeln_global_30):
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln_global_30, "full", 10)
        erwartete = {"erhoehung_limitiert_pct", "erhoehung_limitiert_abs", "praemie_limitiert",
                     "differenz_monatlich", "einmaleinlage", "limitiert",
                     "regel_index", "regel_beschreibung"}
        assert erwartete == set(result.columns)

    def test_keine_limitierung_bei_hohem_ziel(self, bestand_klein, barwertfaktoren):
        regeln = [{"ziel_pct": 100.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        # Kein Versicherter sollte limitiert sein
        assert result["limitiert"].sum() == 0
        assert result["differenz_monatlich"].sum() == pytest.approx(0.0, abs=0.1)

    def test_limitierung_greift(self, bestand_klein, barwertfaktoren, regeln_global_15):
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln_global_15, "full", 10)
        # Versicherte mit >15% werden limitiert (30% und 20%)
        assert result["limitiert"].sum() > 0
        # Limitierte prozentuale Erhöhung darf 15% nicht übersteigen
        assert result["erhoehung_limitiert_pct"].max() <= 15.0 + 0.01

    def test_praemie_limitiert_berechnung(self, bestand_klein, barwertfaktoren, regeln_global_15):
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln_global_15, "full", 10)
        # praemie_limitiert = praemie_alt + erhoehung_limitiert_abs
        praemie_erwartet = bestand_klein["praemie_alt_monatlich"].values + result["erhoehung_limitiert_abs"].values
        np.testing.assert_allclose(result["praemie_limitiert"].values, np.round(praemie_erwartet, 2), atol=0.01)

    def test_differenz_monatlich_nicht_negativ(self, bestand_klein, barwertfaktoren, regeln_global_15):
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln_global_15, "full", 10)
        assert (result["differenz_monatlich"] >= 0).all()

    def test_einmaleinlage_nicht_negativ(self, bestand_klein, barwertfaktoren, regeln_global_15):
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln_global_15, "full", 10)
        assert (result["einmaleinlage"] >= 0).all()

    def test_einmaleinlage_proportional_zu_differenz(self, bestand_klein, barwertfaktoren, regeln_global_15):
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln_global_15, "full", 10)
        limitierte = result[result["limitiert"]]
        # Einmaleinlage = Differenz * 12 * Barwertfaktor → wenn Differenz > 0, dann Einmaleinlage > 0
        for _, row in limitierte.iterrows():
            if row["differenz_monatlich"] > 0.01:
                assert row["einmaleinlage"] > 0

    def test_segmentierte_regel(self, bestand_klein, barwertfaktoren):
        """Regel nur für ambulant-Tarife."""
        regeln = [{
            "ziel_pct": 5.0, "ziel_abs": None,
            "scope_spalte": "tarifart", "scope_werte": ["ambulant"],
        }]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        # Ambulante mit >5% werden limitiert
        ambulant_mask = bestand_klein["tarifart"] == "ambulant"
        # Stationäre sollten NICHT limitiert sein (kein Cap greift)
        stationaer_mask = bestand_klein["tarifart"] == "stationaer"
        assert result.loc[stationaer_mask.values, "limitiert"].sum() == 0

    def test_mehrere_regeln(self, bestand_klein, barwertfaktoren):
        """Globale + segmentierte Regel."""
        regeln = [
            {"ziel_pct": 25.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None},
            {"ziel_pct": 10.0, "ziel_abs": None, "scope_spalte": "tarifart", "scope_werte": ["ambulant"]},
        ]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        # Ambulante werden auf 10% begrenzt, Rest auf 25%
        ambulant_mask = bestand_klein["tarifart"] == "ambulant"
        assert result.loc[ambulant_mask.values, "erhoehung_limitiert_pct"].max() <= 10.0 + 0.01

    def test_absolute_limitierung(self, bestand_klein, barwertfaktoren):
        """Absolute Begrenzung in €."""
        regeln = [{"ziel_pct": None, "ziel_abs": 20.0, "scope_spalte": None, "scope_werte": None}]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        assert result["erhoehung_limitiert_abs"].max() <= 20.0 + 0.01

    def test_kombinierte_abs_und_pct(self, bestand_klein, barwertfaktoren):
        """Sowohl prozentuale als auch absolute Begrenzung."""
        regeln = [{"ziel_pct": 15.0, "ziel_abs": 30.0, "scope_spalte": None, "scope_werte": None}]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        # Beide Grenzen müssen eingehalten werden
        assert result["erhoehung_limitiert_pct"].max() <= 15.0 + 0.01
        assert result["erhoehung_limitiert_abs"].max() <= 30.0 + 0.01

    def test_leere_regeln(self, bestand_klein, barwertfaktoren):
        """Keine Regeln → keine Limitierung."""
        result = berechne_limitierung(bestand_klein, barwertfaktoren, [], "full", 10)
        assert result["limitiert"].sum() == 0

    def test_regel_ohne_ziel(self, bestand_klein, barwertfaktoren):
        """Regel mit ziel_pct=None und ziel_abs=None → wird übersprungen."""
        regeln = [{"ziel_pct": None, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        assert result["limitiert"].sum() == 0

    def test_zeilenzahl_gleich(self, bestand_klein, barwertfaktoren, regeln_global_15):
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln_global_15, "full", 10)
        assert len(result) == len(bestand_klein)

    def test_limitierung_null_praemie(self, barwertfaktoren):
        """Edge Case: Prämie = 0."""
        df = pd.DataFrame({
            "versicherten_id": ["V1"],
            "alter": [30],
            "geschlecht": ["M"],
            "tarifwerk": ["Classic"],
            "tarif_id": ["CL-AMB"],
            "tarifart": ["ambulant"],
            "praemie_alt_monatlich": [0.0],
            "praemie_neu_monatlich": [0.0],
            "erhoehung_absolut": [0.0],
            "erhoehung_prozent": [0.0],
            "alterungsrueckstellung": [0.0],
            "versicherungsdauer_jahre": [0],
        })
        regeln = [{"ziel_pct": 10.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        result = berechne_limitierung(df, barwertfaktoren, regeln, "full", 10)
        assert len(result) == 1
        assert result.iloc[0]["einmaleinlage"] == 0.0

    def test_fehlende_barwertfaktoren_warnung(self, bestand_klein, barwertfaktoren, caplog):
        """Fehlende BWF-Einträge erzeugen eine Warnung im Log."""
        # Entferne BWF für einen Tarif, damit der Merge NaNs erzeugt
        bwf_unvollstaendig = barwertfaktoren[barwertfaktoren["tarif_id"] != "CL-AMB"]
        regeln = [{"ziel_pct": 15.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        with caplog.at_level(logging.WARNING, logger="services.limitierung"):
            result = berechne_limitierung(bestand_klein, bwf_unvollstaendig, regeln, "full", 10)
        assert any("Barwertfaktoren-Merge" in msg for msg in caplog.messages)
        # Ergebnis wird trotzdem berechnet (mit 0 für fehlende BWF)
        assert len(result) == len(bestand_klein)


# ═══════════════════════════════════════════════════════════════════════════════
# Regeltracing
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegeltracing:

    def test_keine_limitierung_kein_tracing(self, bestand_klein, barwertfaktoren):
        """Hohes Ziel → kein Versicherter limitiert → alle regel_index = -1."""
        regeln = [{"ziel_pct": 100.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        assert (result["regel_index"] == -1).all()
        assert (result["regel_beschreibung"] == "").all()

    def test_globale_regel_tracing(self, bestand_klein, barwertfaktoren):
        """Globale Regel bei 15% → limitierte erhalten regel_index=0."""
        regeln = [{"ziel_pct": 15.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        limitierte = result[result["limitiert"]]
        assert (limitierte["regel_index"] == 0).all()
        assert all("Regel 1" in b and "Global" in b for b in limitierte["regel_beschreibung"])

    def test_segmentierte_regel_tracing(self, bestand_klein, barwertfaktoren):
        """Segmentierte Regel → nur ambulante erhalten die Regel-Referenz."""
        regeln = [{
            "ziel_pct": 5.0, "ziel_abs": None,
            "scope_spalte": "tarifart", "scope_werte": ["ambulant"],
        }]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        stationaer_mask = bestand_klein["tarifart"] == "stationaer"
        assert (result.loc[stationaer_mask.values, "regel_index"] == -1).all()

    def test_mehrere_regeln_letzte_gewinnt(self, bestand_klein, barwertfaktoren):
        """Global 25% + ambulant 10% → ambulante mit >10% bekommen Regel 2."""
        regeln = [
            {"ziel_pct": 25.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None},
            {"ziel_pct": 10.0, "ziel_abs": None, "scope_spalte": "tarifart", "scope_werte": ["ambulant"]},
        ]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        ambulant_mask = bestand_klein["tarifart"] == "ambulant"
        ambulant_limitiert = result[ambulant_mask.values & result["limitiert"]]
        # Ambulante mit >10% werden von Regel 2 (Index 1) begrenzt
        assert (ambulant_limitiert["regel_index"] == 1).all()
        assert all("Regel 2" in b for b in ambulant_limitiert["regel_beschreibung"])

    def test_beschreibung_format(self, bestand_klein, barwertfaktoren):
        """Regel-Beschreibung enthält Zielwerte und Scope."""
        regeln = [
            {"ziel_pct": 20.0, "ziel_abs": 50.0, "scope_spalte": None, "scope_werte": None},
            {"ziel_pct": 10.0, "ziel_abs": None, "scope_spalte": "tarifart", "scope_werte": ["ambulant"]},
        ]
        result = berechne_limitierung(bestand_klein, barwertfaktoren, regeln, "full", 10)
        beschreibungen = set(result.loc[result["limitiert"], "regel_beschreibung"])
        for b in beschreibungen:
            assert "Regel" in b
            assert "≤" in b

    def test_leere_regeln_kein_tracing(self, bestand_klein, barwertfaktoren):
        result = berechne_limitierung(bestand_klein, barwertfaktoren, [], "full", 10)
        assert (result["regel_index"] == -1).all()
        assert (result["regel_beschreibung"] == "").all()


# ═══════════════════════════════════════════════════════════════════════════════
# Sensitivitätsanalyse
# ═══════════════════════════════════════════════════════════════════════════════


class TestBerechneSensitivitaet:

    def test_ergebnis_spalten(self, bestand_klein, barwertfaktoren):
        regeln = [{"ziel_pct": 20.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        result = berechne_sensitivitaet(bestand_klein, barwertfaktoren, regeln, "full", 10)
        assert "Limitierungsziel (%)" in result.columns
        assert "RfB-Bedarf (Mio. €)" in result.columns
        assert "Anzahl limitiert" in result.columns
        assert "Ø Entlastung (€/Mon)" in result.columns

    def test_monoton_fallender_bedarf(self, bestand_klein, barwertfaktoren):
        """Höheres Limitierungsziel → weniger Bedarf."""
        regeln = [{"ziel_pct": 20.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        result = berechne_sensitivitaet(bestand_klein, barwertfaktoren, regeln, "full", 10)
        bedarfe = result["RfB-Bedarf (Mio. €)"].values
        # Allgemein fallend (erlaubt Gleichheit)
        for i in range(len(bedarfe) - 1):
            assert bedarfe[i] >= bedarfe[i + 1] - 1e-6

    def test_ohne_globale_regel(self, bestand_klein, barwertfaktoren):
        """Nur segmentierte Regeln → leeres Ergebnis."""
        regeln = [{"ziel_pct": 10.0, "ziel_abs": None, "scope_spalte": "tarifart", "scope_werte": ["ambulant"]}]
        result = berechne_sensitivitaet(bestand_klein, barwertfaktoren, regeln, "full", 10)
        assert len(result) == 0

    def test_mindestens_ein_szenario(self, bestand_klein, barwertfaktoren):
        regeln = [{"ziel_pct": 20.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        result = berechne_sensitivitaet(bestand_klein, barwertfaktoren, regeln, "full", 10)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Personen-Limitierung
# ═══════════════════════════════════════════════════════════════════════════════


class TestBerechneLimitierungPerson:

    def test_ergebnis_spalten_vorhanden(self, bestand_mit_personen, barwertfaktoren):
        """Ergebnis enthält alle Personen-Level-Spalten."""
        regeln = [{"ziel_pct": 25.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        personen_regel = {"ziel_abs": 100.0}
        res = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
        )
        assert "erhoehung_person_gesamt_vorher" in res.columns
        assert "erhoehung_person_gesamt_nachher" in res.columns
        assert "person_limitiert" in res.columns

    def test_proportional_summe_unter_cap(self, bestand_mit_personen, barwertfaktoren):
        """Bei proportionaler Verteilung bleibt die Personen-Gesamterhöhung ≤ Cap."""
        regeln = []
        personen_regel = {"ziel_abs": 100.0}  # Max 100 €/Mon pro Person
        res = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
            verteilungsmodus="proportional",
        )
        # Prüfe pro Person
        df_check = bestand_mit_personen[["person_id"]].copy()
        df_check["erh_limited"] = res["erhoehung_limitiert_abs"].values
        for pid, grp in df_check.groupby("person_id"):
            assert grp["erh_limited"].sum() <= 100.0 + 0.01

    def test_groesster_zuerst_reduziert_maximum(self, bestand_mit_personen, barwertfaktoren):
        """Bei groesster_zuerst wird der größte Tarif bevorzugt reduziert."""
        regeln = []
        # P001 hat erhoehung_absolut [60, 105] → Summe 165, Cap 100 → 65 Reduktion
        personen_regel = {"ziel_abs": 100.0}
        res = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
            verteilungsmodus="groesster_zuerst",
        )
        # P001: V001 (60€) und V002 (105€). Bei groesster_zuerst wird V002 zuerst reduziert
        erh_v002 = res["erhoehung_limitiert_abs"].values[1]
        erh_v001 = res["erhoehung_limitiert_abs"].values[0]
        # V002 sollte stärker reduziert sein als V001
        assert erh_v002 < 105.0  # V002 wurde reduziert
        # Summe P001 muss ≤ 100
        assert erh_v001 + erh_v002 <= 100.0 + 0.01

    def test_proportional_verteilung_korrekt(self, bestand_mit_personen, barwertfaktoren):
        """Proportionale Verteilung: Reduktion proportional zur Einzel-Erhöhung."""
        regeln = []
        personen_regel = {"ziel_abs": 100.0}
        res = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
            verteilungsmodus="proportional",
        )
        # P001 hat [60, 105] → Summe 165, Cap 100, Reduktion 65
        # Proportional: V001 anteil = 60/165, V002 anteil = 105/165
        erh_v001 = res["erhoehung_limitiert_abs"].values[0]
        erh_v002 = res["erhoehung_limitiert_abs"].values[1]
        # V001: 60 - 65 * (60/165) ≈ 60 - 23.64 ≈ 36.36
        assert erh_v001 == pytest.approx(60.0 - 65.0 * (60.0 / 165.0), abs=0.01)
        # V002: 105 - 65 * (105/165) ≈ 105 - 41.36 ≈ 63.64
        assert erh_v002 == pytest.approx(105.0 - 65.0 * (105.0 / 165.0), abs=0.01)

    def test_person_ohne_ueberschreitung_nicht_limitiert(self, bestand_mit_personen, barwertfaktoren):
        """Person unter dem Cap wird nicht limitiert."""
        regeln = []
        # P003 hat [15, 45] → Summe 60. Cap 200 → keine Limitierung
        personen_regel = {"ziel_abs": 200.0}
        res = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
        )
        # P003: V005 und V006 (Indices 4, 5)
        assert not res["person_limitiert"].values[4]
        assert not res["person_limitiert"].values[5]
        # Erhöhungen unverändert
        assert res["erhoehung_limitiert_abs"].values[4] == pytest.approx(15.0, abs=0.01)
        assert res["erhoehung_limitiert_abs"].values[5] == pytest.approx(45.0, abs=0.01)

    def test_ziel_pct_begrenzt_auf_gesamtpraemie(self, bestand_mit_personen, barwertfaktoren):
        """ziel_pct begrenzt auf Prozent der Gesamtprämie der Person."""
        regeln = []
        # P001: praemie_alt = [200, 350] → Gesamt 550, ziel_pct=10 → max 55€
        # Erh = [60, 105] → Summe 165 > 55 → reduziert
        personen_regel = {"ziel_pct": 10.0}
        res = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
            verteilungsmodus="proportional",
        )
        df_check = bestand_mit_personen[["person_id"]].copy()
        df_check["erh_limited"] = res["erhoehung_limitiert_abs"].values
        p001_sum = df_check[df_check["person_id"] == "P001"]["erh_limited"].sum()
        assert p001_sum <= 55.0 + 0.01

    def test_reihenfolge_tarif_zuerst_vs_person_zuerst(self, bestand_mit_personen, barwertfaktoren):
        """Verschiedene Reihenfolgen liefern unterschiedliche aber valide Ergebnisse."""
        regeln = [{"ziel_pct": 25.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        personen_regel = {"ziel_abs": 80.0}

        res_tf = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
            reihenfolge="tarif_zuerst",
        )
        res_pf = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
            reihenfolge="person_zuerst",
        )
        # Beide müssen Personen-Cap einhalten
        df_check_tf = bestand_mit_personen[["person_id"]].copy()
        df_check_tf["erh"] = res_tf["erhoehung_limitiert_abs"].values
        df_check_pf = bestand_mit_personen[["person_id"]].copy()
        df_check_pf["erh"] = res_pf["erhoehung_limitiert_abs"].values

        for pid in bestand_mit_personen["person_id"].unique():
            assert df_check_tf[df_check_tf["person_id"] == pid]["erh"].sum() <= 80.0 + 0.01
            assert df_check_pf[df_check_pf["person_id"] == pid]["erh"].sum() <= 80.0 + 0.01

    def test_keine_person_id_wirft_valueerror(self, bestand_klein, barwertfaktoren):
        """Ohne person_id-Spalte wird ValueError geworfen."""
        regeln = []
        personen_regel = {"ziel_abs": 100.0}
        with pytest.raises(ValueError, match="person_id"):
            berechne_limitierung_person(
                bestand_klein, barwertfaktoren, regeln, personen_regel, "full", 10,
            )

    def test_leere_personen_regel_nur_tarif(self, bestand_mit_personen, barwertfaktoren):
        """Ohne Personen-Ziel wird nur Tarif-Limitierung angewendet."""
        regeln = [{"ziel_pct": 25.0, "ziel_abs": None, "scope_spalte": None, "scope_werte": None}]
        personen_regel = {}  # Kein Personen-Cap
        res = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
        )
        assert not res["person_limitiert"].any()

    def test_einmaleinlage_positiv_bei_limitierung(self, bestand_mit_personen, barwertfaktoren):
        """Limitierte Tarife haben nicht-negative Einmaleinlagen."""
        regeln = []
        personen_regel = {"ziel_abs": 50.0}
        res = berechne_limitierung_person(
            bestand_mit_personen, barwertfaktoren, regeln, personen_regel, "full", 10,
        )
        assert (res["einmaleinlage"] >= 0).all()
        assert res.loc[res["limitiert"], "einmaleinlage"].sum() > 0
