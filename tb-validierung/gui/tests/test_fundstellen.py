"""Tests für gui/fundstellen.py (Fundstellen im PDF finden und rendern).

Ausführen (aus dem Ordner tb-validierung/gui):
    python tests/test_fundstellen.py                  # ohne pytest, Exit-Code 1 bei Fehlern
    python -m pytest tests/test_fundstellen.py -s     # mit pytest

Geprüft wird:
(a) Jeder Befund der beiden Referenz-Prüfberichte erhält eine markierte
    Fundstelle (kein Rückfall „Seite“); Sonderfälle: Einfügemarke im
    Symbolverzeichnis, Streifen bei weit auseinander liegenden Treffern,
    Grafik mit Kurve und Prüfpunkt, Kontext nur dünn, Teilausdruck bei
    Vorzeichenfehlern, Vergleichsbegriffe für die Gegenüberstellung.
(b) Gegenstellen (finde_gegenstellen): genau bei den Widersprüchen über zwei
    Seiten, mit Beschriftung; sonst leere Liste.
(c) Live-Läufe mit claude-sonnet-5-5 (anders formulierte Befunde): jeder
    Befund erhält eine markierte Fundstelle. Übersprungen, wenn die
    Ergebnisdateien fehlen.
(d) Rendern: PNG in der verlangten Breite, Rahmen berühren keine
    Nachbarzeichen, Klammern werden nicht angeschnitten, PDFs unverändert.
(e) anzeige_text, Teilausdruck, L-03-Muster, Ortsname.

Keine Sprachmodell-Aufrufe: gelesen werden nur PDFs und gespeicherte Ergebnisse.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True          # keine __pycache__-Ordner im Repo
GUI_ORDNER = Path(__file__).resolve().parent.parent
TB_ORDNER = GUI_ORDNER.parent
sys.path.insert(0, str(GUI_ORDNER))

import fundstellen as fs  # noqa: E402

PDF_FEHLERHAFT = TB_ORDNER / "synthetische-tb" / "TB_VitalPlus_fehlerhaft.pdf"
PDF_SAUBER = TB_ORDNER / "synthetische-tb" / "TB_VitalPlus.pdf"
PDF = {"fehlerhaft": PDF_FEHLERHAFT, "fehlerfrei": PDF_SAUBER}
BERICHTE = {
    "fehlerhaft": TB_ORDNER / "validierungsnotebook" / "pruefbericht_TB_VitalPlus_fehlerhaft.json",
    "fehlerfrei": TB_ORDNER / "validierungsnotebook" / "pruefbericht_TB_VitalPlus.json",
}
# Ergebnisse der Live-Messung mit claude-sonnet-5-5 (Oktober 2026, zwei volle Läufe)
LIVE_ORDNER = Path(__file__).resolve().parent / "daten"
LIVE_FEHLERHAFT = LIVE_ORDNER / "live1_fehlerhaft.json"
LIVE_SAUBER = LIVE_ORDNER / "live2_fehlerfrei.json"


class _Uebersprungen(Exception):
    """Test übersprungen (Ausführung ohne pytest)."""


def ueberspringen(grund: str):
    try:
        import pytest
    except ImportError:
        raise _Uebersprungen(grund) from None
    pytest.skip(grund)


# --- Befunde laden -------------------------------------------------------------------
def befunde_referenz(dok: str) -> list[tuple[str, dict]]:
    bericht = json.loads(BERICHTE[dok].read_text(encoding="utf-8"))
    return [(c["id"], b) for c in bericht["checks"] for b in c.get("befunde", [])]


def befunde_live(pfad: Path) -> tuple[str, list[tuple[str, dict]]]:
    if not pfad.exists():
        ueberspringen(f"Live-Ergebnisdatei fehlt: {pfad}")
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    return daten["dokument"], [(e["id"], b) for e in daten["ergebnisse"]
                               for b in e.get("befunde", [])]


def fund(dok: str, check_id: str, befund: dict):
    return fs.finde_fundstelle(PDF[dok], check_id, befund["beschreibung"], befund.get("seite"))


def gegen(dok: str, check_id: str, befund: dict):
    return fs.finde_gegenstellen(PDF[dok], check_id, befund["beschreibung"],
                                 befund.get("seite"))


def nimm(befunde, check_id: str, seite: int, nr: int = 0) -> dict:
    """nr-ter Befund eines Checks auf einer Seite."""
    treffer = [b for c, b in befunde if c == check_id and b.get("seite") == seite]
    assert len(treffer) > nr, (check_id, seite, len(treffer))
    return treffer[nr]


def markiert(f) -> bool:
    """Fundstelle mit sichtbarer Markierung (Rechteck, Einfügemarke oder Kurve)."""
    return bool(f.rechtecke or f.einfuegemarke or f.kurve_farbe)


def text_im(pdf: Path, seite: int, rechteck) -> str:
    """Text eines Rechtecks (ohne Polster) im PDF."""
    idx = fs._seitenindex(fs._pfad(pdf), seite)
    innen = fs._polstern(rechteck, -fs._POLSTER_PT + 0.5)
    return "".join(c for c, b in zip(idx.text1, idx.box1)
                   if innen[0] <= (b[0] + b[2]) / 2 <= innen[2]
                   and innen[1] <= (b[1] + b[3]) / 2 <= innen[3])


def png_groesse(daten: bytes) -> tuple[int, int]:
    from PIL import Image
    with Image.open(io.BytesIO(daten)) as bild:
        return bild.size


# =============================================================================
# (a) Referenzberichte
# =============================================================================
def test_a_alle_referenzbefunde_markiert():
    for dok in ("fehlerhaft", "fehlerfrei"):
        for check_id, befund in befunde_referenz(dok):
            f = fund(dok, check_id, befund)
            assert f is not None, (dok, check_id)
            assert f.methode != "Seite", (dok, check_id, befund["beschreibung"][:60])
            assert markiert(f), (dok, check_id, f.hinweis)
            assert f.weitere == [], "finde_fundstelle füllt weitere nicht"
            x0, y0, x1, y1 = f.ausschnitt
            assert x1 > x0 and y1 > y0


def test_a_symbolverzeichnis_einfuegemarke():
    """F06: fehlender Eintrag DQx -> Einfügemarke in der Lücke nach „(q+w)x“,
    keine Fläche über den korrekten Nachbarzeilen."""
    b = nimm(befunde_referenz("fehlerhaft"), "V-04", 7)
    f = fund("fehlerhaft", "V-04", b)
    assert f.seite == 8 and f.methode == "Symbolverzeichnis"
    assert f.rechtecke == [] and f.einfuegemarke is not None
    assert "DQx" in f.marke_text and f.beschriftung == ""
    idx = fs._seitenindex(fs._pfad(PDF_FEHLERHAFT), 8)
    _, _, y = f.einfuegemarke
    davor = [r for r in idx.reihen if r.y1 <= y]
    danach = [r for r in idx.reihen if r.y0 >= y]
    assert davor and danach
    assert fs._norm(davor[-1].worte[0][4]).startswith("(q")   # (q + w)x
    assert fs._norm(danach[0].worte[0][4]).startswith("l")     # lx
    # Gegenüberstellung: in der fehlerfreien TB steht genau dort der DQx-Eintrag
    zeile = fs._zeile_an_marke(fs._seitenindex(fs._pfad(PDF_SAUBER), 8), f.einfuegemarke)
    assert zeile and "DQ" in text_im(PDF_SAUBER, 8, fs._polstern(zeile[0], fs._POLSTER_PT))


def test_a_streifen_bei_weit_auseinander_liegenden_treffern():
    """F07 (S. 73): zwei schmale Streifen statt eines hohen Ausschnitts."""
    befunde = befunde_referenz("fehlerhaft")
    for check_id in ("V-08", "L-03", "L-05"):
        f = fund("fehlerhaft", check_id, nimm(befunde, check_id, 73))
        assert len(f.streifen) == 2, (check_id, f.streifen)
        assert len(f.rechtecke) == 2, check_id
        hoehe = sum(b - a for a, b in f.streifen)
        assert hoehe < 0.75 * (f.ausschnitt[3] - f.ausschnitt[1]), check_id
        texte = [text_im(PDF_FEHLERHAFT, 73, r) for r in f.rechtecke]
        assert any("1910,0070" in t for t in texte) and any("1901,0070" in t for t in texte)


def test_a_grafik_kurve_und_pruefpunkt():
    """F13: Kurve „Frauen“ (Farbe aus der Legende) und Prüfpunkt x=80;
    die Bildunterschrift „Abbildung …“ liegt nicht im Ausschnitt."""
    f = fund("fehlerhaft", "L-06", nimm(befunde_referenz("fehlerhaft"), "L-06", 75))
    assert f.methode == "Grafik" and f.kurve_farbe is not None and f.grafik_bereich
    assert f.pruefpunkt == (80.0, 4.7, 3.0942)
    seite = fs._dokument(fs._pfad(PDF_FEHLERHAFT))[74]
    linien = fs._kurven_linien(seite, f.kurve_farbe, f.grafik_bereich)
    assert linien and max(len(p) for p in linien) > 50
    idx = fs._seitenindex(fs._pfad(PDF_FEHLERHAFT), 75)
    for bbox, text, _ in idx.zeilen:
        if text.strip().startswith("Abbildung"):
            assert not fs._schneiden(bbox, f.ausschnitt), "Bildunterschrift im Ausschnitt"


def test_a_kontextbegriff_nur_duenn():
    """F03 (V-09 S. 16): rot nur „§ 4 VAG“, der Fachbegriff nur dünn gerahmt."""
    f = fund("fehlerhaft", "V-09", nimm(befunde_referenz("fehlerhaft"), "V-09", 16))
    assert len(f.rechtecke) == 1
    assert text_im(PDF_FEHLERHAFT, 16, f.rechtecke[0]) == "§4VAG"
    assert len(f.nebenrechtecke) == 2                     # „Höchstrechnungs-“ / „zins“


def test_a_vorzeichenfehler_markiert_teilausdruck():
    """F12 (L-05 S. 44): rot nur der Klammerterm mit „+ γx“, nicht die ganze
    Gleichung (30); die Legende mit „− γx“ dünn als Gegenstelle."""
    f = fund("fehlerhaft", "L-05", nimm(befunde_referenz("fehlerhaft"), "L-05", 44))
    assert len(f.rechtecke) == 1
    text = text_im(PDF_FEHLERHAFT, 44, f.rechtecke[0])
    assert "+γ" in fs._norm(text) and not text.startswith("V"), text
    neben = [text_im(PDF_FEHLERHAFT, 44, r) for r in f.nebenrechtecke]
    assert any("-γ" in fs._norm(t) for t in neben), neben


def test_a_vergleichsbegriff_fuer_die_gegenueberstellung():
    """F04: in der fehlerfreien TB wird nur „(Anlage 5.2)“ markiert."""
    f = fund("fehlerhaft", "V-01", nimm(befunde_referenz("fehlerhaft"), "V-01", 45))
    assert f.vergleich_begriffe == ["(Anlage 5.2)"]
    teil = fs._vergleich_treffer(fs._seitenindex(fs._pfad(PDF_SAUBER), 45), f)
    assert len(teil) == 1
    assert text_im(PDF_SAUBER, 45, teil[0]) == "(Anlage5.2)"


def test_a_tabellenzeile_nicht_angeschnitten():
    """V-09 S. 79: der Ausschnitt schneidet keine Tabellenzeile an."""
    f = fund("fehlerhaft", "V-09", nimm(befunde_referenz("fehlerhaft"), "V-09", 79))
    idx = fs._seitenindex(fs._pfad(PDF_FEHLERHAFT), 79)
    for a, b in f.streifen or [(f.ausschnitt[1], f.ausschnitt[3])]:
        for r in idx.reihen:
            hoehe = r.y1 - r.y0
            innen = min(r.y1, b) - max(r.y0, a)
            assert innen <= 0.15 * hoehe or innen >= 0.85 * hoehe, (r.y0, r.y1, a, b)


# =============================================================================
# (b) Gegenstellen
# =============================================================================
ERWARTETE_GEGENSTELLEN = {
    # (dok, check_id, seite): (Seite der Gegenstelle, Beschriftung, Beschriftung der Hauptstelle)
    ("fehlerhaft", "L-03", 44): (92, "Seite 92 · Anhang 5, Schritt 4", "Seite 44 · Abschnitt 5.1"),
    ("fehlerhaft", "L-03", 35): (92, "Seite 92 · Anhang 5, Schritt 3", "Seite 35 · Abschnitt 3.2"),
    ("fehlerfrei", "L-03", 92): (35, "Seite 35 · Abschnitt 3.2", "Seite 92 · Anhang 5, Schritt 3"),
}


def test_b_gegenstellen_referenz():
    gefunden = {}
    for dok in ("fehlerhaft", "fehlerfrei"):
        for check_id, befund in befunde_referenz(dok):
            g = gegen(dok, check_id, befund)
            if g:
                gefunden[(dok, check_id, befund.get("seite"))] = (g, fund(dok, check_id, befund))
    assert set(gefunden) == set(ERWARTETE_GEGENSTELLEN), sorted(gefunden)
    for schluessel, (seite, beschriftung, haupt) in ERWARTETE_GEGENSTELLEN.items():
        g, f = gefunden[schluessel]
        assert len(g) == 1, schluessel
        assert g[0].seite == seite and g[0].beschriftung == beschriftung, (schluessel, g[0])
        assert g[0].rechtecke and g[0].methode == "Suchbegriff"
        assert f.beschriftung == haupt, (schluessel, f.beschriftung)
        assert f.seite != g[0].seite


def test_b_gegenstelle_l03_s35_zeigt_beispielrechnung():
    """L-03 S. 35: die Gegenstelle ist die Rechnung P43 in Anhang 5, Schritt 3."""
    b = nimm(befunde_referenz("fehlerhaft"), "L-03", 35)
    (g,) = gegen("fehlerhaft", "L-03", b)
    texte = "".join(text_im(PDF_FEHLERHAFT, 92, r) for r in g.rechtecke)
    assert "4676,48" in texte and "1901,0070" in texte


def test_b_gegenstellen_rendern_auch_neutral():
    b = nimm(befunde_referenz("fehlerhaft"), "L-03", 44)
    (g,) = gegen("fehlerhaft", "L-03", b)
    for pdf, farbe in ((PDF_FEHLERHAFT, "warnung"), (PDF_SAUBER, "neutral")):
        png = fs.rendere_ausschnitt(pdf, g, farbe=farbe, breite_px=1200)
        assert png[:8] == b"\x89PNG\r\n\x1a\n" and png_groesse(png)[0] == 1200
    # Wer beide Stellen in einem Bild möchte, setzt weitere (Kopfbalken = beschriftung)
    f = fund("fehlerhaft", "L-03", b)
    einzeln = png_groesse(fs.rendere_ausschnitt(PDF_FEHLERHAFT, f, breite_px=1200))[1]
    f.weitere = [g]
    zusammen = png_groesse(fs.rendere_ausschnitt(PDF_FEHLERHAFT, f, breite_px=1200))[1]
    assert zusammen > einzeln


def test_b_keine_gegenstelle_ohne_belastbaren_ort():
    """Widerspruch auf derselben Seite oder ohne Ortsangabe -> leere Liste."""
    text = ("Widerspruch „Sicherheitszuschlag σ“: Anlage 2.4, Fließtext (Seite 79) nennt "
            "„5,0 % des Bruttobeitrags“, Anlage 2.4, Tabelle (Seite 79) dagegen „4,5 %“ – x.")
    assert fs.finde_gegenstellen(PDF_FEHLERHAFT, "L-03", text, 79) == []
    erfunden = ("Widerspruch „Testwert“: Abschnitt 3.2 nennt „1234,5678 EUR“, Anhang 5, "
                "Schritt 3 dagegen „8765,4321 EUR“ – frei erfunden.")
    assert fs.finde_gegenstellen(PDF_FEHLERHAFT, "L-03", erfunden, 35) == []
    assert fs.finde_gegenstellen(PDF_FEHLERHAFT, "L-01", "Rechtschreibfehler „x“", 11) == []


# =============================================================================
# (c) Live-Läufe mit anders formulierten Befunden
# =============================================================================
def _live_alle_markiert(pfad: Path) -> list:
    dok, befunde = befunde_live(pfad)
    ergebnisse = []
    for check_id, befund in befunde:
        f = fund(dok, check_id, befund)
        assert f is not None, (check_id, befund.get("seite"))
        assert f.methode != "Seite", (check_id, befund.get("seite"),
                                      befund["beschreibung"][:80])
        assert markiert(f), (check_id, befund.get("seite"), f.hinweis)
        ergebnisse.append((check_id, befund, f))
    return ergebnisse


def test_c_live_fehlerhaft_alle_markiert():
    ergebnisse = _live_alle_markiert(LIVE_FEHLERHAFT)
    assert len(ergebnisse) == 33
    nach = {(c, b.get("seite")): f for c, b, f in ergebnisse}
    # S. 73: zwei Streifen, markiert sind beide Werte (nicht die Abschnittsüberschrift)
    f = nach[("L-03", 73)]
    assert len(f.streifen) == 2 and len(f.rechtecke) == 2
    texte = [text_im(PDF_FEHLERHAFT, 73, r) for r in f.rechtecke]
    assert any("1910,0070" in t for t in texte) and any("1901,0070" in t for t in texte)
    assert not any("Festsetzung" in t for t in texte)
    # S. 44: Klammerterm mit „+ γx“ aus der in der Ortsangabe genannten Formel
    f = nach[("L-03", 44)]
    assert any("+γ" in fs._norm(text_im(PDF_FEHLERHAFT, 44, r)) for r in f.rechtecke)
    f = nach[("L-05", 44)]
    assert len(f.rechtecke) == 1 and not text_im(PDF_FEHLERHAFT, 44, f.rechtecke[0]).startswith("V")
    # S. 92 (L-03): Zahlen aus den Ortsangaben werden nicht markiert
    _, befunde = befunde_live(LIVE_FEHLERHAFT)
    b = nimm(befunde, "L-03", 92, 0)
    f = fund("fehlerhaft", "L-03", b)
    assert [text_im(PDF_FEHLERHAFT, 92, r) for r in f.rechtecke] == ["4676,48EURp.a."]
    # Gegenstellen gibt es in diesem Lauf nicht (alle Widersprüche je auf einer Seite)
    assert all(gegen("fehlerhaft", c, b) == [] for c, b, _ in ergebnisse)


def test_c_live_fehlerfrei_alle_markiert():
    ergebnisse = _live_alle_markiert(LIVE_SAUBER)
    assert len(ergebnisse) == 11
    # L-03 S. 61: früher Rückfall „Seite“ – jetzt beide Stellen des Satzes markiert
    (f,) = [f for c, b, f in ergebnisse if (c, b.get("seite")) == ("L-03", 61)]
    assert f.methode == "Suchbegriff" and len(f.rechtecke) == 2
    texte = [text_im(PDF_SAUBER, 61, r) for r in f.rechtecke]
    assert any("oberhalbderbeobachtetenRohwerte" in t for t in texte), texte
    assert any("ÜberschätzungdesStornos" in t for t in texte), texte


# =============================================================================
# (d) Rendern
# =============================================================================
def _hash(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def test_d_rendern_breite_streifen_marke_und_pdfs_unveraendert():
    vorher = {p: _hash(p) for p in PDF.values()}
    befunde = befunde_referenz("fehlerhaft")
    for check_id, seite in (("V-08", 73), ("V-04", 7), ("L-06", 75), ("V-06", 89)):
        f = fund("fehlerhaft", check_id, nimm(befunde, check_id, seite))
        for pdf, farbe in ((PDF_FEHLERHAFT, "fehler"), (PDF_SAUBER, "neutral")):
            png = fs.rendere_ausschnitt(pdf, f, markieren=True, farbe=farbe, breite_px=1500)
            breite, hoehe = png_groesse(png)
            assert breite == 1500 and 60 < hoehe < 1500, (check_id, farbe, hoehe)
    # Einfügemarke: eingeschobene Zeile macht das Bild höher als ohne Markierung
    f = fund("fehlerhaft", "V-04", nimm(befunde, "V-04", 7))
    mit = png_groesse(fs.rendere_ausschnitt(PDF_FEHLERHAFT, f, breite_px=1500))[1]
    ohne = png_groesse(fs.rendere_ausschnitt(PDF_FEHLERHAFT, f, markieren=False,
                                             breite_px=1500))[1]
    assert mit > ohne
    assert {p: _hash(p) for p in PDF.values()} == vorher


def test_d_rahmen_beruehrt_keine_nachbarzeichen():
    """Rahmen mit Abstand zum „=“ (S. 73) bzw. Klammer mit eingerahmt (S. 33)."""
    befunde = befunde_referenz("fehlerhaft")
    rand_pt = 1.66
    # S. 73: „G^M = 1910,0070“ – zwischen „=“ und Rahmen bleibt Weißraum
    f = fund("fehlerhaft", "V-08", nimm(befunde, "V-08", 73))
    idx = fs._seitenindex(fs._pfad(PDF_FEHLERHAFT), 73)
    neu, staerken = fs._rahmen_an_nachbarn(idx, f.rechtecke, rand_pt)
    for r, n, (links, rechts) in zip(f.rechtecke, neu, staerken):
        laeufe = fs._tinte_laeufe(idx, r[0] - 10, r[2] + 10, r[1] + 2.3, r[3] - 2.3)
        nachbar_links = max(b for a, b in laeufe if b < r[0] + fs._POLSTER_PT - 0.3)
        assert n[0] - links / 2 >= nachbar_links + 1.5, (n, nachbar_links)
        text_links = min(a for a, b in laeufe if a >= r[0] + fs._POLSTER_PT - 0.3)
        assert n[0] + links / 2 <= text_links, (n, text_links)
    # S. 33: „(§ 10 Abs. 1 KVAV)“ – die öffnende Klammer liegt innerhalb des Rahmens
    f = fund("fehlerhaft", "L-04", nimm(befunde, "L-04", 33))
    idx = fs._seitenindex(fs._pfad(PDF_FEHLERHAFT), 33)
    neu, _ = fs._rahmen_an_nachbarn(idx, f.rechtecke, rand_pt)
    erste = min(neu, key=lambda r: r[1])
    assert text_im(PDF_FEHLERHAFT, 33, fs._polstern(erste, 0.3)).startswith("(§")


# =============================================================================
# (e) Hilfsfunktionen
# =============================================================================
def test_e_anzeige_text():
    v01 = befunde_referenz("fehlerhaft")[0][1]["beschreibung"]
    assert "\ufe00" in v01
    text = fs.anzeige_text(v01)
    assert text == ("Nicht aufgelöster Verweis: „… verwendet (Anlage 5.2, Abschnitt ??); "
                    "die Bilanzdeckungsrückstellung einer …“"), text
    # Rechtschreib-Kontext ohne Formelsatz: nur Auslassungszeichen
    l01 = fs.anzeige_text("Rechtschreibfehler „Äquivalenzprinizip“ im Kontext: „...ergibt "
                          "sich nach dem Äquivalenzprinizip (Barwert d...“")
    assert l01 == ("Rechtschreibfehler „Äquivalenzprinizip“ im Kontext: „… ergibt sich nach "
                   "dem Äquivalenzprinizip (Barwert d …“"), l01
    # Kombinationszeichen vor dem Buchstaben (Formelsatz) -> an den Buchstaben hängen
    assert fs.anzeige_text("Satz zu \u0304wneu: x") == "Satz zu w\u0304neu: x"
    assert fs.anzeige_text("A\u200bB\u00adC  D") == "ABC D"
    assert fs.anzeige_text("") == "" and fs.anzeige_text(None) == ""
    # Normale Befundtexte bleiben unverändert
    satz = "Normzitat „§ 4 VAG“ passt nicht zum Sachverhalt – einschlägig wäre § 4 KVAV."
    assert fs.anzeige_text(satz) == satz


def test_e_teilausdruck_und_fragmente():
    formel = "V_x(b) = G·A_x − [12·(1−(σ+Ω_x))·b + γ_x]·a_x"
    assert fs._fragmente("mit positivem Vorzeichen (+γ_x). Legende zieht ab") == ["+γ_x"]
    assert fs._teilausdruck(formel, "+γ_x") == "12·(1−(σ+Ω_x))·b + γ_x"
    assert fs._teilausdruck(formel, "−γ_x") is None          # steht nicht in der Formel
    assert fs._teilausdruck("a + b", "+b") is None            # kein Klammerausdruck
    assert fs._fragmente("Standard-/Basistarif, x−1, Abschnitt 5.1") == []


def test_e_l03_muster_und_ortsname():
    m = fs._L03_MUSTER.search("Widerspruch „T“: Abschnitt 3.2 nennt „a“, Anhang 5, "
                              "Schritt 3 dagegen „b“ – weil.")
    assert (m.group("stelle_a"), m.group("wert_a"), m.group("wert_b"),
            m.group("begruendung")) == ("Abschnitt 3.2", "a", "b", "weil.")
    ohne = fs._L03_MUSTER.search("Widerspruch „T“: A nennt „a“, B dagegen „b“")
    assert ohne and ohne.group("wert_b") == "b" and ohne.group("begruendung") is None
    assert fs._ortsname("Anhang 5 (Teil B), Schritt 4, Berechnung von b43") \
        == "Anhang 5, Schritt 4"
    assert fs._ortsname("Teil A, Abschnitt 3.2 (Seite 35)") == "Abschnitt 3.2"
    assert fs._ortsname("Einleitender Text") == ""
    pfad = fs._pfad(PDF_FEHLERHAFT)
    assert fs._ortsname("Abschnitt 5.1, Aufzählung; Anhang 5, Schritt 4", pfad, 92) \
        == "Anhang 5, Schritt 4"


def test_e_schnittstelle():
    import dataclasses
    felder = {f.name: f for f in dataclasses.fields(fs.Fundstelle)}
    for name in ("seite", "rechtecke", "ausschnitt", "methode", "beschriftung", "marke_text",
                 "streifen", "nebenrechtecke", "einfuegemarke", "weitere"):
        assert name in felder, name
    assert felder["beschriftung"].default == ""
    assert {"finde_fundstelle", "finde_gegenstellen", "rendere_ausschnitt",
            "anzeige_text", "Fundstelle"} <= set(fs.__all__)
    assert fs.finde_fundstelle(TB_ORDNER / "gibt-es-nicht.pdf", "V-01", "x", 1) is None
    assert fs.finde_gegenstellen(TB_ORDNER / "gibt-es-nicht.pdf", "L-03", "x", 1) == []
    # Rückgaben sind Kopien: Änderungen wirken nicht auf den Zwischenspeicher
    b = nimm(befunde_referenz("fehlerhaft"), "V-08", 73)
    f = fund("fehlerhaft", "V-08", b)
    f.rechtecke.clear()
    assert fund("fehlerhaft", "V-08", b).rechtecke


# =============================================================================
# Ausführung ohne pytest
# =============================================================================
def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fehler = 0
    for name, funktion in list(globals().items()):
        if not (name.startswith("test_") and callable(funktion)):
            continue
        try:
            funktion()
            print(f"BESTANDEN     {name}")
        except KeyboardInterrupt:
            raise
        except BaseException as e:  # noqa: BLE001  (auch pytest-Skip)
            if isinstance(e, _Uebersprungen) or type(e).__name__ == "Skipped":
                print(f"ÜBERSPRUNGEN  {name}: {e}")
                continue
            fehler += 1
            print(f"FEHLER        {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
    print(f"\n{'Alle Tests bestanden.' if not fehler else f'{fehler} Test(s) fehlgeschlagen.'}")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
