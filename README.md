# KI und moderne Methoden in der Krankenversicherung

Dieses Repository bündelt die frei verfügbaren Werkzeuge der Arbeitsgruppe
**„Künstliche Intelligenz und moderne Methoden in der Krankenversicherung“**
des Ausschusses Krankenversicherung der Deutschen
Aktuarvereinigung e. V. (DAV). Die Arbeitsgruppe untersucht, wie künstliche
Intelligenz (KI), maschinelles Lernen und moderne Softwareentwicklung die
aktuarielle Arbeit in der privaten Krankenversicherung (PKV) unterstützen
können – von der Beitragsanpassung bis zur Qualitätssicherung zentraler
Dokumente.

## Inhalte

| Deliverable | Kurzbeschreibung |
|---|---|
| **[Limitierungstool](limitierungstool/)** | Streamlit-Anwendung für Bestandsanalyse und Limitierungsrechnung bei Beitragsanpassungen in der PKV: regelbasierte Limitierung (tarif- und personenbezogene Caps), Sensitivitätsanalysen, Mittelquellen-Steuerung und Einmaleinlagen-Berechnung über Barwertfaktoren. |
| **[TB-Validierung](tb-validierung/)** | Jupyter-Notebook zur automatisierten Validierung Technischer Berechnungsgrundlagen (TB) im PDF-Format – 13 deterministische und 6 LLM-gestützte Prüfungen (LLM = Large Language Model, großes Sprachmodell) – samt einer vollsynthetischen Test-TB mit 13 dokumentierten Fehlern als messbarem Wirksamkeitsnachweis. |
| **[Fallprognose: Wiedereinweisung](fallprognose-wiedereinweisung/)** | Jupyter-Notebook (Python) zur Ereignisprognose mit maschinellem Lernen: Wiedereinweisungswahrscheinlichkeit ins Krankenhaus, von einem CatBoost-Basismodell über SHAP, Hyperparameter-Optimierung, neuronale Netze und regularisierte logistische Regression bis AutoGluon. Übertragbar auf andere binäre Klassifikationen, etwa eine Stornoprognose. |
| **[Prämienstruktur](praemienstruktur/)** | R-Markdown-Analyse eines Krankenversicherungsbestands: explorative Untersuchung der Bestands- und Prämienstruktur, Identifikation nicht ausgewiesener Produktsegmente und Modellierung des Prämienniveaus mit Regressions- und Gamma-GLM-Ansätzen. Niedrigschwelliger Einstieg in die Open-Source-Analytik. |

Alle vier Deliverables werden im Ergebnisbericht der Arbeitsgruppe
(„Künstliche Intelligenz und moderne Methoden in der Krankenversicherung“)
als Praxisbeispiele vertieft beschrieben – in den Abschnitten 5.1, 5.2, 5.4
und 5.5.

## Repository-Struktur

```
├── limitierungstool/          Streamlit-App inkl. Tests, Mock-Daten-Generator und Doku
│   └── README.md              Einstieg, Datenverträge, Bedienung, fachlicher Kern
├── tb-validierung/
│   ├── synthetische-tb/       vollsynthetische Test-TB (fehlerfreie + fehlerhafte Fassung,
│   │                          LaTeX-Quellen, Kalkulationspipeline, Referenzwerte)
│   ├── validierungsnotebook/  Prüf-Notebook mit gespeichertem Nachweis-Lauf
│   └── README.md              Zielsetzung, Setup, Nutzung, Reproduktionskette
├── fallprognose-wiedereinweisung/
│   ├── hospital-readmission.ipynb   ausführbares Jupyter-Notebook (mit Ergebnissen)
│   ├── hospital-readmission.html    dokumentierter HTML-Analysebericht
│   ├── data/README.md               Bezugsquellen der Eingangsdaten
│   └── README.md              Inhalt, Datenbasis, Ausführung, Herkunft
└── praemienstruktur/
    ├── praemienstruktur.Rmd   ausführbarer R-Markdown-Code
    ├── praemienstruktur.html  dokumentierter HTML-Analysebericht
    ├── data/README.md         Bezugsquelle der Eingangsdaten
    └── README.md              Inhalt, Datenbasis, Ausführung
```

