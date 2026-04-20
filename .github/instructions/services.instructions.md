---
applyTo: "services/**/*.py"
description: "Use when: editing business logic for limitierung, barwertfaktoren, sensitivitaet, optimierung, and data loading in services/."
---

# Services Instruction

## Prioritaet
1. Fachliche Korrektheit
2. Numerische Stabilitaet
3. Nachvollziehbarkeit
4. Performance

## Rechenlogik
- Halte mathematische Formeln explizit und nachvollziehbar.
- Nutze klare Zwischenvariablen statt dichter Einzeiler bei versicherungsmathematischen Berechnungen.
- Wende Caps fuer ziel_pct und ziel_abs unabhaengig an und dokumentiere die Reihenfolge der Regelwirkung.
- Verwende defensive Checks fuer ungueltige Eingaben (z. B. negative Werte, fehlende Spalten, falsche Typen).

## DataFrame-Regeln
- Kopiere DataFrames vor mutierenden Operationen, wenn Eingaben unveraendert bleiben sollen.
- Validiere Join-Schluessel vor Merge und behandle fehlende Treffer explizit.
- Erzeuge neue Spalten mit klaren, stabilen Namen; vermeide Umbenennungen ohne Not.

## Logging und Fehler
- Nutze logger fuer zentrale Rechenschritte mit knappen, fachlichen Meldungen.
- Raise ValueError bei fachlich unzulaessigen Eingaben statt still weiterzurechnen.

## Tests als Pflicht
- Bei jeder fachlichen Aenderung: mindestens ein neuer oder angepasster Test in tests/.
- Decke mindestens einen Randfall ab (z. B. leere Regeln, Grenzwert-Cap, segmentierte Anwendung).
