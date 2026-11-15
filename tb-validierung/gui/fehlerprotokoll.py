"""Abgleich der Prüfbefunde mit dem Fehlerprotokoll der synthetischen TB.

In die fehlerhafte Variante ``TB_VitalPlus_fehlerhaft.pdf`` wurden 13 Fehler
absichtlich eingebaut (F01–F13, F05 besteht aus drei Tippfehlern F05a–c).
Dieses Modul

* liest die Tabelle aus ``synthetische-tb/Fehlerprotokoll.md`` ein
  (``lade_fehlerprotokoll``) und
* ordnet die Befunde eines Prüflaufs den dokumentierten Fehlern zu
  (``gleiche_ab``), damit die GUI zeigen kann, welche Fehler gefunden wurden.

Zuordnungsregel je Fehler = Seitenfenster + Textmuster:

1. Seitenfenster: die Seite(n) des Fehlers im fehlerhaften PDF (mit PyMuPDF
   verifiziert, siehe Test) und ggf. die Seiten der widersprechenden
   Gegenstelle, die ein Konsistenz-Check stattdessen nennen kann – jeweils
   ±1 Seite Toleranz, weil das Sprachmodell die Seite aus dem nächsten
   [Seite N]-Marker abliest.
2. Textmuster: reguläre Ausdrücke auf die Befundbeschreibung. Das Kernmuster
   trifft den Fehlwert bzw. das Fehlbild selbst (z. B. „653,33“, „§ 4 VAG“,
   „Alterungsrückstelung“). Diese Werte stehen nur in der fehlerhaften TB,
   nicht in der fehlerfreien Gegenprobe. Ergänzende Muster fangen
   Umformulierungen ohne Zahlenwert ab (die Live-Antworten des Sprachmodells
   klingen jedes Mal etwas anders), gelten aber nur im Seitenfenster.

Die Befunde werden nur über die vier Attribute ``check_id``,
``beschreibung``, ``seite`` und ``schwere`` angesprochen (``BefundGUI`` aus
engine.py oder jede gleichartige Attrappe); ausgewertet werden davon
``beschreibung`` und ``seite``.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Protocol, TypeVar

__all__ = [
    "FEHLERPROTOKOLL_PFAD", "SEITEN_TOLERANZ", "DokFehler", "BefundArtig",
    "lade_fehlerprotokoll", "gleiche_ab", "passt_zu", "fehler_zu_befund",
]

FEHLERPROTOKOLL_PFAD = (Path(__file__).resolve().parent.parent
                        / "synthetische-tb" / "Fehlerprotokoll.md")

# Erlaubte Abweichung der Befundseite vom Seitenfenster (in Seiten)
SEITEN_TOLERANZ = 1


# =============================================================================
# Datenstrukturen
# =============================================================================
class BefundArtig(Protocol):
    """Was ein Befund mitbringen muss (erfüllt von engine.BefundGUI)."""
    check_id: str
    beschreibung: str
    seite: int | None
    schwere: str


B = TypeVar("B", bound=BefundArtig)


@dataclass(frozen=True)
class DokFehler:
    """Ein dokumentierter Fehler aus dem Fehlerprotokoll."""
    nr: str                        # "F01" … "F13", F05a/F05b/F05c einzeln
    ort: str                       # Fundort laut Protokoll
    fehler: str                    # was falsch ist
    korrekt: str                   # was richtig wäre
    kurz: str                      # sehr kurzer Laientext für die Leinwand
    kategorie: str = ""            # Kategorie des Prüf-Katalogs (Phase 3)
    seiten: tuple[int, ...] = ()   # PDF-Seite(n) des Fehlers (1-basiert, verifiziert)
    markierung: str | None = None  # Suchtext für page.search_for() im fehlerhaften PDF
    markierung_korrekt: str | None = None  # Suchtext an derselben Stelle der fehlerfreien TB

    @property
    def gruppe(self) -> str:
        """Hauptnummer ohne Buchstaben ("F05a" -> "F05"), um 13 Fehler zu zählen."""
        treffer = re.match(r"F\d+", self.nr)
        return treffer.group(0) if treffer else self.nr


@dataclass(frozen=True)
class _Regel:
    """Zuordnungsregel eines dokumentierten Fehlers (siehe Modul-Docstring)."""
    kurz: str
    fundstellen: tuple[int, ...]               # verifizierte Seite(n) des Fehlers
    muster: tuple[tuple[re.Pattern, ...], ...]  # ODER über Alternativen, UND innerhalb
    gegenstellen: tuple[int, ...] = ()         # Seiten der widersprechenden Passage
    seitenunabhaengig: bool = False            # Seite spielt keine Rolle (fehlender Eintrag)
    kern_eindeutig: bool = True                # Kernmuster = Fehlwert, der nur hier vorkommt
    markierung: str | None = None
    markierung_korrekt: str | None = None


def _alle(*muster: str) -> tuple[re.Pattern, ...]:
    """Eine Muster-Alternative: alle Ausdrücke müssen in der Beschreibung vorkommen."""
    return tuple(re.compile(m, re.IGNORECASE) for m in muster)


# =============================================================================
# Zuordnungsregeln F01–F13
# =============================================================================
# Die erste Alternative in ``muster`` ist jeweils das Kernmuster.
# Seitenzahlen = physische PDF-Seiten (1-basiert, wie in den Prüfberichten),
# nicht die „Blatt“-Nummern der Kopfzeile (Blatt = Seite − 1).
_ZAHL_VORN = r"(?<![\d.,])"                  # keine Ziffer direkt davor
_PROZENT = r"\s*(?:%|Prozent|v\.\s*H\.)"
_GAMMA = "\N{MATHEMATICAL ITALIC SMALL GAMMA}"
_B_KURSIV = "\N{MATHEMATICAL ITALIC SMALL B}"
_X_KURSIV = "\N{MATHEMATICAL ITALIC SMALL X}"
_SIGMA_KURSIV = "\N{MATHEMATICAL ITALIC SMALL SIGMA}"

_REGELN: dict[str, _Regel] = {
    # Anhang 3, Beitragstabelle, Alter 50, b_x Männer: 653,33 statt 635,33
    "F01": _Regel(
        kurz="Zahlendreher in der Beitragstabelle",
        fundstellen=(89,),
        muster=(
            _alle(_ZAHL_VORN + r"653[,.]33(?!\d)"),
            _alle(r"Beitrags(?:tabelle|rate)|Monatsbeitrag|Anhang\s*3",
                  r"Alter\s*50|x\s*=\s*50|Eintrittsalter\s*50",
                  r"Zahlendreher|Ziffern\s*vertauscht"),
        ),
        markierung="653,33", markierung_korrekt="635,33"),

    # Anlage 2.4, Zeile Sicherheitszuschlag: 4,5 % statt 5,0 % (§ 7 KVAV)
    "F02": _Regel(
        kurz="Sicherheitszuschlag 4,5 % statt 5,0 %",
        fundstellen=(79,),
        gegenstellen=(27,),            # Abschnitt 2.4.1 (Sicherheitszuschlag)
        muster=(
            _alle(_ZAHL_VORN + r"4[,.]50?" + _PROZENT,
                  r"Sicherheits|σ|sigma|Zuschlag"),
            _alle(r"Sicherheitszuschlag|σ|sigma",
                  _ZAHL_VORN + r"5(?:[,.]0)?" + _PROZENT,
                  r"Tabelle|uneinheitlich|widersprüch|Widerspruch|abweich|weicht"
                  r"|unterschreit|statt"),
        ),
        markierung="4,5 %", markierung_korrekt=f"{_SIGMA_KURSIV} 5,0 %"),

    # Abschnitt 2.1: Höchstrechnungszins „gemäß § 4 VAG“ statt § 4 KVAV
    "F03": _Regel(
        kurz="falsches Gesetz zitiert",
        fundstellen=(16,),
        muster=(
            _alle(r"(?:§|Paragra(?:ph|f)(?:en)?|Para\.)\s*4(?![\d,.])\s*"
                  r"(?:Abs(?:atz|\.)\s*\d+\s*)?(?:des\s+|im\s+)?VAG\b"),
            # Umschreibung: „VAG zitiert, richtig wäre § 4 KVAV“ (bzw. umgekehrt)
            _alle(r"\bVAG\b[^.]{0,80}?(?:statt|anstelle|anstatt|sondern|richtig"
                  r"|korrekt|einschlägig)[^.]{0,40}?§\s*4(?![\d,.])\s*KVAV"),
            _alle(r"§\s*4(?![\d,.])\s*KVAV[^.]{0,40}?(?:statt|anstelle|anstatt"
                  r"|nicht)\s[^.]{0,30}?\bVAG\b"),
        ),
        markierung="§ 4 VAG", markierung_korrekt="§ 4 KVAV"),

    # Abschnitt 5.2: Verweis auf nicht existierendes Label -> „Abschnitt ??“
    "F04": _Regel(
        kurz="Verweis ins Leere",
        fundstellen=(45,),
        muster=(
            _alle(r"\?\?"),
            _alle(r"nicht\s+aufgel[öo]st|unaufgel[öo]st|ins\s+Leere"
                  r"|(?:tote|kaputte|defekte|fehlerhafte|ungültige|leere)[rn]?\s+"
                  r"(?:Quer)?verweis|Verweisziel|nicht\s+existier|sec:anlage523"),
        ),
        markierung="Abschnitt ??", markierung_korrekt="verwendet (Anlage 5.2)"),

    # Tippfehler (Rechtschreibung); die falschen Schreibweisen gibt es nur hier
    "F05a": _Regel(
        kurz="Tippfehler „Alterungsrückstelung“",
        fundstellen=(44,),
        muster=(_alle(r"r(?:ü|ue|u)ckstelung"),),
        markierung="Alterungsrückstelung",
        markierung_korrekt="Die Alterungsrückstellung wird"),
    "F05b": _Regel(
        kurz="Tippfehler „Äquivalenzprinizip“",
        fundstellen=(35,),
        muster=(_alle(r"prinizip"),),
        markierung="Äquivalenzprinizip", markierung_korrekt="Äquivalenzprinzip"),
    "F05c": _Regel(
        kurz="Tippfehler „Krankheitskostenvollversichrung“",
        fundstellen=(11,),
        muster=(_alle(r"versichrung"),),
        markierung="Krankheitskostenvollversichrung",
        markierung_korrekt="Krankheitskostenvollversicherung"),

    # Symbolverzeichnis (Abschnitt 0.3, Seiten 8–9): Eintrag DQ_x fehlt.
    # Ein fehlender Eintrag hat keine Fundstelle im Text – Checks melden die
    # Verwendungsstellen (7, 20, 34, 44, …), daher seitenunabhängig.
    "F06": _Regel(
        kurz="Symbol fehlt im Verzeichnis",
        fundstellen=(8, 9),
        seitenunabhaengig=True,
        muster=(
            _alle(r"(?<![A-Za-z])(?-i:DQ)",
                  r"Symbolverzeichnis|Symbol(?:übersicht|liste|tabelle)|Glossar"
                  r"|Verzeichnis|Formelzeichen|nicht\s+(?:erklärt|definiert|eingeführt"
                  r"|aufgeführt|erläutert)|undefiniert|ohne\s+(?:Erklärung|Definition)"),
        ),
        markierung=None,                # die Lücke selbst ist nicht markierbar
        markierung_korrekt="diskontierte Übergangswahrscheinlichkeit"),

    # Anlage 2.3.3, Einleitungstext: G^M = 1910,0070 statt 1901,0070 EUR
    "F07": _Regel(
        kurz="Parameter doppelt mit anderem Wert",
        fundstellen=(73,),
        gegenstellen=(24,),            # Abschnitt 2.3.3 (Paar für den Konsistenz-Check)
        muster=(
            _alle(_ZAHL_VORN + r"1[.\s]?910[,.]007"),
            _alle(r"(?-i:(?<![A-Za-z])G\s*[\^_]?\s*\{?M\}?(?![A-Za-zÄÖÜäöü]))"
                  r"|Grundkopfschaden\w*\s+(?:für\s+|der\s+)?Männer",
                  r"Zahlendreher|vertauscht|unterschiedliche[nr]?\s+Wert"
                  r"|widersprüchlich|Widerspruch|abweich"),
        ),
        markierung="1910,0070", markierung_korrekt="1901,0070 EUR und"),

    # Anlage 2.2 Männer, Alter 50, (q+w)_x: 0,037271 statt 0,036271
    "F08": _Regel(
        kurz="Summe q + w in der Tabelle falsch",
        fundstellen=(62,),
        muster=(_alle(_ZAHL_VORN + r"0[,.]037\s?271"),),
        markierung="0,037271", markierung_korrekt="0,036271"),

    # Anlage 2.1: Rechnungszins Frauen „2,2 %“, gerechnet ist mit 2,0 %
    "F09": _Regel(
        kurz="Rechnungszins falsch beschriftet",
        fundstellen=(60,),
        gegenstellen=(16, 64, 81),     # Abschnitt 2.1, Ausscheideordnung Frauen, Anlage 3.1
        muster=(
            _alle(_ZAHL_VORN + r"2[,.]20?" + _PROZENT,
                  r"Frau|weiblich|\bF\b|Zins"),
        ),
        markierung="2,2 %", markierung_korrekt="2,0 %"),

    # Inhaltsverzeichnis: „Grundwerte der Versicherungstechnik“ statt
    # „Versicherungstechnische Grundwerte“ (Überschrift auf Seite 81)
    "F10": _Regel(
        kurz="Inhaltsverzeichnis passt nicht",
        fundstellen=(3, 81),
        muster=(
            _alle(r"Grundwerte\s+der\s+Versicherungstechnik"),
            _alle(r"Inhaltsverzeichnis|\bIHV\b",
                  r"Anlage\s*3\.1",
                  r"Titel|Überschrift|lautet|abweich|stimmt\s+nicht|passt\s+nicht"
                  r"|anders|falsch"),
        ),
        markierung="Grundwerte der Versicherungstechnik",
        markierung_korrekt="Versicherungstechnische Grundwerte"),

    # Anhang 5, Schritt 3: P_43 = 4676,48 statt 4667,48 EUR
    "F11": _Regel(
        kurz="Rechenwert im Anhang falsch",
        fundstellen=(92,),
        muster=(_alle(_ZAHL_VORN + r"4[.\s]?676[,.]48"),),
        markierung="4676,48", markierung_korrekt="4667,48"),

    # Abschnitt 5.1, Gl. (30): „… · b + γ_x“ statt „… · b − γ_x“.
    # Gegenstelle: Anhang 5 (Seite 92) rechnet mit der korrekten Formel.
    # Kein Fehlwert -> Kernmuster ist nicht eindeutig, Seite ist Pflicht.
    "F12": _Regel(
        kurz="Vorzeichenfehler in der Formel",
        fundstellen=(44,),
        gegenstellen=(92,),
        kern_eindeutig=False,
        muster=(
            _alle(r"Vorzeichen|Pluszeichen|Minuszeichen|\bplus\b|\bminus\b"
                  r"|addiert|subtrahiert|abgezogen",
                  r"γ|gamma|Zillmer|\bGl(?:eichung|\.)?\s*\(?30\)?(?!\d)"),
        ),
        markierung=f"{_B_KURSIV}+ {_GAMMA}{_X_KURSIV}",
        # Die korrekte Stelle ist per Textsuche nicht eindeutig auffindbar;
        # das Layout ist identisch, die Position der Markierung also dieselbe.
        markierung_korrekt=None),

    # Anlage 2.3.3, Profil-Grafik (Seite 75): Frauen-Kurve um Faktor 1,5 überhöht
    "F13": _Regel(
        kurz="Grafik passt nicht zur Tabelle",
        fundstellen=(75,),
        kern_eindeutig=False,
        muster=(
            _alle(r"Grafik|Diagramm|Kurve|Abbildung|Schaubild|Plot",
                  # Die abweichende Kurve muss die der Frauen sein (nicht Männer)
                  r"Kurve\s*[„\"»'‚]\s*[^„“”\"»«'‚‘’]{0,25}?(?:Frau|weiblich|Damen)"
                  r"|(?:Frau|weiblich|Damen)\w*[\s-]*(?:Kurve|Linie|Graph|Verlauf)"
                  r"|Kurve\w*\s+(?:der|für\s+die|für)\s+(?:Frau|weiblich|Damen)"),
        ),
        markierung=None, markierung_korrekt=None),
}


# =============================================================================
# Fehlerprotokoll einlesen
# =============================================================================
def _md_bereinigen(text: str) -> str:
    """Entfernt Markdown-Auszeichnung (**fett**, `Code`) und glättet Leerraum."""
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r'„([^"“”„]*)"', r"„\1“", text)   # „…" -> „…“ (gerades Schlusszeichen)
    return re.sub(r"\s+", " ", text).strip()


def _zellen(zeile: str) -> list[str]:
    return [z.strip() for z in zeile.strip().strip("|").split("|")]


def _spalte(kopf: list[str], *praefixe: str) -> int:
    """Index der Kopfspalte, die mit einem der Präfixe beginnt."""
    for i, name in enumerate(kopf):
        if any(name.casefold().startswith(p.casefold()) for p in praefixe):
            return i
    raise ValueError(f"Spalte {praefixe[0]!r} fehlt in der Fehlerprotokoll-Tabelle.")


@lru_cache(maxsize=4)
def _lade(pfad: str, _stand: float) -> tuple[DokFehler, ...]:
    """Parst die Markdown-Tabelle (``_stand`` = Änderungszeit, für den Cache)."""
    tabelle = [_zellen(z) for z in Path(pfad).read_text(encoding="utf-8").splitlines()
               if z.lstrip().startswith("|")]
    kopf = next((zellen for zellen in tabelle if zellen[0].startswith("Nr")), None)
    if kopf is None:
        raise ValueError(f"Keine Fehlertabelle (Kopfzeile „Nr.“) in {pfad} gefunden.")
    spalte = {name: _spalte(kopf, name)
              for name in ("Nr", "Kategorie", "Ort", "Fehler", "Korrekt")}
    eintraege: list[DokFehler] = []
    for zellen in tabelle:
        nr = _md_bereinigen(zellen[spalte["Nr"]]) if len(zellen) > spalte["Nr"] else ""
        if not re.fullmatch(r"F\d{2}[a-z]?", nr):
            continue                       # Kopf-, Trennzeile |---| oder Fremdzeile
        if len(zellen) < len(kopf):
            raise ValueError(f"Zeile {nr} im Fehlerprotokoll ist unvollständig.")
        feld = {name: _md_bereinigen(zellen[i]) for name, i in spalte.items()}
        regel = _REGELN.get(nr)
        eintraege.append(DokFehler(
            nr=nr,
            ort=feld["Ort"],
            fehler=feld["Fehler"],
            korrekt=feld["Korrekt"],
            # Fallback für künftige Einträge ohne Regel: gekürzter Fehlertext
            kurz=regel.kurz if regel else feld["Fehler"][:40],
            kategorie=feld["Kategorie"],
            seiten=regel.fundstellen if regel else (),
            markierung=regel.markierung if regel else None,
            markierung_korrekt=regel.markierung_korrekt if regel else None,
        ))
    if not eintraege:
        raise ValueError(f"Keine Fehlertabelle (F01 …) in {pfad} gefunden.")
    return tuple(eintraege)


def lade_fehlerprotokoll(pfad: str | Path = FEHLERPROTOKOLL_PFAD) -> list[DokFehler]:
    """Liest die dokumentierten Fehler (F01–F13 inkl. F05a–c) in Protokoll-Reihenfolge."""
    pfad = Path(pfad).resolve()
    return list(_lade(str(pfad), pfad.stat().st_mtime))


# =============================================================================
# Abgleich Befunde <-> dokumentierte Fehler
# =============================================================================
# Unsichtbare Zeichen aus PDF-Extraktion/Formelsatz (weiches Trennzeichen,
# Nullbreiten-Zeichen, Variantenselektoren wie „︀“)
_UNSICHTBAR = dict.fromkeys(
    [0x00AD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, *range(0xFE00, 0xFE10)])


def _normiere(text: str | None) -> str:
    """NFKC (mathematische Unicode-Buchstaben wie 𝛾 -> γ, geschützte
    Leerzeichen -> Leerzeichen), unsichtbare Zeichen entfernen, Leerraum glätten."""
    text = unicodedata.normalize("NFKC", text or "").translate(_UNSICHTBAR)
    return re.sub(r"\s+", " ", text)


def _seitenzahl(seite) -> int | None:
    """Befundseite als positive Ganzzahl oder None (unbekannt)."""
    try:
        zahl = int(seite)
    except (TypeError, ValueError):
        return None
    return zahl if zahl > 0 else None


def _im_seitenfenster(regel: _Regel, seite: int) -> bool:
    return any(abs(seite - s) <= SEITEN_TOLERANZ
               for s in (*regel.fundstellen, *regel.gegenstellen))


def _regel_greift(regel: _Regel, befund: BefundArtig) -> bool:
    text = _normiere(getattr(befund, "beschreibung", ""))
    seite = _seitenzahl(getattr(befund, "seite", None))
    if regel.seitenunabhaengig:
        alternativen = regel.muster
    elif seite is None:
        # Seite unbekannt: nur ein eindeutiger Fehlwert reicht als Beleg
        alternativen = regel.muster[:1] if regel.kern_eindeutig else ()
    elif _im_seitenfenster(regel, seite):
        alternativen = regel.muster
    else:
        return False
    return any(all(rx.search(text) for rx in alternative) for alternative in alternativen)


def passt_zu(befund: BefundArtig, fehler: DokFehler) -> bool:
    """True, wenn der Befund den dokumentierten Fehler trifft."""
    regel = _REGELN.get(fehler.nr)
    return regel is not None and _regel_greift(regel, befund)


def fehler_zu_befund(befund: BefundArtig,
                     fehlerliste: list[DokFehler] | None = None) -> list[DokFehler]:
    """Alle dokumentierten Fehler, die ein einzelner Befund trifft (meist 0 oder 1)."""
    fehlerliste = lade_fehlerprotokoll() if fehlerliste is None else fehlerliste
    return [f for f in fehlerliste if passt_zu(befund, f)]


def gleiche_ab(befunde: Iterable[B],
               fehlerliste: list[DokFehler] | None = None
               ) -> list[tuple[DokFehler, list[B]]]:
    """Je dokumentiertem Fehler (Protokoll-Reihenfolge) die zuordenbaren Befunde.

    Eine leere Befundliste bedeutet: Dieser Fehler wurde nicht gefunden.
    """
    fehlerliste = lade_fehlerprotokoll() if fehlerliste is None else fehlerliste
    befunde = list(befunde)
    return [(f, [b for b in befunde if passt_zu(b, f)]) for f in fehlerliste]
