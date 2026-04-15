import numpy as np
import pandas as pd


def erzeuge_altersgruppen(df: pd.DataFrame, schritt: int = 10):
    alter_min = int(np.floor(df["alter"].min() / schritt) * schritt)
    alter_max = int(np.ceil((df["alter"].max() + 1) / schritt) * schritt)
    grenzen = list(range(alter_min, alter_max + schritt, schritt))
    labels = [f"{i}-{i + schritt - 1}" for i in range(alter_min, alter_max, schritt)]
    return grenzen, labels


def lade_csv(datei, name: str) -> pd.DataFrame:
    df = pd.read_csv(datei, sep=";", low_memory=False)
    if name == "bestand":
        erwartete = [
            "versicherten_id", "alter", "geschlecht", "tarifwerk", "tarif_id",
            "tarifart", "praemie_alt_monatlich", "praemie_neu_monatlich",
            "erhoehung_absolut", "erhoehung_prozent", "alterungsrueckstellung",
            "versicherungsdauer_jahre",
        ]
        fehlende = [s for s in erwartete if s not in df.columns]
        if fehlende:
            raise ValueError(f"Fehlende Spalten: {fehlende}")
        grenzen, labels = erzeuge_altersgruppen(df)
        df["altersgruppe"] = pd.cut(
            df["alter"], bins=grenzen,
            right=False, labels=labels,
        ).astype(str)
    return df
