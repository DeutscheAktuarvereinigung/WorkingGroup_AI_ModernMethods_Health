"""
Fundstellen im TB-PDF finden und stark vergrößert darstellen
=============================================================

Zu jedem Befund eines Prüflaufs wird die betroffene Passage im PDF gesucht,
markiert und als eng zugeschnittener, stark vergrößerter Bildausschnitt (PNG)
gerendert – für die Präsentation auf einer großen Leinwand.

Vorgehen in ``finde_fundstelle``:

1. Suchbegriffe aus der Befund-Beschreibung ableiten: Zitate in „…“ oder "…",
   deutsche Zahlen (653,33 / 0,037271 / 4,5 %), Normzitate (§ 4 VAG),
   kaputte Verweise („??“), Gleichungsnummern, Altersangaben in Tabellen.
   Zitate mit „...“ am Rand (Textauszüge), Themen-Zitate („Widerspruch „…“:“),
   Zitate in '…' sowie Soll-/Referenzwerte dienen nur als *Kontext* (Ortung),
   sie werden nicht markiert. L-03-Widersprüche werden nach dem Format des
   Notebooks zerlegt: markiert werden nur die beiden zitierten Werte;
   Ortsangaben (auch Formeln und Wortlaut darin) dienen der Ortung. Bei
   Vorzeichenbefunden („+γ_x“) wird nur der betroffene Klammerausdruck markiert.
2. Auf der angegebenen Seite suchen – in einem eigenen Zeichenindex: Text
   NFKC-normalisiert (Formel-Kursivschrift 𝑥 → x), Leerraum ignoriert,
   Silbentrennung am Zeilenende aufgelöst; Zahlen nur mit sauberen Grenzen.
   Umschriebene Zitate (Live-Antworten) über das längste wörtliche Wortfenster.
3. Bei mehreren Treffern die zueinander passendsten wählen (räumliche Nähe
   zum seltensten Begriff); weit entfernte Treffer gelten als Rauschen.
4. Sonderfälle: Grafiken (Kurve und Prüfpunkt), Inhaltsverzeichnis (ganze
   Zeile), Symbolverzeichnis (Einfügemarke an der Stelle des fehlenden
   Eintrags), Gleichungsnummern (Formelzeile), Tabellen (Spaltenkopf wird
   mitgezeigt), weit auseinander liegende Treffer (schmale Streifen).
5. Rückfall: oberer Bereich der Seite (methode "Seite") – kein Befund bleibt
   ohne Fundstelle.

``finde_gegenstellen`` liefert weitere im Befundtext genannte Stellen auf
anderen Seiten (z. B. „Anhang 5, Schritt 3“ eines Widerspruchs), je mit
Beschriftung. ``anzeige_text`` bereitet den Befundtext für die Leinwand auf.

``rendere_ausschnitt`` rendert den Ausschnitt mit PyMuPDF und legt die
Markierung mit Pillow darüber (Tönung per Multiplikation, damit der Text
schwarz bleibt, plus kräftiger Rahmen, der keine Nachbarzeichen berührt).
In die PDFs wird nichts geschrieben.
"""

from __future__ import annotations

import copy
import io
import math
import re
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageFont

__all__ = ["Fundstelle", "finde_fundstelle", "finde_gegenstellen", "rendere_ausschnitt",
           "anzeige_text"]

Rechteck = tuple[float, float, float, float]


# =============================================================================
# Ergebnis-Datenklasse
# =============================================================================

@dataclass
class Fundstelle:
    """Ort eines Befunds im PDF (alle Koordinaten in PDF-Punkten)."""
    seite: int                       # PDF-Seite, 1-basiert
    rechtecke: list[Rechteck]        # zu markierende Bereiche
    ausschnitt: Rechteck             # Zoom-Bereich
    methode: str                     # wie gefunden: Suchbegriff / Grafik / Symbolverzeichnis /
                                     # Gleichung / Vorgabe / Seite
    kopf: Rechteck | None = None     # optional: Spaltenkopf einer Tabelle, der weit oberhalb
                                     # steht – wird beim Rendern über den Ausschnitt gesetzt
    hinweis: str = ""                # optional: welche Begriffe gefunden wurden (Nachvollzug)
    # --- optionale Erweiterungen für die Leinwand ---------------------------
    streifen: list = field(default_factory=list)
    """y-Bereiche (y0, y1) innerhalb des Ausschnitts, die einzeln gezeigt und
    gestrichelt getrennt werden (weit auseinander liegende Treffer derselben
    Seite); leer = ganzer Ausschnitt."""
    nebenrechtecke: list = field(default_factory=list)
    """Kontext-Stellen (z. B. der Fachbegriff zu einem falschen Normzitat):
    nur dünn und neutral gerahmt."""
    einfuegemarke: tuple | None = None
    """(x0, x1, y): hier FEHLT etwas (z. B. ein Eintrag im Symbolverzeichnis) –
    gezeichnet als eingeschobene Zeile mit marke_text statt als Fläche
    über den (korrekten) Nachbarzeilen."""
    marke_text: str = ""
    """Text der Einfügemarke, z. B. „Hier fehlt der Eintrag „DQx““."""
    beschriftung: str = ""
    """Bildunterschrift für Stellen eines Befunds auf mehreren Seiten, z. B.
    „Seite 92 · Anhang 5, Schritt 4“ (gesetzt bei Gegenstellen und der
    zugehörigen Hauptstelle; sonst leer)."""
    weitere: list = field(default_factory=list)
    """Optional: Gegenstellen, die rendere_ausschnitt unter der Hauptstelle in
    dasselbe Bild setzt (Kopfbalken = beschriftung). finde_fundstelle füllt
    das Feld NICHT – Gegenstellen liefert finde_gegenstellen; wer sie in einem
    Bild haben möchte, setzt fund.weitere = finde_gegenstellen(...)."""
    vergleich_begriffe: list = field(default_factory=list)
    """Texte, die in der Gegenüberstellung (anderes Dokument) statt der
    übertragenen Markierung markiert werden (z. B. „(Anlage 5.2)“ statt
    „(Anlage 5.2, Abschnitt ??)“)."""
    grafik_bereich: Rechteck | None = None    # Zeichenfläche eines Diagramms
    kurve_farbe: tuple | None = None          # Linienfarbe der betroffenen Kurve (RGB 0..1)
    pruefpunkt: tuple | None = None           # (x, y_grafik, y_tabelle) aus dem Befund


# =============================================================================
# Darstellung
# =============================================================================

FARBEN = {
    "fehler": (222, 45, 18),     # kräftiges Rot-Orange
    "warnung": (232, 135, 0),    # Orange (optional für Warnungen)
    "neutral": (0, 80, 160),     # Blau #0050A0 (fehlerfreie Gegenüberstellung)
}
_TOENUNG = {"fehler": 0.26, "warnung": 0.30, "neutral": 0.20}   # Deckkraft der Flächentönung
_RAND_ANTEIL = 1 / 280            # Rahmenstärke relativ zur Bildbreite (1800 px -> ~6 px)
_POLSTER_PT = 2.0                 # Abstand Markierung <-> Text
_RAND_PT = 8.0                    # Rand um den Ausschnitt
_MIN_BREITE_PT = 300.0            # schmale Tabellen nicht übermäßig vergrößern
_MAX_ABSTAND_PT = 260.0           # weiter entfernte Treffer gelten als Rauschen
_MAX_KONTEXT_PT = 150.0           # Kontext-Treffer erweitern den Ausschnitt nur in diesem Umkreis
_STREIFEN_ZEILEN = 5              # Treffergruppen, zwischen denen mindestens so viele Zeilen …
_STREIFEN_ABSTAND_PT = 60.0       # … und so viel Abstand liegen, werden getrennt gezeigt
_LEERRAUM_MAX_PT = 10.0           # längere weiße Zwischenräume im Bild werden gekürzt …
_LEERRAUM_REST_PT = 7.0           # … auf diese Höhe
_LEERRAUM_RAND_PT = 3.0           # weißer Rand oben/unten im Bild
_NEBEN_FARBE = (96, 106, 122)     # dünner Rahmen für Kontext-Stellen (neutral grau)
_OK_FARBE = (27, 127, 59)         # Grün für den Sollwert (Tabelle) im Diagramm

_SPERRE = threading.RLock()       # PyMuPDF-Dokumente sind nicht threadsicher (Streamlit)


# =============================================================================
# Kuratierte Vorgaben – nur dort, wo die Heuristik nachweislich versagt
# =============================================================================
# Eintrag: check_id, seite (oder None), Teilstring der Beschreibung und
# entweder "begriffe" (zu markierende Suchtexte) oder "bereich" (Rechteck).
_VORGABEN: list[dict] = []


# =============================================================================
# Text-Normalisierung
# =============================================================================

_LOESCHEN = {"\ufe00", "\u00ad", "\u200b", "\u200c", "\u200d", "\ufeff"}
_ERSATZ = str.maketrans({
    "−": "-", "–": "-", "—": "-", "‐": "-", "‑": "-",
    "∙": "·", "⋅": "·",
    "„": '"', "“": '"', "”": '"', "‚": "'", "‘": "'", "’": "'",
})


def _norm(text: str) -> str:
    """Suchform: NFKC (𝑥 -> x, Ligaturen aufgelöst), einheitliche Striche, ohne Leerraum."""
    s = "".join(c for c in text if c not in _LOESCHEN)
    s = unicodedata.normalize("NFKC", s).translate(_ERSATZ)
    return "".join(ch for ch in s if not ch.isspace())


def _stufe2(s: str) -> str:
    """Gelockerte Suchform: nur Buchstaben, Ziffern, Prozent und Komma."""
    return "".join(ch for ch in s if ch.isalnum() or ch in "%,")


def _nadel(text: str) -> str:
    """Suchform eines Begriffs aus der Beschreibung (LaTeX-artige Indizes entfernt)."""
    t = text.strip()
    t = re.sub(r"^(?:\.\.\.|…)\s*|\s*(?:\.\.\.|…)$", "", t)
    t = re.sub(r"[_^{}]", "", t)
    return _norm(t)


def _ist_mathe(c: str) -> bool:
    o = ord(c)
    return 0x1D400 <= o <= 0x1D7FF or 0x0391 <= o <= 0x03C9


# =============================================================================
# Seitenindex: Zeichen mit Koordinaten, visuelle Zeilen ("Reihen"), Wörter
# =============================================================================

_ZAHLWORT = re.compile(r"^[-−–]?\d{1,3}(?:[.]\d{3})*(?:,\d+)?%?$|^\d+(?:,\d+)?%?$|^[—–-]$|^%$")


@dataclass
class _Reihe:
    """Visuelle Zeile: alle Textzeilen mit vertikaler Überlappung (inkl. Indizes, Brüche)."""
    y0: float
    y1: float
    x0: float
    x1: float
    worte: list = field(default_factory=list)   # (x0, y0, x1, y1, text, block, zeile, wortnr)

    @property
    def ist_daten(self) -> bool:
        """Tabellen-Datenzeile: mindestens zwei Wörter, alle numerisch."""
        return len(self.worte) >= 2 and all(_ZAHLWORT.match(w[4]) for w in self.worte)


@dataclass
class _SeitenIndex:
    pfad: str
    nummer: int
    rect: pymupdf.Rect
    text1: str                      # Suchform (Stufe 1)
    box1: list                      # Box je Zeichen
    zeile1: list                    # Zeilen-ID je Zeichen
    mathe1: list                    # stammt das Zeichen aus dem Formelsatz?
    luecke1: list                   # stand vor dem Zeichen Leerraum / Zeilenwechsel?
    text2: str                      # gelockerte Suchform (Stufe 2)
    pos2: list                      # Index Stufe 2 -> Index Stufe 1
    zeilen: list                    # (bbox, text, schriftgröße) aller Textzeilen
    reihen: list                    # _Reihe, von oben nach unten

    def reihe_von(self, r) -> int | None:
        """Index der Reihe mit der größten vertikalen Überlappung zum Rechteck r."""
        beste, best_ue = None, 0.0
        for i, z in enumerate(self.reihen):
            ue = min(z.y1, r[3]) - max(z.y0, r[1])
            if ue > best_ue:
                beste, best_ue = i, ue
        return beste


@lru_cache(maxsize=8)
def _dokument(pfad: str) -> pymupdf.Document:
    return pymupdf.open(pfad)


def _pfad(pdf_pfad) -> str:
    return str(Path(pdf_pfad).resolve())


@lru_cache(maxsize=512)
def _seitenindex(pfad: str, nummer: int) -> _SeitenIndex:
    seite = _dokument(pfad)[nummer - 1]
    roh = seite.get_text("rawdict")
    hoehe = seite.rect.height

    bloecke = []
    for block in roh["blocks"]:
        if block["type"] != 0:
            continue
        zeilen = []
        for z in block["lines"]:
            zeichen = [ch for sp in z["spans"] for ch in sp["chars"]]
            groesse = max((sp["size"] for sp in z["spans"]), default=0.0)
            zeilen.append((tuple(z["bbox"]), zeichen, groesse))
        bloecke.append(zeilen)

    # Kopfzeile (Firmenname, "Teil:", "Blatt:") liegt im obersten Zehntel der Seite
    kopf_unten = max((bb[3] for bl in bloecke for bb, _, _ in bl if bb[1] < 0.1 * hoehe),
                     default=0.0)

    text1, box1, zeile1, mathe1, luecke1 = [], [], [], [], []
    zeilen_info = []
    zeilen_id = 0
    for bl in bloecke:
        for j, (bbox, zeichen, groesse) in enumerate(bl):
            if bbox[3] <= kopf_unten + 0.5:
                continue
            roh_text = "".join(ch["c"] for ch in zeichen)
            zeilen_info.append((bbox, roh_text, groesse))
            # Silbentrennung: Trennstrich am Zeilenende vor kleingeschriebener Fortsetzung
            entferne = None
            sichtbar = [k for k, ch in enumerate(zeichen) if not ch["c"].isspace()]
            if sichtbar and zeichen[sichtbar[-1]]["c"] in ("-", "\u00ad") and j + 1 < len(bl):
                folge = "".join(ch["c"] for ch in bl[j + 1][1]).lstrip()
                if folge[:1].islower():
                    entferne = sichtbar[-1]
            luecke = True
            letzte_x1 = None
            for k, ch in enumerate(zeichen):
                c = ch["c"]
                if k == entferne:
                    continue
                if c.isspace():
                    luecke = True
                    continue
                b = ch["bbox"]
                # deutlicher horizontaler Abstand zählt ebenfalls als Lücke
                if letzte_x1 is not None and b[0] - letzte_x1 > 0.25 * max(groesse, 1.0):
                    luecke = True
                for n in _norm(c):
                    text1.append(n)
                    box1.append((b[0], max(b[1], bbox[1]), b[2], min(b[3], bbox[3])))
                    zeile1.append(zeilen_id)
                    mathe1.append(_ist_mathe(c))
                    luecke1.append(luecke)
                    luecke = False
                letzte_x1 = b[2]
            zeilen_id += 1

    text1_s = "".join(text1)
    pos2 = [i for i, ch in enumerate(text1_s) if ch.isalnum() or ch in "%,"]
    text2 = "".join(text1_s[i] for i in pos2)

    # Visuelle Reihen aus den Zeilen-Boxen
    reihen: list[_Reihe] = []
    for bbox, _, _ in sorted(zeilen_info, key=lambda z: (z[0][1], z[0][0])):
        x0, y0, x1, y1 = bbox
        mitte, h = (y0 + y1) / 2, y1 - y0
        for r in reversed(reihen[-4:]):
            ue = min(r.y1, y1) - max(r.y0, y0)
            if r.y0 <= mitte <= r.y1 or ue >= 0.3 * min(h, r.y1 - r.y0):
                r.y0, r.y1 = min(r.y0, y0), max(r.y1, y1)
                r.x0, r.x1 = min(r.x0, x0), max(r.x1, x1)
                break
        else:
            reihen.append(_Reihe(y0, y1, x0, x1))
    reihen.sort(key=lambda r: r.y0)
    for w in seite.get_text("words"):
        if w[3] <= kopf_unten + 0.5:
            continue
        mitte = (w[1] + w[3]) / 2
        for r in reihen:
            if r.y0 - 0.5 <= mitte <= r.y1 + 0.5:
                r.worte.append(tuple(w[:5]) + tuple(w[5:8]))
                break
    for r in reihen:
        r.worte.sort(key=lambda w: w[0])

    return _SeitenIndex(pfad, nummer, seite.rect, text1_s, box1, zeile1, mathe1, luecke1,
                        text2, pos2, zeilen_info, reihen)


