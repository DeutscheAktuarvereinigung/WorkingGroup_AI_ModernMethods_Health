# PKV-Limitierungstool

Streamlit-Anwendung zur Bestandsanalyse und Limitierungsrechnung.

## Voraussetzungen

- Python 3.11
- Optional: Docker

## Lokal starten

1. Virtuelle Umgebung erstellen und aktivieren (optional, empfohlen)
2. Abhaengigkeiten installieren
3. App starten

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Die Anwendung ist danach unter http://localhost:8501 erreichbar.

## Start per Docker

```powershell
docker build -t limitierungs-tool .
docker run --rm -p 8501:8501 limitierungs-tool
```

Danach ist die App unter http://localhost:8501 erreichbar.

## Deployment-Hinweise (kurz)

- Fuer interne Nutzung ist ein Deployment als Container (z. B. Azure App Service oder interne VM mit Docker) sinnvoll.
- Zugriff sollte ueber internes Netz oder SSO abgesichert werden.
- Fuer Endnutzer ist CSV-Upload der einfachste Datenfluss.

## Projektstruktur (Auszug)

- app.py: Streamlit-Einstiegspunkt
- app/pages/: Seitenlogik
- services/: Fachlogik und Datenverarbeitung
- output_daten/: lokale Beispiel-/Mock-Daten
