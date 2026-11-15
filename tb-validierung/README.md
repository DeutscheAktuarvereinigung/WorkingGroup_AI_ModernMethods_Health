# TB-Validierung: Automatisierte Prüfung Technischer Berechnungsgrundlagen

Technische Berechnungsgrundlagen (TB) dokumentieren die Kalkulation eines
Tarifs der privaten Krankenversicherung (PKV) vollständig und
nachvollziehbar; sie sind Grundlage der Prüfung durch Treuhänder und
Aufsicht. Bei jeder Beitragsanpassung müssen zahlreiche Werte, Tabellen,
Formeln und Querverweise konsistent fortgeschrieben werden – eine
vollständige manuelle Prüfung ist im engen Zeitplan kaum leistbar.

Dieses Deliverable zeigt, wie sich die TB-Validierung durch die Kombination
aus **regelbasierten Prüfungen** und **LLM-gestützter Analyse** (LLM =
Large Language Model, großes Sprachmodell) weitgehend automatisieren lässt –
und wie man die Wirksamkeit eines solchen Prüfwerkzeugs **messbar
nachweist**: an einer vollsynthetischen TB, in die 13 dokumentierte Fehler
gezielt eingebaut wurden.

## Aufbau

```
tb-validierung/
├── README.md                  diese Datei
├── requirements.txt           Python-Abhängigkeiten (getestet mit Python 3.13, Minimum 3.11)
├── synthetische-tb/
│   ├── TB_VitalPlus.pdf             fehlerfreie Fassung der synthetischen TB (93 Seiten)
│   ├── TB_VitalPlus_fehlerhaft.pdf  Prüfobjekt: Fassung mit 13 eingebauten Fehlern („Exemplar V-17b“)
│   ├── Fehlerprotokoll.md           Ground Truth: die 13 Fehler F01–F13 mit Ort, Fehlbild, Soll-Wert
│   ├── kalkulation/
│   │   ├── pipeline.py              Kalkulationsstrecke: Rohdaten → Rechnungsgrundlagen, Barwerte,
│   │   │                            Beiträge, LaTeX-Tabellen (tex/gen/) und Kontroll-CSVs (out/)
│   │   ├── erzeuge_fehlervariante.py  kopiert tex/ → tex_fehlerhaft/ und injiziert die 13 Fehler
│   │   │                              (jeder Einbau wird per assert verifiziert)
│   │   ├── erzeuge_datenbank.py     baut die SQLite-Referenzdatenbank für Prüfung V-13
│   │   └── out/                     Referenzwerte: 4 CSV-Dateien + rechnungsgrundlagen.db
│   ├── tex/                         LaTeX-Quellen der fehlerfreien Fassung (inkl. generierter gen/)
│   └── tex_fehlerhaft/              LaTeX-Quellen der fehlerhaften Fassung (Diff zu tex/ = die Fehler)
├── validierungsnotebook/
│   ├── TB_Validierung.ipynb         das Prüf-Notebook (19 Checks) mit gespeichertem Nachweis-Lauf
│   ├── llm_cache.json               Antwort-Cache: Wiederholungsläufe kosten keine API-Aufrufe
│   ├── normtexte.json               gespeicherte Gesetzestexte (Ersatz für L-04 ohne Internet)
│   ├── pruefbericht_TB_VitalPlus_fehlerhaft.json   Prüfbericht des Nachweis-Laufs (21 F, 11 W)
│   └── pruefbericht_TB_VitalPlus.json              Gegenprobe fehlerfreie Fassung (0 F, 6 W)
└── gui/                             Demo-Oberfläche (Streamlit) für Live-Vorführungen, siehe gui/README.md
```

## Prüfkatalog (19 Checks)

**13 deterministische Prüfungen (V-01…V-13)** – reines Python, exakt
reproduzierbar, laufen auch ohne API-Schlüssel: tote und fehlende interne
Verweise, Inhaltsverzeichnis-Abgleich, Vollständigkeit des
Symbolverzeichnisses, rechnerische Tabellen-Identitäten und implizierter
Rechnungszins, Beitragsmonotonie (Rückgänge, die die TB selbst begründet –
etwa durch den Wegfall von Zuschlägen ab Alter 65 –, gelten als plausibel),
zellgenauer Abgleich mit Referenzwerten
(CSV) und Referenzdatenbank (SQLite), Konsistenz benannter Parameter,
Normzitat-Wissensbasis, Rahmen-TB-Register, Versionskonsistenz,
Vollständigkeit der Alterstabellen.

