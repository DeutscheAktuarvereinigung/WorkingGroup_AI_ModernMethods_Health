# Analyse der Prämienstruktur eines Krankenversicherungsbestands

Dieses Deliverable zeigt, wie sich ein Krankenversicherungsbestand mit
Open-Source-Werkzeugen **explorativ analysieren** und seine Prämienstruktur
anschließend mit **klassischen Regressions- und GLM-Ansätzen** nachbilden
lässt. Der Weg führt bewusst schrittweise von der deskriptiven Betrachtung
über die Identifikation von Produktsegmenten bis zu Modellen, die die
wesentlichen Einflussgrößen auf das Prämienniveau quantifizieren.

Der untersuchte Datensatz hat eine Struktur, die in der
Krankenversicherung häufig auftritt: eine longitudinale Komponente (das
Alter) neben mehreren diskreten Komponenten (Produktlinie, Vertriebsweg,
Vertragsart). Dieselbe Vorgehensweise trägt deshalb auch für
unternehmenseigene Auswertungen, etwa der eingetretenen Schäden. Das
Notebook setzt keine Vorkenntnisse im maschinellen Lernen voraus und
eignet sich damit als niedrigschwelliger Einstieg in die Open-Source-Analytik.

## Aufbau

```
praemienstruktur/
├── README.md                  diese Datei
├── praemienstruktur.Rmd       ausführbarer R-Markdown-Code
├── praemienstruktur.html      dokumentierter HTML-Analysebericht – ohne R-Umgebung lesbar
└── data/
    └── README.md              Bezugsquelle der Eingangsdaten (nicht mitversioniert)
```

Beim ersten Lauf legt das Notebook zusätzlich den Ordner `data_cache/` an
und speichert dort die aufbereitete Tabelle, damit die langsame
Excel-Einlesung nicht bei jedem Lauf wiederholt werden muss. Der Cache ist
ein reines Zwischenergebnis und wird nicht mitversioniert.

## Inhalt des Notebooks

**Deskriptive Analyse.** Beobachtungszeitraum, Produktarten, Erstattungsart
und Ärztenetzwerk, Gruppenversicherung, Geschlechter- und Altersverteilung
sowie Vertriebskanal.

**Analyse der Prämienverteilung.** Gesamtbild und Ausreißer sowie der
Einfluss von Erstattungsart und Vertriebskanal auf das Prämienniveau.

**Detailanalysen nach Produktart.** Getrennte Betrachtung der
internationalen Produkte, der Dentalprodukte sowie der Standard- und
Premiumprodukte. Dabei werden Segmente sichtbar, die im Datensatz gar nicht
explizit ausgewiesen sind.

**Modellierung der Prämien.** Regressionsmodelle je Produktart – für die
internationalen Produkte getrennt nach Erstattungsart –, Splines für den
Alterseffekt sowie GLMs mit Gamma-Verteilung, die die heterogene
Varianzstruktur der Prämien deutlich besser abbilden als lineare Modelle
mit konstanter Varianz.

**Fazit.** Was die Modelle leisten und wo die Grenzen liegen: Fehlen
wichtige Strukturinformationen im Datensatz – konkrete Produktlinien, Höhe
und Anlass von Risikozuschlägen, genaue Leistungsumfänge –, erklären die
Modelle zwangsläufig nur einen Teil der beobachteten Variation. Ausreißer
sind in der Datenaufbereitung zu erkennen und zu begründen.

## Datenbasis

Verwendet wird ein öffentlich verfügbarer, anonymisierter Vertragsbestand
eines spanischen Krankenversicherers mit den Produktlinien Standard,
Premium, International und Dental sowie Angaben zu Alter, Geschlecht,
Vertriebsweg, Vertragsart und Vertragsdauer einschließlich Neugeschäft und
Storno. Der Bestand umfasst rund 225.000 Datensätze zu über 70.000
versicherten Personen aus den Jahren 2017 bis 2019.

Bezugsquelle und Zitierweise stehen in [`data/README.md`](data/README.md);
die Daten selbst sind **nicht** Teil dieses Repositorys. Die im Datensatz
enthaltenen geografischen und sozioökonomischen Zusatzmerkmale werden in
dieser Analyse nicht ausgewertet und im Notebook verworfen.

Vergleichbare öffentlich zugängliche, branchenspezifische Vertragsdaten aus
Deutschland sind der Arbeitsgruppe nicht bekannt. Die verwendeten Methoden
lassen sich jedoch ohne Weiteres auf unternehmenseigene Datensätze
übertragen.

## Ausführen

1. Die Excel-Datei gemäß [`data/README.md`](data/README.md) beziehen und
   als `data/Dataset of health insurance portfolio.xlsx` ablegen.
2. `praemienstruktur.Rmd` in RStudio öffnen und *Knit* ausführen – oder in
   einer R-Konsole:
   `rmarkdown::render("praemienstruktur.Rmd")`.

Benötigt werden R (getestet mit R 4.x) und die Pakete `readxl`, `DT`,
`data.table`, `ggplot2`, `splines` und `knitr`; fehlende Pakete installiert
das Notebook im Setup-Chunk selbst nach. Ergebnis ist ein HTML-Bericht mit
Inhaltsverzeichnis.

Wer die Ergebnisse nur nachlesen möchte, öffnet `praemienstruktur.html` im
Browser – dort ist der komplette Lauf samt allen Grafiken und Tabellen
enthalten.

## Autoren

Jens Piontkowski, Stefan Nohl (Arbeitsgruppe „Künstliche Intelligenz und
moderne Methoden in der Krankenversicherung")

## Bezug zum Ergebnisbericht

Dieser Anwendungsfall wird in Abschnitt 5.5 des Ergebnisberichts
„Künstliche Intelligenz und moderne Methoden in der Krankenversicherung"
beschrieben.
