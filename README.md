# KI und moderne Methoden in der Krankenversicherung

Dieses Repository bündelt die frei verfügbaren Werkzeuge der Arbeitsgruppe
**„Künstliche Intelligenz und moderne Methoden in der Krankenversicherung“**
des Ausschusses Actuarial Data Science / AI (ADS/AI) der Deutschen
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

Beide Werkzeuge werden im Ergebnisbericht der Arbeitsgruppe („Moderne
Methoden in der Krankenversicherung“) als Praxisbeispiele vertieft
beschrieben.

## Repository-Struktur

```
├── limitierungstool/          Streamlit-App inkl. Tests, Mock-Daten-Generator und Doku
│   └── README.md              Einstieg, Datenverträge, Bedienung, fachlicher Kern
└── tb-validierung/
    ├── synthetische-tb/       vollsynthetische Test-TB (fehlerfreie + fehlerhafte Fassung,
    │                          LaTeX-Quellen, Kalkulationspipeline, Referenzwerte)
    ├── validierungsnotebook/  Prüf-Notebook mit gespeichertem Nachweis-Lauf
    └── README.md              Zielsetzung, Setup, Nutzung, Reproduktionskette
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

## Daten und Haftung

- Alle in diesem Repository enthaltenen oder erzeugten Daten sind
  **ausschließlich synthetisch** bzw. simuliert: Das Limitierungstool
  arbeitet auf frei generierten Mock-Beständen, die Test-TB gehört zum
  fiktiven Tarif „VitalPlus“ der fiktiven „Feldafinger Brandkasse (FFBK)“.
  Es sind keine Echt-, Mandanten- oder personenbezogenen Daten enthalten.
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
Krankenversicherung“ (Ausschuss ADS/AI der DAV):

- Simon Hatzesberger ([@simonhatzesberger](https://github.com/simonhatzesberger), simon.hatzesberger@gmail.com)
- Daniel Hasler ([@DanielHustler](https://github.com/DanielHustler))
- Marco Nickel

Fragen und Anregungen gerne auch als [GitHub-Issue](../../issues).

## Lizenz

[MIT-Lizenz](LICENSE) – Nutzung, Änderung und auch kommerzielle Verwendung
sind ausdrücklich erlaubt.