# =============================================================================
# Rechteck-Hilfen
# =============================================================================

def _vereinigung(rechtecke) -> Rechteck:
    rs = list(rechtecke)
    return (min(r[0] for r in rs), min(r[1] for r in rs),
            max(r[2] for r in rs), max(r[3] for r in rs))


def _polstern(r, d) -> Rechteck:
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def _schneiden(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _flaeche(r) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _schnitt(a, b) -> Rechteck:
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def _verschmelzen(rechtecke) -> list[Rechteck]:
    """Überlappende Markierungen zu einem Rechteck zusammenfassen."""
    rs = [tuple(r) for r in rechtecke]
    geaendert = True
    while geaendert:
        geaendert = False
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                if _schneiden(rs[i], rs[j]):
                    rs[i] = _vereinigung([rs[i], rs[j]])
                    del rs[j]
                    geaendert = True
                    break
            if geaendert:
                break
    return [tuple(round(v, 2) for v in r) for r in rs]


def _weissraum(pfad: str, nummer: int, x0: float, x1: float, ya: float, yb: float,
               mit_tinte: bool = False):
    """y-Position (PDF-Punkte) der saubersten Lücke zwischen ya und yb: Mitte des
    längsten Pixelstreifens mit minimaler Tinte. So schneiden Ausschnittkanten und
    Zeilenbänder keine Hoch-/Tiefstellungen an, auch wenn die Textboxen eng liegen.
    mit_tinte=True liefert (y, Tinte): Tinte 0 heißt sauberer Schnitt mit
    mindestens 1,2 pt Weißraum; sonst die Zahl der Tintenpixel (mindestens 1)."""
    if yb - ya < 0.6:
        return ((ya + yb) / 2, 1) if mit_tinte else (ya + yb) / 2
    zoom = 4.0
    seite = _dokument(pfad)[nummer - 1]
    pix = seite.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY,
                           clip=pymupdf.Rect(x0, ya, x1, yb), alpha=False)
    daten, breite = pix.samples, pix.width
    tinte = [sum(1 for v in daten[z * pix.stride:z * pix.stride + breite] if v < 170)
             for z in range(pix.height)]
    if not tinte:
        return ((ya + yb) / 2, 0) if mit_tinte else (ya + yb) / 2
    minimum = min(tinte)
    bester, anfang = (0, 0), None
    for z, t in enumerate(tinte + [None]):
        if t is not None and t <= minimum:
            anfang = z if anfang is None else anfang
        elif anfang is not None:
            if z - anfang > bester[1] - bester[0]:
                bester = (anfang, z)
            anfang = None
    y = ya + (bester[0] + bester[1]) / 2 / zoom
    if not mit_tinte:
        return y
    # Zu schmaler Weißraum (eng gesetzte Tabellenzeilen) zählt nicht als sauber
    return y, (minimum if minimum or (bester[1] - bester[0]) >= 1.2 * zoom else 1)


def _reihenband(idx: _SeitenIndex, i_von: int, i_bis: int) -> Rechteck:
    """Markierungsband über ganze visuelle Zeilen; Ober-/Unterkante in der Lücke
    zu den Nachbarzeilen (höchstens 2,5 pt über die Textbox hinaus)."""
    reihen = idx.reihen
    oben, unten = reihen[i_von], reihen[i_bis]
    x0 = min(r.x0 for r in reihen[i_von:i_bis + 1]) - _POLSTER_PT
    x1 = max(r.x1 for r in reihen[i_von:i_bis + 1]) + _POLSTER_PT
    ya = oben.y0 - 2.5
    if i_von > 0:
        ya = max(ya, (reihen[i_von - 1].y0 + reihen[i_von - 1].y1) / 2)
    y0 = _weissraum(idx.pfad, idx.nummer, x0, x1, ya, oben.y0 + 0.3 * (oben.y1 - oben.y0))
    yb = unten.y1 + 2.5
    if i_bis + 1 < len(reihen):
        yb = min(yb, (reihen[i_bis + 1].y0 + reihen[i_bis + 1].y1) / 2)
    y1 = _weissraum(idx.pfad, idx.nummer, x0, x1, unten.y1 - 0.3 * (unten.y1 - unten.y0), yb)
    return (x0, y0, x1, y1)


@dataclass
class _Treffer:
    rechtecke: list

    @property
    def box(self) -> Rechteck:
        return _vereinigung(self.rechtecke)


def _abstand(a: _Treffer, b: _Treffer) -> float:
    """Vertikaler Abstand plus ein Viertel des horizontalen (0 bei Überlappung)."""
    ra, rb = a.box, b.box
    dy = max(0.0, max(ra[1], rb[1]) - min(ra[3], rb[3]))
    dx = max(0.0, max(ra[0], rb[0]) - min(ra[2], rb[2]))
    return dy + 0.25 * dx


# =============================================================================
# Suche im Seitenindex
# =============================================================================

def _vorkommen(text: str, nadel: str):
    start = text.find(nadel)
    while start >= 0:
        yield start
        start = text.find(nadel, start + 1)


def _treffer_aus(idx: _SeitenIndex, indizes) -> _Treffer:
    """Zeichenbereich -> ein Rechteck je Textzeile."""
    je_zeile: dict[int, list] = {}
    for i in indizes:
        je_zeile.setdefault(idx.zeile1[i], []).append(idx.box1[i])
    return _Treffer([_vereinigung(bs) for bs in je_zeile.values()])


def _grenze_ok(idx: _SeitenIndex, start: int, ende: int, zahl: bool) -> bool:
    """Zahlen/Normzitate nur als ganze Einheit (nicht '5 %' in '4,5 %')."""
    t = idx.text1
    if start > 0 and not idx.luecke1[start]:
        v = t[start - 1]
        if zahl and (v.isdigit() or v in ",."):
            return False
        if not zahl and v.isalnum():
            return False
    if ende < len(t) and not idx.luecke1[ende]:
        n = t[ende]
        if zahl and (n.isdigit() or (n == "," and ende + 1 < len(t) and t[ende + 1].isdigit())):
            return False
        if not zahl and n.isalnum():
            return False
    return True


def _finde(idx: _SeitenIndex, text: str, *, grenze: str | None = None,
           stufe2: bool = True) -> list[_Treffer]:
    """Alle Vorkommen eines Begriffs: erst exakt (Stufe 1), sonst gelockert (Stufe 2,
    nur Buchstaben/Ziffern – z. B. 'Frauen: 2,3 %' findet 'Frauen 2,3 %').
    grenze "zahl"/"wort": nur ganze Zahlen bzw. Wörter."""
    n1 = _nadel(text)
    if len(n1) < 2:
        return []
    treffer = []
    for start in _vorkommen(idx.text1, n1):
        ende = start + len(n1)
        if grenze and not _grenze_ok(idx, start, ende, grenze == "zahl"):
            continue
        treffer.append(_treffer_aus(idx, range(start, ende)))
    if treffer or not stufe2:
        return treffer
    n2 = _stufe2(n1)
    if len(n2) < 6:
        return []
    # Satzzeichen am Rand der Nadel (z. B. schließende Klammer) mitnehmen
    kopf = n1[:len(n1) - len(n1.lstrip("([{\"'"))]
    schwanz = n1[len(n1.rstrip(")]}\"'.;:")):]
    for start in _vorkommen(idx.text2, n2):
        a, b = idx.pos2[start], idx.pos2[start + len(n2) - 1]
        while a > 0 and kopf and idx.text1[a - 1] in kopf:
            a -= 1
        while b + 1 < len(idx.text1) and schwanz and idx.text1[b + 1] in schwanz:
            b += 1
        treffer.append(_treffer_aus(idx, range(a, b + 1)))
    return treffer


# =============================================================================
# Suchbegriffe aus der Beschreibung ableiten
# =============================================================================

@dataclass
class _Begriff:
    text: str
    art: str            # zitat | kontext | zahl | paragraf | verweis | gleichung | alter | teil | formel
    markieren: bool
    gewicht: float = 1.0
    ersatz: list = field(default_factory=list)   # Teilbegriffe, falls das Zitat nicht passt
    quelle: "_Begriff | None" = None             # bei Teilbegriffen: das ursprüngliche Zitat
    neben: bool = False                          # Kontext-Stelle: nur dünn, neutral rahmen

    @property
    def ist_neben(self) -> bool:
        return self.neben or (self.quelle is not None and self.quelle.neben)

    def __repr__(self):
        return f"{self.art}{'*' if self.markieren else ''}:{self.text[:40]!r}"


_ZITATE = [
    (re.compile(r"„([^“”„]+)[“”]"), True),
    (re.compile(r"“([^”“„]+)”"), True),
    (re.compile(r'"([^"]+)"'), True),
    (re.compile(r"‚([^‘’]+)[‘’]"), False),
    (re.compile(r"(?<![\w])'([^'\n]{2,}?)'(?![\w])"), False),
]
_ZAHL = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:\.\d{3})+,\d+|\d+,\d+)(?:\s*%)?(?!\d|,\d)"
                   r"|(?<![\d.,])\d+\s*%")
_PARAGRAF = re.compile(r"§§?\s*\d+[a-z]?(?:\s*Abs\.\s*\d+)?(?:\s*(?:Satz|S\.)\s*\d+)?"
                       r"(?:\s*Nrn?\.\s*\d+)?\s*[A-ZÄÖÜ][A-Za-zÄÖÜäöü]+(?:\s+[IVX]+\b)?")
_GLEICHUNG = re.compile(r"(?:Gleichung(?:en)?|Gl\.)\s*\(?(\d{1,3})\)?")
_ALTER = re.compile(r"\bAlter\s+(\d{1,3})\b")
_TEIL = re.compile(r"\bbei\s+((?:Abschnitt|Anlage|Anhang|Kapitel)\s+\d+(?:\.\d+)*)")
# Soll-/Referenzwerte: Zahlen und Zitate nach diesen Wörtern (im selben Satzteil)
# werden nicht markiert – sie stehen gerade *nicht* (so) im Dokument.
_ERWARTET = re.compile(r"Referenz|ergibt|ergeben|richtig|korrekt|stimmt nicht mit|statt\b|"
                       r"erwartet|einschlägig|Mindestsatz|gesetzlich|wäre|müsste|lautet",
                       re.IGNORECASE)
# L-03 (Format des Notebooks, Zelle 14):
#   Widerspruch „Thema“: <Stelle A> nennt „Wert A“, <Stelle B> dagegen „Wert B“ – Begründung
# Markiert werden nur Wert A und Wert B; Ortsangaben und Begründung dienen der Ortung.
_L03_MUSTER = re.compile(r"Widerspruch „(?P<thema>.*?)“: (?P<stelle_a>.*?) nennt „(?P<wert_a>.*?)“, "
                         r"(?P<stelle_b>.*?) dagegen „(?P<wert_b>.*?)“"
                         r"(?:\s+[–—-]\s+(?P<begruendung>.*))?\s*$", re.S)
# Vorangestellte Bezeichnung in Formel-Zitaten: „Gleichung (30): V_x(b) = …“
_LABEL = re.compile(r"^\s*(?:Gleichung|Gl\.|Formel)\s*\(?\d{1,3}\)?\s*:\s*")
# Kurzes Formel-Fragment mit Vorzeichen, z. B. „+γ_x“, „− γx“ (Vorzeichenbefunde)
_FRAGMENT = re.compile(r"(?<![\w)\]])([+−-]\s?[A-Za-zΑ-Ωα-ω\U0001D400-\U0001D7FF]"
                       r"(?:_?\{?[A-Za-z0-9]{1,3}\}?)?)(?![\w(])")


def _ist_erwartet(beschreibung: str, pos: int) -> bool:
    vor = beschreibung[max(0, pos - 70):pos]
    for trenner in (", ", "; ", ". "):
        k = vor.rfind(trenner)
        if k >= 0:
            vor = vor[k + len(trenner):]
    return bool(_ERWARTET.search(vor))


def _ohne_erlaeuterungen(text: str) -> str:
    """Entfernt Klammerzusätze mit Fließtext, z. B. '(Gleichung 30)' oder
    '(γx wird addiert)' – Formelklammern wie '(b)' oder '(1-(σ+Ωx))' bleiben."""
    ergebnis, stapel = [], []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "(":
            stapel.append(len(ergebnis))
            ergebnis.append(c)
        elif c == ")" and stapel:
            anfang = stapel.pop()
            ergebnis.append(c)
            inhalt = "".join(ergebnis[anfang + 1:-1])
            if re.search(r"[A-Za-zÄÖÜäöüß]{3,}", re.sub(r"\([^()]*\)", "", inhalt)):
                del ergebnis[anfang:]
                while ergebnis and ergebnis[-1] == " ":
                    ergebnis.pop()
        else:
            ergebnis.append(c)
        i += 1
    return re.sub(r"\s{2,}", " ", "".join(ergebnis)).strip()


def _formelstuecke(text: str) -> list[str]:
    """Zusammenhängende Formel-Abschnitte eines Zitats (ohne Fließtext-Wörter)."""
    stuecke, aktuell = [], []
    for tok in text.split():
        rein = tok.strip(".,:;!?()[]\"'„“”")
        ist_wort = len(rein) >= 3 and rein.isalpha() and not any(_ist_mathe(c) for c in rein)
        if ist_wort:
            if aktuell:
                stuecke.append(" ".join(aktuell))
            aktuell = []
        else:
            aktuell.append(tok)
    if aktuell:
        stuecke.append(" ".join(aktuell))
    return [s.strip(" ,;:") for s in stuecke
            if len(_nadel(s)) >= 5 and re.search(r"[\d=+·/\-−]|[Α-ω]", s)]


def _ersatzbegriffe(zitat: str) -> list[_Begriff]:
    """Teilbegriffe eines nicht wörtlich gefundenen Zitats."""
    ersatz = []
    gesehen = set()

    def neu(text, art, stufe2_erlaubt=True):
        n = _nadel(text)
        if len(n) < 3 or n in gesehen:
            return
        gesehen.add(n)
        b = _Begriff(text, art, True)
        if not stufe2_erlaubt:
            b.art = "formel"
        ersatz.append(b)

    kurz = _ohne_erlaeuterungen(zitat)
    if kurz != zitat:
        neu(kurz, "zitat")
    for teil in re.split(r"\s+(?:vs\.|bzw\.|sowie|statt|und|oder)\s+|;\s*|\s+[–—]\s+", zitat):
        if teil and teil != zitat:
            neu(teil, "zitat")
            neu(_ohne_erlaeuterungen(teil), "zitat")
    for stueck in _formelstuecke(kurz):
        neu(stueck, "formel", stufe2_erlaubt=False)
    for m in _ZAHL.finditer(zitat):
        neu(m.group(0), "zahl")
    for m in _PARAGRAF.finditer(zitat):
        neu(m.group(0), "paragraf")
    return ersatz


def _fragmente(text: str) -> list[str]:
    """Kurze Formel-Fragmente mit Vorzeichen („+γ_x“) in einem Befundtext."""
    return list(dict.fromkeys(m.group(1) for m in _FRAGMENT.finditer(text)))


