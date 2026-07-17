# PKV-Limitierungstool

Streamlit-Anwendung fuer Bestandsanalyse und Limitierungsrechnung in der PKV.

> Teil des Repositories der DAV-Arbeitsgruppe "Kuenstliche Intelligenz und
> moderne Methoden in der Krankenversicherung" (siehe [Haupt-README](../README.md)).
> Alle nachfolgenden Befehle werden aus diesem Ordner heraus ausgefuehrt:
> vorher `cd limitierungstool`.

Stand: 2026-04-16

## Ziel und Funktionsumfang

Das Tool unterstuetzt zwei zentrale Aufgaben:

1. Analyse von Beitragsanpassungen im Bestand
2. Simulation von Limitierungsregeln inkl. RfB-Bedarfsrechnung

Kernfunktionen:

- Interaktiver Datenimport (lokaler Pfad, CSV-Upload oder Snowflake-Schema)
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
- scipy

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

Die Sidebar bietet drei Modi:

- Mock-Daten (lokaler Pfad), Default `./output_daten`
- CSV-Upload (3 Dateien)
- Snowflake-Schema über die aktive Snowflake-Session

Erwartete Dateien:

- bestand.csv
- tarife.csv
- ausscheideordnung.csv

Optional fuer die Mittelquellen-Erweiterung:

- mittelquellen_config.csv

Separator in allen CSV-Dateien: Semikolon `;`

Beim Snowflake-Import werden standardmaessig folgende Tabellen in einem gewaehlten Schema erwartet:

- `BESTAND`
- `TARIFE`
- `AUSSCHEIDEORDNUNG`
- `MITTELQUELLEN_CONFIG` (optional)

Datenbank, Schema und Tabellennamen koennen in der Sidebar angepasst werden. Die App nutzt in Streamlit in Snowflake die aktive Snowpark-Session; Credentials sollten nicht in der App gepflegt werden. Snowflake-Spaltennamen werden auf Kleinschreibung normalisiert, sodass unquoted Snowflake-Spalten wie `VERSICHERTEN_ID` dem App-Datenvertrag `versicherten_id` entsprechen.

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
- ueberzins_mittel_euro
- zu10_mittel_euro

Die optionalen Mittelspalten muessen numerisch und nicht negativ sein. Sie werden fuer die Mittelquellen-Erweiterung als Einmaleinlagen-/Kapitalwertbetraege interpretiert, sofern in der Mittelquellen-Konfiguration keine andere Einheit gesetzt wird.

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

### 4) mittelquellen_config.csv (optional)

Die Datei beschreibt die Mittelquellen fuer die Topfsteuerung. Sie wird vom Mock-Daten-Generator bereits als Beispiel erzeugt und enthaelt u. a. folgende Spalten:

- quelle_id
- name
- aktiv
- prioritaet
- typ
- betrag_euro
- betrag_spalte
- betrag_einheit
- unterliegt_limitierungsregeln
- einsatzmodus
- anwendungsphase
- filter_spalten
- filter_operatoren
- filter_werte
- fallback_erlaubt

Referenzierte `betrag_spalte`- und `filter_spalten`-Werte muessen im Bestand vorhanden sein; fehlende Spalten gelten als fachlicher Fehler.

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

## Tab 2: Mittelkonfiguration

Bereitgestellte Funktionen:

- Optionales Laden einer `mittelquellen_config.csv` oder Erzeugung einer Default-Konfiguration
- Aktivierung/Deaktivierung einzelner Mittelquellen
- Konfiguration von Prioritaet, Typ, Betragsspalte oder globalem Betrag
- Steuerung, ob ein Topf den Limitierungsregeln unterliegt
- Berechtigungsfilter, z. B. fuer ZU10 mit `tarifart == voll` und `alter >= 65`
- Validierung der Konfiguration gegen den geladenen Bestand

## Tab 3: Limitierungsrechnung

Bereitgestellte Funktionen:

- Regeldefinition mit Reihenfolge (spaetere Regeln koennen nur verschaerfen)
- Globale und segmentbezogene Caps in Prozent und/oder Euro
- Sensitivitaetsanalyse ueber ein Zielraster
- Limitierungsberechnung inkl. Budgetvergleich
- Optional befristete Limitierung (Mischung dauerhaft/befristet)
- Integration der Mittelquellen-Konfiguration: regelunabhaengige Vorab-Entlastung, regelgebundene Finanzierung, Unterdeckung und Finanzierungsquote
- Treemap der verwendeten RfB-Mittel
- Balkendiagramm der verwendeten Mittel je Quelle
- Spitzenreduktion nach Alter (P90/P95/P99/Maximum)
- Bubble-Chart zur Effizienz des RfB-Einsatzes
- Gruppierte Detailanalyse und Export

## Mittelquellen und Topfsteuerung

Die fachliche Erweiterung fuehrt getrennte Mittelquellen fuer die Limitierung ein. Der Umsetzungsplan und das Testprotokoll sind in [docs/mittelquellen_umsetzungsplan.md](docs/mittelquellen_umsetzungsplan.md) dokumentiert.

Fachliche Leitplanken:

- Mittelquellen koennen freie RfB, Ueberzinsen, ZU10-Mittel aus der Vollversicherung oder weitere frei definierbare Toepfe sein.
- Je Topf soll konfigurierbar sein, ob er den UI-Limitierungsregeln unterliegt oder regelunabhaengig vorab zur Beitragsentlastung eingesetzt wird.
- Ueberzins wird als regelunabhaengige Pflichtquelle soweit moeglich vollstaendig zur Reduktion der Beitragsanpassung verwendet.
- ZU10-Mittel werden als zeilenindividuelle externe Betragsspalte standardmaessig nur fuer Vollversicherte ab Alter 65 regelgebunden eingesetzt.
- Externe Mittelspalten werden als Einmaleinlagen-/Kapitalwertbetraege interpretiert; laufende Monatsbetraege muessen explizit gekennzeichnet werden.
- Die bestehende Limitierungsrechnung bleibt rueckwaertskompatibel; neue Mittelquellen-Spalten werden additiv fuer Finanzierungsnachweis, Unterdeckung und Export ergaenzt.

Technischer Stand:

- Die Mockdaten und die CSV-Validierung enthalten bereits die Mittelspalten und eine Beispiel-Konfiguration.
- Die Service-Schicht `services/mittelverwendung.py` stellt die regelunabhaengige Vorab-Entlastung und die regelgebundene Finanzierungszuordnung bereit.
- Die UI-Anbindung fuer die Mittelkonfiguration ist vorhanden und speichert die validierte Konfiguration im Session-State.
- Die Orchestrierung in der Limitierungsrechnung ist integriert; das bestehende RfB-Budget wird in die freie RfB-Quelle gespiegelt.
- Die Regressionstests fuer Ueberzins, ZU10-Altersgrenze, freie RfB, Fallback, Validierung, Rueckwaertskompatibilitaet und Exportspalten sind umgesetzt.

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
- output_daten/mittelquellen_config.csv

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
