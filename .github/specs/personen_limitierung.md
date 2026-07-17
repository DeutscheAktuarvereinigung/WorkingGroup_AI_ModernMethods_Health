# Spec: Limitierung auf Personenebene

> Hinweis: Das Limitierungstool liegt seit der Repo-Umstrukturierung im Unterordner limitierungstool/. Alle Pfadangaben in diesem Dokument (services/, tests/, app/pages/, ui/, app.py) verstehen sich relativ zu limitierungstool/.


## Motivation

Eine natürliche Person kann in der PKV mehrere Tarife gleichzeitig versichert haben
(z. B. Ambulant + Stationär + Zahn). Bei einer Beitragsanpassung können alle diese
Tarife gleichzeitig betroffen sein. Die bestehende Limitierung greift nur auf
Einzeltarif-Ebene — es gibt keine Möglichkeit, die **Gesamtbelastung einer Person**
über alle ihre Tarife hinweg zu begrenzen.

## Ziel

Einführung einer zusätzlichen Limitierungsebene auf **Personenebene**, die:

1. Mehrere Tarife einer natürlichen Person über eine `person_id` gruppiert
2. Die Gesamterhöhung pro Person gegen konfigurierbare Caps prüft
3. Den Überschuss nach wählbarem Verteilungsmodus auf Einzeltarife zurückverteilt
4. Abwärtskompatibel bleibt (`person_id` ist optional)

## Begriffe

| Begriff | Definition |
|---|---|
| `person_id` | Eindeutige Kennung einer natürlichen Person. Eine Person kann 1–n `versicherten_id`-Einträge haben. |
| `versicherten_id` | Eindeutige Kennung eines Tarif-Vertrags (1 Zeile im Bestand). Bleibt unverändert. |
| Personen-Cap | Maximale Gesamterhöhung (€/Monat und/oder % der Gesamtprämie) pro Person. |
| Verteilungsmodus | Methode zur Rückverteilung des Überschusses auf Einzeltarife: `proportional` oder `groesster_zuerst`. |
| Reihenfolge | Ob zuerst Tarif-Caps oder Personen-Caps angewendet werden. |

## Entscheidungen

| # | Entscheidung | Begründung |
|---|---|---|
| E1 | `person_id` ist **optional** im Bestand | Abwärtskompatibilität; bestehende Daten ohne `person_id` funktionieren wie bisher. |
| E2 | `versicherten_id` bleibt unique pro Zeile | Kein Breaking Change; `person_id` ist die neue Gruppierungsspalte. |
| E3 | Personen-Cap: **flexibel** (`ziel_pct` und/oder `ziel_abs`) | Konsistenz mit bestehender Regel-Struktur. `ziel_pct` bezieht sich auf die Gesamtprämie der Person. |
| E4 | Verteilungsmodus: **konfigurierbar** (`proportional` / `groesster_zuerst`) | Fachliche Anforderung; verschiedene Szenarien erfordern verschiedene Strategien. |
| E5 | Reihenfolge: **konfigurierbar** (`tarif_zuerst` / `person_zuerst`) | `tarif_zuerst` als Default (erst Tarif-Caps, dann Personen-Cap auf bereits limitierte Werte). |
| E6 | Einmaleinlage: **pro Tarif** berechnet (eigener BWF), dann **pro Person aggregiert** | Barwertfaktoren sind tarifspezifisch; Aggregation nur für Reporting. |
| E7 | Mock-Daten: **~50% Voll-Tarif (1 Tarif)**, ~50% Modul-Tarife (2–4 Tarife pro Person) | Realistische PKV-Struktur abbilden. |
| E8 | Personen-Caps zunächst **nur global** (keine Segmentierung) | Reduziert Komplexität; Segmentierung als spätere Erweiterung. |

## Offene Fragen

| # | Frage | Empfehlung |
|---|---|---|
| O1 | Sollen Personen-Caps segmentierbar sein (z. B. nur Classic-Personen)? | Nicht in Phase 1 — aber Datenstruktur so gestalten, dass Erweiterung möglich ist. |
| O2 | Eigener Tab „Personen-Analyse" oder Abschnitt im bestehenden Tab? | Abschnitt im bestehenden Tab. |

## Akzeptanzkriterien

### Datenmodell
- [ ] `person_id`-Spalte in Mock-Daten vorhanden und korrekt zugewiesen
- [ ] Personen mit Voll-Tarif haben genau 1 Zeile (1 `versicherten_id`)
- [ ] Modultarif-Personen haben 2–4 Zeilen mit identischem Alter, Geschlecht, Tarifwerk
- [ ] `data_loader` akzeptiert Bestand mit und ohne `person_id` ohne Fehler
- [ ] Validierung warnt bei inkonsistenter Demographie innerhalb einer `person_id`

