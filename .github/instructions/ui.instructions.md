---
applyTo: "{app.py,app/pages/**/*.py,ui/**/*.py}"
description: "Use when: editing Streamlit UI, page rendering, sidebar filters, charts, and theme behavior."
---

# UI Instruction

## Schichten und Verantwortung
- UI-Dateien rendern und orchestrieren; fachliche Kernrechnungen bleiben in services/.
- Keine duplizierte Berechnungslogik in Widgets oder Plot-Aufbereitung.

## Streamlit-Verhalten
- Session State nur fuer notwendige, klar benannte Schluessel verwenden.
- Filterlogik konsistent halten: Eingaben im Formular, Anwendung erst bei expliziter Aktion.
- Cache-Wrapper nur fuer reine Funktionen mit stabilen Inputs einsetzen.

## Datenanzeige
- Verwende bestehende Formatierungen fuer Euro, Prozent und Labels.
- Zeige fachlich relevante Fehlermeldungen und Warnungen nutzerfreundlich an.

## Visualisierung
- Erhalte bestehende Farb- und Theme-Konstanten aus ui/theme.py.
- Veraendere Diagrammachsen, Legenden und KPI-Beschriftungen nur bei fachlichem Mehrwert.

## Exporte
- CSV-Exporte muessen reproduzierbar sein und die erwarteten Schluesselspalten enthalten.