def _teilausdruck(formel: str, fragment: str) -> str | None:
    """Kleinster Klammerausdruck einer Formel, der das Fragment enthält – z. B.
    „12·(1−(σ+Ω_x))·b + γ_x“ in „V_x(b) = G·A_x − [12·(1−(σ+Ω_x))·b + γ_x]·a_x“
    für „+γ_x“. So wird bei Vorzeichenfehlern der betroffene Term markiert
    statt der ganzen Gleichung. None, wenn das Fragment nicht in der Formel
    steht oder kein passender Klammerausdruck existiert."""
    nf = _nadel(fragment)
    if len(nf) < 2 or nf not in _nadel(formel):
        return None
    paare, stapel = [], []
    for i, c in enumerate(formel):
        if c in "([":
            stapel.append(i)
        elif c in ")]" and stapel:
            paare.append((stapel.pop(), i))
    beste = None
    for j, i in paare:
        inhalt = formel[j + 1:i].strip()
        ni = _nadel(inhalt)
        if nf in ni and len(ni) >= len(nf) + 4 and (beste is None
                                                     or len(ni) < len(_nadel(beste))):
            beste = inhalt
    return beste


def _wert_begriff(wert: str, stelle: str = "") -> _Begriff:
    """Markierbarer Begriff für einen zitierten Wert (L-03: Wert A / Wert B).
    Ersatz: Teilausdruck einer in der Ortsangabe genannten Formel, der das
    Fragment des Werts enthält (Wert „+γx im Klammerausdruck“ zur Formel
    „Vx(b) = G·Ax − [12·(1−(σ+Ωx))·b + γx]·ax“), dann die üblichen Teilbegriffe."""
    art = "zahl" if _ZAHL.fullmatch(wert.strip()) else "zitat"
    b = _Begriff(wert.strip(), art, True)
    teile = []
    for formel in (f for f in _formelstuecke(stelle) if "=" in f):
        for frag in _fragmente(wert):
            if (t := _teilausdruck(formel, frag)) and t not in teile:
                teile.append(t)
    b.ersatz = [_Begriff(t, "formel", True) for t in teile] + (
        _ersatzbegriffe(wert) if art == "zitat" else [])
    for e in b.ersatz:
        e.quelle = b
    return b


def _begriffe_l03(m: re.Match) -> list[_Begriff]:
    """Suchbegriffe eines L-03-Widerspruchs: markiert werden nur die beiden
    zitierten Werte; Zitate, Formeln, Zahlen und der Wortlaut in den
    Ortsangaben („Anhang 5, Schritt 3: Rechenansatz P43 = …“) sowie die
    Begründung dienen nur der Ortung (Kontext)."""
    begriffe: list[_Begriff] = []
    gesehen: set[str] = set()

    def kontext(text, art="kontext", gewicht=0.8):
        n = _nadel(text)
        if len(n) >= 3 and n not in gesehen:
            gesehen.add(n)
            begriffe.append(_Begriff(text.strip(), art, False, gewicht))

    if len(_nadel(m.group("thema"))) >= 3:
        kontext(m.group("thema"), gewicht=0.5)
    for teil in ("a", "b"):
        wert, stelle = m.group(f"wert_{teil}"), m.group(f"stelle_{teil}")
        if len(_nadel(wert)) >= 2:
            begriffe.append(_wert_begriff(wert, stelle))
            gesehen.add(_nadel(wert))
            if "??" in wert:
                begriffe.append(_Begriff("??", "verweis", True))
    for teil in ("a", "b"):
        stelle = m.group(f"stelle_{teil}")
        for q in re.finditer(r"„([^“”„]+)[“”]|‚([^‘’]+)[‘’]|(?<![\w])'([^'\n]{3,}?)'(?![\w])",
                             stelle):
            kontext(next(g for g in q.groups() if g), gewicht=1.0)
        for formel in _formelstuecke(stelle):
            if "=" in formel:
                kontext(formel, gewicht=1.0)
        # Wortlaut nach dem letzten Doppelpunkt („Begründung im selben Satz: Eine …“)
        if ": " in stelle:
            wortlaut = stelle.rsplit(": ", 1)[1]
            if len(wortlaut.split()) >= 3:
                kontext(wortlaut, gewicht=1.0)
        for z in _ZAHL.finditer(stelle):
            kontext(z.group(0), "zahl", 0.4)
        for p in _PARAGRAF.finditer(stelle):
            kontext(p.group(0), "paragraf", 0.4)
    begruendung = m.group("begruendung") or ""
    for q in re.finditer(r"„([^“”„]+)[“”]|‚([^‘’]+)[‘’]", begruendung):
        kontext(next(g for g in q.groups() if g), gewicht=0.5)
    for z in _ZAHL.finditer(begruendung):
        kontext(z.group(0), "zahl", 0.4)
    for g in _GLEICHUNG.finditer(m.group(0)):
        kontext(f"({g.group(1)})", "gleichung", 0.8)
    return begriffe


def _l05_verfeinern(begriffe: list[_Begriff], problem: str) -> None:
    """L-05 („Formel „…“: Problem – Begründung“): Bezeichnung „Gleichung (30):“
    vor der Formel entfernen; nennt das Problem ein Fragment der Formel
    („+γ_x“), nur den kleinsten Klammerausdruck damit markieren (Rückfall: die
    ganze Formel); zitierte Gegenstellen mit Formel und Fließtext („'12(1−…)b
    − γ_x den Jahresbetrag …'“) auf den Formelteil kürzen (dünner Rahmen)."""
    formel_b = next((b for b in begriffe if b.art == "zitat" and b.markieren), None)
    if formel_b is None:
        return
    formel = _LABEL.sub("", formel_b.text)
    if formel != formel_b.text:
        formel_b.text = formel
        formel_b.ersatz = _ersatzbegriffe(formel)
        for e in formel_b.ersatz:
            e.quelle = formel_b
    for b in begriffe:
        if b.art == "kontext" and not b.markieren and len(b.text.split()) >= 4:
            stuecke = _formelstuecke(b.text)
            if stuecke:
                b.text = stuecke[0]
    formel_kurz = _ohne_erlaeuterungen(formel)
    for frag in _fragmente(problem):
        teil = _teilausdruck(formel_kurz, frag)
        if not teil:
            continue
        voll = _Begriff(formel_b.text, "zitat", True)
        neu = _Begriff(teil, "formel", True, 1.0)
        neu.ersatz = [voll] + [e for e in formel_b.ersatz]
        for e in neu.ersatz:
            e.quelle = neu
        formel_b.markieren, formel_b.art, formel_b.ersatz = False, "kontext", []
        begriffe.insert(0, neu)
        return


def _begriffe_ableiten(check_id: str, beschreibung: str) -> list[_Begriff]:
    if check_id == "L-03" and (m := _L03_MUSTER.search(beschreibung)):
        return _begriffe_l03(m)
    begriffe: list[_Begriff] = []
    # Bei LLM-Widersprüchen/Formelbefunden folgt nach " – " die Begründung:
    # dort erwähnte Zahlen dienen nur der Ortung.
    kern_ende = len(beschreibung)
    if check_id in ("L-03", "L-05"):
        k = beschreibung.find(" – ")
        if k > 0:
            kern_ende = k
    elif check_id == "L-04":
        # „Normzitat „§ …“ passt nicht …“: markiert wird nur das zitierte Normzitat
        m = re.search(r"„[^“”]+[“”]", beschreibung)
        if m:
            kern_ende = m.end()

    belegt = []   # Zeichenbereiche der Zitate (Zahlen darin nicht doppelt zählen)
    for muster, markierbar in _ZITATE:
        for m in muster.finditer(beschreibung):
            if any(a <= m.start() < b for a, b in belegt):
                continue
            belegt.append((m.start(), m.end()))
            inhalt = m.group(1).strip()
            if len(_nadel(inhalt)) < 3:
                continue
            vor = beschreibung[max(0, m.start() - 14):m.start()]
            ist_auszug = inhalt.startswith(("...", "…")) or inhalt.endswith(("...", "…"))
            # Themen-Zitat: „Jahresnettobeitrag P43“: … bzw. Widerspruch „…“: …
            ist_thema = ((m.start() <= 1 and beschreibung[m.end():m.end() + 1] == ":")
                         or vor.rstrip().endswith("Widerspruch"))
            markieren = (markierbar and not ist_auszug and not ist_thema
                         and m.start() < kern_ende
                         and not _ist_erwartet(beschreibung, m.start()))
            if ist_auszug or not markierbar or ist_thema:
                b = _Begriff(inhalt, "kontext", False, 1.0 if ist_auszug else 0.5)
            else:
                b = _Begriff(inhalt, "zitat", markieren, 1.0 if markieren else 0.5)
                if markieren:
                    b.ersatz = _ersatzbegriffe(inhalt)
                    for e in b.ersatz:
                        e.quelle = b
            begriffe.append(b)
            if "??" in inhalt:
                begriffe.append(_Begriff("??", "verweis", True))

    def ausserhalb(pos):
        return not any(a <= pos < b for a, b in belegt)

    for m in _ZAHL.finditer(beschreibung):
        if ausserhalb(m.start()):
            markieren = m.start() < kern_ende and not _ist_erwartet(beschreibung, m.start())
            begriffe.append(_Begriff(m.group(0), "zahl", markieren, 1.0 if markieren else 0.4))
    for m in _PARAGRAF.finditer(beschreibung):
        if ausserhalb(m.start()):
            markieren = m.start() < kern_ende and not _ist_erwartet(beschreibung, m.start())
            begriffe.append(_Begriff(m.group(0), "paragraf", markieren, 1.0 if markieren else 0.4))
    if "??" in beschreibung and not any(b.art == "verweis" for b in begriffe):
        begriffe.append(_Begriff("??", "verweis", True))
    for m in _GLEICHUNG.finditer(beschreibung):
        begriffe.append(_Begriff(f"({m.group(1)})", "gleichung", False, 0.8))
    for m in _ALTER.finditer(beschreibung):
        begriffe.append(_Begriff(m.group(1), "alter", False, 1.0))
    if check_id == "V-03":
        for m in _TEIL.finditer(beschreibung):
            begriffe.append(_Begriff(m.group(1) + ":", "teil", True))
    if check_id == "L-05":
        _l05_verfeinern(begriffe, beschreibung[:kern_ende])
    # Normzitat-Befunde („Begriff“ wird mit „§ 4 VAG“ belegt): Fehlerstück ist
    # das Normzitat; zitierte Fachbegriffe sind nur Kontext (dünn gerahmt).
    normzitate = [b for b in begriffe if b.art == "zitat" and b.markieren
                  and _PARAGRAF.fullmatch(b.text.strip())]
    if normzitate:
        for b in begriffe:
            if b.art == "zitat" and b.markieren and b not in normzitate:
                b.neben = True
    return begriffe


def _suche_begriff(idx: _SeitenIndex, b: _Begriff) -> list[_Treffer]:
    if b.art == "zahl":
        treffer = _finde(idx, b.text, grenze="zahl", stufe2=False)
        if not treffer and "." in b.text:        # "4.676,48" steht im Dokument als "4676,48"
            treffer = _finde(idx, b.text.replace(".", ""), grenze="zahl", stufe2=False)
        m = re.fullmatch(r"(\d+)\s*%", b.text.strip())
        if not treffer and m:                    # "5 %" steht oft als "5,0 %" im Dokument
            treffer = _finde(idx, f"{m.group(1)},0 %", grenze="zahl", stufe2=False)
        return treffer
    if b.art == "paragraf":
        return _finde(idx, b.text, grenze="wort", stufe2=False)
    if b.art == "verweis":
        return [_treffer_aus(idx, range(*m.span())) for m in re.finditer(
            r"(?:Abschnitt|Anlage|Anhang|Kapitel|Gleichung|Tabelle|Abbildung|Seite)?\?\?",
            idx.text1)]
    if b.art == "gleichung":
        # Gleichungsnummer steht rechts außen in ihrer Reihe
        ergebnis = []
        for t in _finde(idx, b.text, stufe2=False):
            r = idx.reihe_von(t.box)
            if r is not None and t.box[2] >= idx.reihen[r].x1 - 3:
                ergebnis.append(t)
        return ergebnis
    if b.art == "alter":
        ergebnis = []
        for r in idx.reihen:
            if len(r.worte) >= 3 and r.worte[0][4] == b.text and r.ist_daten:
                ergebnis.append(_Treffer([tuple(r.worte[0][:4])]))
        return ergebnis
    if b.art == "teil":
        return _finde(idx, b.text, stufe2=False)
    if b.art == "formel":
        return _finde(idx, b.text, stufe2=False)
    # Zitat oder Kontext
    treffer = _finde(idx, b.text)
    if treffer or b.art != "kontext":
        return treffer
    return _finde_auszug(idx, b.text)


def _finde_auszug(idx: _SeitenIndex, text: str, min_zeichen: int = 15) -> list[_Treffer]:
    """Textauszug ('...xyz...'), der nicht wörtlich passt: längstes passendes
    Fenster aufeinanderfolgender Wörter (mindestens 3 Wörter / min_zeichen Zeichen)."""
    for stueck in re.split(r"\.\.\.|…", text):
        worte = stueck.split()
        for k in range(len(worte), 2, -1):
            for i in range(0, len(worte) - k + 1):
                kandidat = " ".join(worte[i:i + k])
                if len(_nadel(kandidat)) < min_zeichen:
                    continue
                treffer = _finde(idx, kandidat, stufe2=False)
                if treffer:
                    return treffer
    return []


# =============================================================================
# Auswahl passender Treffer und Bildung des Ausschnitts
# =============================================================================

def _geschwister(h: _Treffer, alle: list[_Treffer]) -> list[_Treffer]:
    """Weitere Treffer desselben Begriffs in derselben visuellen Zeile (z. B. vier Tabellenzellen)."""
    y = (h.box[1] + h.box[3]) / 2
    return [t for t in alle if t is not h and abs((t.box[1] + t.box[3]) / 2 - y) < 3]


def _auswahl(gefunden: list[tuple[_Begriff, list[_Treffer]]]):
    """Wählt zueinander passende Treffer: Anker = seltenster Markier-Begriff."""
    markier = [(b, t) for b, t in gefunden if b.markieren and t]
    kontext = [(b, t) for b, t in gefunden if not b.markieren and t]
    if not markier:
        if not kontext:
            return None
        # nur Kontext gefunden: den spezifischsten Kontextbegriff markieren
        kontext.sort(key=lambda bt: (len(bt[1]), -len(_nadel(bt[0].text))))
        if kontext[0][0].art in ("gleichung", "alter"):
            return [], kontext
        markier, kontext = [kontext[0]], kontext[1:]

    anker_b, anker_t = min(markier, key=lambda bt: (len(bt[1]), -len(_nadel(bt[0].text))))
    andere = [(b, t) for b, t in markier + kontext if b is not anker_b]

    def guete(h):
        return sum(b.gewicht * math.exp(-min(_abstand(h, x) for x in t) / 80.0)
                   for b, t in andere)

    anker = max(anker_t, key=guete)
    gew_markier = [(anker_b, [anker] + _geschwister(anker, anker_t))]
    for b, t in markier:
        if b is anker_b:
            continue
        naechster = min(t, key=lambda x: _abstand(anker, x))
        if _abstand(anker, naechster) <= _MAX_ABSTAND_PT:
            gew_markier.append((b, [naechster] + _geschwister(naechster, t)))
    gew_kontext = []
    for b, t in kontext:
        naechster = min(t, key=lambda x: _abstand(anker, x))
        if _abstand(anker, naechster) <= _MAX_KONTEXT_PT:
            gew_kontext.append((b, [naechster]))
    return gew_markier, gew_kontext


def _tabellenkopf(idx: _SeitenIndex, erste_reihe: int) -> int | None:
    """Kopfzeile oberhalb eines Blocks von Tabellen-Datenzeilen."""
    i = erste_reihe
    if not idx.reihen[i].ist_daten:
        return None
    while i - 1 >= 0 and idx.reihen[i - 1].ist_daten:
        i -= 1
    k = i - 1
    if k < 0:
        return None
    kopf = idx.reihen[k]
    if kopf.ist_daten or not kopf.worte or any(len(w[4]) > 18 for w in kopf.worte):
        return None
    if idx.reihen[i].y0 - kopf.y1 > 25:
        return None
    return k


