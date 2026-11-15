# TB-Validierung – Oberfläche für die Live-Vorführung

Streamlit-App für die DAV/DGVFM-Herbsttagung. Sie zeigt auf der Leinwand, wie
eine Technische Berechnungsgrundlage (TB) automatisiert geprüft wird: feste
Regeln (V-01 … V-13) und Sprachmodell-Checks (L-01 … L-06), Schritt für
Schritt, mit Statusfarben plus Piktogrammen. Die Status-Symbole sind farbige
Kreise mit weißem Zeichen: Haken = bestanden (grün), Ausrufezeichen = Warnung
(gelb), Kreuz = Fehler (rot), Strich = übersprungen (grau), Blitz =
fehlgeschlagen (violett).

Gestaltung: sachlich und eckig (keine abgerundeten Ecken außer den runden
Status-Symbolen), Seitengrund hellgrau, Flächen weiß mit feinem Rand,
DAV-Blau für den aktiven Schritt. Schrift **Roboto**, lokal eingebunden (siehe
unten); Piktogramme aus „Material Symbols Rounded“, die Streamlit selbst
mitliefert. Beides funktioniert ohne Internet.

Die Prüflogik wird nicht kopiert: `engine.py` führt die Code-Zellen des
Validierungsnotebooks (`../validierungsnotebook/TB_Validierung.ipynb`) aus.
Notebook, Cache, Prüfberichte, PDFs und Fehlerprotokoll werden nur gelesen.

| Datei | Aufgabe |
|---|---|
| `app.py` | Oberfläche (Prozesskette, Prüfkatalog, Prüflauf, Befunde, Abgleich) |
| `engine.py` | Prüfmaschine: Notebook-Zellen ausführen, Live- und Notfallmodus |
| `fundstellen.py` | Passage zu einem Befund im PDF finden und vergrößert markieren |
| `fehlerprotokoll.py` | Abgleich der Befunde mit den eingebauten Fehlern F01–F13 |
| `.streamlit/config.toml` | nur lokal (127.0.0.1), helles eckiges Theme, DAV-Blau, Roboto, keine Statistik |
| `static/fonts/` | Schrift Roboto (woff2, variable Strichstärke) samt Lizenz `OFL.txt` |
| `tests/` | Tests ohne Netzwerk (siehe unten) |

## Start (PowerShell)

Voraussetzungen: Python 3.13 mit streamlit 1.56, pymupdf 1.28, pandas,
anthropic und pillow.

```powershell
cd "…\tb-validierung\gui"
$env:ANTHROPIC_API_KEY = "<Schlüssel>"     # nur für den Live-Betrieb, siehe unten
python -m streamlit run app.py
```

Danach im Browser **http://127.0.0.1:8501** öffnen (ist der Port belegt,
nennt die Konsole die tatsächliche Adresse) und mit **F11** auf Vollbild
schalten. Für einen Neubeginn ohne alte Ergebnisse (z. B. nach der
Generalprobe) einmal **http://127.0.0.1:8501/?neu=1** aufrufen. Das setzt alle
Ergebnisse und Einstellungen zurück, auch den Notfallschalter.

Das Konsolenfenster bleibt während des Vortrags offen. Technische Fehler
erscheinen nur dort und in der Seitenleiste, nie auf der Leinwand.

## Regieblatt für den Vortrag

**Vorher (Technik)**

1. Leinwand bzw. Beamer anschließen, F11 (Vollbild).
2. **Schriftgröße mit dem Browser-Zoom einstellen** (Strg + / Strg − /
   Strg 0), bis die Schrift von hinten im Saal lesbar ist. Die Oberfläche hat
   bei 100 % normale Bildschirmgrößen (Grundschrift 16 px); auf der Leinwand
   sind meist 150 % bis 200 % passend. Bei 150 % und 200 % bleibt alles
   sauber; Inhalte, die nicht mehr ins Fenster passen, werden senkrecht
   gescrollt (nie waagrecht). Der Browser merkt sich den Zoom je Adresse.
3. Seitenleiste prüfen und wieder einklappen: „API-Schlüssel: vorhanden“,
   Notfallschalter AUS. Beim Öffnen der Seite klappt die App die
   Seitenleiste selbst ein, auch wenn sie bei der Probe offen war.
4. Generalprobe: einmal live prüfen (fehlerhafte TB und Gegenprobe), dann
   `/?neu=1` aufrufen.

**Während des Vortrags**

- **Seite nicht neu laden (kein F5).** Passiert es trotzdem (oder stürzt der
  Browser ab), gehen weder Ergebnisse noch Einstellungen verloren: Sie liegen
  im Serverprozess, solange die Konsole läuft. Lief gerade eine Prüfung,
  erscheint im Prüfkatalog „Prüfung wurde abgebrochen – bitte neu starten.“
  Dann einfach erneut „Prüfung starten“ drücken.
- Während eines Prüflaufs sind Dokument-Umschalter, Prozesskette und Regler
  gesperrt. Ein versehentlicher Klick bricht den Lauf also nicht ab.
  Bedienbar bleibt nur der Notfallschalter.
