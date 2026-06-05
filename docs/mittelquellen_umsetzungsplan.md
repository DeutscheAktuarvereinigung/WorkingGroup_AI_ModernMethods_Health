# Umsetzungsplan: Mittelquellen und Topfsteuerung

Dieses Markdown-Dokument ist die Grundlage fuer die naechsten Implementierungen. Es dokumentiert aktuellen Status, getroffene Entscheidungen, auszufuehrende Tasks und spaeter die ausgefuehrten Tests.

## 1. Aktueller Status

- Stand: 2026-06-05.
- Phase A wurde dokumentarisch umgesetzt: Fachsemantik, Konfigurationsschema, Default-Konfiguration und offene Folgephasen sind festgehalten.
- Phase B wurde umgesetzt: Mock-Bestand enthaelt Mittelspalten, Beispiel-Konfiguration wird erzeugt, und Datenvalidierung fuer Mittelspalten/Konfiguration ist vorhanden.
- Phase C wurde umgesetzt: Die Service-Schicht fuer regelunabhaengige Vorab-Entlastung und regelgebundene Mittelverwendung ist vorhanden.
- Phase D wurde umgesetzt: Die App enthaelt einen Tab „Mittelkonfiguration“ mit editierbarer, validierter Quellenkonfiguration im Session-State.
- Phase E wurde umgesetzt: Die Limitierungsrechnung orchestriert regelunabhaengige Mittel, UI-Regeln, Personen-Limitierung, Befristungsmischung und regelgebundene Finanzierung.
- Die aktuelle Kernrechnung erzeugt in `berechne_limitierung()` weiterhin einen Gesamtbedarf je Zeile ueber `einmaleinlage`; die Mittelquellen-Orchestrierung liegt additiv in `services/limitierungs_pipeline.py`.
- Das einzelne RfB-Budget wird fuer die Rechnung in die Quelle `rfb_frei` gespiegelt.
- Die Bestandssimulation erzeugt `ueberzins_mittel_euro`, `zu10_mittel_euro` und `mittelquellen_config.csv`.
- Automatisierte Tests fuer Phase B/C/D/E wurden ausgefuehrt; Details stehen im Testprotokoll.

## 2. Getroffene fachliche Entscheidungen

- Mittelquellen initial:
  - freie RfB als globaler Topf,
  - Ueberzinsen kunden-/tarifindividuell,
  - ZU10-Mittel aus der Vollversicherung,
  - weitere frei definierbare Toepfe.
- Bei erschoepftem Topf faellt Restbedarf in der konfigurierten Reihenfolge auf den naechsten Topf zurueck.
- ZU10-Mittel werden als externe Betragsspalte geliefert; in der Mocksimulation darf eine plausible Beispielspalte erzeugt werden.
- ZU10-Mittel duerfen erst fuer Versicherte ab Alter 65 angewendet werden und sollen fachlich zusaetzlich auf Vollversicherung eingeschraenkt werden.
- Ueberzins soll immer vollstaendig zur Limitierung der Beitragsanpassung verwendet werden, unabhaengig von den in der UI definierten Limitierungsregeln.
- Die Konfiguration muss explizit bestimmen koennen, ob ein Topf den UI-Limitierungsregeln unterliegt oder regelunabhaengig angewendet wird.
- Phase-A-Entscheidung fuer die Default-Konfiguration: ZU10 wird zunaechst regelgebunden modelliert, aber mit festem Berechtigungsfilter `alter >= 65` und `tarifart == voll`. Die UI muss diese Regelbindung spaeter aenderbar machen.
- Externe Mittelspalten werden fuer die Erstimplementierung in Einmaleinlagen-/Kapitalwertbasis interpretiert. Laufende Monatsbetraege muessen explizit als `betrag_einheit = monatlich` gekennzeichnet werden.
- UI-Ort: eigener Tab oder eigene Seite „Mittelkonfiguration“.
- Rueckwaertskompatibilitaet: Bestehende Spalten aus der Limitierungsrechnung bleiben erhalten; neue Spalten werden additiv ergaenzt.

## 3. Praezisiertes Fachmodell

### 3.1 Begriffe

