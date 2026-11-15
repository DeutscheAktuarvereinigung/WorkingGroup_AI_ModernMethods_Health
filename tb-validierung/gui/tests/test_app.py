"""Oberflächentests der Streamlit-App (app.py) mit streamlit.testing.v1.AppTest.

Aufruf:   python tests/test_app.py      (aus dem Ordner gui/)
          (pytest funktioniert ebenfalls, ist aber nicht nötig)

Alle Prüfläufe laufen im Notfallmodus (gespeicherte Antworten des
Nachweis-Laufs) mit Pause 0 – ohne Netzwerk: engine._neuer_client ist durch
eine Sperre ersetzt, die jeden Versuch, einen API-Client zu erzeugen, als
Testfehler meldet. Die Umgebungsvariable des API-Schlüssels wird weder
gelesen noch verändert (für den Live-Fall ohne Schlüssel wird nur die
Abfrage engine.api_schluessel_vorhanden durch „False“ ersetzt).

Jeder Test beginnt mit „?neu=1“ (leerer Vorführstand); nur der
Neuladen-Test baut bewusst auf dem Stand einer vorigen Sitzung auf.

Geprüft wird:
 1. Die App startet ohne Ausnahme im Prüfkatalog (19 Checks, alle gewählt,
    beide Kategorie-Checkboxen gesetzt, keine Schnellauswahl-Knöpfe, keine
    Erklärtexte unter den Checks); Titel „TB-Validierung“ + „Live-Demo“;
    der Notfallmodus ist nur in der Seitenleiste zu erkennen.
 2. Kategorie-Checkbox „Sprachmodell“ aus + „Prüfung starten“ liefert genau
    die 13 Regel-Checks; der Haken der Kategorie folgt Einzeländerungen.
 3. Kompletter Lauf auf der fehlerhaften TB: 21 Fehler, 11 Warnungen, jeder
    Check-Status wie im Referenz-Prüfbericht; grüne Kachel „Checks ohne
    Befund“; keine Modellnamen auf der Leinwand; angezeigte Dauer = sichtbare
    Dauer; „Befunde ansehen“ steht nach der Ablaufliste.
 4. Befundansicht: alle 32 Befunde lassen sich mit den Pfeilen (ohne Wörter)
    durchblättern, jeweils mit markierter Passage, mit Gegenüberstellung zwei
    Bilder; Grafik-Befunde nebeneinander; Gegenstellen in der Beschriftung;
    Befundtexte aufbereitet (fundstellen.anzeige_text); Fundstellen-Seite
    (V-04: S. 8); Typografie der Befundkarte in beiden Ansichten gleich.
 5. Abgleich: „13 von 13“, Sprung „Zeigen“ in die Befundansicht, Befunde ohne
    Bezug zum Fehlerprotokoll werden gekennzeichnet.
 6. Dokumentwechsel auf die Gegenprobe: 0 Fehler, 6 Warnungen, grüne Kachel.
 7. Live-Modus ohne API-Schlüssel: Sprachmodell-Checks „übersprungen“ mit
    sichtbarem Grund; Schritt 3/4 und Gegenprobe sagen „unvollständig“ statt
    „bestanden“.
 8. Fehlgeschlagener Check: fester deutscher Satz auf der Leinwand, der
    technische Grund nur in der Seitenleiste.
 9. Fehler im Prüflauf: verständliche Meldung ohne technischen Grund.
10. Während eines Laufs sind Umschalter, Prozesskette und Regler gesperrt;
    ein abgebrochener Lauf wird gemeldet (auch nach dem Neuladen).
11. Neuladen der Seite: Einstellungen (Notfallschalter) und Ergebnisse
    bleiben erhalten; „?neu=1“ beginnt von vorn.
12. Standardwerte: Pause 0,5 s, Notfall-Tempo „wie live“, 24 parallele Anfragen.
13. Stylesheet: feste Grundschrift (16 px × Faktor, nicht an vw/vh gekoppelt),
    Nebenzeilen mindestens .85rem, keine abgerundeten Ecken außer bei den
    kreisrunden Status-Symbolen, Roboto als Schrift.
14. Piktogramme: eine Familie (Material Symbols), keine Unicode-Ersatzzeichen;
    Prozesskette ohne Nummern mit Piktogrammen.
15. config.toml: baseRadius „none“, statische Dateien an, Roboto lokal.
16. Notebook, Cache, Prüfberichte, PDFs und Fehlerprotokoll bleiben unverändert.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import re
import sys
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True          # keine __pycache__-Ordner im Repo
GUI_ORDNER = Path(__file__).resolve().parents[1]
if str(GUI_ORDNER) not in sys.path:
    sys.path.insert(0, str(GUI_ORDNER))

from streamlit.runtime.scriptrunner_utils.exceptions import StopException  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

import engine  # noqa: E402   (dasselbe Modulobjekt, das app.py importiert)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

APP_PFAD = GUI_ORDNER / "app.py"
TIMEOUT_S = 240

# Dateien, die niemals verändert werden dürfen
GESCHUETZT = [engine.NOTEBOOK_PFAD, engine.REFERENZ_CACHE_PFAD,
              *engine.REFERENZBERICHTE.values(), *engine.DOKUMENTE.values(),
              engine.FEHLERPROTOKOLL_PFAD]

# --- Netzwerksperre: kein Anthropic-Client im Test -------------------------
CLIENT_VERSUCHE: list[str] = []


def _kein_netz():
    CLIENT_VERSUCHE.append(time.strftime("%H:%M:%S"))
    raise AssertionError("Im Test darf kein API-Client erzeugt werden (Netzwerk gesperrt).")


engine._neuer_client = _kein_netz
ORIGINAL_LAUFE = engine.Pruefstrecke.laufe


class _Ersetzt:
    """Ersetzt Attribute eines Objekts vorübergehend (wie unittest.mock.patch)."""

    def __init__(self, ziel, **neu):
        self.ziel, self.neu, self.alt = ziel, neu, {}

    def __enter__(self):
        for name, wert in self.neu.items():
            self.alt[name] = getattr(self.ziel, name)
            setattr(self.ziel, name, wert)
        return self

    def __exit__(self, *_):
        for name, wert in self.alt.items():
            setattr(self.ziel, name, wert)


# =============================================================================
# Hilfsfunktionen
# =============================================================================
def neue_app(neu: bool = True, **zustand) -> AppTest:
    """Frische Sitzung im Notfallmodus, ohne Pausen; erster Aufbau.
    neu=True: mit „?neu=1“ (leerer Vorführstand, unabhängig von vorigen Tests)."""
    at = AppTest.from_file(str(APP_PFAD), default_timeout=TIMEOUT_S)
    if neu:
        at.query_params["neu"] = "1"
    vorgaben = {"notfall": True, "pause_s": 0.0, "notfall_verzoegerung_s": 0.0}
    vorgaben.update(zustand)
    for schluessel, wert in vorgaben.items():
        if wert is not None:
            at.session_state[schluessel] = wert
    at.run()
    ohne_fehler(at, "Start")
    return at


def ohne_fehler(at: AppTest, schritt: str) -> None:
    """Weder Ausnahme noch Fehlermeldung auf der Leinwand."""
    assert not at.exception, f"{schritt}: Ausnahme {[e.value for e in at.exception]}"
    assert not at.error, f"{schritt}: Fehlermeldung {[e.value for e in at.error]}"


def html_haupt(at: AppTest) -> str:
    """Alle HTML-Bausteine der Hauptfläche (ohne Seitenleiste) als ein Text."""
    return "\n".join(h.proto.body for h in at.main.get("html"))


def text_seitenleiste(at: AppTest) -> str:
    teile = [str(m.value) for m in at.sidebar.get("markdown")]
    teile += [str(c.value) for c in at.sidebar.get("caption")]
    teile += [str(c.value) for c in at.sidebar.get("code")]
    return "\n".join(teile)


def klicke(at: AppTest, schluessel: str) -> AppTest:
    at.button(key=schluessel).click().run()
    ohne_fehler(at, f"Klick auf {schluessel}")
    return at


def lauf(at: AppTest, dokument: str) -> dict:
    return at.session_state["laeufe"][dokument]


def bilder(at: AppTest) -> int:
    return len(at.main.get("imgs"))


def hat_block(at: AppTest, schluessel: str) -> bool:
    """Gibt es auf der Hauptfläche einen Behälter mit diesem Schlüssel?"""
    def suche(knoten) -> bool:
        proto = getattr(knoten, "proto", None)
        if proto is not None and str(getattr(proto, "id", "")).endswith(f"-{schluessel}"):
            return True
        return any(suche(k) for k in getattr(knoten, "children", {}).values())
    return suche(at.main)


def hash_dateien() -> dict:
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in GESCHUETZT}


def haken(at: AppTest, schluessel: str, an: bool) -> AppTest:
    """Checkbox setzen (z. B. Kategorie-Checkbox) und neu aufbauen."""
    at.checkbox(key=schluessel).set_value(an).run()
    ohne_fehler(at, f"Checkbox {schluessel} = {an}")
    return at


def voller_lauf(dokument: str = "fehlerhaft") -> AppTest:
    """Neue Sitzung (alle Checks gewählt), ggf. Dokument wechseln, ausführen."""
    at = neue_app()
    if dokument != "fehlerhaft":
        at.button_group(key="dok_wahl").set_value(dokument).run()
        ohne_fehler(at, "Dokumentwechsel")
    klicke(at, "start")
    return at


def stylesheet(at: AppTest) -> str:
    """Das Stylesheet der App (ein reines <style>-Element legt Streamlit
    außerhalb der Hauptfläche ab)."""
    alles = "\n".join(h.proto.body for h in at.get("html"))
    return alles[alles.index("<style>\n:root"):alles.index("</style>", alles.index("<style>\n:root"))]


def position(at: AppTest, merkmal: str) -> int:
    """Position eines Elements der obersten Ebene der Hauptfläche: Behälter
    mit Schlüssel „merkmal“ oder HTML-Baustein, der „merkmal“ enthält."""
    for i, kind in enumerate(at.main.children.values()):
        proto = getattr(kind, "proto", None)
        if str(getattr(proto, "id", "")).endswith(f"-{merkmal}"):
            return i
        if merkmal in str(getattr(proto, "body", "")):
            return i
    raise AssertionError(f"{merkmal} nicht auf der Hauptfläche")


def befund_text_klassen(html: str) -> set:
    return set(re.findall(r"<div class='(befund-text[^']*)'[ >]", html))


def laufe_mit_abbruch(nach_ereignissen: int):
    """Ersatz für Pruefstrecke.laufe: liefert einige echte Ereignisse und
    beendet dann den Skriptlauf so, wie Streamlit es bei einem Neuladen oder
    einer Bedienung während des Laufs tut (StopException)."""
    def laufe(self, *args, **kwargs):
        gen = ORIGINAL_LAUFE(self, *args, **kwargs)
        try:
            for i, ereignis in enumerate(gen):
                if i >= nach_ereignissen:
                    raise StopException()
                yield ereignis
        finally:
            gen.close()
    return laufe


# =============================================================================
# Tests
# =============================================================================
def test_start_ohne_fehler():
    at = neue_app()
    assert at.session_state["schritt"] == 1
    assert at.session_state["dok_wahl"] == "fehlerhaft"
    checks = [c for c in at.checkbox if (c.key or "").startswith("cb_")]
    assert len(checks) == 19 and all(c.value for c in checks), "19 Checks, alle gewählt"
    # Kategorie-Checkboxen statt Schnellauswahl-Knöpfen
    assert at.checkbox(key="kat_regeln").value and at.checkbox(key="kat_ki").value
    knoepfe = {b.key for b in at.button}
    assert not knoepfe & {"alle", "keine", "nur_regeln", "nur_ki"}, knoepfe
    assert at.button(key="start").label == "Prüfung starten (19 von 19 Checks)"
    assert at.button(key="start").proto.icon == ":material/play_arrow:"
    haupt = html_haupt(at)
    # Titel: „TB-Validierung“ fett + „Live-Demo“ normal, ohne Balken
    assert ("<span class='kopf-titel'>TB-Validierung</span>"
            "<span class='kopf-zusatz'>Live-Demo</span>") in haupt
    assert "kopf-balken" not in haupt
    # Keine Erklärtexte unter den Checks – die Erklärung steht nur im Tooltip
    assert "class='erklaerung'" not in haupt
    v01 = at.checkbox(key="cb_V-01")
    assert v01.help and "Leere" in v01.help, v01.help
    # Auch die Kategorie-Köpfe ohne Untertitel – Erklärung nur im Tooltip
    assert "Python prüft nach festen Regeln" not in haupt
    assert "liest mit" not in haupt and "block-unter" not in haupt
    assert "Python prüft" in at.checkbox(key="kat_regeln").help
    assert "Sprachmodell" in at.checkbox(key="kat_ki").help
    # Prozesskette: ohne Nummern, mit Piktogramm; ohne Ergebnis sind 2–4 gesperrt
    assert [at.button(key=f"schritt_{n}").label for n in (1, 2, 3, 4)] == \
        ["Prüfkatalog", "Prüflauf", "Befunde", "Abgleich"]
    assert all(at.button(key=f"schritt_{n}").proto.icon.startswith(":material/")
               for n in (1, 2, 3, 4))
    assert [at.button(key=f"schritt_{n}").disabled for n in (1, 2, 3, 4)] == \
        [False, True, True, True]
    # Notfallmodus: Hinweis nur in der Seitenleiste, nicht auf der Hauptfläche
    seitenleiste = " ".join(c.value for c in at.sidebar.get("caption"))
    assert "Notfallmodus aktiv" in seitenleiste
    haupt = html_haupt(at) + " ".join(str(m.value) for m in at.main.get("markdown"))
    assert not re.search(r"Notfall|gespeicherte Antworten|claude", haupt, re.I)
    # Seitenleiste wird beim ersten Aufbau eingeklappt (localStorage-Skript)
    assert "stSidebarCollapsed-" in haupt and "aria-expanded" in haupt
    # Beide Kategorien ab -> nichts gewählt -> Start gesperrt
    haken(at, "kat_regeln", False)
    haken(at, "kat_ki", False)
    assert at.button(key="start").disabled
    assert at.button(key="start").label == "Prüfung starten (0 von 19 Checks)"
    # Das Einklapp-Skript läuft nur beim ersten Aufbau der Sitzung
    assert "stSidebarCollapsed-" not in html_haupt(at)
    print("  Start: 19 Checks, Kategorie-Checkboxen, Prozesskette ohne Nummern, "
          "Notfallhinweis nur in der Seitenleiste")


def test_kategorie_checkboxen():
    at = neue_app()
    # Kategorie „Sprachmodell“ ab: nur die 13 festen Regeln bleiben gewählt
    haken(at, "kat_ki", False)
    assert at.button(key="start").label == "Prüfung starten (13 von 19 Checks)"
    assert not any(at.checkbox(key=f"cb_L-{i:02d}").value for i in range(1, 7))
    assert all(at.checkbox(key=f"cb_V-{i:02d}").value for i in range(1, 14))
    # Einzeländerungen spiegeln sich im Haken der Kategorie
    haken(at, "cb_V-01", False)
    assert not at.checkbox(key="kat_regeln").value, "nicht mehr alle Regeln gewählt"
    assert at.button(key="start").label == "Prüfung starten (12 von 19 Checks)"
    haken(at, "cb_V-01", True)
    assert at.checkbox(key="kat_regeln").value, "wieder alle Regeln gewählt"
    for i in range(1, 7):
        haken(at, f"cb_L-{i:02d}", True)
    assert at.checkbox(key="kat_ki").value, "alle Sprachmodell-Checks einzeln gewählt"
    haken(at, "kat_ki", False)
    klicke(at, "start")
    ergebnisse = lauf(at, "fehlerhaft")["ergebnisse"]
    assert [r.id for r in ergebnisse] == [f"V-{i:02d}" for i in range(1, 14)]
    assert all(r.methode == "deterministisch" for r in ergebnisse)
    assert at.session_state["schritt"] == 2
    # Nach Laufende sind Befunde und Abgleich freigeschaltet (Neuaufbau)
    assert not at.button(key="schritt_3").disabled and not at.button(key="schritt_4").disabled
    print(f"  Kategorie-Checkboxen: Sprachmodell ab -> {len(ergebnisse)} Ergebnisse "
          "(V-01 … V-13), Haken folgt Einzeländerungen")


def test_kompletter_lauf_fehlerhaft():
    at = neue_app(pause_s=0.2)
    klicke(at, "start")
    l = lauf(at, "fehlerhaft")
    assert len(l["ergebnisse"]) == 19
    assert (l["fehler"], l["warnungen"]) == (21, 11), (l["fehler"], l["warnungen"])
    referenz = {c["id"]: c["status"] for c in engine.lade_referenzbericht("fehlerhaft")["checks"]}
    abweichend = {r.id: (r.status, referenz.get(r.id)) for r in l["ergebnisse"]
                  if r.status != referenz.get(r.id)}
    assert not abweichend, f"Status weicht vom Referenzbericht ab: {abweichend}"
    haupt = html_haupt(at)
    assert haupt.count("<div class='zeile fertig'>") == 19, "Ablaufliste genau einmal, 19 Zeilen"
    assert "21</span>" in haupt and "11</span>" in haupt, "Ergebnis-Kacheln"
    # Grüne Kachel: Checks ohne Befund (statt „19 Checks in … s“)
    n_ok = sum(r.status == "BESTANDEN" for r in l["ergebnisse"])
    assert n_ok > 0
    assert (f"<div class='kachel ok'><span class='sym ok gross'><span class='ic' "
            f"aria-hidden='true'>check</span></span><span class='k-zahl'>{n_ok}</span>"
            f"<span class='k-text'>Checks ohne Befund</span></div>") in haupt
    assert "Checks in" not in haupt
    # „Befunde ansehen“ unten (nach der Ablaufliste), Pfeil statt Wort
    knopf = at.button(key="zu_befunden")
    assert knopf.label == "Befunde ansehen" and knopf.proto.icon == ":material/arrow_forward:"
    assert position(at, "weiterleiste") > position(at, "lauf-raster"), \
        "„Befunde ansehen“ steht nach der Ablaufliste"
    # Modellnamen (würden Live/Notfall unterscheiden) erscheinen nicht auf der Leinwand
    assert "claude" not in haupt.lower()
    # Angezeigte Dauer je Check = sichtbare Dauer (mindestens die Pause von 0,2 s)
    dauern = l["dauer_sichtbar"]
    assert set(dauern) == {r.id for r in l["ergebnisse"]}
    assert all(d >= 0.2 for d in dauern.values()), dauern
    assert "0,0 s" not in haupt, "keine reine Rechenzeit „0,0 s“ in der Ablaufliste"
    print("  Fehlerhafte TB: 19 Checks, 21 Fehler, 11 Warnungen – Status wie Referenzbericht")


def test_befundansicht():
    at = voller_lauf("fehlerhaft")
    klicke(at, "zu_befunden")
    assert at.session_state["schritt"] == 3
    befunde = [b for r in lauf(at, "fehlerhaft")["ergebnisse"] for b in r.befunde]
    assert len(befunde) == 32
    assert bilder(at) == 1, "markierte Passage"
    assert all(".png" in str(i.proto) for i in at.main.get("imgs")), "verlustfrei als PNG"
    # Navigation nur mit Pfeilen (Piktogramme), ohne „Zurück“/„Weiter“
    assert at.button(key="vorheriger").label == ":material/chevron_left:"
    assert at.button(key="naechster").label == ":material/chevron_right:"
    # Ohne Tooltip (läge nach einem Klick über der Prozesskette); Kürzel bleiben
    assert not at.button(key="vorheriger").help and not at.button(key="naechster").help
    assert at.button(key="naechster").proto.shortcut.lower() == "right"
    # V-01: Befundtext für die Leinwand aufbereitet (keine Formel-Bruchstücke)
    haupt = html_haupt(at)
    assert befunde[0].check_id == "V-01" and "ax+1/2" in befunde[0].beschreibung
    assert "Abschnitt ??" in haupt and "ax+1/2" not in haupt, "anzeige_text für V-01"
    assert "--bild-max" in haupt and "--liste-hoehe" in haupt, "Einpass-Skript"
    # Befundkarte: Kopfleiste mit Schwere, Check, Methode und Seite
    assert "<div class='befund-karte fehler'><div class='befund-kopf'>" in haupt
    assert "<span class='befund-seite'>" in haupt and ">description</span>Seite 45" in haupt
    # Warnfarbe der Listensymbole: spezifischer als die Grundregel (sonst rot)
    assert ("[data-testid='stMain'] .st-key-befundliste .st-key-befund_5 .stButton "
            "[data-testid='stIconMaterial']") in haupt, "Warnfarbe für V-06 (Befund 6)"
    klassen_ohne = befund_text_klassen(haupt)
    assert klassen_ohne == {"befund-text"}, klassen_ohne
    haken(at, "vergleich_umschalter", True)
    assert bilder(at) == 2, "Passage + fehlerfreie Vergleichsstelle"
    assert "Zum Vergleich: Fehlerfreie TB" in html_haupt(at)
    # Gleiche Typografie mit Gegenüberstellung (keine kleinere Schriftklasse)
    assert befund_text_klassen(html_haupt(at)) == klassen_ohne
    assert "kompakt" not in html_haupt(at)
    gesehen = set()
    # Alle Befunde durchblättern (mit Gegenüberstellung)
    for i in range(1, len(befunde)):
        klicke(at, "naechster")
        assert at.session_state["befund_idx"]["fehlerhaft"] == i
        assert bilder(at) == 2, f"Befund {i + 1}: Bilder fehlen"
        haupt = html_haupt(at)
        assert f"Befund {i + 1} von {len(befunde)}" in haupt
        b = befunde[i]
        if b.check_id == "V-04":
            # Fundstelle (Symbolverzeichnis S. 8) statt gemeldeter Seite 7
            assert b.seite == 7 and "Seite 8" in haupt, "V-04: Fundstellen-Seite"
            gesehen.add("V-04")
        if b.check_id == "L-06":
            # Grafik: Passage und Vergleich nebeneinander
            assert hat_block(at, "passagen_nebeneinander"), "L-06 nebeneinander"
            assert not hat_block(at, "passagen_vergleich")
            gesehen.add("L-06")
        elif hat_block(at, "passagen_nebeneinander"):
            raise AssertionError(f"Befund {i + 1} ({b.check_id}) ist keine Grafik")
        if b.check_id == "L-03" and b.seite == 44:
            # Gegenstelle auf S. 92 (Anhang 5, Schritt 4) im selben Bild
            assert "Seiten 44 und 92" in haupt, "L-03 S. 44: Gegenstelle S. 92"
            gesehen.add("Gegenstelle")
        # Gegenüberstellung: Typografie der Karte wie ohne (eine Schriftklasse)
        assert befund_text_klassen(haupt) == {"befund-text"}
        assert "kompakt" not in haupt
    assert gesehen == {"V-04", "L-06", "Gegenstelle"}, gesehen
    assert at.button(key="naechster").disabled, "letzter Befund"
    klicke(at, "vorheriger")
    assert at.session_state["befund_idx"]["fehlerhaft"] == len(befunde) - 2
    # Ohne Gegenüberstellung wieder ein Bild
    haken(at, "vergleich_umschalter", False)
    assert bilder(at) == 1
    assert befund_text_klassen(html_haupt(at)) == {"befund-text"}
    print(f"  Befundansicht: {len(befunde)} Befunde durchgeblättert, je 2 Bilder im Vergleich, "
          "Grafik nebeneinander, Gegenstelle S. 92")


def test_abgleich_13_von_13():
    at = voller_lauf("fehlerhaft")
    klicke(at, "schritt_4")
    haupt = html_haupt(at)
    assert "13 von 13</span>" in haupt and "dokumentierten Fehlern gefunden" in haupt
    assert "Befunde ohne Bezug zum Fehlerprotokoll (6)" in haupt
    assert haupt.count("nicht gefunden") == 0
    assert "übersprungen" not in haupt, "alle Checks liefen"
    # Sprung zum Befund von F07 (Grundkopfschaden doppelt)
    klicke(at, "zeige_F07")
    assert at.session_state["schritt"] == 3
    index = at.session_state["befund_idx"]["fehlerhaft"]
    befund = [b for r in lauf(at, "fehlerhaft")["ergebnisse"] for b in r.befunde][index]
    assert "1910" in befund.beschreibung and befund.seite == 73, befund
    assert "F07" in html_haupt(at), "Befundkarte nennt den Eintrag im Fehlerprotokoll"
    # Befund ohne Bezug wird in der Karte gekennzeichnet
    klicke(at, "schritt_4")
    ohne = [b.key for b in at.button if (b.key or "").startswith("zeige_b")]
    assert len(ohne) == 6
    klicke(at, ohne[0])
    assert "Ohne Bezug zum Fehlerprotokoll" in html_haupt(at)
    print("  Abgleich: 13 von 13, Sprung F07 -> Befund S. 73, 6 Befunde ohne Bezug")


def test_gegenprobe():
    at = voller_lauf("fehlerhaft")
    at.button_group(key="dok_wahl").set_value("fehlerfrei").run()
    ohne_fehler(at, "Dokumentwechsel")
    assert at.session_state["schritt"] == 1, "ohne Ergebnis zurück zum Prüfkatalog"
    klicke(at, "start")
    l = lauf(at, "fehlerfrei")
    assert (l["fehler"], l["warnungen"]) == (0, 6), (l["fehler"], l["warnungen"])
    # Grüne Kachel auch bei der Gegenprobe
    n_ok = sum(r.status == "BESTANDEN" for r in l["ergebnisse"])
    assert f"<span class='k-zahl'>{n_ok}</span><span class='k-text'>Checks ohne Befund" \
        in html_haupt(at)
    klicke(at, "schritt_4")
    haupt = html_haupt(at)
    # Kopfzeile wie im Abgleich: nur die Zahl in Statusfarbe, Warnungen in Warnfarbe
    assert ("<span class='abgleich-zahl ok'>0 Fehler</span><span class='abgleich-text'>in der "
            "fehlerfreien TB · <span class='warn-zahl'>6 Warnungen</span> zum Nachsehen") in haupt
    assert "Gegenprobe bestanden: Keiner der 13 eingebauten Fehler" in haupt
    assert len([b for b in at.button if (b.key or "").startswith("zeige_b")]) == 6
    # Befundkarte der Gegenprobe: als Hinweis bzw. möglicher Fehlalarm gekennzeichnet
    klicke(at, "zeige_b0")
    assert "Fehlerfreie TB: Hinweis zum Nachsehen oder Fehlalarm" in html_haupt(at)
    # Zurück zur fehlerhaften TB: deren Ergebnis ist noch da
    at.button_group(key="dok_wahl").set_value("fehlerhaft").run()
    ohne_fehler(at, "Dokumentwechsel zurück")
    assert lauf(at, "fehlerhaft")["fehler"] == 21
    assert at.session_state["schritt"] == 3
    print("  Gegenprobe: 0 Fehler, 6 Warnungen; Ergebnis der fehlerhaften TB bleibt erhalten")


def test_live_ohne_schluessel():
    with _Ersetzt(engine, api_schluessel_vorhanden=lambda: False):
        at = neue_app(notfall=False)
        assert "Kein API-Schlüssel gesetzt" in html_haupt(at), "Warnung im Prüfkatalog"
        haken(at, "kat_regeln", False)          # nur die Sprachmodell-Checks
        klicke(at, "start")
        ergebnisse = lauf(at, "fehlerhaft")["ergebnisse"]
        assert [r.id for r in ergebnisse] == [f"L-{i:02d}" for i in range(1, 7)]
        assert all(r.status == "ÜBERSPRUNGEN" for r in ergebnisse)
        haupt = html_haupt(at)
        assert haupt.count("übersprungen</div>") == 6
        assert "Kein API-Schlüssel gesetzt" in haupt, "Grund in der Ablaufliste sichtbar"
        assert "Die Checks laufen nacheinander" not in haupt   # Lauf ist fertig
        # Schritt 3: kein grünes „alle bestanden“, sondern „unvollständig“
        klicke(at, "schritt_3")
        haupt = html_haupt(at)
        assert "unvollständig: 6 Checks übersprungen" in haupt and "bestanden" not in haupt
        # Schritt 4: Untertitel nennt die übersprungenen Checks
        klicke(at, "schritt_4")
        assert "davon 6 Checks übersprungen" in html_haupt(at)
        # Gegenprobe nur mit (übersprungenen) Sprachmodell-Checks: nicht „bestanden“
        at.button_group(key="dok_wahl").set_value("fehlerfrei").run()
        ohne_fehler(at, "Dokumentwechsel")
        assert not at.checkbox(key="kat_regeln").value, "Auswahl bleibt beim Dokumentwechsel"
        klicke(at, "start")
        klicke(at, "schritt_4")
        haupt = html_haupt(at)
        assert "Gegenprobe unvollständig: 6 Checks übersprungen" in haupt
        assert "Gegenprobe bestanden" not in haupt and "abgleich-zahl ok" not in haupt
    print("  Live ohne Schlüssel: 6 übersprungen mit Grund; Schritt 3/4 und Gegenprobe "
          "„unvollständig“")


def test_fehlgeschlagen_fester_satz():
    def laufe(self, *args, **kwargs):
        for ereignis in ORIGINAL_LAUFE(self, *args, **kwargs):
            if ereignis.art == "ergebnis" and ereignis.check_id == "V-02":
                r = ereignis.ergebnis
                r.status, r.befunde = "FEHLGESCHLAGEN", []
                r.hinweis = "KeyError: 'abschnitt' in C:\\Temp\\x.py"
            yield ereignis

    with _Ersetzt(engine.Pruefstrecke, laufe=laufe):
        at = neue_app()
        haken(at, "kat_ki", False)              # nur die festen Regeln
        klicke(at, "start")
    haupt = html_haupt(at)
    assert "fehlgeschlagen</div>" in haupt
    assert "<div class='kachel kaputt'>" in haupt, "Kachel für fehlgeschlagene Checks"
    assert "Check konnte nicht ausgeführt werden." in haupt
    assert "KeyError" not in haupt and "C:\\" not in haupt, "kein technischer Grund auf der Leinwand"
    assert "KeyError" in text_seitenleiste(at), "technischer Grund in der Seitenleiste"
    klicke(at, "schritt_4")
    assert "davon 1 Check fehlgeschlagen" in html_haupt(at)
    print("  Fehlgeschlagen: fester Satz auf der Leinwand, Grund nur in der Seitenleiste")


def test_fehler_ohne_traceback():
    def kaputt(self, *args, **kwargs):
        raise RuntimeError("Testfehler im Prüflauf")

    konsole = io.StringIO()      # die App schreibt den Traceback nur in die Konsole
    with _Ersetzt(engine.Pruefstrecke, laufe=kaputt), contextlib.redirect_stderr(konsole):
        at = neue_app()
        at.button(key="start").click().run()
    assert "Traceback" in konsole.getvalue() and "Testfehler im Prüflauf" in konsole.getvalue()
    assert not at.exception, "keine Ausnahme/Traceback auf der Leinwand"
    meldungen = [e.value for e in at.error]
    assert len(meldungen) == 1 and "unerwartet unterbrochen" in meldungen[0], meldungen
    # Nur der deutsche Satz – der technische Grund steht in der Seitenleiste
    assert "Testfehler im Prüflauf" not in meldungen[0] and "Traceback" not in meldungen[0]
    assert "fehlerhaft" not in at.session_state["laeufe"]
    assert "RuntimeError" in at.session_state["letzter_fehler"]
    assert "Testfehler im Prüflauf" in text_seitenleiste(at)
    assert not at.session_state["lauf_laeuft"], "Fehler ist kein Abbruch durch Bedienung"
    print("  Fehler im Prüflauf: verständliche Meldung, kein Traceback")


def test_sperre_und_abbruch():
    # Vorher: fertiger Lauf auf der fehlerhaften TB
    at = voller_lauf("fehlerhaft")
    assert lauf(at, "fehlerhaft")["fehler"] == 21
    # Neuer Lauf, der mitten im Ablauf abgebrochen wird (wie bei einer Bedienung)
    with _Ersetzt(engine.Pruefstrecke, laufe=laufe_mit_abbruch(8)):
        klicke(at, "schritt_1")
        at.button(key="start").click().run()
    assert not at.exception
    # Während des Laufs: alles gesperrt (Stand beim Abbruch)
    assert all(at.button(key=f"schritt_{n}").disabled for n in (1, 2, 3, 4)), "Schrittleiste"
    assert at.button_group(key="dok_wahl").disabled, "Dokument-Umschalter"
    for schluessel in ("pause_s", "schrift_faktor"):
        assert at.select_slider(key=schluessel).disabled, schluessel
    assert at.number_input(key="max_parallel").disabled
    assert not at.checkbox(key="notfall").disabled, "Notfallschalter bleibt bedienbar"
    assert "Prüfung läuft" in html_haupt(at)
    # Nächster Aufbau: Abbruch wird gemeldet, kein altes Ergebnis
    at.run()
    ohne_fehler(at, "nach Abbruch")
    assert at.session_state["schritt"] == 1
    assert "fehlerhaft" not in at.session_state["laeufe"], "altes Ergebnis wird nicht gezeigt"
    assert "Prüfung wurde abgebrochen – bitte neu starten." in html_haupt(at)
    assert not at.button(key="schritt_1").disabled and not at.select_slider(key="pause_s").disabled
    # Neustart: Meldung verschwindet, Lauf läuft durch
    klicke(at, "start")
    assert lauf(at, "fehlerhaft")["fehler"] == 21
    assert "abgebrochen" not in html_haupt(at)
    print("  Sperre während des Laufs, Abbruch gemeldet, Neustart klappt")


def test_neuladen():
    # Sitzung 1: Notfall an, Lauf auf beiden Dokumenten, Befundansicht
    at = voller_lauf("fehlerhaft")
    klicke(at, "zu_befunden")
    klicke(at, "naechster")
    at.select_slider(key="pause_s").set_value(0.7).run()
    # Sitzung 2 (Neuladen der Seite): nichts vorbelegt – alles kommt aus dem Vorführstand
    at2 = AppTest.from_file(str(APP_PFAD), default_timeout=TIMEOUT_S)
    at2.session_state["notfall_verzoegerung_s"] = 0.0
    at2.run()
    ohne_fehler(at2, "nach Neuladen")
    assert at2.session_state["notfall"] is True, "Notfallschalter bleibt an"
    assert at2.checkbox(key="notfall").value is True
    assert at2.session_state["pause_s"] == 0.7
    assert lauf(at2, "fehlerhaft")["fehler"] == 21, "Ergebnis bleibt erhalten"
    assert at2.session_state["schritt"] == 3 and at2.session_state["befund_idx"]["fehlerhaft"] == 1
    assert "Befund 2 von 32" in html_haupt(at2)
    # Neuladen während eines Laufs: Sitzung 3 meldet den Abbruch
    with _Ersetzt(engine.Pruefstrecke, laufe=laufe_mit_abbruch(5)):
        klicke(at2, "schritt_1")
        at2.button(key="start").click().run()
    at3 = AppTest.from_file(str(APP_PFAD), default_timeout=TIMEOUT_S)
    at3.session_state["notfall_verzoegerung_s"] = 0.0
    at3.run()
    ohne_fehler(at3, "Neuladen während des Laufs")
    assert at3.session_state["schritt"] == 1
    assert "Prüfung wurde abgebrochen – bitte neu starten." in html_haupt(at3)
    # „?neu=1“: Neubeginn mit Standardwerten
    at4 = AppTest.from_file(str(APP_PFAD), default_timeout=TIMEOUT_S)
    at4.query_params["neu"] = "1"
    at4.run()
    ohne_fehler(at4, "?neu=1")
    assert at4.session_state["notfall"] is False and at4.session_state["laeufe"] == {}
    assert "neu" not in at4.query_params, "Parameter wird entfernt"
    assert "abgebrochen" not in html_haupt(at4)
    print("  Neuladen: Notfallschalter, Pause, Ergebnis und Ansicht bleiben; Abbruch gemeldet; "
          "?neu=1 setzt zurück")


def test_notfall_tempo_und_parallel():
    aufrufe = []

    def laufe(self, check_ids, modus="live", modell=None, max_parallel=None, **kwargs):
        aufrufe.append({"modus": modus, "max_parallel": max_parallel, **kwargs})
        kwargs["notfall_verzoegerung_s"] = 0.0          # Test: ohne Wartezeit
        return ORIGINAL_LAUFE(self, check_ids, modus, modell, max_parallel, **kwargs)

    with _Ersetzt(engine.Pruefstrecke, laufe=laufe):
        # Standardwerte der App für Pause und Notfall-Tempo
        at = neue_app(notfall_verzoegerung_s=None, pause_s=None)
        assert at.session_state["pause_s"] == 0.5, "Pause je Check: Standard 0,5 s"
        assert at.select_slider(key="pause_s").value == 0.5
        # Deutsche Schreibweise am Regler (Komma)
        assert "0,5 s" in at.select_slider(key="pause_s").options
        haken(at, "kat_regeln", False)          # nur die Sprachmodell-Checks
        at.session_state["pause_s"] = 0.0       # Test: ohne Mindestdauer
        klicke(at, "start")
    erwartet = "live" if hasattr(engine, "_verzoegerungsplan") else 6.0
    assert aufrufe == [{"modus": "notfall", "max_parallel": 24,
                        "notfall_verzoegerung_s": erwartet}], aufrufe
    assert at.number_input(key="max_parallel").value == 24
    assert at.number_input(key="max_parallel").max == 64
    print(f"  Pause 0,5 s, Notfall-Tempo „{erwartet}“, 24 parallele Anfragen (höchstens 64)")


def test_stylesheet():
    at = neue_app()
    stil = stylesheet(at)
    # Feste Grundschrift (Browser-Zoom wirkt), nicht an die Fenstergröße gekoppelt
    assert "html { font-size: calc(var(--schrift-faktor) * 16px) !important; }" in stil
    html_regeln = re.findall(r"(?:^|\n)html \{([^}]*)\}", stil)
    assert html_regeln and not any(re.search(r"\d(vw|vh|vmin|vmax)", r) for r in html_regeln), \
        html_regeln
    assert "--schrift-faktor: 1.00" in stil
    # Schriftgrößen der Hauptfläche nur in rem/em, mindestens .85rem
    zu_klein = sorted({float(w) for w in re.findall(r"font-size: (\d*\.?\d+)rem", stil)
                       if float(w) < 0.85})
    assert not zu_klein, f"Schrift kleiner als .85rem: {zu_klein}"
    for regel in re.findall(r"([^{}]+)\{[^{}]*font-size: \d+(?:\.\d+)?px", stil):
        assert "stSidebar" in regel, f"px-Schrift außerhalb der Seitenleiste: {regel.strip()}"
    # Keine abgerundeten Ecken: border-radius nur 0, außer 50 % für Kreis-Symbole
    ohne_kommentare = re.sub(r"/\*.*?\*/", "", stil, flags=re.S)
    for regel, wert in re.findall(r"([^{}]+)\{[^{}]*border-radius: ([^;]+);", ohne_kommentare):
        if wert.strip().startswith("0"):
            continue
        assert wert.strip() == "50% !important", (regel.strip(), wert)
        selektoren = [s.strip() for s in regel.split(",")]
        assert all(s.startswith(".sym") or "stSpinner" in s or "stIconMaterial" in s
                   for s in selektoren), selektoren
    assert "*, *::before, *::after { border-radius: 0 !important; }" in stil
    # Schrift Roboto mit Ersatzschriften, Ziffern tabellarisch, Farb-Tokens
    assert '--schrift: Roboto, "Segoe UI", system-ui, sans-serif;' in stil
    assert "font-variant-numeric: tabular-nums" in stil
    for token in ("--blau: #00539F", "--seite: #F3F5F8", "--flaeche: #FFFFFF",
                  "--linie: #D5DCE5"):
        assert token in stil, token
    # Prozesskette als Pfeilboxen
    assert "clip-path: polygon(" in stil
    # Gesperrter Start-Knopf grau (nicht blau), Hover nur für bedienbare Knöpfe
    assert '.stButton button[kind="primary"]:disabled' in stil
    assert '.stButton button[kind="primary"]:hover:not(:disabled)' in stil
    # Prozesskette: Pfeilspitzen klickbar (nur die Knöpfe nehmen Klicks an)
    assert ".st-key-schrittleiste .stButton button, .st-key-schrittleiste .stButton button *" in stil
    # Kein eigener Farbakzent für die Methode (Farben nur für den Status)
    assert "--ki" not in stil and ".chip.ki" not in stil
    # Schmale Hauptfläche: Katalog und Grafiken untereinander (Container-Abfragen)
    assert "container-type: inline-size" in stil and "@container (max-width:" in stil
    # Keine Schatten-Effekte
    assert not re.search(r"box-shadow: (?!none)", stil), "Schatten im Stylesheet"
    # Faktor aus der Seitenleiste wirkt auf die Grundschrift
    at.select_slider(key="schrift_faktor").set_value(1.25).run()
    assert "--schrift-faktor: 1.25" in stylesheet(at)
    print("  Stylesheet: feste Grundschrift 16 px × Faktor, ≥ .85rem, eckig, Roboto, "
          "Ziffern tabellarisch")


def test_piktogramme():
    at = voller_lauf("fehlerhaft")
    texte = [html_haupt(at)]
    klicke(at, "zu_befunden")
    texte.append(html_haupt(at))
    haken(at, "vergleich_umschalter", True)
    texte.append(html_haupt(at))
    assert at.checkbox(key="vergleich_umschalter").label.startswith(":material/compare:")
    assert at.button(key="naechster").label == ":material/chevron_right:"
    klicke(at, "schritt_4")
    texte.append(html_haupt(at))
    alles = "\n".join(texte)
    # Eine Icon-Familie: alle Piktogramme über icon() (Material-Symbols-Namen)
    namen = set(re.findall(r"<span class='ic[^']*' aria-hidden='true'>([^<]*)</span>", alles))
    assert namen, "keine Piktogramme gefunden"
    assert all(re.fullmatch(r"[a-z_]+", n) for n in namen), namen
    assert {"close", "check", "priority_high", "description", "rule", "psychology"} <= namen, namen
    assert "class='chip ki'" not in alles, "Methode nur über das Piktogramm im Chip"
    # Keine Unicode-Ersatzzeichen mehr als Symbole
    for zeichen in ("✓", "✗", "⚠", "▶", "◀"):
        assert zeichen not in alles, f"Ersatzzeichen {zeichen} auf der Hauptfläche"
    # Streamlit-Beschriftungen: Piktogramme derselben Familie
    knoepfe = [b for b in at.button if (b.key or "").startswith(("schritt_", "zeige_"))]
    assert knoepfe and all((b.proto.icon or "").startswith(":material/") for b in knoepfe)
    print(f"  Piktogramme: {len(namen)} Material-Symbole ({', '.join(sorted(namen))}), "
          "keine Ersatzzeichen")


def test_konfiguration():
    import tomllib
    konfig = tomllib.loads((GUI_ORDNER / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    thema = konfig["theme"]
    assert thema["baseRadius"] == "none" and thema["buttonRadius"] == "none"
    assert thema["baseFontSize"] == 16
    assert thema["font"].startswith("Roboto")
    assert konfig["server"]["enableStaticServing"] is True
    schriften = thema["fontFaces"]
    assert {f["family"] for f in schriften} == {"Roboto"} and len(schriften) == 3
    for f in schriften:
        assert f["url"].startswith("app/static/fonts/") and f["weight"] == "100 900"
        assert (GUI_ORDNER / f["url"].removeprefix("app/")).is_file(), f["url"]
        assert f["unicodeRange"].startswith("U+")
    assert (GUI_ORDNER / "static" / "fonts" / "OFL.txt").is_file(), "Lizenz der Schrift"
    print("  config.toml: eckig (baseRadius none), Roboto lokal aus static/fonts (3 Dateien)")


# =============================================================================
# Ausführung ohne pytest
# =============================================================================
TESTS = [test_start_ohne_fehler, test_kategorie_checkboxen, test_kompletter_lauf_fehlerhaft,
         test_befundansicht, test_abgleich_13_von_13, test_gegenprobe,
         test_live_ohne_schluessel, test_fehlgeschlagen_fester_satz, test_fehler_ohne_traceback,
         test_sperre_und_abbruch, test_neuladen, test_notfall_tempo_und_parallel,
         test_stylesheet, test_piktogramme, test_konfiguration]


def main() -> int:
    vorher = hash_dateien()
    fehlgeschlagen = 0
    for test in TESTS:
        start = time.time()
        try:
            test()
            print(f"[OK]     {test.__name__} ({time.time() - start:.1f} s)")
        except Exception:
            fehlgeschlagen += 1
            print(f"[FEHLER] {test.__name__}")
            traceback.print_exc()
    if CLIENT_VERSUCHE:
        fehlgeschlagen += 1
        print(f"[FEHLER] {len(CLIENT_VERSUCHE)} Versuch(e), einen API-Client zu erzeugen")
    else:
        print("[OK]     kein API-Client erzeugt (kein Netzwerk)")
    nachher = hash_dateien()
    geaendert = [p.name for p in GESCHUETZT if vorher[p] != nachher[p]]
    if geaendert:
        fehlgeschlagen += 1
        print(f"[FEHLER] geschützte Dateien verändert: {geaendert}")
    else:
        print(f"[OK]     {len(GESCHUETZT)} geschützte Dateien unverändert")
    if fehlgeschlagen:
        print(f"\n{fehlgeschlagen} Prüfung(en) fehlgeschlagen")
        return 1
    print(f"\nAlle {len(TESTS)} Tests bestanden, kein Netzwerk, geschützte Dateien unverändert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
