"""
Werkzeug: Fundstellen aller Befunde rendern (Sichtprüfung vor der Live-Demo)
=============================================================================

Liest Befunde und rendert zu jedem die Fundstelle als PNG:

* die beiden Referenz-Prüfberichte des Nachweis-Laufs (fehlerhafte TB und
  Gegenprobe auf der fehlerfreien TB) – Standard bzw. ``--referenz``;
* optional Ergebnisdateien von Live-Läufen (``--live datei.json …``) im Format
  ``{"dokument": "fehlerhaft"|"fehlerfrei", "laufzeit_s": …,
  "ergebnisse": [{"id": "L-03", "befunde": [{"beschreibung", "seite",
  "schwere"}, …]}, …]}``.

Ausgabe je Befund:

  <ziel>/<präfix>_<nr>_<checkid>_S<seite>.png             Befund-Dokument, markiert
  <ziel>/<präfix>_<nr>_<checkid>_S<seite>_vergleich.png   dieselbe Stelle im anderen
                                                          Dokument (Layout identisch),
                                                          neutral markiert
  <ziel>/…_gegen<k>.png / …_gegen<k>_vergleich.png        Gegenstellen auf anderen
                                                          Seiten (finde_gegenstellen)
  <ziel>/index.json                                       Übersicht aller Befunde

Präfix: „fehlerhaft“/„fehlerfrei“ (Referenzberichte) bzw. der Dateiname der
Live-Ergebnisdatei (z. B. „live1_fehlerhaft“).

Es werden keine Sprachmodell-Aufrufe ausgeführt; PDFs und Berichte werden
nur gelesen.

Aufruf (aus dem Ordner gui/):
    python werkzeuge/render_fundstellen.py --ziel <Ordner> [--breite 1800]
           [--referenz] [--live lauf1.json lauf2.json]
Ohne --referenz und ohne --live werden die Referenzberichte gerendert.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True          # keine __pycache__-Ordner im Repo
GUI_ORDNER = Path(__file__).resolve().parents[1]
TB_ORDNER = GUI_ORDNER.parent
sys.path.insert(0, str(GUI_ORDNER))

from fundstellen import (anzeige_text, finde_fundstelle, finde_gegenstellen,  # noqa: E402
                         rendere_ausschnitt)

PDF = {
    "fehlerhaft": TB_ORDNER / "synthetische-tb" / "TB_VitalPlus_fehlerhaft.pdf",
    "fehlerfrei": TB_ORDNER / "synthetische-tb" / "TB_VitalPlus.pdf",
}
ANDERES = {"fehlerhaft": "fehlerfrei", "fehlerfrei": "fehlerhaft"}
BERICHTE = {
    "fehlerhaft": TB_ORDNER / "validierungsnotebook" / "pruefbericht_TB_VitalPlus_fehlerhaft.json",
    "fehlerfrei": TB_ORDNER / "validierungsnotebook" / "pruefbericht_TB_VitalPlus.json",
}


def befunde_referenz():
    """(präfix, dok, nr, check_id, befund) aus den Referenz-Prüfberichten."""
    for dok, pfad in BERICHTE.items():
        bericht = json.loads(pfad.read_text(encoding="utf-8"))
        nr = 0
        for check in bericht["checks"]:
            for befund in check.get("befunde", []):
                nr += 1
                yield dok, dok, nr, check["id"], befund


def befunde_live(pfad: Path):
    """(präfix, dok, nr, check_id, befund) aus einer Live-Ergebnisdatei."""
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    dok = daten["dokument"]
    nr = 0
    for ergebnis in daten["ergebnisse"]:
        for befund in ergebnis.get("befunde", []):
            nr += 1
            yield pfad.stem, dok, nr, ergebnis["id"], befund


def rendern(ziel: Path, stamm: str, pdf: Path, vergleich_pdf: Path, fund, farbe: str,
            breite: int) -> list[str]:
    """Fundstelle markiert und neutral im anderen Dokument rendern."""
    (ziel / f"{stamm}.png").write_bytes(
        rendere_ausschnitt(pdf, fund, markieren=True, farbe=farbe, breite_px=breite))
    (ziel / f"{stamm}_vergleich.png").write_bytes(
        rendere_ausschnitt(vergleich_pdf, fund, markieren=True, farbe="neutral",
                           breite_px=breite))
    return [f"{stamm}.png", f"{stamm}_vergleich.png"]


def main() -> int:
    # Windows-Konsole (cp1252) kann z. B. U+FE00 aus Formel-Auszügen nicht
    # darstellen – ohne diese Umstellung bräche die Ausgabe ab.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--ziel", required=True, help="Ausgabeordner für PNGs und index.json")
    parser.add_argument("--breite", type=int, default=1800, help="Bildbreite in Pixeln")
    parser.add_argument("--referenz", action="store_true",
                        help="Referenz-Prüfberichte rendern (Standard ohne --live)")
    parser.add_argument("--live", nargs="+", type=Path, default=[], metavar="JSON",
                        help="Ergebnisdateien von Live-Läufen zusätzlich rendern")
    args = parser.parse_args()

    quellen = []
    if args.referenz or not args.live:
        quellen.append(befunde_referenz())
    for pfad in args.live:
        if not pfad.exists():
            print(f"Live-Datei fehlt: {pfad}")
            return 1
        quellen.append(befunde_live(pfad))

    ziel = Path(args.ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    index = []
    methoden = Counter()
    beginn = time.perf_counter()

    for befunde in quellen:
        for praefix, dok, nr, check_id, befund in befunde:
            pdf, vergleich_pdf = PDF[dok], PDF[ANDERES[dok]]
            t0 = time.perf_counter()
            fund = finde_fundstelle(pdf, check_id, befund["beschreibung"], befund.get("seite"))
            gegen = finde_gegenstellen(pdf, check_id, befund["beschreibung"],
                                       befund.get("seite"))
            dauer_suche = time.perf_counter() - t0
            stamm = f"{praefix}_{nr:02d}_{check_id}_S{befund.get('seite')}"
            farbe = "warnung" if befund.get("schwere") == "WARNUNG" else "fehler"
            dateien = []
            if fund is not None:
                dateien += rendern(ziel, stamm, pdf, vergleich_pdf, fund, farbe, args.breite)
                methoden[fund.methode] += 1
            for k, g in enumerate(gegen, start=1):
                dateien += rendern(ziel, f"{stamm}_gegen{k}", pdf, vergleich_pdf, g, farbe,
                                   args.breite)
            eintrag = {
                "quelle": praefix,
                "dok": dok,
                "nr": nr,
                "check_id": check_id,
                "schwere": befund.get("schwere"),
                "seite": befund.get("seite"),
                "beschreibung": befund["beschreibung"],
                "anzeige_text": anzeige_text(befund["beschreibung"]),
                "methode": fund.methode if fund else None,
                "fund_seite": fund.seite if fund else None,
                "rechtecke": fund.rechtecke if fund else [],
                "ausschnitt": fund.ausschnitt if fund else None,
                "kopf": fund.kopf if fund else None,
                "streifen": fund.streifen if fund else [],
                "neben": fund.nebenrechtecke if fund else [],
                "einfuegemarke": fund.einfuegemarke if fund else None,
                "beschriftung": fund.beschriftung if fund else "",
                "gegenstellen": [{"seite": g.seite, "beschriftung": g.beschriftung,
                                  "rechtecke": g.rechtecke, "ausschnitt": g.ausschnitt}
                                 for g in gegen],
                "hinweis": fund.hinweis if fund else "",
                "suche_ms": round(dauer_suche * 1000, 1),
                "dateien": dateien,
            }
            index.append(eintrag)
            zusatz = "".join([
                " +Kopf" if eintrag["kopf"] else "",
                f" {len(eintrag['streifen'])} Streifen" if eintrag["streifen"] else "",
                f" +{len(eintrag['neben'])} Kontext" if eintrag["neben"] else "",
                " +Einfügemarke" if eintrag["einfuegemarke"] else "",
                "".join(f" +S.{g.seite}" for g in gegen)])
            print(f"{stamm:36s} {eintrag['methode'] or '-':17s} "
                  f"S.{eintrag['fund_seite']!s:>3} {len(eintrag['rechtecke'])} Markierung(en)"
                  f"{zusatz}  {eintrag['hinweis'][:80]}")

    (ziel / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    print()
    print(f"{len(index)} Befunde in {time.perf_counter() - beginn:.1f} s gerendert -> {ziel}")
    print("Methoden: " + ", ".join(f"{m}: {n}" for m, n in methoden.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