- `regelgebunden`: Der Topf finanziert nur Bedarf, der aus den in der UI definierten Limitierungsregeln entsteht.
- `regelunabhaengig`: Der Topf wird unabhaengig von UI-Regeln zur Reduktion der Beitragsanpassung verwendet.
- `pflicht_vollstaendig`: Verfuegbare Mittel muessen soweit moeglich voll zur Entlastung eingesetzt werden, begrenzt durch die vorhandene Beitragsanpassung.
- `berechtigungsfilter`: Fachliche Einschraenkung einer Quelle, z. B. Alter >= 65 und Tarifart == voll.
- `fallback`: Nicht gedeckter Bedarf oder nicht ausgeschopfte Entlastung wird gemaess Prioritaet an die naechste passende Quelle uebergeben.

### 3.2 Konfigurationsmodell

Die Mittelquellen-Konfiguration soll je Quelle mindestens enthalten:

- `quelle_id`: stabiler technischer Schluessel, z. B. `rfb_frei`, `ueberzins`, `zu10`.
- `name`: Anzeige in der UI.
- `aktiv`: Quelle wird verwendet oder ignoriert.
- `prioritaet`: Anwendungsreihenfolge.
- `typ`: `global`, `zeilenindividuell` oder `segmentiert`.
- `betrag_euro` oder `betrag_spalte`: globaler Betrag oder zeilenindividuelle Betragsspalte.
- `betrag_einheit`: `einmaleinlage` oder `monatlich`; empfohlen wird `einmaleinlage` fuer externe Mittelspalten.
- `unterliegt_limitierungsregeln`: `True` fuer regelgebundene Quellen, `False` fuer regelunabhaengige Quellen.
- `einsatzmodus`: z. B. `pflicht_vollstaendig`, `nur_bedarf_finanzieren`, `optional`.
- `anwendungsphase`: empfohlen `vor_regeln` fuer regelunabhaengige Quellen und `nach_regeln` fuer regelgebundene Quellen.
- `scope_spalte`/`scope_werte` oder strukturierte Filterbedingungen fuer berechtigte Zeilen.
- `fallback_erlaubt`: bestimmt, ob offener Rest an nachfolgende Toepfe weitergegeben wird.

Verbindliches Schema fuer die naechste Implementierungsphase:

| Feld | Pflicht | Typ / Werte | Bedeutung |
| --- | --- | --- | --- |
| `quelle_id` | ja | string, eindeutig | Stabiler technischer Schluessel fuer Spaltennamen, Trace und Export. |
| `name` | ja | string | Fachlicher Anzeigename in UI und Export. |
| `aktiv` | ja | bool | Steuert, ob die Quelle in der Berechnung verwendet wird. |
| `prioritaet` | ja | int >= 1 | Niedrigere Zahl wird frueher angewendet. Doppelte aktive Prioritaeten sind unzulaessig. |
| `typ` | ja | `global`, `zeilenindividuell`, `segmentiert` | Bestimmt, ob Mittel global, je Zeile oder auf einem Segment verfuegbar sind. |
| `betrag_euro` | bedingt | float >= 0 | Globaler oder segmentierter Betrag, erforderlich falls keine `betrag_spalte` gesetzt ist. |
| `betrag_spalte` | bedingt | string | Spalte im Bestand fuer zeilenindividuelle Mittel, erforderlich fuer `zeilenindividuell`. |
| `betrag_einheit` | ja | `einmaleinlage`, `monatlich` | Einheit der Mittel; Default und empfohlene Erstimplementierung ist `einmaleinlage`. |
| `unterliegt_limitierungsregeln` | ja | bool | `False` bedeutet regelunabhaengige Vorab-Entlastung; `True` bedeutet Finanzierung des regelbedingten Bedarfs. |
| `einsatzmodus` | ja | `pflicht_vollstaendig`, `nur_bedarf_finanzieren`, `optional` | Fachliche Verpflichtung zur Mittelverwendung. |
| `anwendungsphase` | ja | `vor_regeln`, `nach_regeln` | Technische Phase in der Berechnungspipeline. Muss zur Regelbindung passen. |
| `filter` | nein | Liste von Bedingungen | Berechtigungsfilter, z. B. Alter >= 65 und Tarifart == voll. |
| `fallback_erlaubt` | ja | bool | Erlaubt Weitergabe offenen Bedarfs an nachfolgende Quellen. |