def _ausschnitt_bilden(idx: _SeitenIndex, markierungen: list, kontext: list,
                       auffuellen: bool = True, polster: int | None = None):
    """Ausschnitt: betroffene Reihen plus wenig Kontext (typisch 4–8 Zeilen),
    Breite = Textspalte bzw. Tabellenbreite. Liefert (ausschnitt, kopf, streifen).

    Liegen die Treffer weit auseinander (z. B. zwei Werte 130 pt voneinander
    entfernt), werden statt eines hohen Ausschnitts mit unbeteiligtem Text
    dazwischen mehrere schmale Streifen gebildet (je Treffergruppe die Zeile
    plus eine Zeile Kontext darüber); beim Rendern gestrichelt getrennt.
    polster: feste Zahl an Kontextzeilen (sonst nach Anzahl der Zeilen)."""
    reihen = idx.reihen
    m_idx = sorted({i for r in markierungen if (i := idx.reihe_von(r)) is not None})
    if not m_idx:
        box = _vereinigung(markierungen)
        return _rand_und_breite(idx, box), None, []
    k_idx = sorted({i for r in kontext if (i := idx.reihe_von(r)) is not None
                    and min(abs(i - j) for j in m_idx) <= 4})

    # Gruppen weit auseinander liegender Trefferzeilen -> eigene Streifen.
    # Kontextzeilen schließen keine Lücke; sie kommen nur zu einer Gruppe,
    # wenn sie höchstens zwei Zeilen davon entfernt stehen.
    gruppen = [[m_idx[0]]]
    for i in m_idx[1:]:
        vorher = gruppen[-1][-1]
        if i - vorher >= _STREIFEN_ZEILEN and reihen[i].y0 - reihen[vorher].y1 > _STREIFEN_ABSTAND_PT:
            gruppen.append([i])
        else:
            gruppen[-1].append(i)
    if len(gruppen) > 1:
        for k in k_idx:
            naechste = min(gruppen, key=lambda g: min(abs(k - j) for j in g))
            if min(abs(k - j) for j in naechste) <= 2:
                naechste.append(k)
        return _streifen_bilden(idx, markierungen, [sorted(set(g)) for g in gruppen])

    alle = sorted(set(m_idx + k_idx))
    lo, hi = min(alle), max(alle)
    if auffuellen:
        n = hi - lo + 1
        if polster is None:
            polster = 2 if n <= 2 else (1 if n <= 7 else 0)
            # Abgesetzte Formel (hohe Zeile mit Bruch): eine Zeile Kontext genügt
            if n <= 2 and max(reihen[i].y1 - reihen[i].y0 for i in m_idx) > 18:
                polster = 1
        lo, hi = max(0, lo - polster), min(len(reihen) - 1, hi + polster)

    # Tabellen: Spaltenkopf mitzeigen – direkt, wenn nah; sonst als Kopf-Streifen
    kopf_idx = None
    k = _tabellenkopf(idx, m_idx[0])
    if k is not None:
        if lo - k <= 3:
            lo = min(lo, k)
        else:
            kopf_idx = k
            while lo < m_idx[0] and not reihen[lo].ist_daten:   # keine Fremdzeilen unter dem Kopf
                lo += 1

    x0 = min(min(r.x0 for r in reihen[lo:hi + 1]), min(m[0] for m in markierungen))
    x1 = max(max(r.x1 for r in reihen[lo:hi + 1]), max(m[2] for m in markierungen))
    y0, y1 = _kanten(idx, lo, hi, x0, x1, kern=(min(alle), max(alle)))
    # Markierungsrahmen (ca. 1,5 pt) muss vollständig im Bild liegen
    y0 = min(y0, min(m[1] for m in markierungen) - 2)
    y1 = max(y1, max(m[3] for m in markierungen) + 2)
    ausschnitt = _rand_und_breite(idx, (x0, y0, x1, y1), rand_y=False)
    kopf = None
    if kopf_idx is not None:
        k0, k1 = _kanten(idx, kopf_idx, kopf_idx, ausschnitt[0], ausschnitt[2])
        kopf = (ausschnitt[0], round(k0, 2), ausschnitt[2], round(k1, 2))
    return ausschnitt, kopf, []


def _streifen_bilden(idx: _SeitenIndex, markierungen: list, gruppen: list):
    """Mehrere schmale Streifen (je Treffergruppe) statt eines hohen Ausschnitts."""
    reihen = idx.reihen
    bereiche = []
    for g in gruppen:
        lo, hi = min(g), max(g)
        if lo == hi:                     # einzelne Zeile: eine Zeile Kontext darüber
            lo = max(0, lo - 1)
        if bereiche and lo <= bereiche[-1][1] + 1:
            bereiche[-1] = (bereiche[-1][0], max(hi, bereiche[-1][1]), bereiche[-1][2] + g)
        else:
            bereiche.append((lo, hi, list(g)))
    x0 = min(min(r.x0 for lo, hi, _ in bereiche for r in reihen[lo:hi + 1]),
             min(m[0] for m in markierungen))
    x1 = max(max(r.x1 for lo, hi, _ in bereiche for r in reihen[lo:hi + 1]),
             max(m[2] for m in markierungen))
    streifen = []
    for lo, hi, g in bereiche:
        y0, y1 = _kanten(idx, lo, hi, x0, x1, kern=(min(g), max(g)))
        eigene = [m for m in markierungen if (i := idx.reihe_von(m)) is not None and lo <= i <= hi]
        if eigene:
            y0 = min(y0, min(m[1] for m in eigene) - 2)
            y1 = max(y1, max(m[3] for m in eigene) + 2)
        streifen.append((round(y0, 2), round(y1, 2)))
    ausschnitt = _rand_und_breite(idx, (x0, streifen[0][0], x1, streifen[-1][1]), rand_y=False)
    return ausschnitt, None, streifen


def _kanten(idx: _SeitenIndex, lo: int, hi: int, x0: float, x1: float,
            kern: tuple[int, int] | None = None) -> tuple[float, float]:
    """Ober-/Unterkante eines Ausschnitts über den Reihen lo..hi – jeweils in der
    tintenfreien Lücke zur Nachbarzeile (höchstens 6 pt über die Textbox hinaus).

    kern = (erste, letzte) Zeile, die sicher dazugehören: Liegt an der Kante
    keine saubere Lücke (eng gesetzte Tabellenzeilen – der Schnitt träfe Indizes
    oder Unterlängen), wird zuerst eine Kontextzeile weniger, dann eine mehr
    versucht."""
    reihen = idx.reihen

    def oben_kante(i):
        oben = reihen[i]
        ya = oben.y0 - 6
        if i > 0:
            ya = max(ya, (reihen[i - 1].y0 + reihen[i - 1].y1) / 2)
        return _weissraum(idx.pfad, idx.nummer, x0, x1, ya,
                          oben.y0 + 0.25 * (oben.y1 - oben.y0), mit_tinte=True)

    def unten_kante(i):
        unten = reihen[i]
        yb = unten.y1 + 6
        if i + 1 < len(reihen):
            yb = min(yb, (reihen[i + 1].y0 + reihen[i + 1].y1) / 2)
        return _weissraum(idx.pfad, idx.nummer, x0, x1,
                          unten.y1 - 0.25 * (unten.y1 - unten.y0), yb, mit_tinte=True)

    kandidaten_lo, kandidaten_hi = [lo], [hi]
    if kern is not None:
        if lo + 1 <= kern[0]:
            kandidaten_lo.append(lo + 1)
        if lo - 1 >= 0:
            kandidaten_lo.append(lo - 1)
        if hi - 1 >= kern[1] and hi - 1 >= lo:
            kandidaten_hi.append(hi - 1)
        if hi + 1 < len(reihen):
            kandidaten_hi.append(hi + 1)
    ergebnisse = [oben_kante(i) for i in kandidaten_lo[:1]]
    for i in kandidaten_lo[1:]:
        if ergebnisse[0][1] == 0:
            break
        y, t = oben_kante(i)
        if t == 0:
            ergebnisse[0] = (y, t)
            break
    y0 = ergebnisse[0][0]
    unten = unten_kante(kandidaten_hi[0])
    for i in kandidaten_hi[1:]:
        if unten[1] == 0:
            break
        y, t = unten_kante(i)
        if t == 0:
            unten = (y, t)
            break
    return y0, unten[0]


def _rand_und_breite(idx: _SeitenIndex, box, rand_y: bool = True) -> Rechteck:
    x0, y0, x1, y1 = box
    x0, x1 = x0 - _RAND_PT, x1 + _RAND_PT
    if rand_y:
        y0, y1 = y0 - _RAND_PT, y1 + _RAND_PT
    if x1 - x0 < _MIN_BREITE_PT:
        mitte = (x0 + x1) / 2
        x0, x1 = mitte - _MIN_BREITE_PT / 2, mitte + _MIN_BREITE_PT / 2
    s = idx.rect
    if x0 < s.x0:
        x0, x1 = s.x0, min(s.x1, x1 + (s.x0 - x0))
    if x1 > s.x1:
        x0, x1 = max(s.x0, x0 - (x1 - s.x1)), s.x1
    return (round(x0, 2), round(max(s.y0, y0), 2), round(x1, 2), round(min(s.y1, y1), 2))


# =============================================================================
# Strategien
# =============================================================================

def _fund_suchbegriffe(pfad: str, nummer: int, check_id: str, begriffe: list[_Begriff],
                       polster: int | None = None):
    """Allgemeiner Weg über Suchbegriffe. Liefert (Fundstelle, Güte) oder None."""
    idx = _seitenindex(pfad, nummer)
    gefunden = []
    for b in begriffe:
        treffer = _suche_begriff(idx, b)
        if treffer:
            gefunden.append((b, treffer))
            continue
        vorher = len(gefunden)
        for e in b.ersatz:
            t = _suche_begriff(idx, e)
            if t:
                gefunden.append((e, t))
        if len(gefunden) == vorher and b.markieren and b.art == "zitat" \
                and len(b.text.split()) >= 4:
            # Umschriebenes Zitat (Sprachmodell kürzt oder stellt um): längstes
            # wörtlich passendes Wortfenster, z. B. „oberhalb der beobachteten
            # Rohwerte“ aus „w̄neu oberhalb der beobachteten Rohwerte“
            t = _finde_auszug(idx, b.text, min_zeichen=18)
            if t:
                gefunden.append((b, t))
    auswahl = _auswahl(gefunden)
    if auswahl is None:
        return None
    gew_markier, gew_kontext = auswahl
    methode = "Suchbegriff"
    eintraege = []    # (Begriff, gepolsterte Rechtecke eines Treffers)
    for b, treffer in gew_markier:
        for t in treffer:
            rs = list(t.rechtecke)
            if b.art == "verweis":
                rs = _mit_vorwort(idx, rs)
            if check_id == "V-03" or b.art == "teil":
                eintraege.append((b, _ganze_reihe(idx, rs)))     # Zeilenband, schon fertig
                continue
            if b.art in ("formel", "zitat"):
                rs = _je_reihe(idx, rs)       # Bruch, Indizes: ein Kasten je Zeile
                if "=" in b.text or check_id == "L-05":
                    rs = _bruch_erweitern(idx, rs)
            eintraege.append((b, [_polstern(r, _POLSTER_PT) for r in rs]))

    # Teilbegriffe desselben Zitats in derselben Zeile zu einem Kasten zusammenfassen
    # (z. B. „P43 = … = 1901,0070 · 44,1833 = 4667,48 EUR“ über einem Bruch)
    gruppen: dict[tuple, list] = {}
    for nr, (b, rs) in enumerate(eintraege):
        if b.quelle is not None and len(rs) == 1:
            gruppen.setdefault((id(b.quelle), idx.reihe_von(rs[0])), []).append(nr)
    zusammengefasst, markierungen, neben = set(), [], []
    for nummern in gruppen.values():
        if len({id(eintraege[n][0]) for n in nummern}) < 2:
            continue
        box = _vereinigung(eintraege[n][1][0] for n in nummern)
        if "=" in eintraege[nummern[0]][0].quelle.text:
            box = _polstern(_bruch_erweitern(idx, [_polstern(box, -_POLSTER_PT)])[0],
                            _POLSTER_PT)
        (neben if eintraege[nummern[0]][0].ist_neben else markierungen).append(box)
        zusammengefasst.update(nummern)
    for nr, (b, rs) in enumerate(eintraege):
        if nr not in zusammengefasst:
            (neben if b.ist_neben else markierungen).extend(rs)
    if not markierungen:                 # nur Kontext-Stellen gefunden: diese markieren
        markierungen, neben = neben, []
    if check_id == "L-05" and markierungen:
        # Formelbefunde: zitierte Gegenstellen in '…' (z. B. die Legende mit
        # „− γx“ zu „+ γx“ in der Gleichung) dünn mitrahmen, sofern sie nicht
        # ohnehin in der markierten Formel liegen.
        for b, ts in gew_kontext:
            if b.art != "kontext" or not re.search(r"[=+−·\-]", b.text) or len(_nadel(b.text)) < 4:
                continue
            for t in ts:
                box = _polstern(t.box, _POLSTER_PT)
                if any(_flaeche(_schnitt(box, m)) > 0.5 * _flaeche(box) for m in markierungen):
                    continue                      # liegt ohnehin in der Markierung
                if any(_flaeche(_schnitt(box, m)) > 0.5 * _flaeche(m) for m in markierungen):
                    continue                      # umschließt die Markierung (ganze Gleichung)
                neben.append(box)

    # Ortungshilfen mit geringem Gewicht (Zahlen aus der Begründung) vergrößern
    # den Ausschnitt nicht – sonst stünde unbeteiligter Text mit im Bild.
    kontext_rechtecke = [r for b, ts in gew_kontext if b.gewicht > 0.45
                         for t in ts for r in t.rechtecke]
    if not markierungen:
        # nur Gleichungsnummer bzw. Tabellenalter gefunden: ganze Zeile markieren
        for art, name in (("gleichung", "Gleichung"), ("alter", "Suchbegriff")):
            zeilen = [t for b, ts in gew_kontext if b.art == art for t in ts]
            if zeilen:
                markierungen = _ganze_reihe(idx, zeilen[0].rechtecke)
                methode = name
                break
        else:
            return None
    ausschnitt, kopf, streifen = _ausschnitt_bilden(idx, markierungen + neben,
                                                    kontext_rechtecke, polster=polster)
    guete = len(gew_markier) + 0.5 * len(gew_kontext)
    hinweis = "gefunden: " + ", ".join(
        f"„{b.text[:40]}“" for b, _ in gew_markier + gew_kontext)
    return Fundstelle(nummer, _verschmelzen(markierungen), ausschnitt, methode, kopf,
                      hinweis, streifen=streifen,
                      nebenrechtecke=_verschmelzen(neben)), guete


def _mit_vorwort(idx: _SeitenIndex, rechtecke: list) -> list:
    """'??' samt vorangehendem Wort (z. B. 'Abschnitt ??')."""
    ergebnis = []
    for r in rechtecke:
        mitte = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        reihe = idx.reihe_von(r)
        neu = r
        if reihe is not None:
            worte = idx.reihen[reihe].worte
            for i, w in enumerate(worte):
                if w[0] <= mitte[0] <= w[2] and i > 0 and r[0] - worte[i - 1][2] < 8:
                    if worte[i - 1][4].strip("(").isalpha():
                        neu = _vereinigung([r, tuple(worte[i - 1][:4])])
                    break
        ergebnis.append(neu)
    return ergebnis


def _ganze_reihe(idx: _SeitenIndex, rechtecke: list) -> list:
    """Markierung auf die ganze visuelle Zeile ausdehnen (Inhaltsverzeichnis,
    Formelzeile); Ober-/Unterkante liegen in der Lücke zu den Nachbarzeilen."""
    ergebnis = []
    for r in rechtecke:
        i = idx.reihe_von(r)
        if i is None:
            ergebnis.append(_polstern(r, _POLSTER_PT))
        else:
            ergebnis.append(_reihenband(idx, i, i))
    return ergebnis