**6 LLM-gestützte Prüfungen (L-01…L-06)** – dort, wo Sprach-, Kontext- oder
Bildverständnis nötig ist: Rechtschreibung, Nachrechnen der
Beispielrechnungen (das Modell extrahiert nur, Python rechnet nach),
Konsistenz Abschnitt ↔ Anlage, Prüfung der Normzitate am amtlichen Wortlaut
(das Modell schlägt die zitierten Paragrafen per Werkzeugaufruf selbst auf
gesetze-im-internet.de nach), Vision-Prüfung des Formelsatzes
(formelhaltige Seiten als Bild – erkennt Fehler, die im PDF-Text-Layer
unsichtbar sind) sowie der Grafik-Tabellen-Abgleich.

Gegen typische LLM-Schwächen ist das Notebook mehrfach abgesichert:
strukturierte Antwortschemata, Grounding (gemeldete Wörter und Zahlen
müssen wörtlich im Dokument stehen), Warnung-statt-Fehler-Semantik bei
Unsicherheit – und beim Grafik-Abgleich eine **„blinde“ Ablesung**: Das
Modell erhält nur das Seitenbild ohne die Soll-Werte, der Vergleich erfolgt
anschließend deterministisch in Python. Kennt das Modell die Tabellenwerte,
neigt es dazu, sie schlicht zu bestätigen (Verankerungseffekt) – in der
Erprobung übersah es so selbst eine um 50 % verfälschte Kurve.

## Validierungsergebnis

| | fehlerhafte TB | fehlerfreie TB (Gegenprobe) |
|---|---|---|
| gefundene dokumentierte Fehler | **13 / 13** | – |
| Gesamtbefunde | 21 Fehler, 11 Warnungen | **0 Fehler**, 6 Warnungen |

Neun der 13 Fehler findet bereits die deterministische Ebene; zwei Befunde
(Vorzeichenfehler im Formelsatz, verfälschte Grafik-Kurve) sind nur über
die bildbasierten Prüfschritte als Fehler klassifizierbar. Die sechs
Warnungen der Gegenprobe sind Sichtungshinweise ohne Fehlercharakter; fünf
davon betreffen Normzitate, deren Absatz laut amtlichem Wortlaut nicht
genau passt (z. B. § 10 Abs. 1 statt Abs. 5 KVAV). Der maßgebliche Lauf
(Modell: `claude-sonnet-5`, Juli 2026; L-04 und V-06 im November 2026
erneuert) ist mitsamt Ausgaben im Notebook gespeichert und als
JSON-Prüfbericht exportiert.

## Voraussetzungen und Setup