Validierungsentscheidungen fuer Phase B/C:

- Aktive Quellen muessen eine eindeutige `quelle_id` und eindeutige `prioritaet` besitzen.
- Fuer `typ = zeilenindividuell` ist `betrag_spalte` verpflichtend; die Spalte muss vorhanden, numerisch und nicht negativ sein.
- Fuer `typ = global` ist `betrag_euro` verpflichtend, falls keine alternative spaetere Budgetquelle definiert wird.
- `unterliegt_limitierungsregeln = False` erzwingt `anwendungsphase = vor_regeln`.
- `unterliegt_limitierungsregeln = True` erzwingt `anwendungsphase = nach_regeln`.
- Fehlende Filterspalten sind fachliche Fehler und duerfen nicht still ignoriert werden.

### 3.3 Default-Konfiguration

- Ueberzins:
  - `typ = zeilenindividuell`,
  - `unterliegt_limitierungsregeln = False`,
  - `einsatzmodus = pflicht_vollstaendig`,
  - `anwendungsphase = vor_regeln`,
  - Betrag aus einer Bestandsspalte, z. B. `ueberzins_mittel_euro`.
- ZU10:
  - `typ = zeilenindividuell`,
  - `unterliegt_limitierungsregeln = True`,
  - `einsatzmodus = nur_bedarf_finanzieren`,
  - `anwendungsphase = nach_regeln`,
  - Betrag aus einer Bestandsspalte, z. B. `zu10_mittel_euro`,
  - Berechtigungsfilter: `tarifart == voll` und `alter >= 65`,
  - Regelbindung und Prioritaet bleiben in der UI konfigurierbar, damit spaetere fachliche Varianten ohne Codeaenderung abbildbar sind.
- Freie RfB:
  - `typ = global`,
  - `unterliegt_limitierungsregeln = True`,
  - `einsatzmodus = nur_bedarf_finanzieren`,
  - `anwendungsphase = nach_regeln`.

## 4. Empfohlene Rechenlogik

1. Eingangsbestand validieren und Barwertfaktoren ermitteln.
2. Regelunabhaengige Quellen in Prioritaetsreihenfolge anwenden:
   - nur auf berechtigte Zeilen,
   - maximal bis zur vorhandenen Beitragsanpassung,
   - bei Betragseinheit `einmaleinlage` Umrechnung in moegliche monatliche Entlastung ueber `betrag / (12 * barwertfaktor)`,
   - bei fehlendem oder nullnahem Barwertfaktor klare Warnung oder `ValueError` je nach Kritikalitaet.
3. Einen modifizierten Rechenbestand fuer die UI-Limitierungsregeln erzeugen, in dem bereits regelunabhaengige Entlastungen beruecksichtigt sind.
4. Bestehende UI-Limitierungsregeln auf den verbleibenden Anpassungsbetrag anwenden.
5. Regelgebundene Quellen in Prioritaetsreihenfolge zur Finanzierung des regelbedingten Bedarfs verwenden.
6. Ergebnis additiv ausgeben:
   - bestehende Spalten der Limitierung,
   - Entlastung und verwendete Mittel je Quelle,
   - `finanziert_gesamt`,
   - `unterdeckung`,
   - `finanzierungsquote`,
   - Trace-Spalten fuer Quelle, Phase und Regelbindung.
7. Konsistenzregel fuer Plausibilitaet: verwendete Mittel je Quelle duerfen die konfigurierte Verfuegbarkeit nicht ueberschreiten; Summe regelunabhaengige Entlastung plus regelgebundene Entlastung muss nachvollziehbar zur finalen limitierten Praemie passen.

## 5. Auszufuehrende Tasks

### Phase A — Dokumentation und fachliche Schemata

