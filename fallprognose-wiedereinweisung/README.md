# Fallprognose: Wiedereinweisung ins Krankenhaus

Dieses Deliverable zeigt an einem durchgängigen Beispiel, wie sich eine
**Ereignisprognose** mit Methoden des maschinellen Lernens methodisch sauber
aufbauen, bewerten und interpretieren lässt. Prognostiziert wird die
Wahrscheinlichkeit, dass ein Krankenhausfall innerhalb kurzer Zeit zu einer
**Wiedereinweisung** führt – auf Basis von Einzeldiagnosen und zahlreichen
weiteren Merkmalen.

Die gezeigte Vorgehensweise ist nicht auf diese Fragestellung beschränkt:
Dieselbe Struktur trägt für jede binäre Klassifikation im aktuariellen
Umfeld, etwa für eine Stornoprognose oder eine Betrugserkennung. Das
Notebook lässt sich in die eigene Entwicklungsumgebung kopieren und auf
eigene Datensätze anpassen.

## Aufbau

```
fallprognose-wiedereinweisung/
├── README.md                    diese Datei
├── hospital-readmission.ipynb   ausführbares Jupyter-Notebook (188 Zellen, mit Ergebnissen)
├── hospital-readmission.html    dokumentierter HTML-Analysebericht – ohne Python-Umgebung lesbar
└── data/
    └── README.md                Bezugsquellen der Eingangsdaten (nicht mitversioniert)
```

## Inhalt des Notebooks

Das Notebook ist in drei Teile gegliedert, die vom schnellen Ergebnis zur
vertieften Modellierung führen. Es ist – wie sein Ursprungsnotebook (siehe
unten) – in englischer Sprache verfasst.

**Teil A – Quick & Easy.** Aufbau eines Basismodells mit CatBoost, das ohne
aufwendige Datenaufbereitung auskommt: Datensichtung, Fallauswahl, Bildung
von Diagnosegruppen, Zieldefinition, Behandlung kategorialer Merkmale,
Aufteilung in Trainings-, Validierungs- und Testmenge, Training des
Referenzmodells.

**Teil B – Erkenntnisse aus Daten und Modell.** Interpretierbarkeit der
logistischen Regression und modellagnostische Erklärung beliebiger Modelle
mit SHAP; Hyperparameter-Optimierung für CatBoost; Encoding und Skalierung
und deren Wirkung auf das Referenzmodell; neuronale Netze in PyTorch;
explorative Datenanalyse und Feature Engineering.

**Teil C – Modelle abstimmen und anwenden.** Logistische Regression als
klassischer Zugang, regularisierte logistische Regression gegen Overfitting,
automatisiertes maschinelles Lernen mit AutoGluon, abschließende
Modellbewertung auf Validierungs- und Testmenge sowie die Anwendung auf die
Identifikation von Hochrisikofällen. Ein Anhang ergänzt weiterführende
Hinweise zu CatBoost und zur Ausführung auf einer GPU.

Die methodischen Grundlagen der verwendeten Verfahren – Entscheidungsbäume
und Gradient Boosting, logistische Regression und Regularisierung,
neuronale Netze, AutoML-Werkzeuge und Erklärbarkeit – sind in Anhang A des
Ergebnisberichts der Arbeitsgruppe zusammengefasst.

## Datenbasis

Verwendet wird der öffentlich verfügbare Datensatz **„Diabetes 130-US
Hospitals for Years 1999-2008"** aus dem UCI Machine Learning Repository:
rund 101.766 US-amerikanische Krankenhausfälle mit 47 Merkmalen, darunter
drei ICD-Diagnosen sowie die Angabe, ob eine Wiedereinweisung innerhalb
kurzer Zeit, zu einem späteren Zeitpunkt oder gar nicht erfolgte. Fälle mit
einem Entlassungsgrund, der auf Tod oder Hospizversorgung hinweist, werden
im Notebook ausgeschlossen.

Der Datensatz wurde zusammen mit dem Artikel von Strack et al. (2014)
veröffentlicht. Quellen und Bezugswege stehen in
[`data/README.md`](data/README.md); die Daten selbst sind **nicht** Teil
dieses Repositorys.

Vergleichbare öffentlich zugängliche, branchenspezifische Datensätze aus
Deutschland sind der Arbeitsgruppe nicht bekannt – der Datensatz dient
deshalb als Ersatzgrundlage für eine realitätsnahe Demonstration.

## Ausführen

Das Notebook ist für die Ausführung auf **Kaggle** geschrieben und liest die
Eingangsdaten über Kaggle-Pfade (`/kaggle/input/…` bzw. `../input/…`). Der
bequemste Weg ist daher:

1. Notebook auf Kaggle hochladen (*Create → New Notebook → File → Import
   Notebook*).
2. Über *Add Input* die beiden in [`data/README.md`](data/README.md)
   genannten Datensätze einbinden.
3. *Run All*. Ohne GPU dauert ein vollständiger Lauf spürbar länger;
   Abschnitt A2 im Anhang des Notebooks beschreibt die GPU-Nutzung.

**Lokale Ausführung** ist ebenso möglich, erfordert aber zwei Eingriffe:
die beiden CSV-Dateien müssen unter den im Notebook hinterlegten Pfaden
liegen (oder die Pfade in den Ladezellen angepasst werden), und die
Bibliotheken sind selbst zu installieren – im Wesentlichen `pandas`,
`numpy`, `scipy`, `scikit-learn`, `statsmodels`, `matplotlib`, `seaborn`,
`catboost`, `shap`, `autogluon`, `torch`, `tensorflow` und
`tab_transformer_pytorch`. Getestet wurde mit Python 3.12.

Wer die Ergebnisse nur nachlesen möchte, öffnet
`hospital-readmission.html` im Browser – dort ist der komplette Lauf samt
allen Ausgaben und Grafiken enthalten.

## Herkunft

Das Notebook ist eine Adaption des Kaggle-Notebooks
[„Binary Classification Use Case: Credit
Scoring"](https://www.kaggle.com/code/floser/binary-classification-credit-scoring),
das als ADS Use Case auch auf dem
[GitHub-Account der DAV](https://github.com/DeutscheAktuarvereinigung/ADS_Use_Cases)
verfügbar ist. Es überträgt dieselbe Notebook-Struktur auf einen deutlich
anderen Anwendungsfall und enthält die dafür nötigen Code-Anpassungen
(Stand: Januar 2026).

Das Notebook wurde mit Unterstützung eines großen Sprachmodells erstellt.
Das zeigt, wie effizient sich mit Werkzeugen wie CatBoost und AutoGluon
inzwischen auch ohne umfangreiche Programmierkenntnisse belastbare
Ereignisprognosen aufbauen lassen. Die fachliche Bewertung der Ergebnisse
bleibt davon unberührt und ist Aufgabe der Aktuarin bzw. des Aktuars.

## Autor

Friedrich Loser (Arbeitsgruppe „Künstliche Intelligenz und moderne Methoden
in der Krankenversicherung")

## Bezug zum Ergebnisbericht

Dieser Anwendungsfall wird in Abschnitt 5.4 des Ergebnisberichts
„Künstliche Intelligenz und moderne Methoden in der Krankenversicherung"
beschrieben.
