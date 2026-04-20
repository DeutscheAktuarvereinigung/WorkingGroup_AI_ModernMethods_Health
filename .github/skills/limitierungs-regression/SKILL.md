---
name: limitierungs-regression
description: "Use when: changing limitierung, barwertfaktoren, sensitivitaet, optimierung, segmentierte Regeln, Caps in Prozent oder Euro, oder CSV-Validierung mit Einfluss auf die Fachlogik."
argument-hint: "Describe the changed fachliche rule, expected behavior, and affected functions or tests."
user-invocable: true
disable-model-invocation: false
---

# Limitierungs Regression

Nutze diesen Skill fuer wiederkehrende Fachlogik-Aenderungen im PKV-Limitierungstool, insbesondere in services/ und den dazugehoerigen Tests.

## Wann verwenden
- Anpassung von Limitierungsregeln oder Regelreihenfolgen
- Aenderung an ziel_pct, ziel_abs oder segmentierten Scopes
- Aenderung an Barwertfaktoren oder befristeter Berechnung
- Datenvalidierung, die Fachlogik oder Join-Verhalten beeinflusst
- Bugfixes mit Regressionsrisiko in Bestands- oder Limitierungsrechnungen

## Ziel
Sicherstellen, dass fachliche Aenderungen nicht nur implementiert, sondern gegen typische Regressionsmuster abgesichert werden.

## Vorgehen
1. Bestimme, welche fachliche Annahme sich aendert.
2. Lokalisiere die Kernfunktion in services/ und die bestehende Testdatei in tests/.
3. Pruefe, ob die Aenderung eine dieser Kategorien betrifft:
   - globale Regel
   - segmentierte Regel
   - Kombination Prozent und Euro
   - Regelreihenfolge und Verschaerfung
   - Merge-/Validierungsverhalten
   - befristete versus unbefristete Berechnung
4. Ergaenze mindestens einen Regressionsfall und einen passenden Randfall.
5. Verifiziere, dass Spaltennamen, Join-Schluessel und Rueckgabeform stabil bleiben.
6. Fuehre gezielt pytest fuer die betroffene Testdatei oder Testklasse aus.

## Checkliste
- Die Regelwirkung ist fachlich nachvollziehbar beschrieben.
- Prozent- und Euro-Logik bleiben explizit getrennt.
- Keine stillen Defaults bei fehlenden Pflichtdaten.
- Rueckgabe-Spalten bleiben stabil oder sind bewusst angepasst.
- Tests pruefen Grenzwerte, nicht nur Mittelwerte.

## Referenz
- [Regression-Checkliste](./references/regression-checkliste.md)
