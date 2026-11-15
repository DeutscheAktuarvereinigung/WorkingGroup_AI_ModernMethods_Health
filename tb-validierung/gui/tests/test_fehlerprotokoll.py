"""Tests für gui/fehlerprotokoll.py (Abgleich Befunde <-> Fehlerprotokoll).

Ausführen (aus dem Ordner tb-validierung/gui):
    python -m pytest tests/test_fehlerprotokoll.py -s     # -s zeigt die Tabellen
    python tests/test_fehlerprotokoll.py                  # ohne pytest

Geprüft wird:
(a) Referenzbericht der fehlerhaften TB: jeder dokumentierte Fehler (inkl.
    F05a–c) hat mindestens einen Befund, und zwar genau die erwarteten.
(b) Gegenprobe (fehlerfreie TB): kein dokumentierter Fehler gilt als gefunden.
(c) Je Fehler zwei umformulierte Befundtexte (wie sie eine Live-Antwort des
    Sprachmodells liefern könnte) werden genau diesem Fehler zugeordnet.
(d) Ähnlich klingende, aber unbeteiligte Befunde werden keinem Fehler zugeordnet.
(e) Seiten und Markierungen sind per PyMuPDF in beiden PDFs verifiziert.
(f) Echte Live-Läufe mit claude-sonnet-5-5 (anders formuliert als der
    Nachweis-Lauf): fehlerhafte TB 13 von 13 Fehlergruppen mit genau den
    erwarteten Befunden, fehlerfreie TB keine. Übersprungen, wenn die
    Ergebnisdateien fehlen.

Keine Sprachmodell-Aufrufe: Es werden nur die gespeicherten Prüfberichte,
Live-Ergebnisse und die PDFs gelesen. Ohne pytest endet das Skript bei einem
fehlgeschlagenen Test mit Exit-Code 1.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import traceback
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.dont_write_bytecode = True          # keine __pycache__-Ordner im Repo
GUI_ORDNER = Path(__file__).resolve().parent.parent
TB_ORDNER = GUI_ORDNER.parent
sys.path.insert(0, str(GUI_ORDNER))

import fehlerprotokoll as fp  # noqa: E402

BERICHT_FEHLERHAFT = TB_ORDNER / "validierungsnotebook" / "pruefbericht_TB_VitalPlus_fehlerhaft.json"
BERICHT_SAUBER = TB_ORDNER / "validierungsnotebook" / "pruefbericht_TB_VitalPlus.json"
PDF_FEHLERHAFT = TB_ORDNER / "synthetische-tb" / "TB_VitalPlus_fehlerhaft.pdf"
PDF_SAUBER = TB_ORDNER / "synthetische-tb" / "TB_VitalPlus.pdf"
# Ergebnisse der Live-Messung mit claude-sonnet-5-5 (Oktober 2026, zwei volle Läufe)
LIVE_ORDNER = Path(__file__).resolve().parent / "daten"
LIVE_FEHLERHAFT = LIVE_ORDNER / "live1_fehlerhaft.json"
LIVE_SAUBER = LIVE_ORDNER / "live2_fehlerfrei.json"

ALLE_NUMMERN = ["F01", "F02", "F03", "F04", "F05a", "F05b", "F05c",
                "F06", "F07", "F08", "F09", "F10", "F11", "F12", "F13"]


# --- Befund-Attrappe -------------------------------------------------------------
@dataclass
class BefundAttrappe:
    """Minimale Attrappe mit denselben vier Feldern wie engine.BefundGUI."""
    check_id: str
    beschreibung: str
    seite: int | None
    schwere: str = "FEHLER"


try:   # bevorzugt die echte Klasse aus engine.py, falls importierbar
    from engine import BefundGUI as _BefundKlasse
except Exception:  # engine.py fehlt oder ist (noch) nicht importierbar
    _BefundKlasse = BefundAttrappe


def befund(check_id: str, beschreibung: str, seite: int | None,
           schwere: str = "FEHLER"):
    return _BefundKlasse(check_id=check_id, beschreibung=beschreibung,
                         seite=seite, schwere=schwere)


def befunde_aus_bericht(pfad: Path) -> list:
    bericht = json.loads(pfad.read_text(encoding="utf-8"))
    return [befund(c["id"], b["beschreibung"], b.get("seite"), b["schwere"])
            for c in bericht["checks"] for b in c.get("befunde", [])]


class _Uebersprungen(Exception):
    """Test übersprungen (Ausführung ohne pytest)."""


def ueberspringen(grund: str):
    try:
        import pytest
    except ImportError:
        raise _Uebersprungen(grund) from None
    pytest.skip(grund)


def befunde_aus_live_lauf(pfad: Path) -> list:
    """Befunde einer Live-Ergebnisdatei ({"dokument", "ergebnisse": [CheckErgebnis]})."""
    if not pfad.exists():
        ueberspringen(f"Live-Ergebnisdatei fehlt: {pfad}")
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    return [befund(e["id"], b["beschreibung"], b.get("seite"), b["schwere"])
            for e in daten["ergebnisse"] for b in e.get("befunde", [])]


def kurzform(b) -> str:
    return f"{b.check_id} S.{b.seite} {b.schwere[0]}"


def tabelle(abgleich) -> str:
    """Zuordnung als Texttabelle (für die Testausgabe)."""
    zeilen = [f"{'Nr.':<5} | {'Kurztext':<44} | {'gef.':<4} | Befunde",
              "-" * 120]
    for fehler, treffer in abgleich:
        zeilen.append(f"{fehler.nr:<5} | {fehler.kurz:<44} | "
                      f"{'ja' if treffer else 'NEIN':<4} | "
                      + ", ".join(kurzform(b) for b in treffer))
    return "\n".join(zeilen)


# =============================================================================
# Fehlerprotokoll einlesen
# =============================================================================
def test_fehlerprotokoll_wird_vollstaendig_gelesen():
    fehlerliste = fp.lade_fehlerprotokoll()
    assert [f.nr for f in fehlerliste] == ALLE_NUMMERN
    assert len({f.gruppe for f in fehlerliste}) == 13
    for f in fehlerliste:
        assert f.ort and f.fehler and f.korrekt and f.kategorie, f.nr
        assert f.kurz and len(f.kurz) <= 45, f.nr
        assert "**" not in f.fehler + f.korrekt and "`" not in f.fehler, f.nr
        assert f.seiten, f"{f.nr}: keine Fundstelle hinterlegt"
    f01 = fehlerliste[0]
    assert "653,33" in f01.fehler and "635,33" in f01.korrekt
    assert "Anhang 3" in f01.ort


# =============================================================================
# (a) Referenzbericht der fehlerhaften TB
# =============================================================================
# Erwartete Zuordnung nach manueller Durchsicht aller 32 Befunde
# (Check-ID, Seite). Nicht zugeordnet bleiben: L-03 S.35 (vermeintliche
# Formel ohne Division – PDF-Extraktionsartefakt des Bruchstrichs) und die
# fünf L-04-Warnungen S. 24/33/40/46/47 (Normzitate, deren Absatz laut
# amtlichem Wortlaut nicht genau passt – stehen so auch in der fehlerfreien TB).
ERWARTET_FEHLERHAFT = {
    "F01": [("V-06", 89), ("V-07", 89)],
    "F02": [("V-09", 79), ("V-09", 79), ("L-03", 79), ("L-05", 79)],
    "F03": [("V-09", 16), ("L-04", 16)],
    "F04": [("V-01", 45)],
    "F05a": [("L-01", 44)],
    "F05b": [("L-01", 35)],
    "F05c": [("L-01", 11)],
    "F06": [("V-04", 7)],
    "F07": [("V-08", 73), ("L-03", 73), ("L-05", 73)],
    "F08": [("V-05", 62), ("V-07", 62), ("V-13", 62)],
    "F09": [("V-05", 60), ("L-03", 60)],
    "F10": [("V-03", 3)],
    "F11": [("L-02", 92)],
    "F12": [("L-03", 44), ("L-05", 44)],
    "F13": [("L-06", 75)],
}
ERWARTET_NICHT_ZUGEORDNET = Counter([("L-03", 35), ("L-04", 24), ("L-04", 33),
                                     ("L-04", 40), ("L-04", 46), ("L-04", 47)])


def test_a_referenzbericht_fehlerhaft_findet_alle():
    befunde = befunde_aus_bericht(BERICHT_FEHLERHAFT)
    assert len(befunde) == 32          # 21 Fehler + 11 Warnungen
    abgleich = fp.gleiche_ab(befunde)
    print("\n(a) Zuordnung – Referenzbericht der fehlerhaften TB")
    print(tabelle(abgleich))

    nicht_gefunden = [f.nr for f, treffer in abgleich if not treffer]
    assert not nicht_gefunden, f"Nicht gefunden: {nicht_gefunden}"
    for fehler, treffer in abgleich:
        assert sorted((b.check_id, b.seite) for b in treffer) \
            == sorted(ERWARTET_FEHLERHAFT[fehler.nr]), fehler.nr

    # Kein Befund darf zwei verschiedenen Fehlern zugeordnet werden
    for b in befunde:
        assert len(fp.fehler_zu_befund(b)) <= 1, kurzform(b)
    rest = [b for b in befunde if not fp.fehler_zu_befund(b)]
    print("Nicht zugeordnet:", ", ".join(kurzform(b) for b in rest))
    assert Counter((b.check_id, b.seite) for b in rest) == ERWARTET_NICHT_ZUGEORDNET


# =============================================================================
# (b) Gegenprobe auf der fehlerfreien TB
# =============================================================================
def test_b_gegenprobe_sauber_findet_nichts():
    befunde = befunde_aus_bericht(BERICHT_SAUBER)
    assert len(befunde) == 6           # 0 Fehler + 6 Warnungen
    abgleich = fp.gleiche_ab(befunde)
    print("\n(b) Zuordnung – Gegenprobe (fehlerfreie TB)")
    print(tabelle(abgleich))
    gefunden = {f.nr: [kurzform(b) for b in t] for f, t in abgleich if t}
    assert not gefunden, f"Falschzuordnung in der Gegenprobe: {gefunden}"


# =============================================================================
# (c) Robustheit gegen umformulierte Befundtexte
# =============================================================================
# Je Fehler zwei plausible Umformulierungen: andere Wortwahl, andere
# Zahlenschreibweise (Tausenderpunkt, Dezimalpunkt, „%“ ohne Leerzeichen,
# „Prozent“), Seitenangabe ±1 oder Seite der Gegenstelle.
UMFORMULIERUNGEN = [
    ("F01", "L-03", 89, "Widerspruch „Monatsbeitrag Männer, Alter 50“: Anhang 3 nennt "
     "„653,33 EUR“, die Nachrechnung mit A_50/a_50 aus Anlage 3.1.1 ergibt dagegen "
     "„635,33 EUR“ – vermutlich ein Zahlendreher."),
    ("F01", "V-07", 90, "Anhang 3 (Beitragsraten), Eintrittsalter 50, Männer: Die Tabelle "
     "zeigt 653.33 €, laut Referenzdaten wären es 635.33 €."),
    ("F02", "L-05", 79, "Formel „σ = 5,0 %“: In der Zuschlagstabelle steht beim "
     "Sicherheitszuschlag durchgehend 4,5% – das passt nicht zur Festsetzung in Gleichung (43)."),
    ("F02", "L-03", 27, "Widerspruch „Sicherheitszuschlag“: Abschnitt 2.4.1 nennt "
     "„mindestens 5 % gemäß § 7 KVAV“, Anlage 2.4 dagegen „4,5 Prozent“ – der "
     "Tabellenwert liegt unter dem gesetzlichen Minimum."),
    ("F03", "L-04", 16, "Normzitat „§4 VAG“ passt nicht zum Sachverhalt – einschlägig wäre "
     "§ 4 KVAV. (Der Höchstrechnungszins der PKV steht in der Kalkulationsverordnung.)"),
    ("F03", "L-04", 15, "Für den Höchstrechnungszins wird das VAG zitiert; richtig wäre "
     "§ 4 KVAV, da der Zins in der Krankenversicherungsaufsichtsverordnung geregelt ist."),
    ("F04", "L-03", 45, "Abschnitt 5.2 verweist bei den gemittelten Barwerten auf einen "
     "nicht existierenden Abschnitt („Abschnitt ??“) statt auf Anlage 5.2."),
    ("F04", "L-05", 44, "Der Querverweis bei den gemittelten Barwerten ist nicht aufgelöst – "
     "statt eines Verweisziels steht nur ein Platzhalter im Satz."),
    ("F05a", "L-01", 43, "Tippfehler: „Alterungsrückstelung“ – es fehlt ein „l“ "
     "(korrekt: Alterungsrückstellung)."),
    ("F05a", "L-01", 45, "Schreibfehler im ersten Satz von Abschnitt 5.1: "
     "„Alterungsrueckstelung“ statt „Alterungsrückstellung“."),
    ("F05b", "L-01", 35, "Rechtschreibfehler „Äquivalenzprinizip“ – gemeint ist "
     "„Äquivalenzprinzip“ (überzähliges „i“)."),
    ("F05b", "L-01", 36, "Falsch geschrieben: Aequivalenzprinizip → Äquivalenzprinzip."),
    ("F05c", "L-01", 11, "„Krankheitskostenvollversichrung“ ist falsch geschrieben "
     "(richtig: „Krankheitskostenvollversicherung“), Abschnitt 1.1."),
    ("F05c", "L-01", 10, "Rechtschreibung: Im Feld „Versicherungsform“ fehlt ein Buchstabe "
     "– „Krankheitskostenvollversichrung“."),
    ("F06", "V-04", 20, "Das Formelzeichen „DQ_x“ wird in Abschnitt 2.2.3, 3.1 und "
     "Anlage 2.2 benutzt, fehlt aber im Symbolverzeichnis."),
    ("F06", "L-03", 34, "Das Symbol DQx ist nirgends definiert (kein Eintrag im Glossar), "
     "obwohl es in den Rekursionsformeln vorkommt."),
    ("F07", "V-08", 73, "Parameter „G^M“ hat zwei verschiedene Werte: 1.910,0070 EUR im "
     "Einleitungstext, 1.901,0070 EUR in Gleichung (42)."),
    ("F07", "L-05", 73, "Formel „G^M = 1901,0070 EUR p. a. (42)“: Im Fließtext darüber steht "
     "für den Grundkopfschaden der Männer ein anderer Wert – offenbar Ziffern vertauscht."),
    ("F08", "V-05", 62, "Ausscheideordnung Männer, x = 50: Die Summe (q+w)_x ist mit "
     "0,037271 angegeben, q_50 + w_50 ergibt jedoch 0,036271."),
    ("F08", "V-13", 61, "Anlage 2.2 (Männer), Alter 50, Spalte (q+w)x: PDF 0.037271 vs. "
     "Datenbank 0.036271."),
    ("F09", "L-03", 60, "Widerspruch „Rechnungszins Frauen“: Anlage 2.1 nennt „2,2 %“, die "
     "Ausscheideordnung Frauen (Tabelle 2) ist dagegen mit „2,0 %“ überschrieben."),
    ("F09", "V-05", 64, "Die Barwerte der Frauen sind erkennbar mit 2,0 % gerechnet, in der "
     "Zinsübersicht steht für Frauen aber 2,2 Prozent."),
    ("F10", "V-03", 3, "Inhaltsverzeichnis: Der Eintrag „Anlage 3.1: Grundwerte der "
     "Versicherungstechnik“ weicht von der Überschrift im Dokument ab."),
    ("F10", "V-03", 81, "Die Überschrift von Anlage 3.1 lautet anders als im "
     "Inhaltsverzeichnis (IHV) angegeben."),
    ("F11", "L-02", 92, "„P_43 (Jahresnettobeitrag, Schritt 3)“: Das Dokument behauptet "
     "4.676,48, die Formel G_M * A_43 / a_43 ergibt mit den angegebenen Eingaben aber 4667,48."),
    ("F11", "L-02", 91, "Beispielrechnung Anhang 5: 1901,0070 · 44,1833 / 17,9953 = "
     "4667,48 EUR, abgedruckt sind 4676,48 EUR."),
    ("F12", "L-05", 44, "Formel „V_x(b) = G·A_x − [12·(1−(σ+Ω_x))·b + 𝛾_x]·a_x“: γ_x wird in "
     "der Klammer addiert, laut Legende und Gl. (31) aber subtrahiert."),
    ("F12", "L-03", 92, "Widerspruch „Zillmerprämie in der Rückstellungsformel“: Abschnitt "
     "5.1 nennt „+ γx“, Anhang 5, Schritt 4 dagegen „− γx“ – das Pluszeichen in "
     "Gleichung (30) passt nicht zur Beispielrechnung."),
    ("F13", "L-06", 75, "Grafik widerspricht den Tabellenwerten – Kurve „k_x Frauen“ weicht "
     "selbst von der am besten passenden Spalte (Anlage 2.3.3, Spalte „kxFrauen“ (Nr. 3)) "
     "im Median um 48 % ab (x=40: Grafik ≈1,5, Tabelle 0,9971)."),
    ("F13", "L-06", 76, "In der Profilgrafik liegt die Frauen-Kurve etwa um den Faktor 1,5 "
     "über den Tabellenwerten k_x."),
]


def test_c_umformulierungen_werden_richtig_zugeordnet():
    fehlerliste = fp.lade_fehlerprotokoll()
    assert Counter(nr for nr, *_ in UMFORMULIERUNGEN) == Counter(
        {nr: 2 for nr in ALLE_NUMMERN})
    print("\n(c) Umformulierte Befundtexte")
    falsch = []
    for nr, check_id, seite, text in UMFORMULIERUNGEN:
        treffer = [f.nr for f in fp.fehler_zu_befund(befund(check_id, text, seite),
                                                      fehlerliste)]
        ok = treffer == [nr]
        print(f"  {'ok  ' if ok else 'FALSCH'} {nr:<5} {check_id} S.{seite:<3} -> "
              f"{treffer or '–'}")
        if not ok:
            falsch.append((nr, check_id, seite, treffer))
    assert not falsch, falsch


def test_c_ergaenzende_muster_ohne_zahlenwert():
    """Jede Muster-Alternative wird mindestens einmal benutzt – auch die
    ergänzenden Muster für Live-Antworten ganz ohne Fehlwert."""
    faelle = [
        ("F01", "V-06", 89, "Anhang 3, Männer, Alter 50: Beitragsrate wirkt wie ein "
         "Zahlendreher (Rückgang zum Folgealter)."),
        ("F02", "L-05", 79, "Formel „σ = 5,0 % (43)“: Die Tabelle darunter weist für den "
         "Sicherheitszuschlag einen niedrigeren Wert aus."),
        ("F03", "L-04", 16, "Zitiert werden müsste § 4 KVAV statt des allgemeinen VAG – "
         "der Höchstrechnungszins ist in der KVAV geregelt."),
    ]
    benutzt = {nr: set() for nr in fp._REGELN}
    for nr, check_id, seite, text in [*faelle, *UMFORMULIERUNGEN]:
        b = befund(check_id, text, seite)
        assert [f.nr for f in fp.fehler_zu_befund(b)] == [nr], (nr, text[:50])
        regel, norm = fp._REGELN[nr], fp._normiere(text)
        benutzt[nr] |= {i for i, alt in enumerate(regel.muster)
                        if all(rx.search(norm) for rx in alt)}
    for nr, regel in fp._REGELN.items():
        assert benutzt[nr] == set(range(len(regel.muster))), (nr, benutzt[nr])


# =============================================================================
# (d) Unbeteiligte, ähnlich klingende Befunde
# =============================================================================
NEGATIVBEISPIELE = [
    ("L-02", 92, "„Monatlicher Bruttobeitrag b43“: Das Dokument behauptet 529,01, die "
     "Formel (GM*A43 + gamma43*a43)/(12*(1-0.057)*a43-3.5) ergibt aber 529,90."),
    ("L-06", 75, "Grafik widerspricht den Tabellenwerten – Kurve „Männer“ weicht selbst "
     "von der am besten passenden Spalte (Anlage 2.3.3, kx Frauen, Spalte „k“ (Nr. 3)) "
     "im Median um 25 % ab."),
    ("L-06", 78, "Grafik widerspricht den Tabellenwerten – Kurve „Frauen“ (Kopfschäden "
     "K_x, Abbildung 2) weicht im Median um 30 % ab."),
    ("L-04", 16, "Normzitat „§ 4 KVAV“ ist fraglich: Der Höchstrechnungszins könnte auch "
     "an anderer Stelle geregelt sein."),
    ("L-04", 30, "Normzitat „§ 154 VAG“ ist fraglich: eher § 152 VAG (Basistarif)."),
    ("L-04", 27, "Normzitat „§ 7 KVAV“ ist fraglich: Der Mindest-Sicherheitszuschlag von "
     "5 % wird dort nicht wörtlich genannt."),
    ("V-06", 90, "Anhang 3, Spalte b_x (Spalte 5): Wert fällt von Alter 64 (814,70) auf "
     "Alter 65 (813,43). Kann systembedingt sein, sollte aber geprüft werden."),
    ("L-01", 44, "Rechtschreibfehler „Beitragsanpasung“ (richtig: „Beitragsanpassung“)."),
    ("L-03", 60, "Widerspruch „Rechnungszins Männer“: Anlage 2.1 nennt „2,7 %“, "
     "Anlage 3.1 dagegen „2,75 %“."),
    ("V-08", 73, "Widersprüchliche Werte für „GF“: Grundkopfschaden Frauen 2898,3813 EUR "
     "(Seite 73) und 2898,381 EUR (Seite 76) – abweichende Rundung."),
    ("V-03", 3, "Seitenzahl-Abweichung bei Anlage 2.4: IHV nennt Seite 78, die Überschrift "
     "steht auf Seite 79."),
    ("V-04", 8, "Symbol „Ω“ wird verwendet, ist im Symbolverzeichnis aber nicht erklärt."),
    ("V-05", 62, "Anlage 2.2 – Männer, Alter 50: (q+w)_x = 0,036271 bestätigt."),
    ("L-05", 44, "Formel (31): Vorzeichen von α_x ist ohne Legende nicht eindeutig."),
    ("L-02", 92, "„Jahresnettobeitrag P43“: Ergebnis 4667,48 weicht leicht vom "
     "nachgerechneten Wert 4667,4823 ab – kann an der Rundungskaskade liegen."),
    ("L-03", 35, "Widerspruch „Formel für den Jahresnettobeitrag Px“: Abschnitt 3.2 nennt "
     "„Px = G · Ax“, Anhang 5 dagegen „P43 = 4676,48 EUR“ – keine Division durch ax."),
]


def test_d_unbeteiligte_befunde_werden_nicht_zugeordnet():
    fehlerliste = fp.lade_fehlerprotokoll()
    print("\n(d) Negativbeispiele")
    falsch = []
    for check_id, seite, text in NEGATIVBEISPIELE:
        treffer = [f.nr for f in fp.fehler_zu_befund(befund(check_id, text, seite),
                                                      fehlerliste)]
        print(f"  {'ok  ' if not treffer else 'FALSCH'} {check_id} S.{seite:<3} -> "
              f"{treffer or '–'}")
        if treffer:
            falsch.append((check_id, seite, text[:60], treffer))
    assert not falsch, falsch


def test_d_seite_unbekannt_und_seitenfenster():
    fehlerliste = fp.lade_fehlerprotokoll()
    nr = lambda b: [f.nr for f in fp.fehler_zu_befund(b, fehlerliste)]
    # Eindeutiger Fehlwert genügt, wenn die Seite fehlt …
    assert nr(befund("L-02", "Das Dokument behauptet 4676,48.", None)) == ["F11"]
    # … nicht aber ein bloßes Fehlbild ohne Fehlwert (F12, F13 brauchen die Seite)
    assert nr(befund("L-05", "Vorzeichen von γ_x in Gl. (30) falsch.", None)) == []
    assert nr(befund("L-05", "Vorzeichen von γ_x in Gl. (30) falsch.", 44)) == ["F12"]
    # Fehlwert auf weit entfernter Seite wird nicht zugeordnet
    assert nr(befund("L-03", "Anhang 5 nennt 4676,48 EUR.", 35)) == []
    # Fehlender Glossareintrag ist seitenunabhängig
    assert nr(befund("V-04", "Symbol „DQx“ ist im Symbolverzeichnis nicht erklärt.", 63)) \
        == ["F06"]


# =============================================================================
# (e) Seiten und Markierungen in den PDFs verifizieren (PyMuPDF)
# =============================================================================
def _seitentexte(pfad: Path) -> list[str]:
    import pymupdf
    with pymupdf.open(pfad) as dok:
        return [re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s.get_text())
                       .replace("-\n", "")) for s in dok]


def test_e_seiten_und_markierungen_im_pdf():
    import pymupdf
    fehlerliste = fp.lade_fehlerprotokoll()
    with pymupdf.open(PDF_FEHLERHAFT) as fehlerhaft, pymupdf.open(PDF_SAUBER) as sauber:
        assert fehlerhaft.page_count == sauber.page_count == 93
        for f in fehlerliste:
            seite = f.seiten[0] - 1
            if f.markierung:
                assert fehlerhaft[seite].search_for(f.markierung), f"{f.nr}: nicht im PDF"
                assert not sauber[seite].search_for(f.markierung), f"{f.nr}: auch sauber"
            if f.markierung_korrekt:
                assert sauber[seite].search_for(f.markierung_korrekt), f.nr
    # Symbolverzeichnis (F06): DQ-Eintrag fehlt nur in der fehlerhaften TB
    assert "Symbolverzeichnis" in _seitentexte(PDF_FEHLERHAFT)[7]


def test_e_kernmuster_stehen_nur_in_der_fehlerhaften_tb():
    """Die eindeutigen Fehlwerte (Kernmuster) stehen auf der Fundstelle der
    fehlerhaften TB und nirgends in der fehlerfreien TB."""
    fehlerhaft, sauber = _seitentexte(PDF_FEHLERHAFT), _seitentexte(PDF_SAUBER)
    geprueft = []
    for nr, regel in fp._REGELN.items():
        if not regel.kern_eindeutig or regel.seitenunabhaengig:
            continue
        kern = regel.muster[0]
        greift = lambda text: all(rx.search(text) for rx in kern)
        assert greift(fehlerhaft[regel.fundstellen[0] - 1]), nr
        assert not any(greift(t) for t in sauber), nr
        geprueft.append(nr)
    assert len(geprueft) == 12          # alle außer F06, F12, F13


# =============================================================================
# (f) Echte Live-Läufe mit claude-sonnet-5-5
# =============================================================================
# Erwartete Zuordnung nach manueller Durchsicht aller 33 Live-Befunde. Nicht
# zugeordnet bleiben: V-06 S.90 (systembedingt, auch in der fehlerfreien TB),
# L-03 S.61 (Begründung der Stornomarge – auch in der fehlerfreien TB),
# L-04 S.24 und L-04 S.30 (Absatzangaben fraglich).
ERWARTET_LIVE_FEHLERHAFT = {
    "F01": [("V-06", 89), ("V-07", 89)],
    "F02": [("V-09", 79), ("V-09", 79), ("L-03", 79), ("L-05", 79)],
    "F03": [("V-09", 16), ("L-04", 16)],
    "F04": [("V-01", 45)],
    "F05a": [("L-01", 44)],
    "F05b": [("L-01", 35)],
    "F05c": [("L-01", 11)],
    "F06": [("V-04", 7)],
    "F07": [("V-08", 73), ("L-03", 73), ("L-05", 73)],
    "F08": [("V-05", 62), ("V-07", 62), ("V-13", 62)],
    "F09": [("V-05", 60), ("L-03", 60)],
    "F10": [("V-03", 3)],
    "F11": [("L-02", 92), ("L-03", 92), ("L-03", 92), ("L-05", 92)],
    "F12": [("L-03", 44), ("L-05", 44)],
    "F13": [("L-06", 75)],
}
ERWARTET_LIVE_NICHT_ZUGEORDNET = Counter([("V-06", 90), ("L-03", 61), ("L-04", 24),
                                          ("L-04", 30)])


def test_f_live_lauf_fehlerhaft_13_von_13():
    befunde = befunde_aus_live_lauf(LIVE_FEHLERHAFT)
    assert len(befunde) == 33          # 22 Fehler + 11 Warnungen
    abgleich = fp.gleiche_ab(befunde)
    print("\n(f) Zuordnung – Live-Lauf claude-sonnet-5-5, fehlerhafte TB")
    print(tabelle(abgleich))
    assert len({f.gruppe for f, treffer in abgleich if treffer}) == 13
    for fehler, treffer in abgleich:
        assert sorted((b.check_id, b.seite) for b in treffer) \
            == sorted(ERWARTET_LIVE_FEHLERHAFT[fehler.nr]), fehler.nr
    for b in befunde:
        assert len(fp.fehler_zu_befund(b)) <= 1, kurzform(b)
    rest = [b for b in befunde if not fp.fehler_zu_befund(b)]
    print("Nicht zugeordnet:", ", ".join(kurzform(b) for b in rest))
    assert Counter((b.check_id, b.seite) for b in rest) == ERWARTET_LIVE_NICHT_ZUGEORDNET


def test_f_live_lauf_fehlerfrei_findet_nichts():
    befunde = befunde_aus_live_lauf(LIVE_SAUBER)
    assert len(befunde) == 11          # 0 Fehler + 11 Warnungen
    abgleich = fp.gleiche_ab(befunde)
    print("\n(f) Zuordnung – Live-Lauf claude-sonnet-5-5, fehlerfreie TB")
    print(tabelle(abgleich))
    gefunden = {f.nr: [kurzform(b) for b in t] for f, t in abgleich if t}
    assert not gefunden, f"Falschzuordnung in der Gegenprobe: {gefunden}"


# =============================================================================
# Schnittstelle zu engine.py (nur statisch, ohne Import-Nebenwirkungen)
# =============================================================================
def test_schnittstelle_befundgui_aus_engine():
    engine = GUI_ORDNER / "engine.py"
    if not engine.exists():
        ueberspringen("engine.py noch nicht vorhanden")
    baum = ast.parse(engine.read_text(encoding="utf-8"))
    klasse = next((k for k in baum.body
                   if isinstance(k, ast.ClassDef) and k.name == "BefundGUI"), None)
    assert klasse is not None, "BefundGUI fehlt in engine.py"
    felder = {k.target.id for k in klasse.body
              if isinstance(k, ast.AnnAssign) and isinstance(k.target, ast.Name)}
    assert {"check_id", "beschreibung", "seite", "schwere"} <= felder


def main() -> int:
    """Ausführung ohne pytest: alle Tests nacheinander, Tabellen werden
    gedruckt; Exit-Code 1, sobald ein Test fehlschlägt."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fehlgeschlagen = 0
    for name, funktion in list(globals().items()):
        if not (name.startswith("test_") and callable(funktion)):
            continue
        try:
            funktion()
            print(f"BESTANDEN     {name}")
        except KeyboardInterrupt:
            raise
        except BaseException as fehler:  # noqa: BLE001  (auch pytest-Skip)
            if isinstance(fehler, _Uebersprungen) or type(fehler).__name__ == "Skipped":
                print(f"ÜBERSPRUNGEN  {name}: {fehler}")
                continue
            fehlgeschlagen += 1
            print(f"FEHLER        {name}: {type(fehler).__name__}: {fehler}")
            traceback.print_exc()
    print("\nAlle Tests bestanden." if not fehlgeschlagen
          else f"\n{fehlgeschlagen} Test(s) fehlgeschlagen.")
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    sys.exit(main())