- Ein Live-Lauf dauert **etwa 30 Sekunden bis 1 Minute je Dokument** und
  stellt **65 Anfragen** an das Sprachmodell (24 davon mit Seitenbild).
  Gemessen: 39 s mit 24 parallelen Anfragen (Standard, Oktober 2026), 30 s
  im November 2026; 60 s bzw. 63 s mit 8. Die Dauer bestimmen wenige lange
  Einzelanfragen (L-02, L-04). Jeder neue Lauf fragt erneut an und kostet erneut.
- L-04 schlägt die zitierten Paragrafen per Werkzeugaufruf live auf
  gesetze-im-internet.de nach (rund 28 Abrufe, gedrosselt). Ist die Seite
  nicht erreichbar, nimmt L-04 die gespeicherte Kopie
  `../validierungsnotebook/normtexte.json`; die Antwort nennt die Quelle.
- Live-Ergebnisse weichen etwas vom Referenz-Prüfbericht ab und schwanken
  von Lauf zu Lauf, weil Claude Sonnet 5.5 anders formuliert und abwägt als
  der Nachweis-Lauf. Gemessen, fehlerhafte TB: 22 Fehler / 11 Warnungen bzw.
  21 Fehler / 14 Warnungen (Oktober), 22 Fehler / 13 Warnungen (November,
  L-04 am Gesetzestext), jeweils alle 13 dokumentierten Fehler gefunden.
  Gegenprobe (L-04 am Gesetzestext): 0 Fehler, die L-04-Warnungen nennen
  konkrete Absatzabweichungen. Keine Zahl ist fest eingeplant.

**Bei einer Störung (Internet, API, Rate-Limit)**

Anzeichen: Sprachmodell-Checks enden mit „fehlgeschlagen – Check konnte nicht
ausgeführt werden.“, oder der Lauf hängt sichtbar.

1. Seitenleiste öffnen (dezenter Pfeil ganz oben links).
2. **„Gespeicherte Antworten verwenden (Notfall)“** einschalten. Ein
   laufender Lauf wird dabei abgebrochen.
3. Seitenleiste wieder einklappen, im Prüfkatalog „Prüfung starten“.

Der Notfallmodus spielt die Antworten des Nachweis-Laufs ab, ohne Internet
und ohne Kosten, im Tempo eines echten Live-Laufs. Ergebnis wie im
Referenz-Prüfbericht (November 2026, L-04 am Gesetzestext): fehlerhafte TB
21 Fehler / 11 Warnungen, Gegenprobe 0 / 6. Auf der Leinwand ist der Modus nicht zu erkennen, der Hinweis steht nur
in der Seitenleiste. Der Schalter bleibt auch nach einem Neuladen eingeschaltet.

## API-Schlüssel (Live-Betrieb)

Die Sprachmodell-Checks laufen live gegen die Anthropic-API, Standardmodell
`claude-sonnet-5-5` (Claude Sonnet 5.5). Der Schlüssel wird **nur** aus der
Umgebungsvariablen `ANTHROPIC_API_KEY` gelesen. Er gehört nicht in Dateien
dieses Ordners; gesetzt wird er in derselben Konsole vor dem Start (siehe oben).

Ob ein Schlüssel vorhanden ist, zeigt die Seitenleiste (nur ja/nein). Ohne
Schlüssel werden die Sprachmodell-Checks übersprungen; der Prüfkatalog warnt
davor im Sprachmodell-Block.

## Seitenleiste

Die Seitenleiste ist nur für die Vortragenden gedacht und beim Start
eingeklappt.

- **Sprachmodell**: Modellname für den Live-Betrieb.
- **API-Schlüssel**: vorhanden / nicht gesetzt.
- **Gespeicherte Antworten verwenden (Notfall)**: eckige Checkbox,
  standardmäßig AUS (siehe Regieblatt).
- **Pause je Check** (Standard 0,5 s): So lange bleibt jeder Check mindestens
  sichtbar, damit das Publikum mitlesen kann. Die Ablaufliste zeigt die
  sichtbare Dauer je Check.
- **Parallele Anfragen** (Standard 24, höchstens 64).
- **Schriftgröße (Faktor)**: Faktor auf die Grundschrift von 16 px
  (Standard 1,0). Für die Leinwand besser den Browser-Zoom verwenden.
- Hinweis zu den Tastenkürzeln: Die Pfeiltasten ← → blättern die Befunde.
  Hat ein Regler den Fokus, verstellen sie nur den Regler.
- Der Knopf zum Öffnen der Seitenleiste ist für das Publikum unsichtbar; er
  erscheint, sobald die Maus oben links darüberfährt.
- **Weitere Einstellungen**:
  - Antwortzeit im Notfallmodus (Standard „wie live“: die gemessenen
    Antwortzeiten eines echten Laufs, je Check gestreut; „sofort“ für Proben);
  - „Alle Ergebnisse zurücksetzen“.
