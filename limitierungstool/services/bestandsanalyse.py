import hashlib

import numpy as np
import pandas as pd


def geschlecht_label(code):
    mapping = {"M": "Männlich", "W": "Weiblich", "D": "Divers"}
    return mapping.get(code, code)


def farb_map_dynamisch(df: pd.DataFrame, spalte: str, palette):
    kategorien = sorted(df[spalte].unique())
    return {k: palette[i % len(palette)] for i, k in enumerate(kategorien)}


def formatiere_euro(wert):
    if abs(wert) >= 1_000_000:
        return f"{wert / 1_000_000:,.1f} Mio. €"
    if abs(wert) >= 1_000:
        return f"{wert:,.0f} €"
    return f"{wert:.2f} €"


def df_hash(df: pd.DataFrame):
    n = len(df)
    if n == 0:
        return "empty"
    key = f"{n}_{list(df.columns)}"
    key += f"_{df.iloc[0].values.tobytes().hex()[:32]}"
    key += f"_{df.iloc[-1].values.tobytes().hex()[:32]}"
    key += f"_{df.iloc[n // 2].values.tobytes().hex()[:32]}"
    return hashlib.md5(key.encode()).hexdigest()


def berechne_kpis(df: pd.DataFrame):
    return {
        "n": len(df),
        "praemie_alt_mean": df["praemie_alt_monatlich"].mean(),
        "praemie_neu_mean": df["praemie_neu_monatlich"].mean(),
        "erh_pct_mean": df["erhoehung_prozent"].mean(),
        "erh_pct_median": df["erhoehung_prozent"].median(),
        "erh_abs_mean": df["erhoehung_absolut"].mean(),
        "erh_abs_median": df["erhoehung_absolut"].median(),
        "jahres_vol": (df["erhoehung_absolut"] * 12).sum(),
    }


def berechne_treemap_daten(df: pd.DataFrame, farb_spalte: str):
    s4 = (df.groupby(["tarifwerk", "tarifart", "geschlecht", "altersgruppe"], observed=True)
          .agg(anzahl=("versicherten_id", "count"), erh=(farb_spalte, "mean"))
          .reset_index())
    s4["id"] = s4["tarifwerk"] + "/" + s4["tarifart"] + "/" + s4["geschlecht"] + "/" + s4["altersgruppe"]
    s4["parent"] = s4["tarifwerk"] + "/" + s4["tarifart"] + "/" + s4["geschlecht"]
    s4["label"] = s4["altersgruppe"]

    s3 = (df.groupby(["tarifwerk", "tarifart", "geschlecht"], observed=True)
          .agg(anzahl=("versicherten_id", "count"), erh=(farb_spalte, "mean"))
          .reset_index())
    s3["id"] = s3["tarifwerk"] + "/" + s3["tarifart"] + "/" + s3["geschlecht"]
    s3["parent"] = s3["tarifwerk"] + "/" + s3["tarifart"]
    s3["label"] = s3["geschlecht"].map(geschlecht_label)

    s2 = (df.groupby(["tarifwerk", "tarifart"], observed=True)
          .agg(anzahl=("versicherten_id", "count"), erh=(farb_spalte, "mean"))
          .reset_index())
    s2["id"] = s2["tarifwerk"] + "/" + s2["tarifart"]
    s2["parent"] = s2["tarifwerk"]
    s2["label"] = s2["tarifart"].str.capitalize()

    s1 = (df.groupby("tarifwerk", observed=True)
          .agg(anzahl=("versicherten_id", "count"), erh=(farb_spalte, "mean"))
          .reset_index())
    s1["id"] = s1["tarifwerk"]
    s1["parent"] = ""
    s1["label"] = s1["tarifwerk"]

    spalten = ["id", "parent", "label", "anzahl", "erh"]
    return pd.concat([s1[spalten], s2[spalten], s3[spalten], s4[spalten]], ignore_index=True)