- [x] Fachliche Semantik in README und separatem Projektdokument ergaenzen: Bedarf, Finanzierung, regelgebunden, regelunabhaengig, Fallback, Unterdeckung.
- [x] Endgueltiges Schema fuer Mittelquellen-Konfiguration definieren.
- [x] Default-Konfiguration fuer Ueberzins, ZU10 und freie RfB festlegen.
- [x] Entscheiden und dokumentieren, ob ZU10 defaultmaessig regelunabhaengig oder regelgebunden angewendet wird; Alter >= 65 und Vollversicherung sind gesetzt.
- [x] Dokumentieren, welche Betragseinheit fuer externe Mittelspalten gilt; empfohlen: Einmaleinlagen-/Kapitalwertbasis.

### Phase B — Bestandssimulation und Datenvalidierung

- [x] Bestandssimulation um Spalte `ueberzins_mittel_euro` erweitern.
- [x] Bestandssimulation um Spalte `zu10_mittel_euro` erweitern; Werte nur fuer Vollversicherung, sonst 0.
- [x] ZU10-Beispielwerte in der Simulation so erzeugen, dass Alter >= 65 fachlich relevante Mittel erhaelt; Juengere duerfen zwar Spaltenwerte haben, werden aber ueber Konfiguration nicht angewendet, oder erhalten 0.
- [x] Beispiel-Konfigurationsdatei fuer Mittelquellen erzeugen, falls CSV-/Dateiimport vorgesehen wird.
- [x] Validierung fuer referenzierte Betragsspalten ergaenzen: vorhanden, numerisch, nicht negativ.
- [x] Validierung fuer Scope-/Filterspalten ergaenzen: keine stillen Defaults bei fehlenden Spalten.

### Phase C — Service-Schicht fuer Mittelwirkung und Mittelverwendung

- [x] Neues Service-Modul fuer Mittelquellen-Validierung und Allokation planen und anlegen.
- [x] `validiere_mittelquellen_config(config, df_bestand)` implementieren und in der neuen Service-Schicht verwenden.
- [x] Funktion fuer regelunabhaengige Vorab-Entlastung implementieren, z. B. `wende_regelunabhaengige_mittel_an(...)`.
- [x] Funktion fuer regelgebundene Finanzierung implementieren, z. B. `berechne_mittelverwendung(...)`.
- [x] BWF-Umrechnung fuer Mittel in Einmaleinlagenbasis zentral und testbar kapseln.
- [x] Sicherstellen, dass Eingabe-DataFrames nicht in-place mutiert werden.
- [x] Bestehende `berechne_limitierung()` nicht mit Topf-Logik ueberladen; sie bleibt Kernfunktion fuer UI-Regel-Caps.
- [x] Trace-Spalten fuer Quelle, Phase, angewendete Mittel und Restbedarf definieren.

### Phase D — UI-Konfiguration

- [x] Neuen Tab oder neue Seite „Mittelkonfiguration“ in die Streamlit-App aufnehmen.
- [x] UI fuer Quellen aktivieren/deaktivieren, Prioritaet sortieren, Typ waehlen und Betrag/Betragsspalte setzen.
- [x] UI-Feld `unterliegt Limitierungsregeln` je Topf ergaenzen.
- [x] UI fuer Berechtigungsfilter ergaenzen, mindestens Alter, Tarifart, Tarifwerk, Tarif, Geschlecht.
- [x] Default fuer Ueberzins als regelunabhaengige Pflichtquelle vorbelegen.
- [x] Default fuer ZU10 mit Filter Alter >= 65 und Tarifart == voll vorbelegen.
- [x] Aktuelles einzelne RfB-Budget in freie RfB-Quelle ueberfuehren oder spiegeln.
- [x] Konfiguration in `st.session_state` mit klar benannten Schluesseln speichern.

### Phase E — Limitierungs-Orchestrierung und Ergebnisse

- [x] Berechnungspipeline in der UI anpassen: regelunabhaengige Mittel anwenden, danach UI-Regeln, danach regelgebundene Finanzierung.
- [x] Personen-Limitierung in die Pipeline einordnen und Reihenfolge fachlich dokumentieren.
- [x] Befristungsmischung pruefen: Bedarf fuer regelgebundene Quellen muss mit gemischtem Bedarf konsistent sein.
- [x] Ergebnis-KPIs erweitern: Bedarf vor/nach regelunabhaengiger Entlastung, freie RfB, Ueberzins, ZU10, weitere Quellen, Unterdeckung.
- [x] Charts um Quelle/Topf erweiterbar machen: Verteilung Mittel je Quelle, Waterfall oder gestapelte Balken.
- [x] Detailanalyse und Export um Mittelquellen-Spalten ergaenzen.

