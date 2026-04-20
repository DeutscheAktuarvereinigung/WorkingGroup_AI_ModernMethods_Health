# Regression-Checkliste fuer Limitierungslogik

## Fachliche Aenderung einordnen
- Welche Funktion in services/ aendert sich?
- Welche fachliche Aussage soll danach gelten?
- Ist die Aenderung global, segmentiert, befristet oder validierungsbezogen?

## Minimale Testmatrix
- Ein Standardfall mit erwarteter Regelwirkung
- Ein Grenzwertfall exakt auf dem Cap
- Ein Fall oberhalb des Caps
- Falls relevant: Kombination aus ziel_pct und ziel_abs
- Falls relevant: mehrere Regeln mit Verschaerfung
- Falls relevant: fehlender Merge-Treffer oder Pflichtspalte

## Rueckgaben pruefen
- Spaltennamen unveraendert?
- Schluesselspalten noch vorhanden?
- Numerische Spalten nur an Ausgabestellen gerundet?
- Fehlermeldung fachlich klar?

## Validierung
- Bevorzugt gezielter pytest-Lauf fuer die betroffene Datei oder Klasse
- Bei Datenlade-Logik zusaetzlich Pflichtspalten und Warnungen pruefen