### Service-Logik
- [ ] `berechne_limitierung_person()` aggregiert Erhöhungen pro Person korrekt
- [ ] Personen-Cap (`ziel_abs`) begrenzt die Summe aller Einzeltarif-Erhöhungen
- [ ] Personen-Cap (`ziel_pct`) begrenzt auf % der Gesamtprämie der Person
- [ ] Verteilung `proportional`: Reduktion proportional zur Einzeltarif-Erhöhung aller Tarife der Person
- [ ] Verteilung `groesster_zuerst`: Tarif mit höchster €-Erhöhung wird zuerst reduziert
- [ ] Reihenfolge `tarif_zuerst`: bestehende Tarif-Regeln → dann Personen-Cap
- [ ] Reihenfolge `person_zuerst`: Personen-Cap → dann Tarif-Regeln
- [ ] Einmaleinlage pro Tarif korrekt (eigener Barwertfaktor), Summe pro Person korrekt
- [ ] Neue Ergebnis-Spalten: `person_id`, `erhoehung_person_gesamt_vorher`, `erhoehung_person_gesamt_nachher`, `person_limitiert`
- [ ] Ohne `person_id` in den Daten: bestehende Limitierung funktioniert identisch (Regression)

### Tests
- [ ] Happy Path: 2-Tarif-Person, proportionale Verteilung → Summe ≤ Cap
- [ ] Happy Path: 2-Tarif-Person, größter-zuerst → höchster Tarif wird zuerst reduziert
- [ ] Reihenfolge: `tarif_zuerst` vs `person_zuerst` liefern unterschiedliche, valide Ergebnisse
- [ ] Edge Case: 1-Tarif-Person → Personen-Cap wirkt wie normaler Tarif-Cap
- [ ] Edge Case: Alle Tarife einer Person bereits unter Cap → keine Reduktion
- [ ] Edge Case: Person hat Tarife mit `praemie_alt_monatlich = 0` → kein Division-by-Zero
- [ ] Regression: Alle bestehenden Tests in `test_limitierung.py` bleiben grün

### UI
- [ ] Neuer Abschnitt „Personen-Limitierung" im Limitierungs-Tab
- [ ] Eingabefelder: Max €/Monat pro Person, Max % der Gesamtprämie, Verteilungsmodus, Reihenfolge
- [ ] Ergebnis-KPIs: Anzahl Personen limitiert, Ø Entlastung/Person
- [ ] `person_id` als Gruppierungs-Dimension in Bestandsanalyse verfügbar

## Änderungsumfang

### Notwendig (Must)
| Datei | Änderung |
|---|---|
| `mock_daten_erzeugen.py` | `person_id`-Spalte in `erzeuge_bestand()` hinzufügen, Multi-Tarif-Logik |
| `services/data_loader.py` | `person_id` als optionale Spalte akzeptieren, Konsistenz-Validierung |
| `services/limitierung.py` | Neue Funktion `berechne_limitierung_person()` |
| `tests/conftest.py` | Fixtures mit `person_id` erweitern |
| `tests/test_limitierung.py` | Neue Tests für Personen-Limitierung |
| `tests/test_data_loader.py` | Validierungstests für `person_id` |

### Empfohlen (Should)
| Datei | Änderung |
|---|---|
| `app/pages/limitierung.py` | UI-Abschnitt für Personen-Limitierung |
| `app.py` | `GRUPPIER_DIMENSIONEN` um `"Person": "person_id"` erweitern, Cache-Wrapper |
| `app/pages/bestandsanalyse.py` | `person_id` als Gruppierungs-Dimension |

### Optional (Could)
| Datei | Änderung |
|---|---|
| `services/limitierung.py` | Personen-Caps in `berechne_sensitivitaet()` |
| `services/optimierung.py` | Grid-Suche um Personen-Cap-Dimension erweitern |

## Verteilungsalgorithmus (Detail)

### Modus `proportional`
```
Für jede Person p mit Tarif-Erhöhungen [e1, e2, ..., en]:
  gesamt_erhoehung = e1 + e2 + ... + en
  if gesamt_erhoehung > personen_cap:
      reduktion = gesamt_erhoehung - personen_cap
      for each ei:
          anteil_i = ei / gesamt_erhoehung
          ei_neu = ei - reduktion * anteil_i
```

### Modus `groesster_zuerst`
```
Für jede Person p mit Tarif-Erhöhungen [e1, e2, ..., en] sortiert absteigend:
  gesamt_erhoehung = sum(ei)
  if gesamt_erhoehung > personen_cap:
      reduktion_rest = gesamt_erhoehung - personen_cap
      for each ei (größter zuerst):
          moegliche_reduktion = min(reduktion_rest, ei - next_smaller_or_zero)
          ei_neu = ei - moegliche_reduktion
          reduktion_rest -= moegliche_reduktion
          if reduktion_rest <= 0: break
```

## Implementierungsreihenfolge

1. **Mock-Daten** — `person_id` erzeugen
2. **Data-Loader** — `person_id` optional akzeptieren
3. **Service-Logik** — `berechne_limitierung_person()`
4. **Tests** — Fixtures + Testfälle
5. **UI** — Eingabe + Ergebnisanzeige
