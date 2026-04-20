# PKV-Limitierungstool: Projektweite Copilot Instructions

## Zielbild
- Liefere fachlich nachvollziehbare, testbare und stabile Aenderungen fuer Bestandsanalyse und Limitierungsrechnung.
- Trenne strikt zwischen UI, Service-Logik und Datenvalidierung.
- Bewahre bestehende APIs und Datenvertraege, sofern keine explizite Aenderung angefordert ist.

## Fachliche Guardrails
- Nutze die bestehende Terminologie konsistent: Bestand, Limitierung, Ziel Prozent, Ziel Absolut, Einmaleinlage, RfB, Befristung.
- Implementiere fachliche Rechenlogik nur in services/. Keine Berechnungslogik in app/pages/.
- Behandle Prozentwerte und Euro-Werte explizit getrennt. Keine implizite Vermischung.
- Fuehre keine stillen Defaults bei fehlenden Pflichtspalten ein. Stattdessen klare Validierungsfehler mit hilfreicher Meldung.
- Runde numerische Ergebnisse nur an expliziten Ausgabestellen; intern mit voller Praezision rechnen.

## Daten und Robustheit
- Erhalte Spaltennamen und Schluesselspalten stabil (z. B. tarif_id, geschlecht, alter).
- Pruefe Merge-Operationen auf Schluesselvollstaendigkeit und dokumentiere erwartetes Verhalten bei fehlenden Treffern.
- Vermeide in-place Mutation von Eingabe-DataFrames, wenn sie spaeter erneut verwendet werden.

## Tests und Qualitaet
- Jede fachliche Aenderung in services/ braucht mindestens einen passenden Test in tests/.
- Ergaenze bevorzugt Regressionsfaelle fuer Bugfixes und Edge-Cases (leere Daten, Grenzwerte, segmentierte Regeln).
- Halte Tests deterministisch und gut lesbar.

## Implementierungsstil
- Bevorzuge kleine, klar begrenzte Aenderungen statt grosser Refactorings ohne fachlichen Mehrwert.
- Erklaere nicht-triviale Logik kurz im Code mit knappen Kommentaren.
- Achte auf konsistente Benennung und bestehende Projektkonventionen (deutschsprachige Fachbegriffe in snake_case).