- **Technische Einzelheiten** (nur wenn es etwas zu berichten gibt): Gründe
  übersprungener oder fehlgeschlagener Checks und der letzte Fehler.

## Bedienung in der Demo

Oben links steht der Titel „**TB-Validierung** Live-Demo“, rechts daneben der
Dokument-Umschalter: „TB mit 13 eingebauten Fehlern“ (Standard) oder
„Fehlerfreie TB (Gegenprobe)“. Darunter liegt die Prozesskette aus vier
Pfeilboxen (Prüfkatalog → Prüflauf → Befunde → Abgleich): der aktive Schritt
kräftig blau, erreichbare Schritte hellblau, gesperrte grau. Ein Klick auf
eine Box wechselt den Schritt.

1. **Prüfkatalog**: alle 19 Checks in zwei Blöcken. Der Kopf jedes Blocks ist
   eine Checkbox für die ganze Kategorie („Feste Regeln“ bzw. „Sprachmodell
   (KI)“): Sie wählt alle Checks dieser Kategorie aus oder ab; ihr Haken ist
   gesetzt, solange alle Checks der Kategorie gewählt sind. Einzelne Checks
   per Häkchen. Erklärtexte gibt es nur als Tooltip am Fragezeichen, das
   beim Darüberfahren sichtbar wird (je Check und je Kategorie). Ist die
   Hauptfläche schmal (starker Zoom, Seitenleiste offen), stehen die beiden
   Blöcke untereinander. Unten rechts
   „Prüfung starten (n von 19 Checks)“, gesperrt, solange nichts gewählt ist.
   Ein neuer Lauf ersetzt das Ergebnis dieses Dokuments.
2. **Prüflauf**: Die Checks wechseln nacheinander von „wartet“ über „läuft …“
   (bei Sprachmodell-Checks mit „Antworten x von y“) zum Ergebnis. Danach
   stehen oben die Ergebnis-Kacheln (Fehler, Warnungen und grün die Zahl der
   Checks ohne Befund) und unten rechts der Knopf „Befunde ansehen“.
3. **Befunde**: links die Liste, rechts der gewählte Befund als Karte (Kopf
   in der Farbe der Schwere mit Check, Methode und Seite) samt markierter
   Passage aus dem PDF. Die Methode (feste Regel / Sprachmodell) zeigt ein
   neutraler Chip mit Piktogramm. Blättern mit den Pfeilen links und rechts
   neben „Befund x von n“ oder mit den Pfeiltasten ← →. Die Checkbox
   „Gegenüberstellung“ zeigt dieselbe Stelle der jeweils anderen TB (Layout
   identisch, blau markiert): bei Text darunter, bei Grafiken daneben (bei
   schmaler Fläche, etwa 200 % Zoom, ebenfalls untereinander). Die Aussage
   steht in höchstens drei Zeilen (Volltext als Tooltip). Nennt
   ein Befund eine zweite Stelle auf einer anderen Seite (z. B. Anhang 5),
   steht sie im selben Bild darunter. Die Schrift der Befundkarte ist mit und
   ohne Gegenüberstellung gleich groß.
4. **Abgleich**: Tabelle der dokumentierten Fehler F01–F13 mit „gefunden“ bzw.
   „nicht gefunden“ und den Checks, die den Fehler gefunden haben; groß
   „n von 13 dokumentierten Fehlern gefunden“ (F05a–c zählen zusammen als
   F05). „Zeigen“ springt zum Befund. Befunde ohne Bezug zum
   Fehlerprotokoll sind eigens aufgeführt. Bei der Gegenprobe steht hier
   „0 Fehler in der fehlerfreien TB · y Warnungen zum Nachsehen“ mit der
   Liste der Warnungen.

Wurden Checks übersprungen oder sind sie fehlgeschlagen, meldet die App grau
„unvollständig“ mit der Anzahl und nie „bestanden“.

## Schrift Roboto (lokal)

Die Schrift liegt in `static/fonts/` (Roboto, variable Schrift mit allen
Strichstärken 100–900, je eine Datei für die Zeichenbereiche Latein,
Latein-Erweitert und Griechisch). Lizenz: SIL Open Font License 1.1, siehe
`static/fonts/OFL.txt`. Streamlit liefert den Ordner unter `/app/static/`
aus (`server.enableStaticServing = true`); eingebunden wird die Schrift über
`[[theme.fontFaces]]` und `theme.font` in `.streamlit/config.toml`, damit sie
auch für alle Streamlit-Bedienelemente gilt. Ersatzschriften: Segoe UI,
system-ui, sans-serif.

## Tests

Ohne Netzwerk und ohne API-Schlüssel, aus dem Ordner `gui`:

```powershell
python tests/test_app.py              # Oberfläche (AppTest, Notfallmodus)
python tests/test_engine_replay.py    # Prüfmaschine gegen die Referenz-Prüfberichte
python tests/test_fehlerprotokoll.py  # Zuordnung zu F01–F13
python tests/test_fundstellen.py      # Fundstellen und Markierungen
```