### Phase F — Tests und Regression

- [ ] Test: Ueberzins wird auch ohne UI-Regel vollstaendig bis zur vorhandenen Beitragsanpassung angewendet.
- [ ] Test: Ueberzins wird vor UI-Regeln angewendet und reduziert den nachfolgenden regelbedingten Bedarf.
- [ ] Test: ZU10 wird nur fuer Alter >= 65 und Tarifart voll angewendet.
- [ ] Test: ZU10 wird fuer Alter < 65 nicht angewendet, selbst wenn eine Betragsspalte vorhanden ist.
- [ ] Test: freie RfB finanziert nur regelgebundenen Bedarf.
- [ ] Test: Fallback-Reihenfolge bei erschoepftem Topf.
- [ ] Test: globale Quelle wird bei Unterdeckung proportional verteilt oder gemaess dokumentierter Fachentscheidung zugeordnet.
- [ ] Test: fehlende Betragsspalte erzeugt `ValueError`.
- [ ] Test: negative Mittelwerte erzeugen `ValueError`.
- [ ] Test: bestehende Limitierungsfunktion bleibt rueckwaertskompatibel fuer bestehende Tests.
- [ ] Test: Export enthaelt erwartete Schluessel- und Mittelquellen-Spalten.

## 6. Relevante bestehende Dateien

- `services/limitierung.py`: Kernrechnung `berechne_limitierung()`, `berechne_limitierung_person()`, BWF-Logik; soll nicht mit UI-/Topf-Konfiguration ueberladen werden.
- `services/mittelverwendung.py`: Neue Service-Schicht fuer regelunabhaengige Mittelwirkung und regelgebundene Finanzierungszuordnung.
- `app.py`: Tab-Struktur, Imports, Streamlit-Cache-Wrapper; hier ist der neue Tab einzubinden.
- `app/pages/limitierung.py`: aktuelle Regel-/Budget-UI, Befristungsmischung, Ergebnisdarstellung, Export; hier ist die neue Pipeline zu orchestrieren.
- `services/data_loader.py`: CSV-Validierung und kuenftige Validierung referenzierter Mittelspalten.
- `mock_daten_erzeugen.py`: Bestandssimulation um Ueberzins- und ZU10-Spalten erweitern.
- `tests/test_limitierung.py`: Regression bestehender Limitierungslogik und neue Tests fuer Reihenfolge/Regelbindung.
- `tests/test_mittelverwendung.py`: Tests fuer Ueberzins-Vorabentlastung, ZU10-Filter, Fallback, proportionale Topfverteilung und Validierungsfehler.
- `tests/test_data_loader.py`: Tests fuer Validierung neuer Spalten und Konfiguration.
- `tests/conftest.py`: kleine Testfixtures mit Ueberzins, ZU10, Alter-65-Grenze und Vollversicherung.
- `README.md`: fachliche und technische Dokumentation aktualisieren.

## 7. Testprotokoll

### 2026-06-05 — Phase A Dokumentation

- Geaenderte Dateien: `docs/mittelquellen_umsetzungsplan.md`, `README.md`.
- Umfang: reine Dokumentation, keine Aenderung an Service-, UI- oder Testcode.
- Automatisierte Tests: nicht ausgefuehrt, da keine Laufzeitlogik geaendert wurde.
- Verifikation: Markdown-Inhalte manuell geprueft; Folgephasen und Akzeptanzkriterien dokumentiert.

### 2026-06-05 — Phase B Bestandssimulation und Datenvalidierung

- Geaenderte Dateien: `mock_daten_erzeugen.py`, `services/data_loader.py`, `tests/test_data_loader.py`, `README.md`, `docs/mittelquellen_umsetzungsplan.md`.
- Implementierung:
  - `bestand.csv` aus dem Mock-Generator enthaelt nun `ueberzins_mittel_euro` und `zu10_mittel_euro`.
  - ZU10-Mockwerte werden nur fuer `tarifart == voll` und `alter >= 65` erzeugt; alle anderen Zeilen erhalten 0.
  - Der Mock-Generator erzeugt `mittelquellen_config.csv` mit den Phase-A-Defaults fuer Ueberzins, ZU10 und freie RfB.
  - `services/data_loader.py` validiert optionale Mittelspalten im Bestand und eine Mittelquellen-Konfiguration inkl. referenzierter Betragsspalten und Filterspalten.