def berechne_interaktive_statistik(df: pd.DataFrame, gruppen_spalten_tuple):
    gruppen_spalten = list(gruppen_spalten_tuple)

    if not gruppen_spalten:
        row = {
            "Versicherte": len(df),
            "Ø Prämie alt (€)": round(df["praemie_alt_monatlich"].mean(), 0),
            "Ø Prämie neu (€)": round(df["praemie_neu_monatlich"].mean(), 0),
            "Ø Erhöhung (%)": round(df["erhoehung_prozent"].mean(), 1),
            "Median Erhöhung (%)": round(df["erhoehung_prozent"].median(), 1),
            "Ø Erhöhung (€)": round(df["erhoehung_absolut"].mean(), 0),
            "Median Erhöhung (€)": round(df["erhoehung_absolut"].median(), 0),
            "P95 Erhöhung (%)": round(df["erhoehung_prozent"].quantile(0.95), 1),
            "P95 Erhöhung (€)": round(df["erhoehung_absolut"].quantile(0.95), 0),
            "Ø Alter.-Rückst. (€)": round(df["alterungsrueckstellung"].mean(), 0),
            "Volumen p.a. (€)": round((df["erhoehung_absolut"] * 12).sum(), 0),
        }
        return pd.DataFrame([row])

    agg = df.groupby(gruppen_spalten, observed=True).agg(
        Versicherte=("versicherten_id", "count"),
        praemie_alt_mean=("praemie_alt_monatlich", "mean"),
        praemie_neu_mean=("praemie_neu_monatlich", "mean"),
        erh_pct_mean=("erhoehung_prozent", "mean"),
        erh_pct_median=("erhoehung_prozent", "median"),
        erh_abs_mean=("erhoehung_absolut", "mean"),
        erh_abs_median=("erhoehung_absolut", "median"),
        erh_pct_p95=("erhoehung_prozent", lambda x: x.quantile(0.95)),
        erh_abs_p95=("erhoehung_absolut", lambda x: x.quantile(0.95)),
        ar_mean=("alterungsrueckstellung", "mean"),
        erh_abs_sum=("erhoehung_absolut", "sum"),
    ).reset_index()

    agg = agg.rename(columns={
        "praemie_alt_mean": "Ø Prämie alt (€)",
        "praemie_neu_mean": "Ø Prämie neu (€)",
        "erh_pct_mean": "Ø Erhöhung (%)",
        "erh_pct_median": "Median Erhöhung (%)",
        "erh_abs_mean": "Ø Erhöhung (€)",
        "erh_abs_median": "Median Erhöhung (€)",
        "erh_pct_p95": "P95 Erhöhung (%)",
        "erh_abs_p95": "P95 Erhöhung (€)",
        "ar_mean": "Ø Alter.-Rückst. (€)",
        "erh_abs_sum": "erh_abs_sum_raw",
    })

    agg["Volumen p.a. (€)"] = (agg["erh_abs_sum_raw"] * 12).round(0)
    agg = agg.drop(columns=["erh_abs_sum_raw"])

    for col in agg.columns:
        if agg[col].dtype in [np.float64, np.float32]:
            if "(%)" in col:
                agg[col] = agg[col].round(1)
            else:
                agg[col] = agg[col].round(0)

    rename_map = {
        "tarifwerk": "Tarifwerk", "tarifart": "Tarifart", "tarif_id": "Tarif",
        "geschlecht": "Geschlecht", "altersgruppe": "Altersgruppe",
    }
    agg = agg.rename(columns={k: v for k, v in rename_map.items() if k in agg.columns})

    return agg.sort_values("Versicherte", ascending=False).reset_index(drop=True)


def berechne_hist_daten(df: pd.DataFrame, farb_spalte: str, wert_spalte: str):
    if farb_spalte and farb_spalte in df.columns:
        return {kat: df.loc[df[farb_spalte] == kat, wert_spalte].values
                for kat in sorted(df[farb_spalte].unique())}
    return {"_gesamt": df[wert_spalte].values}
