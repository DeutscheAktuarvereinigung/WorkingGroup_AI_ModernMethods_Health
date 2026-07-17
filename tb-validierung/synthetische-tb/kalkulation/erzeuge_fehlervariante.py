# -*- coding: utf-8 -*-
"""
Erzeugt die fehlerhafte Zweitvariante der TB (tex_fehlerhaft/) mit 13
dokumentierten, absichtlichen Fehlern als Pruefobjekt fuer das
Validierungs-Notebook (Phase 3). Jeder Fehler wird nach dem Einbau
verifiziert (assert), damit das Fehlerprotokoll garantiert stimmt.
"""
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASIS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
QUELLE = os.path.join(BASIS, "tex")
ZIEL = os.path.join(BASIS, "tex_fehlerhaft")

# Zielverzeichnis leeren (Datei fuer Datei; rmtree scheitert unter
# Google-Drive-Sync an gesperrten Ordnern) und Quellen frisch kopieren
os.makedirs(os.path.join(ZIEL, "gen"), exist_ok=True)
for wurzel, _, dateien in os.walk(ZIEL):
    for name in dateien:
        try:
            os.remove(os.path.join(wurzel, name))
        except OSError:
            pass
for name in os.listdir(QUELLE):
    if name.endswith(".tex") or name.endswith(".png"):
        shutil.copy(os.path.join(QUELLE, name), ZIEL)
for name in os.listdir(os.path.join(QUELLE, "gen")):
    shutil.copy(os.path.join(QUELLE, "gen", name), os.path.join(ZIEL, "gen"))