- Tests:
  - `python -m pytest tests/test_data_loader.py -q` -> 36 passed in 0.33s.
  - `python -m pytest -q` -> 150 passed in 7.43s.
  - `python -m py_compile mock_daten_erzeugen.py services/data_loader.py` -> Exit-Code 0.
  - `python mock_daten_erzeugen.py -o output_daten -m 0.30 -s 42` -> Exit-Code 0; `bestand.csv` mit 999.999 Zeilen, `mittelquellen_config.csv` erzeugt.
  - Validierung der erzeugten Dateien mit `lade_csv(...)` und `validiere_mittelquellen_config(...)` -> 999.999 Bestandszeilen, Quellen `ueberzins`, `zu10`, `rfb_frei`.

### 2026-06-05 — Phase C Service-Schicht Mittelverwendung

- Geaenderte Dateien: `services/mittelverwendung.py`, `tests/test_mittelverwendung.py`, `docs/mittelquellen_umsetzungsplan.md`.
- Implementierung:
  - `wende_regelunabhaengige_mittel_an(...)` wendet aktive regelunabhaengige Quellen vor den UI-Regeln an und erzeugt einen neuen Rechenbestand.
  - Ueberzins wird ueber `betrag_einheit = einmaleinlage` mit Barwertfaktor in monatliche Entlastung umgerechnet und maximal bis zur vorhandenen Beitragsanpassung verwendet.
  - `berechne_mittelverwendung(...)` ordnet regelgebundene Quellen dem Limitierungsbedarf zu, ohne die Limitierungswirkung zu veraendern.
  - ZU10-Berechtigungsfilter werden generisch ueber `filter_spalten`, `filter_operatoren`, `filter_werte` ausgewertet.
  - Globale Toepfe werden bei Unterdeckung proportional auf offenen berechtigten Bedarf verteilt; Cent-Rundungsdifferenzen werden ohne Budgetueberschreitung korrigiert.
  - Bestehende `berechne_limitierung()` bleibt unveraendert.
- Tests:
  - `python -m pytest tests/test_mittelverwendung.py -q` -> 7 passed in 0.25s.
  - `python -m pytest -q` -> 157 passed in 6.85s.
  - `python -m py_compile services/mittelverwendung.py services/data_loader.py mock_daten_erzeugen.py` -> Exit-Code 0.

### 2026-06-05 — Phase D UI-Konfiguration

- Geaenderte Dateien: `app.py`, `app/pages/mittelkonfiguration.py`, `README.md`, `docs/mittelquellen_umsetzungsplan.md`.
- Implementierung:
  - `app.py` enthaelt nun einen dritten Haupttab „Mittelkonfiguration“ zwischen Bestandsanalyse und Limitierungsrechnung.
  - Lokale Mockdaten und CSV-Upload koennen optional `mittelquellen_config.csv` laden; fehlt die Datei, erzeugt die UI eine Default-Konfiguration.
  - `app/pages/mittelkonfiguration.py` stellt eine editierbare Quellen-Tabelle mit Aktivierung, Prioritaet, Typ, Betragsspalte, Regelbindung, Einsatzmodus, Phase und Filterfeldern bereit.
  - Die Anwendungsphase wird aus `unterliegt_limitierungsregeln` abgeleitet: regelunabhaengig -> `vor_regeln`, regelgebunden -> `nach_regeln`.
  - Defaults sind gesetzt fuer Ueberzins (`vor_regeln`, Pflichtquelle), ZU10 (`tarifart == voll`, `alter >= 65`) und freie RfB als globaler Topf.
  - Der validierte Stand wird in `st.session_state["mittelquellen_config"]` gespeichert; der aktuelle Entwurf in `st.session_state["mittelquellen_config_entwurf"]`.
