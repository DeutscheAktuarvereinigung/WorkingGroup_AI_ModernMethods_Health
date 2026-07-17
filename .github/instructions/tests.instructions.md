---
applyTo: "limitierungstool/tests/**/*.py"
description: "Use when: adding or updating pytest tests for service logic, data loading, and limitierungs rules."
---

# Tests Instruction

## Grundsaetze
- Teste Verhalten, nicht Implementierungsdetails.
- Halte Tests deterministisch: keine zufaelligen Daten ohne festen Seed.
- Nutze sprechende Testnamen im Stil test_<funktion>_<erwartung>.

## Mindestabdeckung bei Fachlogik
- Happy Path fuer Standardfall
- Mindestens ein Edge-Case (leer, nullnah, Grenzwert)
- Mindestens ein Regressionsfall fuer behobene Fehler

## Fuer Limitierungsregeln speziell
- Globale Regel
- Segmentierte Regel (scope_spalte und scope_werte)
- Kombination aus ziel_pct und ziel_abs
- Reihenfolge mehrerer Regeln und Verschaerfungseffekt

## Numerik und Assertions
- Bei Fliekommazahlen pytest.approx oder allclose verwenden.
- Grenzwerte explizit pruefen (<=, >=) statt nur Summen oder Mittelwerte.

## Testdaten
- Bevorzuge kleine, gezielte Fixtures mit minimal notwendiger Komplexitaet.
- Schluesselspalten fuer Merges immer explizit in den Fixtures enthalten.