def ersetze(datei, alt, neu, fehler_nr):
    p = os.path.join(ZIEL, datei)
    with open(p, encoding="utf-8") as f:
        t = f.read()
    assert alt in t, f"Fehler {fehler_nr}: Muster nicht gefunden in {datei}: {alt[:60]}"
    assert t.count(alt) == 1 or fehler_nr in (5,), \
        f"Fehler {fehler_nr}: Muster nicht eindeutig in {datei}"
    t = t.replace(alt, neu, 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(t)
    print(f"F{fehler_nr:02d} eingebaut in {datei}")


# --- F01: Rechenfehler in der Beitragstabelle (Anhang 3): b_50 Maenner
#     635,33 -> 653,33 (Zahlendreher)
ersetze(os.path.join("gen", "gen_anhang_3.tex"),
        "50 & 5855,92 & 635,33 & 5997,90 & 662,02 \\\\",
        "50 & 5855,92 & 653,33 & 5997,90 & 662,02 \\\\", 1)

# --- F02: KVAV-Verstoss + Widerspruch: Sicherheitszuschlag in Anlage 2.4.1
#     als 4,5 % ausgewiesen (Abschnitt 2.4.1 nennt weiterhin 5,0 %;
#     § 7 KVAV verlangt mindestens 5 %)
ersetze("anlagen.tex",
        "Sicherheitszuschlag $\\sigma$ & \\SigmaZ\\,\\% & \\SigmaZ\\,\\% & \\SigmaZ\\,\\% & \\SigmaZ\\,\\% \\\\",
        "Sicherheitszuschlag $\\sigma$ & 4{,}5\\,\\% & 4{,}5\\,\\% & 4{,}5\\,\\% & 4{,}5\\,\\% \\\\", 2)

# --- F03: Falsches Gesetz: § 4 KVAV -> § 4 VAG (Hoechstrechnungszins)
ersetze("abschnitt_2.tex",
        "überschreitet den Höchstrechnungszins von 3{,}5\\,\\% gemäß \\S\\,4 KVAV",
        "überschreitet den Höchstrechnungszins von 3{,}5\\,\\% gemäß \\S\\,4 VAG", 3)

# --- F04: Toter interner Verweis: Anlage 5.2 -> nicht existierendes Label
ersetze("abschnitt_5.tex",
        "verwendet (Anlage~\\ref{sec:anlage521}); die",
        "verwendet (Anlage~5.2, Abschnitt~\\ref{sec:anlage523}); die", 4)

# --- F05: Rechtschreibfehler (3 Stueck)
ersetze("abschnitt_5.tex",
        "Die Alterungsrückstellung wird prospektiv",
        "Die Alterungsrückstelung wird prospektiv", 5)
ersetze("abschnitt_3.tex",
        "Äquivalenzprinzip (Barwert der Leistungen = Barwert der Beiträge)",
        "Äquivalenzprinizip (Barwert der Leistungen = Barwert der Beiträge)", 5)
ersetze("abschnitt_1.tex",
        "\\textbf{Versicherungsform:} Krankheitskostenvollversicherung",
        "\\textbf{Versicherungsform:} Krankheitskostenvollversichrung", 5)

# --- F06: Fehlender Glossareintrag: DQ_x aus dem Symbolverzeichnis entfernt
ersetze("symbolverzeichnis.tex",
        "$DQ_x$ & diskontierte Übergangswahrscheinlichkeit, $DQ_x = v\\cdot(1-(q+w)_x)$ \\\\\n",
        "", 6)

# --- F07: Widerspruch Abschnitt/Anlage: Grundkopfschaden Maenner in
#     Anlage 2.3.3 als 1910,0070 statt 1901,0070
ersetze("anlagen.tex",
        "$K_x = k_x\\cdot G$ mit\n$G^{M} = \\GMann$~EUR",
        "$K_x = k_x\\cdot G$ mit\n$G^{M} = 1910{,}0070$~EUR", 7)

# --- F08: Tafelfehler: (q+w)_50 der Maenner-Ausscheideordnung inkonsistent
#     (q_50=0,001271, w_50=0,035 -> korrekt 0,036271; eingebaut: 0,037271)
ersetze(os.path.join("gen", "gen_anlage_2_2_1_M.tex"),
        "50 & 0,001271 & 0,035000 & 0,036271 & 0,938392 \\\\",
        "50 & 0,001271 & 0,035000 & 0,037271 & 0,938392 \\\\", 8)

# --- F09: Zins-Label-Fehler: Anlage 2.1 weist fuer Frauen 2,2 % aus
#     (gerechnet wurde durchgehend mit 2,0 %)
ersetze("anlagen.tex",
        "$\\ZinsK\\,\\%$ & $\\ZinsM\\,\\%$ & $\\ZinsF\\,\\%$ \\\\",
        "$\\ZinsK\\,\\%$ & $\\ZinsM\\,\\%$ & $2{,}2\\,\\%$ \\\\", 9)

# --- F10: IHV-Fehler: Eintrag der Anlage 3.1 im Inhaltsverzeichnis weicht
#     von der Ueberschrift im Dokument ab (optionales Kurztitel-Argument)
ersetze("anlagen.tex",
        "\\subsection{Versicherungstechnische Grundwerte}\\label{sec:anlage311}",
        "\\subsection[Grundwerte der Versicherungstechnik]{Versicherungstechnische Grundwerte}\\label{sec:anlage311}", 10)

# --- F11: Rechenfehler in der Beispielrechnung: P_43 = 4676,48 statt 4667,48
ersetze("anhang.tex",
        "= \\frac{\\GMann\\cdot\\BspAx}{\\Bspax} = \\BspPx\\ \\text{EUR p.\\,a.}",
        "= \\frac{\\GMann\\cdot\\BspAx}{\\Bspax} = 4676{,}48\\ \\text{EUR p.\\,a.}", 11)

# --- F12: Formelfehler: Vorzeichen von gamma_x in der AR-Formel gedreht
#     (Gl. eq:ar: ... - gamma_x -> ... + gamma_x); die Zahlenwerte in
#     Anhang 5 folgen weiterhin der korrekten Formel
ersetze("abschnitt_5.tex",
        "V_x(b) = G\\cdot A_x\n- \\bigl[\\,12\\cdot\\bigl(1-(\\sigma+\\Omega_x)\\bigr)\\cdot b - \\gamma_x\\,\\bigr]\n\\cdot a_x,",
        "V_x(b) = G\\cdot A_x\n- \\bigl[\\,12\\cdot\\bigl(1-(\\sigma+\\Omega_x)\\bigr)\\cdot b + \\gamma_x\\,\\bigr]\n\\cdot a_x,", 12)

# --- F13: Grafikfehler: Frauen-Profilkurve im k_x-Plot um Faktor 1,5
#     ueberhoeht; die Tabellenwerte k_x in Anlage 2.3.3 bleiben korrekt,
#     sodass Grafik und Tabelle einander widersprechen
import re as _re
_plot = os.path.join(ZIEL, "gen", "gen_plot_kx.tex")
with open(_plot, encoding="utf-8") as f:
    _t = f.read()
_bloecke = _t.split("\\" + "addplot+")
assert len(_bloecke) == 3, "F13: Plotstruktur unerwartet"
_frauen_neu = _re.sub(r"\((\d+),([0-9.]+)\)",
                      lambda m: f"({m.group(1)},{float(m.group(2)) * 1.5:.4f})",
                      _bloecke[2])
assert _frauen_neu != _bloecke[2], "F13: keine Koordinaten skaliert"
with open(_plot, "w", encoding="utf-8") as f:
    f.write(_bloecke[0] + "\\" + "addplot+" + _bloecke[1] + "\\" + "addplot+" + _frauen_neu)
with open(_plot, encoding="utf-8") as f:
    assert "(40,1.5000)" in f.read(), "F13: Skalierung nicht wirksam"
print("F13 eingebaut in gen/gen_plot_kx.tex")

# Titelseite kennzeichnen (interne Kennung, unauffaellig: Aenderungsnr. bleibt)
ersetze("titelseite.tex",
        "{\\normalsize Bitte vertraulich behandeln / Geschäftsgeheimnis}",
        "{\\normalsize Bitte vertraulich behandeln / Geschäftsgeheimnis}\\\\[0.2cm]\n{\\tiny Exemplar V-17b}", 0)

print("Alle Fehler eingebaut.")