- Tests:
  - `python -m py_compile app.py app/pages/mittelkonfiguration.py` -> Exit-Code 0.
  - `python -m pytest -q` -> 157 passed in 5.56s.

### 2026-06-05 — Phase E Limitierungs-Orchestrierung

- Geaenderte Dateien: `services/limitierungs_pipeline.py`, `app/pages/limitierung.py`, `tests/test_limitierungs_pipeline.py`, `README.md`, `docs/mittelquellen_umsetzungsplan.md`.
- Implementierung:
  - `services/limitierungs_pipeline.py` kapselt die Reihenfolge: regelunabhaengige Mittel -> bestehende Tarif-/Personen-Limitierung -> regelgebundene Finanzierung.
  - `app/pages/limitierung.py` nutzt die validierte Mittelkonfiguration aus dem Session-State; `rfb_frei` wird mit dem bestehenden UI-Budget synchronisiert.
  - Ueberzins-Vorabentlastung reduziert den Rechenbestand vor den UI-Regeln; Bedarf vor und nach Vorab-Mitteln wird nachgewiesen.
  - Personen-Limitierung bleibt ueber die bestehende Reihenfolge steuerbar und ist in die Mittelquellen-Pipeline integriert.
  - Bei aktiver Befristungsmischung wird die regelgebundene Mittelverwendung auf Basis der gemischten `einmaleinlage` neu berechnet.
  - Ergebnis-KPIs, Quellenbalkendiagramm, Detailanalyse und Export enthalten Finanzierungsquote, Unterdeckung und verwendete Mittel je Quelle.
- Tests:
  - `python -m pytest tests/test_limitierungs_pipeline.py -q` -> 3 passed in 0.29s.
  - `python -m pytest tests/test_limitierungs_pipeline.py tests/test_mittelverwendung.py tests/test_limitierung.py -q` -> 67 passed in 3.39s.
  - `python -m py_compile services/limitierungs_pipeline.py app/pages/limitierung.py app.py` -> Exit-Code 0.
  - `python -m pytest -q` -> 160 passed in 6.23s.

### Noch nicht ausgefuehrt

- [ ] Manuelle Streamlit-Pruefung mit Mockdaten und Mittelkonfiguration.

### Nach Implementierung zu dokumentieren

- Datum/Uhrzeit der Testausfuehrung.
- Commit/Arbeitsstand.
- Ausgefuehrte Testbefehle.
- Ergebnis: bestanden/fehlgeschlagen.
- Relevante Fehlermeldungen und Folgeaufgaben.

## 8. Akzeptanzkriterien

- Ueberzins reduziert die Beitragsanpassung unabhaengig von UI-Limitierungsregeln.
- ZU10-Mittel werden nur fuer berechtigte Vollversicherte ab Alter 65 eingesetzt.
- In der UI kann je Topf gesteuert werden, ob er den Limitierungsregeln unterliegt.
- Die Anwendungsreihenfolge der aktiven Toepfe ist konfigurierbar und reproduzierbar.
- Fallback bei erschoepften Toepfen ist nachvollziehbar und getestet.
- Bestehende Limitierungsregeln funktionieren weiterhin global, segmentiert, prozentual und absolut.
- Bestehende Rueckgabespalten bleiben erhalten; neue Spalten sind additiv.
- Export und Detailanalyse enthalten die Mittelquellen-Nachweise.
- Tests decken Ueberzins, ZU10-Altersgrenze, Regelbindung, Fallback und Validierungsfehler ab.

## 9. Scope-Grenzen

- Enthalten: Mehrere Mittelquellen, regelgebundene und regelunabhaengige Toepfe, konfigurierbare Reihenfolge, Ueberzins-Pflichteinsatz, ZU10-Alters-/Vollversicherungsfilter, Mockdaten-Erweiterung, UI-Konfiguration, Tests.
- Nicht enthalten in Erstumsetzung: Optimierer, der die Limitierungsregeln automatisch an Topfverfuegbarkeit anpasst; produktionsreife Persistenz der Konfiguration ausserhalb Session/CSV; aufsichtsrechtliche Detailmodellierung der tatsaechlichen ZU10-Zufuehrung ueber Zeit.
