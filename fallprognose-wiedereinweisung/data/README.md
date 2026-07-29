# Eingangsdaten (nicht mitversioniert)

Die Eingangsdaten sind **nicht** Teil dieses Repositorys. Sie sind frei
verfügbar und werden bei Bedarf selbst bezogen.

## Benötigte Dateien

| Datei | Inhalt | Bezugsquelle |
|---|---|---|
| `diabetic_data.csv` | Hauptdatensatz: rund 101.766 Krankenhausfälle mit 47 Merkmalen | Kaggle-Datensatz [`sarika77/diabetic-data`](https://www.kaggle.com/datasets/sarika77/diabetic-data) |
| `id_mapping.csv` | Klartext-Bedeutung der Schlüssel `admission_type_id`, `discharge_disposition_id` und `admission_source_id` | Kaggle-Datensatz [`mhermanns/id-mappings-for-diabetes-dataset`](https://www.kaggle.com/datasets/mhermanns/id-mappings-for-diabetes-dataset) |

Beide Kaggle-Datensätze sind Spiegelungen des Originaldatensatzes
**„Diabetes 130-US Hospitals for Years 1999-2008"** aus dem UCI Machine
Learning Repository, abrufbar unter <https://doi.org/10.24432/C5230J>
(Clore, J., Cios, K., DeShazo, J., Strack, B., 2014).

Der Datensatz wurde zusammen mit folgendem Artikel veröffentlicht:

> Strack, B. et al. (2014): *Impact of HbA1c Measurement on Hospital
> Readmission Rates: Analysis of 70,000 Clinical Database Patient Records*,
> BioMed Research International, Band 2014, Artikel-ID 781670,
> <https://doi.org/10.1155/2014/781670>

## Einbinden

- **Auf Kaggle** (empfohlen): beide Datensätze im Notebook über *Add Input*
  einbinden. Die im Notebook hinterlegten Pfade passen dann ohne Änderung.
- **Lokal**: Die beiden CSV-Dateien so ablegen, dass die im Notebook
  verwendeten Pfade aufgehen, oder die Pfade in den Ladezellen anpassen.
  Das Notebook selbst wird bewusst unverändert bereitgestellt.

Bitte die Nutzungsbedingungen der jeweiligen Quelle beachten.