def _je_reihe(idx: _SeitenIndex, rechtecke: list) -> list:
    """Rechtecke eines Treffers, die in derselben visuellen Zeile liegen (Zähler,
    Nenner und Hauptzeile eines Bruchs, Hoch-/Tiefstellungen), zu einem
    zusammenfassen – sonst zerfiele eine Formel in mehrere Kästen."""
    je_reihe: dict = {}
    for r in rechtecke:
        je_reihe.setdefault(idx.reihe_von(r), []).append(r)
    ergebnis = []
    for reihe, rs in je_reihe.items():
        ergebnis += rs if reihe is None else [_vereinigung(rs)]
    return ergebnis


def _bruch_erweitern(idx: _SeitenIndex, rechtecke: list) -> list:
    """Formeltreffer um Zähler/Nenner derselben Reihe ergänzen, die horizontal
    innerhalb des Treffers liegen (z. B. Nenner 'ax' unter 'G·Ax')."""
    ergebnis = []
    for r in rechtecke:
        i = idx.reihe_von(r)
        if i is None:
            ergebnis.append(r)
            continue
        dazu = [tuple(w[:4]) for w in idx.reihen[i].worte
                if r[0] - 1 <= (w[0] + w[2]) / 2 <= r[2] + 1]
        ergebnis.append(_vereinigung([r] + dazu))
    return ergebnis


# ------------------------------------------------------------------ Grafik
def _ist_grafikbefund(check_id: str, beschreibung: str) -> bool:
    return check_id == "L-06" or bool(re.search(r"\bGrafik|\bKurve|\bDiagramm|\bAbbildung",
                                                 beschreibung))


def _fund_grafik(pfad: str, nummer: int, beschreibung: str) -> Fundstelle | None:
    seite = _dokument(pfad)[nummer - 1]
    pfade = seite.get_drawings()
    if len(pfade) < 30:
        return None
    cluster = [pymupdf.Rect(c) for c in seite.cluster_drawings(drawings=pfade)]
    if not cluster:
        return None
    # Diagramm = Cluster mit den meisten Zeichenpfaden
    plot = max(cluster, key=lambda c: sum(1 for p in pfade if c.contains(p["rect"])))
    idx = _seitenindex(pfad, nummer)
    region = pymupdf.Rect(plot)
    # Achsenbeschriftungen, Legende, Tick-Labels: kurze Textzeilen nahe der Zeichnung
    # (die Bildunterschrift „Abbildung N: …“ bleibt weg – spart Höhe auf der Leinwand)
    for _ in range(3):
        erweitert = region + (-20, -20, 20, 20)
        for bbox, text, _g in idx.zeilen:
            if (len(text.strip()) <= 50 and erweitert.intersects(pymupdf.Rect(bbox))
                    and not text.strip().startswith(("Abbildung", "Abb."))):
                region |= pymupdf.Rect(bbox)

    rechtecke, kurve_farbe = [], None
    m = re.search(r"Kurven?\s*[„\"“]([^“”\"]+)[“”\"]", beschreibung)
    if m:
        for t in _finde(idx, m.group(1), stufe2=False):
            if not plot.intersects(pymupdf.Rect(t.box)):
                continue
            label = pymupdf.Rect(t.box)
            # Linienmuster der Legende links neben der Beschriftung mitnehmen;
            # seine Farbe ist die Farbe der Kurve im Diagramm
            band = pymupdf.Rect(label.x0 - 45, label.y0, label.x0, label.y1)
            for p in pfade:
                if band.intersects(p["rect"]) and p["rect"].width < 45:
                    label |= p["rect"]
                    if p.get("color") and kurve_farbe is None:
                        kurve_farbe = tuple(p["color"])
            rechtecke.append(tuple(label))
            break
    if not rechtecke:
        rechtecke = [tuple(plot)]
    # Prüfpunkt aus dem Befund („x=80: Grafik ≈4,7, Tabelle 3,0942“; erster = größte Abweichung)
    p = re.search(r"x\s*=\s*(\d+)\s*:\s*Grafik\s*≈\s*(-?[\d.,]+)\s*,\s*Tabelle\s*(-?[\d.,]+)",
                  beschreibung)
    pruefpunkt = None
    if p:
        try:
            pruefpunkt = (float(p.group(1)), _de_float(p.group(2)), _de_float(p.group(3)))
        except ValueError:
            pruefpunkt = None
    return Fundstelle(nummer, _verschmelzen(_polstern(r, _POLSTER_PT) for r in rechtecke),
                      _rand_und_breite(idx, tuple(region)), "Grafik",
                      hinweis=f"Diagramm mit {len(pfade)} Zeichenpfaden"
                              + (f", Kurve „{m.group(1)}“" if m else ""),
                      grafik_bereich=tuple(round(v, 2) for v in plot),
                      kurve_farbe=kurve_farbe, pruefpunkt=pruefpunkt)


