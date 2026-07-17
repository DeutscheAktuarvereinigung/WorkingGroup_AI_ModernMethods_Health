# -*- coding: utf-8 -*-
"""Erzeugt die SQLite-Referenzdatenbank der Rechnungsgrundlagen
(Sterbewahrscheinlichkeiten, Stornowahrscheinlichkeiten, Kopfschäden)
aus den Pipeline-CSVs. Die Datenbank dient dem Validierungs-Notebook
als dokumentexterne Referenz (Check V-13)."""
import csv
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASIS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
DB = os.path.join(BASIS, "rechnungsgrundlagen.db")

if os.path.exists(DB):
    os.remove(DB)
verbindung = sqlite3.connect(DB)
verbindung.execute("""
    CREATE TABLE rechnungsgrundlagen (
        geschlecht  TEXT    NOT NULL,   -- 'M' oder 'F'
        x           INTEGER NOT NULL,   -- versicherungstechnisches Alter
        qx          REAL    NOT NULL,   -- Sterbewahrscheinlichkeit q_x
        wx          REAL    NOT NULL,   -- Stornowahrscheinlichkeit w_x
        kopfschaden REAL    NOT NULL,   -- rechnungsmäßiger Kopfschaden K_x (EUR p.a.)
        PRIMARY KEY (geschlecht, x)
    )
""")

n = 0
for geschlecht in ("M", "F"):
    pfad = os.path.join(BASIS, f"rechnungsgrundlagen_{geschlecht}.csv")
    with open(pfad, encoding="utf-8") as f:
        for zeile in csv.DictReader(f, delimiter=";"):
            verbindung.execute(
                "INSERT INTO rechnungsgrundlagen VALUES (?, ?, ?, ?, ?)",
                (geschlecht, int(zeile["x"]), float(zeile["q_x"]),
                 float(zeile["w_x"]), float(zeile["K_x"])))
            n += 1
verbindung.commit()

for g, anzahl in verbindung.execute(
        "SELECT geschlecht, COUNT(*) FROM rechnungsgrundlagen GROUP BY geschlecht"):
    print(f"  {g}: {anzahl} Zeilen")
probe = verbindung.execute(
    "SELECT qx, wx, kopfschaden FROM rechnungsgrundlagen "
    "WHERE geschlecht='M' AND x=50").fetchone()
print(f"  Probe M/50: q={probe[0]}, w={probe[1]}, K={probe[2]}")
verbindung.close()
print(f"Datenbank geschrieben: {DB} ({n} Zeilen)")