1. Python ≥ 3.11 (getestet mit 3.13), z. B. in einer virtuellen Umgebung:

   ```bash
   cd tb-validierung
   python -m venv .venv
   # Windows (PowerShell/cmd):  .venv\Scripts\activate
   # Linux/macOS (bash/zsh):    source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Für die sechs LLM-Prüfungen einen Anthropic-API-Schlüssel als
   Umgebungsvariable setzen, **bevor** Jupyter gestartet wird
   (`ANTHROPIC_API_KEY`). Der Schlüssel wird ausschließlich aus der
   Umgebung gelesen und nie gespeichert. Ohne Schlüssel laufen die
   13 deterministischen Prüfungen; die LLM-Checks werden mit Hinweis
   übersprungen.

3. Nur für die Reproduktion der TB-PDFs: eine LaTeX-Distribution mit
   `pdflatex` (z. B. MiKTeX oder TeX Live).

## Nutzung

**Prüfen (Standardfall):** `validierungsnotebook/TB_Validierung.ipynb`
öffnen und von oben nach unten ausführen („Run All“). In der
Konfigurationszelle lassen sich Prüfobjekt (`TB_PDF_PFAD`), Referenzquellen
und Modell umstellen; standardmäßig wird die fehlerhafte Fassung geprüft.
Der Antwort-Cache (`llm_cache.json`) macht Wiederholungsläufe kostenlos.

> Hinweis: Die im Notebook gespeicherten Ausgaben stammen aus dem
> Nachweis-Lauf vom Juli 2026; dort erscheint der damalige Ordnername
> `2_Synthetische_TB` des Entwicklungsprojekts (heute:
> `synthetische-tb`). Bei einem frischen Lauf zeigen die Ausgaben die
> aktuellen Pfade.

**Live-Vorführung (Demo-Oberfläche):** `gui/` enthält eine
Streamlit-Oberfläche, die die Checks des Notebooks unverändert ausführt
und Schritt für Schritt auf großer Leinwand zeigt – mit Notfallschalter,
der die gespeicherten Antworten ohne Internet abspielt. Start nach
`pip install streamlit` mit `python -m streamlit run app.py` im Ordner
`gui/`; Einzelheiten und Regieblatt in [gui/README.md](gui/README.md).

**Reproduzieren (vollständige Kette, optional):** Alle Schritte aus dem
Ordner `synthetische-tb/` heraus:

1. `python kalkulation/pipeline.py` – erzeugt Rechnungsgrundlagen,
   LaTeX-Tabellen (`tex/gen/`) und Kontroll-CSVs (`kalkulation/out/`);
   benötigt die BaFin-Rohdaten (siehe unten)
2. im Ordner `tex/`: `pdflatex TB_VitalPlus_main.tex` dreimal ausführen
   (Inhaltsverzeichnis, Querverweise, Blattzählung; `pdflatex` muss im
   `tex/`-Ordner laufen, da die Quellen relative `\input`-Pfade nutzen)
3. `python kalkulation/erzeuge_fehlervariante.py` – erzeugt
   `tex_fehlerhaft/` mit den 13 Fehlern
4. im Ordner `tex_fehlerhaft/`: `pdflatex TB_VitalPlus_main.tex` dreimal
   ausführen
5. `python kalkulation/erzeuge_datenbank.py` – baut die
   SQLite-Referenzdatenbank neu
6. Notebook ausführen

## Datenherkunft und Grenzen

- **Alle Inhalte sind synthetisch.** Die TB gehört zum fiktiven Tarif
  „VitalPlus“ der fiktiven „Feldafinger Brandkasse (FFBK)“; sämtliches
  Zahlenwerk entsteht deterministisch aus der Kalkulationspipeline.
- **BaFin-Rohdaten sind nicht enthalten.** Die Pipeline stützt sich auf
  öffentlich verfügbare Veröffentlichungen der BaFin
  (PKV-Kopfschadenstatistik, Beobachtungsjahr 2022; PKV-Sterbetafel 2025)
  sowie eine fiktive Stornotafel. Für eine Neu-Kalkulation sind diese
  Dateien lokal im (unversionierten) Ordner `synthetische-tb/rohdaten/`
  abzulegen – erwartet werden
  `Kopfschäden/PKV_Kopfschadenstatistik_2022_Profile.csv`,
  `Sterbewahrscheinlichkeiten/PKV_Sterbetafel_2025.csv` und
  `Stornowahrscheinlichkeiten/storno2.csv` (die fiktive Stornotafel ist als
  Werteverlauf in Anlage 2.2 der TB dokumentiert). Notebook, Fehlervariante und
  Datenbank-Erzeugung funktionieren auch ohne die Rohdaten.
- **LLM-Prüfungen sind probabilistisch.** Sie können Befunde übersehen oder
  unzutreffende Hinweise erzeugen; ein unauffälliger Prüfbericht ist kein
  Nachweis der Fehlerfreiheit. Die fehlerhafte Referenzfassung dient
  deshalb als dauerhafter Prüfstand („Validierung des Validators“): Jede
  Änderung an Modell oder Prüfregeln ist daran erneut zu messen.
- Das Werkzeug ist eine unterstützende, vorbereitende Prüfung – es ersetzt
  weder die aktuarielle Durchsicht noch die Prüfung durch den Treuhänder.

## Offene Punkte

- Vergleichslauf eines kleineren/schnelleren Modells auf dem aktuellen
  13-Fehler-Stand (bisher nur auf dem früheren 12-Fehler-Stand erprobt).
- Übertragung des Ansatzes auf weitere Dokumenttypen (z. B. Geschäftspläne,
  Konsistenz von AVB-Verweisen, Treuhänder-Unterlagen).
- Abstraktion der LLM-Anbindung, um weitere Modellanbieter anzubinden.