## Einstieg

- **Limitierungstool:** `cd limitierungstool`, dann den Schritten im dortigen
  [README](limitierungstool/README.md) folgen (venv, `pip install -r
  requirements.txt`, Mock-Daten erzeugen, `streamlit run app.py`).
- **TB-Validierung:** `cd tb-validierung`, dann den Schritten im dortigen
  [README](tb-validierung/README.md) folgen (venv, `pip install -r
  requirements.txt`, Notebook öffnen und „Run All“ ausführen; die
  LLM-Prüfungen benötigen einen API-Schlüssel, die 13 deterministischen
  Prüfungen laufen auch ohne).
- **Fallprognose: Wiedereinweisung:** siehe
  [README](fallprognose-wiedereinweisung/README.md). Das Notebook ist für die
  Ausführung auf Kaggle geschrieben; die beiden benötigten Datensätze sind
  dort per *Add Input* einzubinden.
- **Prämienstruktur:** siehe [README](praemienstruktur/README.md). Excel-Datei
  des Datensatzes nach `praemienstruktur/data/` legen, dann
  `praemienstruktur.Rmd` in RStudio öffnen und *Knit* ausführen.

Beide Analyse-Notebooks liegen zusätzlich als **HTML-Analysebericht** bei –
darin ist der komplette Lauf samt allen Grafiken und Tabellen enthalten,
sodass sich die Ergebnisse ohne Python- oder R-Umgebung nachlesen lassen.

## Daten und Haftung

- Alle in diesem Repository **enthaltenen oder erzeugten** Daten sind
  **ausschließlich synthetisch** bzw. simuliert: Das Limitierungstool
  arbeitet auf frei generierten Mock-Beständen, die Test-TB gehört zum
  fiktiven Tarif „VitalPlus“ der fiktiven „Feldafinger Brandkasse (FFBK)“.
  Es sind keine Echt-, Mandanten- oder personenbezogenen Daten enthalten.
- Die beiden Analyse-Notebooks arbeiten auf **öffentlich verfügbaren,
  anonymisierten Fremddatensätzen** (US-Krankenhausfälle bzw. ein
  spanischer Krankenversicherungsbestand). Diese Daten sind **nicht Teil
  dieses Repositorys**; Bezugsquelle, Zitierweise und Nutzungsbedingungen
  stehen im jeweiligen `data/README.md`. Vergleichbare öffentlich
  zugängliche, branchenspezifische Datensätze aus Deutschland sind der
  Arbeitsgruppe nicht bekannt.
- Die Werkzeuge sind **Arbeitsergebnisse der Arbeitsgruppe** und stellen
  keine berufsständisch legitimierte Position der DAV dar. Sie ersetzen
  weder aktuarielle Prüfung noch rechtliche Beratung; ein produktiver
  Einsatz erfordert eine eigenverantwortliche Validierung im jeweiligen
  Unternehmenskontext (u. a. mit Blick auf EU-KI-Verordnung, DORA und
  unternehmensinterne Governance).
- Ein unauffälliges Prüfergebnis der TB-Validierung ist **kein Nachweis der
  Fehlerfreiheit** eines Dokuments, sondern reduziert das Restrisiko.

## Ansprechpartner

Arbeitsgruppe „Künstliche Intelligenz und moderne Methoden in der
Krankenversicherung“ (Ausschuss Krankenversicherung der DAV):

- Simon Hatzesberger ([@simonhatzesberger](https://github.com/simonhatzesberger), simon.hatzesberger@gmail.com)
- Daniel Hasler ([@DanielHustler](https://github.com/DanielHustler))
- Friedrich Loser
- Marco Nickel

Fragen und Anregungen gerne auch als [GitHub-Issue](../../issues).

## Lizenz

[MIT-Lizenz](LICENSE) – Nutzung, Änderung und auch kommerzielle Verwendung
sind ausdrücklich erlaubt.