def _de_float(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def _farbe_gleich(a, b, toleranz: float = 0.03) -> bool:
    return a is not None and b is not None and len(a) == len(b) and \
        all(abs(x - y) <= toleranz for x, y in zip(a, b))


def _kurven_linien(seite: pymupdf.Page, farbe: tuple, bereich: Rechteck) -> list[list]:
    """Polylinien (PDF-Punkte) der Kurve mit der Linienfarbe farbe in der
    Zeichenfläche (lange Pfade aus vielen Segmenten; Legendenmuster und
    Datenpunkte bleiben außen vor)."""
    flaeche = pymupdf.Rect(bereich) + (-2, -2, 2, 2)
    linien = []
    for p in seite.get_drawings():
        if not _farbe_gleich(p.get("color"), farbe) or len(p["items"]) < 10:
            continue
        if not flaeche.contains(p["rect"]) or p["rect"].width < 0.3 * flaeche.width:
            continue
        punkte = []
        for item in p["items"]:
            if item[0] in ("l", "c"):
                for pt in (item[1], item[-1]):
                    if not punkte or (abs(punkte[-1][0] - pt.x) + abs(punkte[-1][1] - pt.y)) > 0.05:
                        punkte.append((pt.x, pt.y))
        if len(punkte) >= 2:
            linien.append(punkte)
    return linien


def _achsen(seite: pymupdf.Page, bereich: Rechteck):
    """Lineare Umrechnung Datenwert -> PDF-Koordinate für x- und y-Achse aus
    den Achsenbeschriftungen (Zahlen unter bzw. links der Zeichenfläche).
    Liefert ((ax, bx), (ay, by)) mit x_pt = ax + bx·x, y_pt = ay + by·y – oder None."""
    b = pymupdf.Rect(bereich)
    xs, ys = [], []
    for w in seite.get_text("words"):
        text = w[4].replace(",", ".")
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
            continue
        mx, my = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if b.x0 - 15 <= mx <= b.x1 + 15 and b.y1 - 3 <= w[1] <= b.y1 + 30:
            xs.append((float(text), mx))
        elif b.x0 - 40 <= w[2] <= b.x0 + 3 and b.y0 - 5 <= my <= b.y1 + 5:
            ys.append((float(text), my))

    def gerade(paare):
        if len({v for v, _ in paare}) < 2:
            return None
        n = len(paare)
        mv = sum(v for v, _ in paare) / n
        mp = sum(p for _, p in paare) / n
        nenner = sum((v - mv) ** 2 for v, _ in paare)
        steigung = sum((v - mv) * (p - mp) for v, p in paare) / nenner
        return mp - steigung * mv, steigung

    gx, gy = gerade(xs), gerade(ys)
    return (gx, gy) if gx and gy else None


def _y_auf_kurve(linien: list[list], x: float) -> float | None:
    """y-Koordinate der Kurve an der Stelle x (lineare Interpolation)."""
    for punkte in linien:
        for (xa, ya), (xb, yb) in zip(punkte, punkte[1:]):
            if min(xa, xb) <= x <= max(xa, xb) and xb != xa:
                return ya + (yb - ya) * (x - xa) / (xb - xa)
    return None


# --------------------------------------------------------- Symbolverzeichnis
def _glossar(pfad: str):
    """Symbolverzeichnis: Liste (seite, reihen_index, symbol_normiert) aller Einträge."""
    doc = _dokument(pfad)
    start = None
    for n in range(1, len(doc) + 1):
        idx = _seitenindex(pfad, n)
        for bbox, text, groesse in idx.zeilen[:3]:
            if groesse >= 12 and re.search(r"Symbolverzeichnis|Glossar", text):
                start = n
                break
        if start:
            break
    if start is None:
        return []
    eintraege = []
    n = start
    while n <= len(doc):
        idx = _seitenindex(pfad, n)
        kopf = next((i for i, r in enumerate(idx.reihen[:6])
                     if [w[4] for w in r.worte][:2] == ["Symbol", "Bedeutung"]), None)
        if kopf is None:
            break
        spalte = idx.reihen[kopf].worte[1][0]          # x-Position der Spalte "Bedeutung"
        for i, r in enumerate(idx.reihen[kopf + 1:], start=kopf + 1):
            symbol_worte = [w for w in r.worte if w[2] < spalte - 3]
            if not symbol_worte or not any(w[0] >= spalte - 3 for w in r.worte):
                continue
            eintraege.append((n, i, _norm("".join(w[4] for w in symbol_worte))))
        n += 1
    return eintraege


def _fund_symbolverzeichnis(pfad: str, beschreibung: str, seite: int | None):
    m = re.search(r"Symbol\s*[„\"“]([^“”\"]+)[“”\"]", beschreibung)
    if not m:
        return None
    symbol = _norm(m.group(1))
    s = re.search(r"Stamm\s*[„\"“]([^“”\"]+)[“”\"]", beschreibung)
    stamm = _norm(s.group(1)) if s else symbol
    eintraege = _glossar(pfad)
    if not eintraege:
        return None

    # 1) Nachbar-Heuristik: welches erklärte Symbol steht in den Verwendungsstellen
    #    unmittelbar vor dem fehlenden? Dort gehört der Eintrag hin.
    seiten = [seite] if seite else []
    liste = re.search(r"Seiten\s*\[([\d,\s]+)\]", beschreibung)
    if liste:
        seiten += [int(x) for x in re.findall(r"\d+", liste.group(1))]
    kandidaten = sorted({e[2] for e in eintraege if len(e[2]) >= 2 and e[2] != symbol},
                        key=len, reverse=True)
    stimmen = Counter()
    for n in dict.fromkeys(s for s in seiten if s):
        idx = _seitenindex(pfad, n)
        for t_start in _vorkommen(idx.text1, symbol):
            if not all(idx.mathe1[i] for i in range(t_start, t_start + len(symbol))
                       if idx.text1[i].isalpha()):
                continue
            davor = idx.text1[max(0, t_start - 40):t_start]
            basis = t_start - len(davor)
            bester, best_ende = None, -1
            for g in kandidaten:
                k = davor.rfind(g)
                if k < 0 or k + len(g) <= best_ende:
                    continue
                if all(idx.mathe1[basis + i] for i in range(k, k + len(g))
                       if davor[i].isalpha()):
                    bester, best_ende = g, k + len(g)
            if bester and len(davor) - best_ende <= 25:
                stimmen[bester] += 1
    if stimmen:
        nachbar = stimmen.most_common(1)[0][0]
        herkunft = f"nach „{nachbar}“ (Nachbar in den Verwendungsstellen)"
    else:
        # 2) Rückfall: alphabetisch nächster Eintrag (längster gemeinsamer Anfang)
        def gemeinsam(a, b):
            k = 0
            while k < min(len(a), len(b)) and a[k] == b[k]:
                k += 1
            return k
        nachbar = max(eintraege, key=lambda e: gemeinsam(e[2], stamm))[2]
        herkunft = f"bei „{nachbar}“ (alphabetisch)"

    pos = next(i for i, e in enumerate(eintraege) if e[2] == nachbar)
    gl_seite, r_a = eintraege[pos][0], eintraege[pos][1]
    idx = _seitenindex(pfad, gl_seite)
    if pos + 1 < len(eintraege) and eintraege[pos + 1][0] == gl_seite:
        r_b = eintraege[pos + 1][1]
    else:
        r_b = r_a
    reihen = idx.reihen
    x0 = min(r.x0 for r in reihen[r_a:r_b + 1]) - _POLSTER_PT
    x1 = max(r.x1 for r in reihen[r_a:r_b + 1]) + _POLSTER_PT
    # Der fehlende Eintrag gehört in die Lücke nach dem Nachbar-Eintrag (vor den
    # folgenden). Markiert wird diese Lücke als Einfügemarke – NICHT die beiden
    # (korrekten) Nachbarzeilen. In der fehlerfreien TB steht bei identischem
    # Layout genau dort der Eintrag (Gegenüberstellung markiert diese Zeile).
    if r_b > r_a:
        y = _weissraum(pfad, gl_seite, x0, x1, reihen[r_b - 1].y1 - 1.0, reihen[r_b].y0 + 1.0)
    else:
        y = reihen[r_a].y1 + 1.5
    band = _reihenband(idx, r_a, r_b)          # nur für die Größe des Ausschnitts
    ausschnitt, _, _ = _ausschnitt_bilden(idx, [band], [])
    return Fundstelle(gl_seite, [], ausschnitt, "Symbolverzeichnis",
                      hinweis=f"Eintrag „{symbol}“ fehlt; gehört {herkunft}",
                      einfuegemarke=(round(x0, 2), round(x1, 2), round(y, 2)),
                      marke_text=f"Hier fehlt der Eintrag „{m.group(1).strip()}“")


# ---------------------------------------------------------------- Vorgaben
def _fund_vorgabe(pfad: str, check_id: str, beschreibung: str, seite: int | None):
    for v in _VORGABEN:
        if v["check_id"] != check_id or (v.get("seite") and v["seite"] != seite):
            continue
        if v.get("enthaelt", "") not in beschreibung:
            continue
        nummer = v.get("ziel_seite") or seite
        idx = _seitenindex(pfad, nummer)
        if "bereich" in v:
            markierung = [tuple(v["bereich"])]
        else:
            markierung = [_polstern(r, _POLSTER_PT) for text in v["begriffe"]
                          for t in _finde(idx, text) for r in t.rechtecke]
        if not markierung:
            continue
        ausschnitt, kopf, streifen = _ausschnitt_bilden(idx, markierung, [])
        return Fundstelle(nummer, _verschmelzen(markierung), ausschnitt, "Vorgabe", kopf,
                          hinweis="kuratierte Vorgabe", streifen=streifen)
    return None


# ---------------------------------------------------------------- Rückfall
def _fund_seite(pfad: str, nummer: int) -> Fundstelle:
    """Kein Begriff gefunden: oberen Bereich der Seite zeigen (Überschrift + Textanfang)."""
    idx = _seitenindex(pfad, nummer)
    if idx.reihen:
        hi = min(6, len(idx.reihen) - 1)
        reihen = idx.reihen[:hi + 1]
        x0, x1 = min(r.x0 for r in reihen), max(r.x1 for r in reihen)
        y0, y1 = _kanten(idx, 0, hi, x0, x1)
        ausschnitt = _rand_und_breite(idx, (x0, y0, x1, y1), rand_y=False)
    else:
        r = idx.rect
        ausschnitt = _rand_und_breite(idx, (r.x0 + 50, r.y0 + 80, r.x1 - 50, r.y0 + 300))
    return Fundstelle(nummer, [], ausschnitt, "Seite",
                      hinweis="keine Fundstelle im Text – Seitenanfang")


# ------------------------------------------------- Gegenstelle (andere Seite)
# V-08: Widersprüchliche Werte für „GM“: 1910,0070 EUR (Seite 73); 1901,0070 EUR (Seite 73).
_V08_WERT = re.compile(r"(?:^|[:;]\s*)([^:;()]+?)\s*\(Seite (\d+)\)")
_TEIL_NAME = re.compile(r"\b(Abschnitt|Anlage|Anhang)\s+(\d+(?:\.\d+)*)")
_ZUSATZ = re.compile(r"\s*,\s*((?:Schritt|Tabelle|Gleichung|Absatz|Zeile|Spalte)\s+[\w.()]+)")


@lru_cache(maxsize=64)
def _seiten_des_teils(pfad: str, praefix: str, nummer: str) -> tuple[int, ...]:
    """Seiten, deren Kopfzeile den Teil nennt (z. B. „Anhang 5“ – die TB führt
    den aktuellen Teil oben auf jeder Seite)."""
    muster = re.compile(rf"^\s*{praefix}\s+{re.escape(nummer)}(?![\d.])")
    seiten = []
    for n, seite in enumerate(_dokument(pfad), start=1):
        if any(muster.match(z) for z in seite.get_text("text").splitlines()[:6]):
            seiten.append(n)
    return tuple(seiten)


def _stellen_aus_befund(check_id: str, beschreibung: str) -> list[tuple[str, str]]:
    """(Ortsangabe, zitierter Wert) der Stellen eines Widerspruchsbefunds."""
    if check_id == "L-03":
        m = _L03_MUSTER.search(beschreibung)
        if m:
            return [(m.group("stelle_a"), m.group("wert_a")),
                    (m.group("stelle_b"), m.group("wert_b"))]
    if check_id == "V-08":
        return [(f"Seite {s}", w.strip()) for w, s in _V08_WERT.findall(beschreibung)]
    return []


def _ortsname(stelle: str, pfad: str | None = None, seite: int | None = None) -> str:
    """Kurzer Ortsname aus einer Ortsangabe für die Bildunterschrift, z. B.
    „Anhang 5 (Teil B), Schritt 4, Berechnung von b43“ -> „Anhang 5, Schritt 4“.
    Nennt die Ortsangabe mehrere Teile, wird der Teil genommen, zu dem die
    Seite gehört. Leer, wenn kein Abschnitt/Anhang/Anlage genannt ist."""
    s = re.sub(r"\([^()]*\)", " ", stelle)
    s = re.sub(r"\bTeil\s+[A-Z]\b\s*,?", " ", s)
    treffer = list(_TEIL_NAME.finditer(s))
    if not treffer:
        return ""
    gewaehlt = treffer[0]
    if pfad is not None and seite is not None:
        gewaehlt = next((t for t in treffer
                         if seite in _seiten_des_teils(pfad, t.group(1), t.group(2))), None)
        if gewaehlt is None:
            return ""
    name = f"{gewaehlt.group(1)} {gewaehlt.group(2)}"
    if z := _ZUSATZ.match(s[gewaehlt.end():]):
        name += ", " + z.group(1).rstrip(".,;:")
    return name


def _beschriftung(seite: int, name: str) -> str:
    return f"Seite {seite} · {name}" if name else f"Seite {seite}"


def _steht_auf_seite(pfad: str, nummer: int, check_id: str, wert: str) -> bool:
    idx = _seitenindex(pfad, nummer)
    for b in _begriffe_ableiten(check_id, f"„{wert}“"):
        if not b.markieren:
            continue
        if _suche_begriff(idx, b) or any(_suche_begriff(idx, e) for e in b.ersatz):
            return True
    return False


def _gegenstellen(pfad: str, check_id: str, beschreibung: str, haupt: Fundstelle,
                  anzahl: int) -> tuple[list[Fundstelle], str]:
    """Stellen eines Widerspruchs, die NICHT auf der Seite der Hauptstelle stehen
    (z. B. „Anhang 5, Schritt 4“ zu einer Formel in Abschnitt 5.1). Gesucht wird
    nur auf den in der Ortsangabe genannten Seiten bzw. den Seiten der
    genannten Teile, und nur ein dort wörtlich stehender Wert (oder die
    Formelzeile einer genannten Größe) zählt – lieber nichts als etwas Falsches.
    Liefert (Gegenstellen, Ortsname der Hauptstelle)."""
    ergebnis, name_haupt = [], ""
    for stelle, wert in _stellen_aus_befund(check_id, beschreibung):
        if _steht_auf_seite(pfad, haupt.seite, check_id, wert):
            name_haupt = name_haupt or _ortsname(stelle, pfad, haupt.seite)
            continue
        seiten = [int(s) for s in re.findall(r"Seite\s+(\d+)", stelle)]
        if not seiten:
            for t in _TEIL_NAME.finditer(stelle):
                seiten += _seiten_des_teils(pfad, t.group(1), t.group(2))
        seiten = [s for s in dict.fromkeys(seiten)
                  if s != haupt.seite and 1 <= s <= anzahl][:8]
        if not seiten:
            continue
        begriffe = _begriffe_ableiten(check_id, f"„{wert}“")
        funde = [e for n in seiten if (e := _fund_suchbegriffe(pfad, n, check_id, begriffe,
                                                                polster=1))]
        fund = max(funde, key=lambda e: e[1])[0] if funde else None
        if fund is None:
            # Der Wert ist umschrieben (nicht wörtlich im Dokument): dann die in
            # der Ortsangabe genannte Größe suchen („Berechnung von b43“ -> die
            # Formelzeile „b43 = …“).
            fund = _fund_formelzeile(pfad, seiten, stelle)
        if fund is None or not fund.rechtecke or any(f.seite == fund.seite for f in ergebnis):
            continue
        fund.beschriftung = _beschriftung(fund.seite, _ortsname(stelle, pfad, fund.seite))
        ergebnis.append(fund)
    return ergebnis[:2], name_haupt


_GROESSE = re.compile(r"(?<![\wÄÖÜäöüß])([A-Za-z]{1,3}_?\d{1,3})(?![\w])")


def _fund_formelzeile(pfad: str, seiten: list[int], stelle: str) -> Fundstelle | None:
    """Formelzeile, in der eine in der Ortsangabe genannte Größe definiert
    wird („b43 = …“); markiert wird die ganze Zeile."""
    groessen = [g.replace("_", "") for g in _GROESSE.findall(stelle)]
    for n in seiten:
        idx = _seitenindex(pfad, n)
        for g in groessen:
            for start in _vorkommen(idx.text1, _norm(g) + "="):
                if not _grenze_ok(idx, start, start + len(_norm(g)), zahl=False):
                    continue
                treffer = _treffer_aus(idx, range(start, start + len(_norm(g))))
                markierung = _ganze_reihe(idx, treffer.rechtecke[:1])
                ausschnitt, kopf, streifen = _ausschnitt_bilden(idx, markierung, [], polster=1)
                return Fundstelle(n, _verschmelzen(markierung), ausschnitt, "Suchbegriff", kopf,
                                  f"Formelzeile „{g} = …“", streifen=streifen)
    return None


def _vergleich_begriffe(beschreibung: str) -> list[str]:
    """Für die Gegenüberstellung: „(Anlage 5.2, Abschnitt ??)“ heißt in der
    fehlerfreien TB „(Anlage 5.2)“ – dort wird genau das markiert."""
    m = re.search(r"\(([^()]{2,40}?),\s*(?:Abschnitt|Anlage|Anhang|Kapitel|Gleichung|Tabelle|"
                  r"Abbildung|Seite)?\s*\?\?\)", beschreibung)
    return [f"({m.group(1).strip()})"] if m else []


# =============================================================================
# Öffentliche Schnittstelle
# =============================================================================

def finde_fundstelle(pdf_pfad, check_id: str, beschreibung: str,
                     seite: int | None) -> Fundstelle | None:
    """Sucht die zu einem Befund gehörende Passage im PDF.

    Liefert immer eine Fundstelle (im Zweifel den Seitenanfang, methode "Seite");
    None nur, wenn das PDF nicht gelesen werden kann. Weitere im Befundtext
    genannte Stellen auf anderen Seiten liefert finde_gegenstellen (das Feld
    weitere bleibt hier leer). Gibt es solche Gegenstellen, ist der Ausschnitt
    knapper (eine Zeile Kontext) und beschriftung gesetzt („Seite 44 · Abschnitt 5.1“).
    """
    ergebnis = _analyse_sicher(pdf_pfad, check_id, beschreibung, seite)
    return copy.deepcopy(ergebnis[0]) if ergebnis else None


def finde_gegenstellen(pdf_pfad, check_id: str, beschreibung: str,
                       seite: int | None) -> list[Fundstelle]:
    """Weitere im Befundtext genannte Stellen auf ANDEREN Seiten als die
    Fundstelle – typisch die zweite Stelle eines Widerspruchs (L-03:
    „Abschnitt 3.2 … nennt …, Anhang 5, Schritt 3 … dagegen …“) oder der zweite
    Wert eines V-08-Befunds auf einer anderen Seite.

    Jede Gegenstelle hat beschriftung („Seite 92 · Anhang 5, Schritt 3“) und wird
    wie eine Fundstelle mit rendere_ausschnitt gerendert (auch neutral auf dem
    anderen Dokument – gleiches Layout). Leere Liste, wenn nichts Belastbares
    gefunden wird (lieber nichts als etwas Falsches).
    """
    ergebnis = _analyse_sicher(pdf_pfad, check_id, beschreibung, seite)
    return copy.deepcopy(list(ergebnis[1])) if ergebnis else []


# ------------------------------------------------------- Text für die Leinwand
# Unsichtbare Zeichen aus PDF-Extraktion/Formelsatz: weiches Trennzeichen,
# Nullbreiten-Zeichen, Variantenselektoren (U+FE00 „︀“ aus Klammern im Formelsatz)
_UNSICHTBAR = dict.fromkeys([0x00AD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF,
                             *range(0xFE00, 0xFE10)])
_AUSZUG_ZITAT = re.compile(r"„\s*(?:\.\.\.|…)(?P<inhalt>[^“”„]*?)(?P<ende>\.\.\.|…)?\s*[“”]")
_KONTEXT_WORTE = 8          # so viele Wörter Kontext vor bzw. nach dem Kern eines Auszugs


def _formel_wort(wort: str) -> bool:
    """Wirkt das Wort wie ein Bruchstück aus dem Formelsatz („ax+“, „A111“, „(32)“)?"""
    w = wort.strip(",;.")
    if not w:
        return True
    return bool(re.search(r"[=+·/^_∑∫√≤≥<>|]|:=", w)
                or re.fullmatch(r"\(\d{1,3}\)|[()\[\]{}]+|[A-Za-z]{1,2}\d+|\d", w))


def _auszug_kuerzen(inhalt: str, rechts_offen: bool) -> str:
    """Kürzt einen Textauszug auf den lesbaren Kern: um „??“ herum bis zum
    nächsten Formel-Bruchstück (höchstens _KONTEXT_WORTE Wörter je Seite);
    ohne „??“ – nur bei viel Formelsatz – die längste zusammenhängende Folge
    normaler Wörter."""
    worte = inhalt.split()
    anker = next((i for i, w in enumerate(worte) if "??" in w), None)
    formel = sum(_formel_wort(w) for w in worte)
    if not worte or not formel or (anker is None and formel < max(3, 0.25 * len(worte))):
        return ("… " + " ".join(worte) + (" …" if rechts_offen else "")).strip()
    if anker is not None:
        a = anker
        while a > 0 and anker - a < _KONTEXT_WORTE and not _formel_wort(worte[a - 1]):
            a -= 1
        b = anker
        while b + 1 < len(worte) and b - anker < _KONTEXT_WORTE and not _formel_wort(worte[b + 1]):
            b += 1
    else:
        laeufe, start = [], None
        for i, w in enumerate(worte + ["="]):
            if not _formel_wort(w) and start is None:
                start = i
            elif _formel_wort(w) and start is not None:
                laeufe.append((start, i - 1))
                start = None
        if not laeufe:
            return "…"
        a, b = max(laeufe, key=lambda lauf: lauf[1] - lauf[0])
    # Ein Auszug beginnt immer mitten im Text („...“), links also stets „…“
    rechts = " …" if b < len(worte) - 1 or rechts_offen else ""
    return "… " + " ".join(worte[a:b + 1]) + rechts


def anzeige_text(beschreibung: str) -> str:
    """Befundtext für die Leinwand aufbereiten (die Prüfung selbst bleibt unverändert):

    - unsichtbare Zeichen entfernen (Variantenselektoren wie U+FE00 aus dem
      Formelsatz, weiche Trennzeichen, Nullbreiten-Zeichen);
    - frei stehende Kombinationszeichen an den folgenden Buchstaben hängen
      („̄wneu“ -> „w̄neu“);
    - Textauszüge in „...…...“ mit zerlegtem Formelsatz auf kurzen lesbaren
      Kontext kürzen, z. B. „..., ax+1/2 = 1 2 (ax+ ax+1 ), A111 := 0, (32)
      verwendet (Anlage 5.2, Abschnitt ??); die …“ -> „… verwendet (Anlage 5.2,
      Abschnitt ??); die …“;
    - „...“ als Auslassungszeichen „…“, Leerraum glätten.
    """
    text = unicodedata.normalize("NFC", (beschreibung or "").translate(_UNSICHTBAR))
    text = re.sub(r"(?<!\w)([̀-ͯ]+)(\w)", r"\2\1", text)

    def kuerzen(m: re.Match) -> str:
        return "„" + _auszug_kuerzen(m.group("inhalt"), bool(m.group("ende"))) + "“"

    text = _AUSZUG_ZITAT.sub(kuerzen, text)
    text = text.replace("...", "…")
    return re.sub(r"[ \t\r\n]+", " ", text).strip()


def _analyse_sicher(pdf_pfad, check_id, beschreibung, seite):
    """Normalisiert die Eingaben und ruft die (zwischengespeicherte) Analyse auf;
    None, wenn das PDF nicht gelesen werden kann."""
    pfad = _pfad(pdf_pfad)
    beschreibung = beschreibung or ""
    check_id = (check_id or "").strip()
    with _SPERRE:
        try:
            anzahl = len(_dokument(pfad))
        except Exception:
            return None
        if seite is not None:
            try:
                seite = int(seite)
            except (TypeError, ValueError):
                seite = None
        if seite is not None and not 1 <= seite <= anzahl:
            seite = None
        return _analyse(pfad, check_id, beschreibung, seite)


@lru_cache(maxsize=512)
def _analyse(pfad: str, check_id: str, beschreibung: str,
             seite: int | None) -> tuple[Fundstelle, tuple[Fundstelle, ...]]:
    """(Fundstelle, Gegenstellen) eines Befunds – siehe finde_fundstelle."""
    anzahl = len(_dokument(pfad))
    fund = _fund_vorgabe(pfad, check_id, beschreibung, seite)
    if fund:
        return fund, ()
    if check_id == "V-04" or re.search(r"Symbolverzeichnis", beschreibung):
        fund = _fund_symbolverzeichnis(pfad, beschreibung, seite)
        if fund:
            return fund, ()
    if seite and _ist_grafikbefund(check_id, beschreibung):
        fund = _fund_grafik(pfad, seite, beschreibung)
        if fund:
            return fund, ()

    begriffe = _begriffe_ableiten(check_id, beschreibung)
    if begriffe:
        if seite:
            kandidaten = [[seite], [seite - 1, seite + 1]]
        else:
            kandidaten = [list(range(1, anzahl + 1))]
        for gruppe in kandidaten:
            ergebnisse = [e for n in gruppe if 1 <= n <= anzahl
                          and (e := _fund_suchbegriffe(pfad, n, check_id, begriffe))]
            if ergebnisse:
                fund = max(ergebnisse, key=lambda e: e[1])[0]
                return _ergaenzen(pfad, check_id, beschreibung, begriffe, fund, anzahl)
    return _fund_seite(pfad, seite or 1), ()


def _ergaenzen(pfad: str, check_id: str, beschreibung: str, begriffe: list,
               fund: Fundstelle, anzahl: int) -> tuple[Fundstelle, tuple[Fundstelle, ...]]:
    """Gegenstellen auf anderen Seiten (Widersprüche) und Vergleichsbegriffe."""
    try:
        gegen, name_haupt = _gegenstellen(pfad, check_id, beschreibung, fund, anzahl)
    except Exception:            # Zusatzinformation – darf die Fundstelle nie verhindern
        gegen, name_haupt = [], ""
    if gegen:
        # Mit Gegenstelle: Hauptstelle knapper (eine Zeile Kontext), damit beide
        # Teile zusammen auf die Leinwand passen.
        knapp = _fund_suchbegriffe(pfad, fund.seite, check_id, begriffe, polster=1)
        if knapp:
            fund = knapp[0]
        fund.beschriftung = _beschriftung(fund.seite, name_haupt)
    fund.vergleich_begriffe = _vergleich_begriffe(beschreibung)
    return fund, tuple(gegen)


def _pixmap_bild(seite: pymupdf.Page, clip, zoom: float) -> Image.Image:
    pix = seite.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=pymupdf.Rect(clip),
                           alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _an_text_anpassen(pfad: str, fundstelle: Fundstelle) -> list[Rechteck]:
    """Markierungen an den Text des *gerenderten* Dokuments anpassen.

    Für die Gegenüberstellung wird die Fundstelle der fehlerhaften TB auf die
    fehlerfreie übertragen. Das Layout ist identisch, die Wörter können aber
    leicht verschoben sein (z. B. „§ 4 VAG“ -> „§ 4 KVAV“). Deshalb:
    - liegen die getroffenen Wörter überwiegend im Rechteck, wird es auf diese
      Wörter erweitert (ganzes Wort, ganze Zahl);
    - schneidet das Rechteck Wörter nur an (Text verschoben, z. B. entfallenes
      „Abschnitt ??“), wird stattdessen die ganze Zeile als Band markiert.
    """
    idx = _seitenindex(pfad, fundstelle.seite)
    worte = [w for r in idx.reihen for w in r.worte]
    kaesten, band_reihen = [], set()
    for r in fundstelle.rechtecke:
        innen = _polstern(r, -_POLSTER_PT)
        if innen[2] <= innen[0] or innen[3] <= innen[1]:
            innen = r
        getroffen = [w for w in worte if _schneiden(innen, w[:4])]
        if not getroffen:
            kaesten.append(r)
            continue
        anteil = {id(w): _flaeche(_schnitt(innen, w[:4])) / max(_flaeche(w[:4]), 1e-6)
                  for w in getroffen}
        dazu = [w for w in getroffen if anteil[id(w)] >= 0.3]      # gehört zur Stelle
        gestreift = [w for w in getroffen if anteil[id(w)] < 0.3]  # Nachbarwort am Rand
        # Wie viel der Rechteckbreite decken die zugehörigen Wörter ab?
        intervalle = sorted((max(w[0], innen[0]), min(w[2], innen[2])) for w in dazu)
        bedeckt, ende = 0.0, innen[0]
        for a, b in intervalle:
            if b > ende:
                bedeckt += b - max(a, ende)
                ende = b
        breite = innen[2] - innen[0]
        if dazu:
            wx0, wx1 = min(w[0] for w in dazu), max(w[2] for w in dazu)
            ueberstand = max(0.0, innen[0] - wx0) + max(0.0, wx1 - innen[2])
        if dazu and bedeckt >= 0.6 * breite and ueberstand <= 0.5 * breite:
            wortkasten = [_polstern(_wortkasten(idx, w), _POLSTER_PT) for w in dazu]
            kaesten.append(_vereinigung(wortkasten + ([r] if not gestreift else [])))
        else:
            band_reihen.update(i for w in getroffen if (i := idx.reihe_von(w[:4])) is not None)
    # Zeilenbänder ersetzen Kästen derselben Zeile; Bänder anderer Zeilen bleiben getrennt
    kaesten = [_in_luecke(idx, k, 2.0) for k in kaesten
               if idx.reihe_von(k) not in band_reihen]
    return _verschmelzen(kaesten) + [_reihenband(idx, i, i) for i in sorted(band_reihen)]


def _wortkasten(idx: _SeitenIndex, w) -> Rechteck:
    """Box eines Worts ohne Satzzeichen am Rand – '(§' -> '§', 'VAG).' -> 'VAG'."""
    zeichen = [i for i, b in enumerate(idx.box1)
               if w[0] - 0.5 <= (b[0] + b[2]) / 2 <= w[2] + 0.5
               and w[1] - 0.5 <= (b[1] + b[3]) / 2 <= w[3] + 0.5]
    while zeichen and idx.text1[zeichen[0]] in "([{\"'":
        zeichen.pop(0)
    while zeichen and idx.text1[zeichen[-1]] in ")]}\"'.,;:!?":
        zeichen.pop()
    return _vereinigung(idx.box1[i] for i in zeichen) if zeichen else tuple(w[:4])


def _in_luecke(idx: _SeitenIndex, r, spanne: float) -> Rechteck:
    """Ober-/Unterkante um höchstens ±spanne in die nächste tintenfreie Lücke rücken
    (Layout des Vergleichsdokuments kann minimal abweichen)."""
    y0 = _weissraum(idx.pfad, idx.nummer, r[0], r[2], r[1] - spanne, r[1] + spanne)
    y1 = _weissraum(idx.pfad, idx.nummer, r[0], r[2], r[3] - spanne, r[3] + spanne)
    return (r[0], y0, r[2], y1) if y1 - y0 > 4 else tuple(r)


_TINTE_ZOOM = 8.0           # Auflösung der Tintenmessung für die Rahmenlage
_ABSTAND_NACHBAR_PT = 1.9   # Mindestabstand Rahmen <-> Nachbarzeichen („=“, Wort)
_ABSTAND_TEXT_PT = 0.5      # Mindestabstand Rahmen <-> markierter Text
_SATZZEICHEN = set("()[]{},.;:\"'»«")
_SATZZEICHEN_LUECKE_PT = 2.4  # kleinerer Tintenabstand = Satzzeichen hängt direkt am Text (Wortabstand ≥ 3 pt)


def _tinte_laeufe(idx: _SeitenIndex, x0: float, x1: float, y0: float,
                  y1: float) -> list[tuple[float, float]]:
    """Zusammenhängende Tintenbereiche (x von, x bis in pt) in einem schmalen
    Band – im Fließtext etwa je Glyphe. Gemessen am gerenderten Bild."""
    seite = _dokument(idx.pfad)[idx.nummer - 1]
    clip = pymupdf.Rect(x0, y0, x1, y1) & seite.rect
    if clip.is_empty or clip.width < 0.5 or clip.height < 0.5:
        return []
    pix = seite.get_pixmap(matrix=pymupdf.Matrix(_TINTE_ZOOM, _TINTE_ZOOM),
                           colorspace=pymupdf.csGRAY, clip=clip, alpha=False)
    bild = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
    spalten = np.flatnonzero((bild[:, :pix.width] < 160).any(axis=0))
    laeufe: list[list[int]] = []
    for s in spalten:
        if laeufe and s == laeufe[-1][1] + 1:
            laeufe[-1][1] = s
        else:
            laeufe.append([s, s])
    return [(clip.x0 + a / _TINTE_ZOOM, clip.x0 + (b + 1) / _TINTE_ZOOM) for a, b in laeufe]


def _gehoert_dazu(idx: _SeitenIndex, lauf: tuple, ya: float, yb: float, seite: str,
                  luecke: float, luecke_noetig: float) -> bool:
    """Gehört der benachbarte Tintenbereich als Satzzeichen zur Markierung?
    Links nur eine öffnende Klammer („(§ 154“, „[12 · …“), rechts eine
    schließende Klammer – jeweils, solange der Rahmen sonst nicht in die
    Lücke passt; Komma, Punkt, Anführung nur rechts und direkt anhängend
    („VAG,“). Ein Komma links gehört zum vorigen Satzteil, eine öffnende
    Klammer rechts zum folgenden."""
    zeichen = [idx.text1[i] for i, b in enumerate(idx.box1)
               if lauf[0] - 0.4 <= (b[0] + b[2]) / 2 <= lauf[1] + 0.4
               and min(b[3], yb) - max(b[1], ya) > 0]
    if not zeichen or not all(c in _SATZZEICHEN for c in zeichen):
        return False
    klammern = "([{" if seite == "links" else ")]}"
    if all(c in klammern for c in zeichen):
        return luecke < luecke_noetig
    return seite == "rechts" and luecke < _SATZZEICHEN_LUECKE_PT \
        and not any(c in "([{" for c in zeichen)


def _rahmen_an_nachbarn(idx: _SeitenIndex, rechtecke: list, rand_pt: float):
    """Seitliche Lage des Rahmens so wählen, dass er Nachbarzeichen weder
    überdeckt noch berührt – z. B. das „=“ vor einer Zahl – und auch nicht den
    markierten Text. Gemessen wird an der tatsächlichen Tinte (gerenderte
    Glyphen), nicht an den Zeichenboxen. Der Rahmen liegt mittig auf der
    Rechteckkante.

    Passt der Rahmen nicht in die Lücke, wird eine anschließende Klammer bzw.
    ein direkt anhängendes Satzzeichen mit eingerahmt („(§ 154“, „VAG),“ – so
    wirkt keine Klammer angeschnitten, siehe _gehoert_dazu); bei anderen
    Zeichen wird der Rahmen mittig in die Lücke gesetzt und notfalls diese
    Seite dünner. Liefert (Rechtecke, Rahmenstärke links/rechts in pt)."""
    neu, staerken = [], []
    luecke_noetig = rand_pt + _ABSTAND_NACHBAR_PT + _ABSTAND_TEXT_PT
    for r in rechtecke:
        x0, y0, x1, y1 = r
        kern0, kern1 = x0 + _POLSTER_PT, x1 - _POLSTER_PT
        ya, yb = y0 + _POLSTER_PT + 0.3, y1 - _POLSTER_PT - 0.3
        if kern1 - kern0 < 1 or yb - ya < 1 or y1 - y0 > 45:   # Bänder, Grafiken: unverändert
            neu.append(tuple(r))
            staerken.append((rand_pt, rand_pt))
            continue
        such = rand_pt + 8.0
        laeufe = _tinte_laeufe(idx, x0 - such, x1 + such, ya, yb)
        innen = [i for i, (a, _b) in enumerate(laeufe) if kern0 - 0.3 <= a <= kern1 + 0.3]
        if not innen:
            neu.append(tuple(r))
            staerken.append((rand_pt, rand_pt))
            continue
        i_l, i_r = innen[0], innen[-1]
        for _ in range(2):                    # höchstens zwei Satzzeichen je Seite
            if i_l > 0 and _gehoert_dazu(idx, laeufe[i_l - 1], ya, yb, "links",
                                         laeufe[i_l][0] - laeufe[i_l - 1][1], luecke_noetig):
                i_l -= 1
            if i_r + 1 < len(laeufe) and _gehoert_dazu(
                    idx, laeufe[i_r + 1], ya, yb, "rechts",
                    laeufe[i_r + 1][0] - laeufe[i_r][1], luecke_noetig):
                i_r += 1
        text_l, text_r = laeufe[i_l][0], laeufe[i_r][1]
        x0, x1 = min(x0, text_l - _POLSTER_PT), max(x1, text_r + _POLSTER_PT)
        nachbar_l = laeufe[i_l - 1][1] if i_l > 0 else None
        nachbar_r = laeufe[i_r + 1][0] if i_r + 1 < len(laeufe) else None

        # Linke Seite: Mitte m, Stärke s; außen >= Nachbar + Abstand, innen <= Text - Abstand
        m, s_l = x0, rand_pt
        innen_grenze = text_l - _ABSTAND_TEXT_PT
        if nachbar_l is not None and m - s_l / 2 < nachbar_l + _ABSTAND_NACHBAR_PT:
            frei = innen_grenze - (nachbar_l + _ABSTAND_NACHBAR_PT)
            if frei >= s_l:
                m = nachbar_l + _ABSTAND_NACHBAR_PT + s_l / 2
            else:                                              # zu eng: dünner, mittig
                s_l = max(0.45 * rand_pt, (text_l - nachbar_l) - 0.8)
                m = (nachbar_l + text_l) / 2
        elif m + s_l / 2 > innen_grenze:
            m = innen_grenze - s_l / 2
        x0 = m
        # Rechte Seite spiegelbildlich
        m, s_r = x1, rand_pt
        innen_grenze = text_r + _ABSTAND_TEXT_PT
        if nachbar_r is not None and m + s_r / 2 > nachbar_r - _ABSTAND_NACHBAR_PT:
            frei = (nachbar_r - _ABSTAND_NACHBAR_PT) - innen_grenze
            if frei >= s_r:
                m = nachbar_r - _ABSTAND_NACHBAR_PT - s_r / 2
            else:
                s_r = max(0.45 * rand_pt, (nachbar_r - text_r) - 0.8)
                m = (nachbar_r + text_r) / 2
        elif m - s_r / 2 < innen_grenze:
            m = innen_grenze + s_r / 2
        x1 = m
        neu.append((x0, y0, x1, y1))
        staerken.append((min(s_l, rand_pt), min(s_r, rand_pt)))
    return neu, staerken


def _zeile_an_marke(idx: _SeitenIndex, marke: tuple) -> list:
    """Gegenüberstellung einer Einfügemarke: im anderen Dokument steht der
    fehlende Eintrag in der Zeile, die direkt unter der Marke beginnt."""
    x0, x1, y = marke
    for i, r in enumerate(idx.reihen):
        if r.y0 >= y - 1.5 and r.x1 > x0 and r.x0 < x1:
            return [_reihenband(idx, i, i)]
    return []


def _vergleich_treffer(idx: _SeitenIndex, teil: Fundstelle) -> list:
    """Markierung der Vergleichsbegriffe im gerenderten (anderen) Dokument –
    der Treffer, der der übertragenen Markierung am nächsten liegt."""
    ausschnitt = teil.ausschnitt
    treffer = [t for text in teil.vergleich_begriffe for t in _finde(idx, text, stufe2=False)
               if _schneiden(t.box, ausschnitt)]
    if not treffer:
        return []
    bezug = _Treffer(list(teil.rechtecke) or [ausschnitt])
    bester = min(treffer, key=lambda t: _abstand(t, bezug))
    return [_polstern(r, _POLSTER_PT) for r in bester.rechtecke]


@lru_cache(maxsize=16)
def _schrift(groesse: int, fett: bool = True):
    """Schrift für Beschriftungen im Bild (Windows: Segoe UI / Arial)."""
    namen = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if fett
             else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    for name in namen:
        try:
            return ImageFont.truetype(name, groesse)
        except OSError:
            continue
    return ImageFont.load_default(size=groesse)


def _ton(rgb: tuple, deckkraft: float) -> tuple:
    """Farbe einer Tönung auf weißem Grund (für die Multiplikation)."""
    return tuple(round(255 * (1 - deckkraft) + c * deckkraft) for c in rgb)


def _in_pixel(r, clip, zoom) -> tuple:
    return ((r[0] - clip.x0) * zoom, (r[1] - clip.y0) * zoom,
            (r[2] - clip.x0) * zoom, (r[3] - clip.y0) * zoom)


def _markierungen_zeichnen(bild: Image.Image, clip, zoom: float, rechtecke: list,
                           neben: list, farbe: str, rand: int,
                           staerken: list | None = None,
                           staerken_neben: list | None = None) -> Image.Image:
    """Tönung per Multiplikation (weißer Grund wird farbig, Schrift bleibt
    schwarz) plus kräftiger Rahmen; Kontext-Stellen nur dünn und grau.
    staerken / staerken_neben: Rahmenstärke (links, rechts) je Rechteck in pt
    (aus _rahmen_an_nachbarn); oben/unten und ohne Angabe: rand bzw. dünn."""
    rgb = FARBEN[farbe]
    duenn = max(2, round(rand / 2.5))

    def seiten_px(liste, i, standard):
        if liste is None or i >= len(liste):
            return standard, standard
        return tuple(max(2, min(standard, round(v * zoom))) for v in liste[i])

    def rahmen(zeichnen, p, b, links, rechts, farbe_rgb):
        """Rahmen mittig auf der Rechteckkante; Seitenstärken einzeln."""
        x0, y0, x1, y1 = p
        aussen_l, aussen_r = x0 - links / 2, x1 + rechts / 2
        zeichnen.rectangle((aussen_l, y0 - b / 2, aussen_r, y0 + b / 2), fill=farbe_rgb)
        zeichnen.rectangle((aussen_l, y1 - b / 2, aussen_r, y1 + b / 2), fill=farbe_rgb)
        zeichnen.rectangle((aussen_l, y0 - b / 2, x0 + links / 2, y1 + b / 2), fill=farbe_rgb)
        zeichnen.rectangle((x1 - rechts / 2, y0 - b / 2, aussen_r, y1 + b / 2), fill=farbe_rgb)

    sichtbar = [(i, _in_pixel(r, clip, zoom)) for i, r in enumerate(rechtecke)
                if _schneiden(r, tuple(clip))]
    if sichtbar:
        toenung = Image.new("RGB", bild.size, (255, 255, 255))
        zeichnen = ImageDraw.Draw(toenung)
        for _, p in sichtbar:
            zeichnen.rectangle(p, fill=_ton(rgb, _TOENUNG[farbe]))
        bild = ImageChops.multiply(bild, toenung)
    zeichnen = ImageDraw.Draw(bild)
    for i, p in sichtbar:
        rahmen(zeichnen, p, rand, *seiten_px(staerken, i, rand), rgb)
    for i, r in enumerate(neben):
        if _schneiden(r, tuple(clip)):
            rahmen(zeichnen, _in_pixel(r, clip, zoom), duenn,
                   *seiten_px(staerken_neben, i, duenn), _NEBEN_FARBE)
    return bild


def _beschriftung_zeichnen(zeichnen: ImageDraw.ImageDraw, xy: tuple, text: str, farbe: tuple,
                           groesse: int, breite: int, rechts_davon: bool = True) -> None:
    """Kurzer Text mit weißem Hintergrund neben einem Punkt (rechts, sonst links)."""
    schrift = _schrift(groesse)
    x, y = xy
    box = zeichnen.textbbox((0, 0), text, font=schrift)
    tw, th = box[2] - box[0], box[3] - box[1]
    abstand = groesse * 0.9
    tx = x + abstand if rechts_davon and x + abstand + tw < breite - 6 else x - abstand - tw
    ty = y - th / 2 - box[1]
    pad = groesse * 0.18
    zeichnen.rectangle((tx - pad, ty + box[1] - pad, tx + tw + pad, ty + box[3] + pad),
                       fill=(255, 255, 255))
    zeichnen.text((tx, ty), text, fill=farbe, font=schrift)


def _kurve_zeichnen(bild: Image.Image, seite: pymupdf.Page, clip, zoom: float,
                    teil: Fundstelle, farbe: str, eigenes_dokument: bool, rand: int,
                    breite_px: int) -> Image.Image:
    """Diagramm: Saum entlang der betroffenen Kurve und Kreis am Prüfpunkt
    (eigenes Dokument zusätzlich der Tabellenwert als grüner Kreis)."""
    if not teil.grafik_bereich:
        return bild
    linien = _kurven_linien(seite, teil.kurve_farbe, teil.grafik_bereich)
    rgb = FARBEN[farbe]
    if linien:
        toenung = Image.new("RGB", bild.size, (255, 255, 255))
        zeichnen = ImageDraw.Draw(toenung)
        breite = max(6, round(4.5 * zoom))
        for punkte in linien:
            zeichnen.line([((x - clip.x0) * zoom, (y - clip.y0) * zoom) for x, y in punkte],
                          fill=_ton(rgb, 0.42), width=breite, joint="curve")
        bild = ImageChops.multiply(bild, toenung)
    if not teil.pruefpunkt or not linien:
        return bild
    achsen = _achsen(seite, teil.grafik_bereich)
    if achsen is None:
        return bild
    (ax, bx), (ay, by) = achsen
    x_wert, y_grafik, y_tabelle = teil.pruefpunkt
    x_pt = ax + bx * x_wert
    y_kurve = _y_auf_kurve(linien, x_pt)
    if y_kurve is None:
        return bild
    zeichnen = ImageDraw.Draw(bild)
    radius = max(14, round(5.5 * zoom))
    groesse = max(22, round(breite_px / 48))
    px, py = (x_pt - clip.x0) * zoom, (y_kurve - clip.y0) * zoom
    zeichnen.ellipse((px - radius, py - radius, px + radius, py + radius), outline=rgb, width=rand)
    if eigenes_dokument:
        pt_tabelle = ((ay + by * y_tabelle) - clip.y0) * zoom
        zeichnen.ellipse((px - radius, pt_tabelle - radius, px + radius, pt_tabelle + radius),
                         outline=_OK_FARBE, width=rand)
        oben_grafik = py < pt_tabelle
        _beschriftung_zeichnen(zeichnen, (px, py - (0.6 * radius if oben_grafik else -0.6 * radius)),
                               f"Grafik ≈ {_de_zahl(y_grafik)}", rgb, groesse, bild.width)
        _beschriftung_zeichnen(zeichnen, (px, pt_tabelle + (0.6 * radius if oben_grafik
                                                             else -0.6 * radius)),
                               f"Tabelle {_de_zahl(y_tabelle)}", _OK_FARBE, groesse, bild.width)
    else:
        y_wert = (y_kurve - ay) / by if by else y_tabelle
        _beschriftung_zeichnen(zeichnen, (px, py), f"≈ {_de_zahl(y_wert)}", rgb, groesse,
                               bild.width)
    return bild


def _de_zahl(wert: float) -> str:
    text = f"{wert:.2f}".rstrip("0").rstrip(".") if abs(wert) < 100 else f"{wert:.0f}"
    return text.replace(".", ",")


def _einfuegemarke_zeichnen(bild: Image.Image, clip, zoom: float, marke: tuple, text: str,
                            farbe: str, rand: int, breite_px: int) -> Image.Image:
    """Schiebt an der Stelle der Marke eine farbige Zeile mit Beschriftung ein
    („Hier fehlt der Eintrag …“) – die Nachbarzeilen bleiben unmarkiert."""
    x0, x1, y = marke
    py = round((y - clip.y0) * zoom)
    if not 0 < py < bild.height:
        return bild
    rgb = FARBEN[farbe]
    hoehe = max(48, round(breite_px / 24))
    band = Image.new("RGB", (bild.width, hoehe), (255, 255, 255))
    zeichnen = ImageDraw.Draw(band)
    px0 = max(0, round((x0 - clip.x0) * zoom))
    px1 = min(bild.width - 1, round((x1 - clip.x0) * zoom))
    zeichnen.rectangle((px0, rand // 2, px1, hoehe - 1 - rand // 2),
                       fill=_ton(rgb, _TOENUNG[farbe]), outline=rgb, width=rand)
    k = hoehe * 0.26                                     # Keil = Einfügezeichen
    zeichnen.polygon([(px0 + 0.8 * k, hoehe / 2 - k), (px0 + 0.8 * k, hoehe / 2 + k),
                      (px0 + 2.0 * k, hoehe / 2)], fill=rgb)
    dunkel = tuple(round(c * 0.7) for c in rgb)
    zeichnen.text((px0 + 2.6 * k, hoehe / 2), text, fill=dunkel,
                  font=_schrift(round(hoehe * 0.5)), anchor="lm")
    neu = Image.new("RGB", (bild.width, bild.height + hoehe), (255, 255, 255))
    neu.paste(bild.crop((0, 0, bild.width, py)), (0, 0))
    neu.paste(band, (0, py))
    neu.paste(bild.crop((0, py, bild.width, bild.height)), (0, py + hoehe))
    return neu


def _leerraum_kuerzen(bild: Image.Image, zoom: float) -> Image.Image:
    """Kürzt lange weiße Zwischenräume (z. B. über/unter abgesetzten Formeln)
    und den Rand oben/unten – bei gleicher Bildhöhe auf der Leinwand wird der
    Text so größer. Markierungen sind farbig und bleiben unberührt."""
    grau = np.asarray(bild.convert("L"))
    leer = (grau < 235).sum(axis=1) <= 1
    behalten = np.ones(len(leer), dtype=bool)
    n, i = len(leer), 0
    while i < n:
        if not leer[i]:
            i += 1
            continue
        j = i
        while j < n and leer[j]:
            j += 1
        lauf = j - i
        if i == 0 or j == n:                       # Rand oben/unten
            weg = int(lauf - _LEERRAUM_RAND_PT * zoom)
            if weg > 0:
                if i == 0:
                    behalten[0:weg] = False
                else:
                    behalten[j - weg:j] = False
        elif lauf > _LEERRAUM_MAX_PT * zoom:       # Zwischenraum
            weg = int(lauf - _LEERRAUM_REST_PT * zoom)
            start = i + (lauf - weg) // 2
            behalten[start:start + weg] = False
        i = j
    if behalten.all() or behalten.sum() < 10:
        return bild
    return Image.fromarray(np.asarray(bild)[behalten])


_TRENNER = "trenner"


def _beschriftungsbalken(text: str, breite_px: int) -> Image.Image:
    """Kopfbalken „Seite N“ für Teile auf verschiedenen Seiten."""
    hoehe = max(40, round(breite_px / 30))
    balken = Image.new("RGB", (breite_px, hoehe), (232, 240, 250))
    ImageDraw.Draw(balken).text((round(hoehe * 0.4), hoehe / 2), text, fill=(0, 55, 110),
                                font=_schrift(round(hoehe * 0.56)), anchor="lm")
    return balken


def _stapeln(bloecke: list, breite_px: int) -> Image.Image:
    """Bilder untereinander; _TRENNER = gestrichelte Linie (ausgelassene Zeilen).
    Das Ergebnis ist genau breite_px breit (Rundung der Pixmap ±1 Pixel)."""
    luecke = max(18, round(breite_px / 60))
    breite = breite_px
    hoehe = sum(luecke if b is _TRENNER else b.height for b in bloecke)
    gesamt = Image.new("RGB", (breite, hoehe), (255, 255, 255))
    zeichnen = ImageDraw.Draw(gesamt)
    y = 0
    strich = max(2, round(breite_px / 600))
    for b in bloecke:
        if b is _TRENNER:
            mitte = y + luecke // 2
            for x in range(0, breite, 28):
                zeichnen.line((x, mitte, x + 14, mitte), fill=(150, 150, 150), width=strich)
            y += luecke
        else:
            gesamt.paste(b, (0, y))
            y += b.height
    return gesamt


def _rendere_teil(pfad: str, teil: Fundstelle, zoom: float, breite_pt: float, breite_px: int,
                  markieren: bool, farbe: str, an_text_anpassen: bool) -> list:
    """Bilder eines Teils (eine Seite): ggf. Spaltenkopf, dann die Streifen."""
    seite = _dokument(pfad)[teil.seite - 1]
    idx = _seitenindex(pfad, teil.seite)
    rand = max(3, round(breite_px * _RAND_ANTEIL))
    # x-Bereich: gemeinsame Breite aller Teile, mittig um den eigenen Ausschnitt
    mitte = (teil.ausschnitt[0] + teil.ausschnitt[2]) / 2
    x0 = min(max(seite.rect.x0, mitte - breite_pt / 2), max(seite.rect.x0,
                                                             seite.rect.x1 - breite_pt))
    x1 = min(seite.rect.x1, x0 + breite_pt)
    streifen = list(teil.streifen) or [(teil.ausschnitt[1], teil.ausschnitt[3])]
    kopf = teil.kopf
    if an_text_anpassen:                   # Layout des anderen Dokuments minimal abweichend
        streifen = [(r[1], r[3]) for r in (_in_luecke(idx, (x0, a, x1, b), 3.0)
                                          for a, b in streifen)]
        kopf = _in_luecke(idx, kopf, 3.0) if kopf else None

    rechtecke, neben = list(teil.rechtecke), list(teil.nebenrechtecke)
    if markieren and an_text_anpassen:
        if teil.einfuegemarke:
            rechtecke = _zeile_an_marke(idx, teil.einfuegemarke)
        elif teil.vergleich_begriffe and (ersatz := _vergleich_treffer(idx, teil)):
            rechtecke = ersatz
        elif rechtecke:
            rechtecke = _an_text_anpassen(pfad, teil)
    staerken = staerken_neben = None
    if markieren:
        rechtecke, staerken = _rahmen_an_nachbarn(idx, rechtecke, rand / zoom)
        neben, staerken_neben = _rahmen_an_nachbarn(idx, neben,
                                                    max(2, round(rand / 2.5)) / zoom)

    bloecke = []
    erster = pymupdf.Rect(x0, streifen[0][0], x1, streifen[0][1])
    if kopf:
        kopf_clip = pymupdf.Rect(x0, kopf[1], x1, kopf[3]) & seite.rect
        if not kopf_clip.is_empty and not kopf_clip.intersects(erster):
            bloecke += [_leerraum_kuerzen(_pixmap_bild(seite, kopf_clip, zoom), zoom), _TRENNER]
    for nr, (y0, y1) in enumerate(streifen):
        clip = pymupdf.Rect(x0, y0, x1, y1) & seite.rect
        bild = _pixmap_bild(seite, clip, zoom)
        if markieren:
            bild = _markierungen_zeichnen(bild, clip, zoom, rechtecke, neben, farbe, rand,
                                          staerken, staerken_neben)
            if teil.kurve_farbe:
                bild = _kurve_zeichnen(bild, seite, clip, zoom, teil, farbe,
                                       not an_text_anpassen, rand, breite_px)
            if teil.einfuegemarke and not an_text_anpassen:
                bild = _einfuegemarke_zeichnen(bild, clip, zoom, teil.einfuegemarke,
                                               teil.marke_text or "Hier fehlt ein Eintrag",
                                               farbe, rand, breite_px)
        bloecke.append(_leerraum_kuerzen(bild, zoom))
        if nr < len(streifen) - 1:
            bloecke.append(_TRENNER)
    return bloecke


def rendere_ausschnitt(pdf_pfad, fundstelle: Fundstelle, markieren: bool = True,
                       farbe: str = "fehler", breite_px: int = 1800,
                       an_text_anpassen: bool | None = None) -> bytes:
    """Rendert den Ausschnitt einer Fundstelle als PNG (Breite breite_px).

    farbe "fehler": kräftiges Rot-Orange; "warnung": Orange; "neutral": Blau
    #0050A0 (für dieselbe Stelle in der fehlerfreien TB). an_text_anpassen
    (Standard: bei "neutral") schmiegt die Markierung an die Wörter des
    gerenderten Dokuments an – nötig, wenn die Fundstelle aus dem *anderen*
    Dokument stammt (gleiche Seite, gleicher Ausschnitt, Layout identisch).

    Weit auseinander liegende Treffer derselben Seite erscheinen als schmale
    Streifen mit gestrichelter Trennung; lange weiße Zwischenräume werden
    gekürzt. Hat die Fundstelle weitere (vom Aufrufer gesetzte Gegenstellen),
    stehen diese darunter, je mit Kopfbalken (beschriftung bzw. „Seite N“).
    Die PDF-Datei wird nicht verändert.
    """
    pfad = _pfad(pdf_pfad)
    farbe = farbe if farbe in FARBEN else "fehler"
    if an_text_anpassen is None:
        an_text_anpassen = farbe == "neutral"
    teile = [fundstelle] + list(fundstelle.weitere or [])
    breite_pt = max(max(t.ausschnitt[2] - t.ausschnitt[0] for t in teile), 1.0)
    zoom = breite_px / breite_pt
    bloecke = []
    with _SPERRE:
        for teil in teile:
            if len(teile) > 1:
                bloecke.append(_beschriftungsbalken(teil.beschriftung or f"Seite {teil.seite}",
                                                    breite_px))
            bloecke += _rendere_teil(pfad, teil, zoom, breite_pt, breite_px, markieren,
                                     farbe, an_text_anpassen)
    bild = _stapeln(bloecke, breite_px)
    puffer = io.BytesIO()
    bild.save(puffer, format="PNG", optimize=True)
    return puffer.getvalue()
