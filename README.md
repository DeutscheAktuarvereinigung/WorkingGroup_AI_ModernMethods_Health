# PKV-Limitierungstool

Streamlit-Anwendung fuer Bestandsanalyse und Limitierungsrechnung in der PKV.

Stand: 2026-04-16

## Ziel und Funktionsumfang

Das Tool unterstuetzt zwei zentrale Aufgaben:

1. Analyse von Beitragsanpassungen im Bestand
2. Simulation von Limitierungsregeln inkl. RfB-Bedarfsrechnung

Kernfunktionen:

- Interaktiver Datenimport (lokaler Pfad oder CSV-Upload)
- Filterung nach Tarifwerk, Tarifart, Tarif, Geschlecht, Alter und Erhoehungsbereichen
- KPI-, Verteilungs-, Struktur- und Detailanalysen im Tab Bestandsanalyse
- Regelbasierte Limitierung (global und segmentbezogen)
- Sensitivitaetsanalyse fuer Limitierungsziele
- Berechnung von Einmaleinlagen ueber Barwertfaktoren (inkl. befristeter Variante)
- Visualisierungen fuer RfB-Verteilung, Spitzenreduktion und Einsatz-Effizienz
- CSV-Exporte fuer Statistik und limitierte Einzelbestandsdaten

## Technologie-Stack

- Python 3.11
- Streamlit
- pandas
- numpy
- plotly

Abhaengigkeiten siehe requirements.txt.

## Schnellstart (lokal)

### Voraussetzungen

- Python 3.11
- Optional: virtuelle Umgebung (empfohlen)

### Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Danach ist die App unter http://localhost:8501 erreichbar.

## Start mit Docker

```powershell
docker build -t limitierungs-tool .
docker run --rm -p 8501:8501 limitierungs-tool
```

Danach ist die App unter http://localhost:8501 erreichbar.

Hinweise:

- Der Container startet Streamlit headless auf Port 8501.
- Ein Healthcheck prueft `/_stcore/health`.

## Datenquelle und Import

Die Sidebar bietet zwei Modi:

- Mock-Daten (lokaler Pfad), Default `./output_daten`
- CSV-Upload (3 Dateien)

Erwartete Dateien:

- bestand.csv
- tarife.csv
- ausscheideordnung.csv

Separator in allen CSV-Dateien: Semikolon `;`

## Erwartete Datenformate

### 1) bestand.csv

Mindestens folgende Spalten sind erforderlich:

- versicherten_id
- alter
- geschlecht
- tarifwerk
- tarif_id
- tarifart
- praemie_alt_monatlich
- praemie_neu_monatlich
- erhoehung_absolut
- erhoehung_prozent
- alterungsrueckstellung
- versicherungsdauer_jahre

Optional genutzt (wenn vorhanden):

- erhoehung_historisch_kumuliert

Beim Laden wird automatisch eine Altersgruppe erzeugt (`altersgruppe`).

### 2) tarife.csv

Fuer die Barwertberechnung relevant:

- tarif_id
- rechnungszins

Weitere Spalten (z. B. bezeichnung, tarifwerk, tarifart, geschlossen) koennen vorhanden sein.

### 3) ausscheideordnung.csv

Erwartete Schluesselspalten:

- tarif_id
- alter
- geschlecht
- qx
- storno

## Bedienung in der App

## Tab 1: Bestandsanalyse

Bereitgestellte Auswertungen:

- KPI-Karten (Bestand, Praemien, Erhoehungen, Jahresvolumen)
- Histogramm und Boxplot (prozentual oder absolut)
- Treemap zur Bestandsstruktur mit Drilldown
- Gruppierte Statistik-Tabelle mit CSV-Export
- Einzeldaten-Ansichten (Top 100 / Stichprobe)
- Gesamtbestand-Export (gefiltert)

Filterlogik:

- Standardmaessig arbeitet die Analyse auf dem geladenen Gesamtbestand
- Nach Klick auf Filter anwenden wird mit der gesetzten UND/ODER-Logik fuer Prozent- und Euro-Grenzen gefiltert

## Tab 2: Limitierungsrechnung

Bereitgestellte Funktionen:

- Regeldefinition mit Reihenfolge (spaetere Regeln koennen nur verschaerfen)
- Globale und segmentbezogene Caps in Prozent und/oder Euro
- Sensitivitaetsanalyse ueber ein Zielraster
- Limitierungsberechnung inkl. Budgetvergleich
- Optional befristete Limitierung (Mischung dauerhaft/befristet)
- Treemap der verwendeten RfB-Mittel
- Spitzenreduktion nach Alter (P90/P95/P99/Maximum)
- Bubble-Chart zur Effizienz des RfB-Einsatzes
- Gruppierte Detailanalyse und Export

## Mathematischer Kern (vereinfacht)

### Barwertfaktor

Fuer Tarif, Geschlecht und Eintrittsalter wird ein Barwertfaktor aus Rechnungszins sowie kombinierter Ausscheidewahrscheinlichkeit (qx + storno) berechnet.

### Einmaleinlage

Die monatliche Entlastung wird in eine Einmaleinlage umgerechnet:

Einmaleinlage = Entlastung_monatlich * 12 * Barwertfaktor

### Limitierungswirkung

Pro versicherter Person werden urspruengliche Erhoehungen durch Regel-Caps begrenzt. Daraus entstehen:

- neue limitierte Erhoehung in Prozent und Euro
- limitierte neue Praemie
- monatliche Entlastung gegenueber Ursprung
- benoetigte Einmaleinlage

## Mock-Daten erzeugen

Das Projekt enthaelt einen Generator fuer grosse, realistische Testdaten.

### Beispiel

```powershell
python mock_daten_erzeugen.py -o output_daten -m 0.30 -s 42
```

Parameter:

- -o, --ausgabeverzeichnis: Zielordner
- -m, --mittlere_anpassung: Ziel fuer mittlere Anpassung (Dezimal, z. B. 0.30)
- -s, --seed: Reproduzierbarkeit

Erzeugte Dateien:

- output_daten/tarife.csv
- output_daten/ausscheideordnung.csv
- output_daten/bestand.csv

Voraussetzung:

- pkv_sterbetafel.csv muss im Projektverzeichnis vorhanden sein

## Projektstruktur

```text
app.py                        # Einstiegspunkt Streamlit
app/pages/                    # UI-Logik je Tab
services/                     # Fachlogik (Import, Analyse, Limitierung)
ui/theme.py                   # Farben, Plot-Layout, CSS-Theme
mock_daten_erzeugen.py        # Generator fuer Testdaten
output_daten/                 # Beispiel-/Mock-Daten
Dockerfile                    # Container-Setup
requirements.txt              # Python-Abhaengigkeiten
```

## Performance- und Betriebs-Hinweise

- Mehrere rechenintensive Funktionen sind mit Streamlit Cache abgesichert.
- Sehr grosse CSV-Dateien (insb. bestand.csv) benoetigen entsprechend RAM.
- Fuer interne produktive Nutzung wird Container-Betrieb empfohlen.
- Zugriff idealerweise nur intern bzw. ueber SSO abgesichert.

## Troubleshooting

### App startet, aber es werden keine Daten angezeigt

- Pruefen, ob alle drei CSV-Dateien geladen wurden.
- Pruefen, ob der Separator `;` verwendet wurde.
- Spaltennamen auf Schreibweise gemaess obiger Liste pruefen.

### Fehler bei Limitierungsrechnung

- Pruefen, ob `tarif_id`, `geschlecht` und `alter` zwischen bestand.csv und ausscheideordnung.csv zueinander passen.
- Pruefen, ob in tarife.csv pro tarif_id ein rechnungszins vorhanden ist.

### Sehr lange Laufzeiten

- Mit kleinerem Teilbestand testen.
- Falls noetig Mock-Daten mit geringerer Groesse erzeugen (Anpassung im Generator-Skript).

## Weiterentwicklung

Moegliche naechste Schritte:

- Unit-Tests fuer Kernfunktionen in services/
- Fachliche Parametrisierung ueber Konfigurationsdateien
- Deployment-Pipeline (z. B. Container Registry + App Service)
- Rollen-/Rechtekonzept fuer fachliche Freigaben
