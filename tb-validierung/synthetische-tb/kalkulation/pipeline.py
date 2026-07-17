# -*- coding: utf-8 -*-
"""
Kalkulationspipeline Tarif VitalPlus (synthetische TB, Phase 2).

Erzeugt aus den BaFin-Rohdaten (Kopfschadenstatistik 2022, PKV-Sterbetafel 2025,
Stornotafel) alle Rechnungsgrundlagen, Barwerte, Beitraege und AR-Verlaeufe
sowie die LaTeX-Anlagen (tex/gen/*.tex) und CSV-Kontrollausgaben (out/*.csv).

Rundungskonventionen (Abschnitt 1.4 der TB):
  k_x: 4 NK | G: 4 NK | q_x, w_x, DQ_x: 6 NK | A_x, a_x: 4 NK (stufenweise,
  d.h. die Rekursion verwendet die bereits gerundeten Vorwerte) | gamma: 2 NK |
  Beitraege: kaufmaennisch auf 0,01 EUR.
"""
import csv
import os
from decimal import Decimal, ROUND_HALF_UP

# Alle Pfade relativ zu dieser Skriptdatei. Die BaFin-Rohdaten liegen
# NICHT im Repository (siehe README, Abschnitt "Datenherkunft"); sie
# werden im lokalen, unversionierten Ordner rohdaten/ erwartet.
BASIS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATEN = os.path.join(BASIS, "rohdaten")
ZIEL = BASIS
GEN = os.path.join(ZIEL, "tex", "gen")
OUT = os.path.join(ZIEL, "kalkulation", "out")
os.makedirs(GEN, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- Parameter
OMEGA = 110          # Schlussalter
X_ERW = 21           # Beginn Erwachsene
ZINS = {"M": 0.027, "F": 0.020, "K": 0.023}          # Rechnungszins je BE
SIGMA = 0.05                                          # Sicherheitszuschlag
OMEGA_Z = {"u65": 0.007, "o65": 0.006}                # Zuschlag Standard-/Basistarif
DELTA = {"u65": 0.140, "o65": 0.120}                  # Summe prozentuale Kostensaetze
KOSTEN = {"alpha_u": 0.020, "alpha_m": 0.050, "rho": 0.044, "beta": 0.026}
GAMMA_EUBR = {"M": 350.0, "F": 380.0, "K": 80.0}      # euBR-Zuschlag (Annahme)
GAMMA_ALTER = {"M": 42, "F": 44}                      # Gamma-Alter (Annahme)
ZILLMER_VOLL = 3.5                                    # Monatsbeitraege, Alter 21..75
TAFELN_G = ["01_KKV_amb_N_{g}_0-100", "02_KKV_stat_N_{g}_MB",
            "03_KKV_zahn_N_{g}_Beh", "03_KKV_zahn_N_{g}_Ers_70-80"]
LB_NAMEN = ["ambulant", "stationaer", "zahnbeh", "zahners"]

def rnd(wert, stellen):
    """Kaufmaennische Rundung (ROUND_HALF_UP)."""
    q = Decimal(1).scaleb(-stellen)
    return float(Decimal(repr(wert)).quantize(q, rounding=ROUND_HALF_UP))

def dez(s):
    s = s.strip()
    if not s or s == "NA":
        # 'NA' tritt nur in den S-Kosten-Tafeln ausserhalb der fertilen Alter
        # auf (keine Schwangerschafts-/Mutterschaftsleistungen) -> 0
        return None
    if "." in s and "," in s:
        s = s.replace(".", "")
    return float(s.replace(",", "."))

# ---------------------------------------------------------------- 1. Rohdaten
def lade_profile():
    p = os.path.join(DATEN, "Kopfschäden", "PKV_Kopfschadenstatistik_2022_Profile.csv")
    tafeln = {}
    with open(p, encoding="latin-1") as f:
        for r in csv.reader(f, delimiter=";"):
            if r and r[0].isdigit():
                alter, tafel = int(r[0]), r[1]
                tafeln.setdefault(tafel, {})[alter] = {
                    "bestand": dez(r[2]), "kopfschaden": dez(r[5])}
    return tafeln

def lade_sterbetafel():
    p = os.path.join(DATEN, "Sterbewahrscheinlichkeiten", "PKV_Sterbetafel_2025.csv")
    q = {"M": {}, "F": {}}
    with open(p, encoding="utf-8-sig") as f:
        for r in csv.reader(f, delimiter=";"):
            if r and r[0].strip().isdigit():
                q["M"][int(r[0])] = dez(r[1])
                q["F"][int(r[0])] = dez(r[2])
    return q

def lade_storno():
    p = os.path.join(DATEN, "Stornowahrscheinlichkeiten", "storno2.csv")
    w = {}
    with open(p, encoding="utf-8-sig") as f:
        for r in csv.reader(f, delimiter=";"):
            if r and r[0].strip().isdigit():
                w[int(r[0])] = dez(r[1])
    return w

profile = lade_profile()
q_roh = lade_sterbetafel()
w_roh = lade_storno()

# ------------------------------------------------ 2. Kopfschaeden inkl. S-Umlage
# Je Leistungsbereich: K^M, K^W (inkl. S-Kosten), K^S (S-Kosten je Frau),
# Bestaende n^M, n^W. Umlage je Alter x (AGG, geschlechtsunabhaengig):
#   u_x = n^W_x * K^S_x / (n^M_x + n^W_x)
#   K^M,r = K^M + u_x ;  K^W,r = K^W - K^S + u_x
teil = {"M": {}, "F": {}}          # teil[geschlecht][lb][alter]
umlage = {}                        # umlage[lb][alter]
s_kosten = {}                      # s_kosten[lb][alter]
for lb_i, muster in enumerate(TAFELN_G):
    lb = LB_NAMEN[lb_i]
    tm, tw = profile[muster.format(g="M")], profile[muster.format(g="W")]
    ts = profile[muster.format(g="S")]
    umlage[lb], s_kosten[lb] = {}, {}
    for g, t in (("M", tm), ("F", tw)):
        teil[g].setdefault(lb, {})
    for x in range(0, 101):
        nm, nw = tm[x]["bestand"] or 0.0, tw[x]["bestand"] or 0.0
        ks = ts[x]["kopfschaden"] or 0.0
        u = nw * ks / (nm + nw) if (nm + nw) > 0 else 0.0
        umlage[lb][x] = u
        s_kosten[lb][x] = ks
        teil["M"][lb][x] = (tm[x]["kopfschaden"] or 0.0) + u
        teil["F"][lb][x] = (tw[x]["kopfschaden"] or 0.0) - ks + u

# Gesamt-Kopfschaden je BE (Alter 0..100), dann Fortschreibung bis 110.
# Rundungskaskade: K_beob wird auf 4 NK gerundet; Profile und G folgen aus
# den GERUNDETEN Werten, damit alle Tabellenwerte der TB aus den
# abgedruckten Werten exakt reproduzierbar sind (Abschnitt 0.3 der TB).
K_beob = {g: {x: rnd(sum(teil[g][lb][x] for lb in LB_NAMEN), 4)
              for x in range(0, 101)} for g in ("M", "F")}
wachstum = {}
for g in ("M", "F"):
    wachstum[g] = (K_beob[g][100] / K_beob[g][95]) ** (1 / 5)
    for x in range(101, OMEGA + 1):
        K_beob[g][x] = rnd(K_beob[g][100] * wachstum[g] ** (x - 100), 4)

# Profil (Normierung k_40 = 1) und Grundkopfschaden
G = {g: rnd(K_beob[g][40], 4) for g in ("M", "F")}
k = {g: {x: rnd(K_beob[g][x] / K_beob[g][40], 4) for x in range(0, OMEGA + 1)}
     for g in ("M", "F")}
# Monotonisierung der Profile ab Alter MONO_AB (Praxisstandard fuer schwach
# besetzte hohe Alter; sichert zusammen mit Becker Satz 5.3 monoton nicht
# fallende Beitraege, vgl. § 146 Abs. 2 VAG):  k_x := max(k_{x-1}, k_x)
MONO_AB = 80
for g in ("M", "F"):
    for x in range(MONO_AB + 1, OMEGA + 1):
        if k[g][x] < k[g][x - 1]:
            k[g][x] = k[g][x - 1]
K_rechn = {g: {x: rnd(k[g][x] * G[g], 4) for x in range(0, OMEGA + 1)}
           for g in ("M", "F")}

# Kinder/Jugendliche: bestandsgewichtete Mittel (amb-Bestaende als Gewicht).
# Kinder werden geschlechtsunabhaengig kalkuliert; die Jugendlichen werden
# seit dieser Fassung geschlechtsabhaengig in maennliche und weibliche
# Jugendliche aufgesplittet (unterschiedliche mittlere Kopfschaeden).
def gruppe_mittel(x_von, x_bis, g=None):
    """Bestandsgewichtetes Mittel der Gesamtkopfschaeden ueber [x_von, x_bis].
    g=None -> geschlechtsunabhaengig (Maenner + Frauen), sonst g in {M, F}."""
    tm = profile[TAFELN_G[0].format(g="M")]
    tw = profile[TAFELN_G[0].format(g="W")]
    quellen = {"M": tm, "F": tw} if g is None else {g: (tm if g == "M" else tw)}
    z = n = 0.0
    for x in range(x_von, x_bis + 1):
        for gg, t in quellen.items():
            nx = t[x]["bestand"] or 0.0
            z += nx * K_beob[gg][x]
            n += nx
    return z / n

K_KI = rnd(gruppe_mittel(0, 15), 2)            # Kinder 0-15 (geschlechtsunabh.)
K_JU_M = rnd(gruppe_mittel(16, 20, "M"), 2)    # maennliche Jugendliche 16-20
K_JU_F = rnd(gruppe_mittel(16, 20, "F"), 2)    # weibliche Jugendliche 16-20
K_JU = rnd(gruppe_mittel(16, 20), 2)           # Jugendliche gesamt (AF-/gamma-Referenz)

# ------------------------------------------------ 3. Ausscheideordnung (Erwachsene)
# q: PKV-Sterbetafel 2025 (0-102), linear auf q_110 := 1 fortgeschrieben;
# w: storno2.csv; Schlussalter: s_110 := 1 (durch w_110 := 1 - q_110 = 0 umgesetzt)
q = {}
w = {}
for g in ("M", "F"):
    q[g] = {}
    for x in range(X_ERW, OMEGA + 1):
        if x <= 102:
            q[g][x] = rnd(q_roh[g][x], 6)
        elif x < OMEGA:
            q[g][x] = rnd(q_roh[g][102] + (1.0 - q_roh[g][102]) * (x - 102) / (OMEGA - 102), 6)
        else:
            q[g][x] = 1.0
for x in range(X_ERW, OMEGA + 1):
    w[x] = rnd(w_roh[x], 6) if x < OMEGA else 0.0

# ------------------------------------------------ 4. Barwerte (Profileinheiten)
def barwerte(g):
    i = ZINS[g]
    v = 1.0 / (1.0 + i)
    DQ, A, a = {}, {}, {}
    for x in range(X_ERW, OMEGA + 1):
        DQ[x] = rnd(v * (1.0 - q[g][x] - w[x]), 6)
    A[OMEGA] = k[g][OMEGA]
    a[OMEGA] = 1.0
    for x in range(OMEGA - 1, X_ERW - 1, -1):
        A[x] = rnd(k[g][x] + DQ[x] * A[x + 1], 4)
        a[x] = rnd(1.0 + DQ[x] * a[x + 1], 4)
    return DQ, A, a

DQ, A, a = {}, {}, {}
for g in ("M", "F"):
    DQ[g], A[g], a[g] = barwerte(g)

# Gemittelte Barwerte (Bilanz, Anlage 5.2.1); Konvention: Werte fuer x = 21..109,
# A_{110.5} := 0, a_{110.5} := 0 (Schlussalter)
A_h, a_h = {}, {}
for g in ("M", "F"):
    A_h[g] = {x: rnd(0.5 * (A[g][x] + (A[g][x + 1] if x < OMEGA else 0.0)), 4)
              for x in range(X_ERW, OMEGA + 1)}
    a_h[g] = {x: rnd(0.5 * (a[g][x] + (a[g][x + 1] if x < OMEGA else 0.0)), 4)
              for x in range(X_ERW, OMEGA + 1)}

# ------------------------------------------------ 5. Zuschlaege / gamma
def zillmersatz(x):
    if x <= 20 or x >= 80:
        return 0.0
    if x <= 75:
        return ZILLMER_VOLL
    return rnd(ZILLMER_VOLL - 0.7 * (x - 75), 1)

def omega_z(x):
    return OMEGA_Z["u65"] if x <= 64 else OMEGA_Z["o65"]

gamma = {}
for g in ("M", "F"):
    xg = GAMMA_ALTER[g]
    d_u, d_o = DELTA["u65"], DELTA["o65"]
    zaehler = 12.0 * d_u * (G[g] * A[g][xg] + GAMMA_EUBR[g] * a[g][xg])
    nenner = 12.0 * (1.0 - (d_u + SIGMA + OMEGA_Z["u65"])) * a[g][xg] - zillmersatz(xg)
    g_kost_u = rnd(zaehler / nenner, 2)
    g_kost_o = rnd(g_kost_u * d_o / d_u, 2)
    gamma[g] = {"u65": rnd(GAMMA_EUBR[g] + g_kost_u, 2),
                "o65": rnd(GAMMA_EUBR[g] + g_kost_o, 2),
                "kost_u65": g_kost_u, "kost_o65": g_kost_o}

# Kinder/Jugendliche: gamma_K aus gewichteter Gruppe (0,75 Ki + 0,25 Ju)
d_u = DELTA["u65"]
g_kost_k = rnd(12.0 * d_u * (0.75 * K_KI + 0.25 * K_JU + GAMMA_EUBR["K"])
               / (12.0 * (1.0 - (d_u + SIGMA + OMEGA_Z["u65"]))), 2)
gamma["K"] = {"u65": rnd(GAMMA_EUBR["K"] + g_kost_k, 2), "kost_u65": g_kost_k}

# ------------------------------------------------ 6. Beitraege
def gamma_x(g, x):
    return gamma[g]["u65"] if x <= 64 else gamma[g]["o65"]

b = {}
P = {}
for g in ("M", "F"):
    b[g], P[g] = {}, {}
    for x in range(X_ERW, OMEGA + 1):
        P[g][x] = rnd(G[g] * A[g][x] / a[g][x], 2)   # Jahresnettobeitrag
        zae = G[g] * A[g][x] + gamma_x(g, x) * a[g][x]
        nen = 12.0 * (1.0 - (SIGMA + omega_z(x))) * a[g][x] - zillmersatz(x)
        b[g][x] = rnd(zae / nen, 2)

# Kinder/Jugendliche (natuerliche Praemie, keine AR); Jugendliche nach Geschlecht
def b_kind(kopf):
    return rnd((kopf + gamma["K"]["u65"]) / (12.0 * (1.0 - (SIGMA + OMEGA_Z["u65"]))), 2)

P_KI, P_JU_M, P_JU_F = K_KI, K_JU_M, K_JU_F
b_KI = b_kind(K_KI)
b_JU_M = b_kind(K_JU_M)
b_JU_F = b_kind(K_JU_F)

# ------------------------------------------------ 7. Alterungsrueckstellung
def V(g, x_e, m, beitrag=None):
    """Gezillmerte AR (EUR) im erreichten Alter x_e+m fuer Eintrittsalter x_e."""
    bb = beitrag if beitrag is not None else b[g][x_e]
    x = x_e + m
    if x > OMEGA:
        return 0.0
    return G[g] * A[g][x] - (12.0 * (1.0 - (SIGMA + omega_z(x))) * bb - gamma_x(g, x)) * a[g][x]

# Negativitaetsnachweis (§ 8 Abs. 3 KVAV): erstes m mit V >= 0 je Eintrittsalter
negativ = {}
for g in ("M", "F"):
    negativ[g] = {}
    for x_e in range(X_ERW, 76):
        m = 0
        while m <= OMEGA - x_e and V(g, x_e, m) < 0:
            m += 1
        negativ[g][x_e] = m
max_neg = {g: max(negativ[g].values()) for g in ("M", "F")}

# ------------------------------------------------ 8. Beispielrechnung (M, 43)
BSP_G, BSP_X = "M", 43
bsp = {
    "kx": k[BSP_G][BSP_X], "Kx": K_rechn[BSP_G][BSP_X],
    "qx": q[BSP_G][BSP_X], "wx": w[BSP_X],
    "DQx": DQ[BSP_G][BSP_X], "Ax": A[BSP_G][BSP_X], "ax": a[BSP_G][BSP_X],
    "Ax1": A[BSP_G][BSP_X + 1], "ax1": a[BSP_G][BSP_X + 1],
    "Px": P[BSP_G][BSP_X], "bx": b[BSP_G][BSP_X],
    "gamma": gamma_x(BSP_G, BSP_X), "alpha": zillmersatz(BSP_X),
    "V0": rnd(V(BSP_G, BSP_X, 0), 2), "V5": rnd(V(BSP_G, BSP_X, 5), 2),
    "V10": rnd(V(BSP_G, BSP_X, 10), 2), "V20": rnd(V(BSP_G, BSP_X, 20), 2),
    "neg_m": negativ[BSP_G][BSP_X],
}

# ================================================================ AUSGABEN
def fmt(x, nk=4):
    return f"{x:.{nk}f}".replace(".", ",")

def schreibe_csv(name, kopf, zeilen):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="") as f:
        wtr = csv.writer(f, delimiter=";")
        wtr.writerow(kopf)
        wtr.writerows(zeilen)

# --- Kontroll-CSVs
for g in ("M", "F"):
    schreibe_csv(f"rechnungsgrundlagen_{g}.csv",
                 ["x", "k_x", "K_x", "q_x", "w_x", "s_x", "DQ_x", "A_x", "a_x",
                  "A_x+1/2", "a_x+1/2", "P_x", "b_x"],
                 [[x, k[g][x], K_rechn[g][x], q[g][x], w[x],
                   rnd(q[g][x] + w[x], 6), DQ[g][x], A[g][x], a[g][x],
                   A_h[g][x], a_h[g][x], P[g][x], b[g][x]]
                  for x in range(X_ERW, OMEGA + 1)])
schreibe_csv("herleitung_kopfschaeden_M.csv",
             ["x"] + [f"K_{lb}" for lb in LB_NAMEN] + ["Summe"],
             [[x] + [rnd(teil["M"][lb][x], 2) for lb in LB_NAMEN]
              + [rnd(K_beob["M"][x], 2)] for x in range(0, 101)])
schreibe_csv("herleitung_kopfschaeden_F.csv",
             ["x"] + [f"K_{lb}" for lb in LB_NAMEN] + ["Summe"],
             [[x] + [rnd(teil["F"][lb][x], 2) for lb in LB_NAMEN]
              + [rnd(K_beob["F"][x], 2)] for x in range(0, 101)])

# --- LaTeX: Parameter-Makros (einzige Zahlenquelle des Fliesstexts)
def tex_num(x, nk):
    # Dezimalkomma als {,} damit die Makros in Text- UND Mathe-Modus
    # korrekt gesetzt werden
    return f"{x:.{nk}f}".replace(".", "{,}")

mak = []
mak.append(("GMann", tex_num(G["M"], 4)))
mak.append(("GFrau", tex_num(G["F"], 4)))
mak.append(("ZinsM", "2{,}7"))
mak.append(("ZinsF", "2{,}0"))
mak.append(("ZinsK", "2{,}3"))
mak.append(("SigmaZ", "5{,}0"))
mak.append(("OmegaU", "0{,}7"))
mak.append(("OmegaO", "0{,}6"))
mak.append(("DeltaU", "14{,}0"))
mak.append(("DeltaO", "12{,}0"))
mak.append(("AlphaZ", "3{,}5"))
mak.append(("GammaMu", tex_num(gamma["M"]["u65"], 2)))
mak.append(("GammaMo", tex_num(gamma["M"]["o65"], 2)))
mak.append(("GammaFu", tex_num(gamma["F"]["u65"], 2)))
mak.append(("GammaFo", tex_num(gamma["F"]["o65"], 2)))
mak.append(("GammaKi", tex_num(gamma["K"]["u65"], 2)))
mak.append(("GammaEuBRM", tex_num(GAMMA_EUBR["M"], 2)))
mak.append(("GammaEuBRF", tex_num(GAMMA_EUBR["F"], 2)))
mak.append(("GammaEuBRK", tex_num(GAMMA_EUBR["K"], 2)))
mak.append(("GammaKostMu", tex_num(gamma["M"]["kost_u65"], 2)))
mak.append(("GammaKostMo", tex_num(gamma["M"]["kost_o65"], 2)))
mak.append(("GammaKostFu", tex_num(gamma["F"]["kost_u65"], 2)))
mak.append(("GammaKostFo", tex_num(gamma["F"]["kost_o65"], 2)))
mak.append(("GammaKostKi", tex_num(gamma["K"]["kost_u65"], 2)))
mak.append(("GammaAlterM", str(GAMMA_ALTER["M"])))
mak.append(("GammaAlterF", str(GAMMA_ALTER["F"])))
mak.append(("KKinder", tex_num(K_KI, 2)))
mak.append(("KJugend", tex_num(K_JU, 2)))
mak.append(("KJugendM", tex_num(K_JU_M, 2)))
mak.append(("KJugendF", tex_num(K_JU_F, 2)))
mak.append(("BKinder", tex_num(b_KI, 2)))
mak.append(("BJugendM", tex_num(b_JU_M, 2)))
mak.append(("BJugendF", tex_num(b_JU_F, 2)))
mak.append(("WachstumM", tex_num((wachstum["M"] - 1) * 100, 2)))
mak.append(("WachstumF", tex_num((wachstum["F"] - 1) * 100, 2)))
mak.append(("MonoAlter", str(MONO_AB)))
mak.append(("MaxNegM", str(max_neg["M"])))
mak.append(("MaxNegF", str(max_neg["F"])))
# Beispielrechnung
mak.append(("BspAlter", str(BSP_X)))
mak.append(("Bspkx", tex_num(bsp["kx"], 4)))
mak.append(("BspKx", tex_num(bsp["Kx"], 4)))
mak.append(("Bspqx", tex_num(bsp["qx"], 6)))
mak.append(("Bspwx", tex_num(bsp["wx"], 6)))
mak.append(("BspDQx", tex_num(bsp["DQx"], 6)))
mak.append(("BspAx", tex_num(bsp["Ax"], 4)))
mak.append(("Bspax", tex_num(bsp["ax"], 4)))
mak.append(("BspAxE", tex_num(bsp["Ax1"], 4)))
mak.append(("BspaxE", tex_num(bsp["ax1"], 4)))
mak.append(("BspPx", tex_num(bsp["Px"], 2)))
mak.append(("Bspbx", tex_num(bsp["bx"], 2)))
mak.append(("BspGamma", tex_num(bsp["gamma"], 2)))
mak.append(("BspVnull", tex_num(bsp["V0"], 2)))
mak.append(("BspVfuenf", tex_num(bsp["V5"], 2)))
mak.append(("BspVzehn", tex_num(bsp["V10"], 2)))
mak.append(("BspVzwanzig", tex_num(bsp["V20"], 2)))
mak.append(("BspNegM", str(bsp["neg_m"])))
mak.append(("BeitragMFuenfzig", tex_num(b["M"][50], 2)))
mak.append(("BeitragFFuenfzig", tex_num(b["F"][50], 2)))
mak.append(("BeitragMEinundzwanzig", tex_num(b["M"][21], 2)))
mak.append(("BeitragFEinundzwanzig", tex_num(b["F"][21], 2)))

with open(os.path.join(GEN, "gen_parameter.tex"), "w", encoding="utf-8") as f:
    f.write("% Automatisch erzeugt von kalkulation/pipeline.py - NICHT von Hand aendern\n")
    for name, wert in mak:
        f.write(f"\\newcommand{{\\{name}}}{{{wert}}}\n")

# --- LaTeX: Langtabellen-Generator
def longtable(datei, caption, label, kopf, ausr, zeilen, fussnote=""):
    with open(os.path.join(GEN, datei), "w", encoding="utf-8") as f:
        f.write("% Automatisch erzeugt von kalkulation/pipeline.py\n")
        f.write("\\begin{small}\n")
        f.write(f"\\begin{{longtable}}{{{ausr}}}\n")
        f.write(f"\\caption{{{caption}}}\\label{{{label}}}\\\\\n")
        f.write("\\toprule\n" + " & ".join(kopf) + " \\\\\n\\midrule\n\\endfirsthead\n")
        f.write(f"\\caption[]{{{caption} (Fortsetzung)}}\\\\\n")
        f.write("\\toprule\n" + " & ".join(kopf) + " \\\\\n\\midrule\n\\endhead\n")
        f.write("\\bottomrule\n\\endfoot\n")
        for z in zeilen:
            f.write(" & ".join(z) + " \\\\\n")
        f.write("\\end{longtable}\n\\end{small}\n")
        if fussnote:
            f.write(fussnote + "\n")

# Anlage 2.2.1: Ausscheideordnung M/F
for g, gname in (("M", "Maenner"), ("F", "Frauen")):
    longtable(f"gen_anlage_2_2_1_{g}.tex",
              f"Ausscheideordnung {('Männer' if g == 'M' else 'Frauen')}: "
              f"$q_x$, $w_x$, $(q+w)_x$ und $DQ_x$ (Rechnungszins "
              f"{fmt(ZINS[g] * 100, 1)}\\,\\%)",
              f"tab:ao{g}",
              ["$x$", "$q_x$", "$w_x$", "$(q+w)_x$", "$DQ_x$"], "rrrrr",
              [[str(x), fmt(q[g][x], 6), fmt(w[x], 6),
                fmt(rnd(q[g][x] + w[x], 6), 6), fmt(DQ[g][x], 6)]
               for x in range(X_ERW, OMEGA + 1)])

# Anlage 2.3.1: Profile
longtable("gen_anlage_2_3_1.tex",
          "Rechnungsmäßige normierte Kopfschadenprofile $k_x$ (Erwachsene)",
          "tab:kx",
          ["$x$", "$k_x$ Männer", "$k_x$ Frauen"], "rrr",
          [[str(x), fmt(k["M"][x], 4), fmt(k["F"][x], 4)]
           for x in range(X_ERW, OMEGA + 1)])

# Anlage 2.3.3: Kopfschaeden
longtable("gen_anlage_2_3_3.tex",
          "Rechnungsmäßige Kopfschäden $K_x = k_x \\cdot G$ (EUR p.\\,a.)",
          "tab:Kx",
          ["$x$", "$K_x$ Männer", "$K_x$ Frauen"], "rrr",
          [[str(x), fmt(K_rechn["M"][x], 4), fmt(K_rechn["F"][x], 4)]
           for x in range(X_ERW, OMEGA + 1)])

# Anlage 2.3.2: Herleitung (Teilkopfschaeden, alle Alter 0-100, 4 NK;
# zusaetzlich Summe der S-Kosten und der Umlage ueber die Leistungsbereiche,
# damit die Umlage nach Gl. (6)/(7) aus den oeffentlichen BaFin-Tafelwerten
# nachvollziehbar ist)
for g, gname in (("M", "Männer"), ("F", "Frauen")):
    kopf = ["$x$", "ambulant", "stationär", "Zahn-Beh.", "Zahn-Ers."]
    ausr = "rrrrr"
    if g == "F":
        kopf += ["$\\sum K^{S}_x$"]
        ausr += "r"
    kopf += ["$\\sum u_x$", "Summe $K_x^{\\mathrm{beob}}$"]
    ausr += "rr"
    zeilen = []
    for x in range(0, 101):
        z = [str(x), fmt(teil[g]["ambulant"][x], 4), fmt(teil[g]["stationaer"][x], 4),
             fmt(teil[g]["zahnbeh"][x], 4), fmt(teil[g]["zahners"][x], 4)]
        if g == "F":
            z.append(fmt(sum(s_kosten[lb][x] for lb in LB_NAMEN), 4))
        z.append(fmt(sum(umlage[lb][x] for lb in LB_NAMEN), 4))
        z.append(fmt(K_beob[g][x], 4))
        zeilen.append(z)
    longtable(f"gen_anlage_2_3_2_{g}.tex",
              f"Herleitung der Kopfschäden {gname}: beobachtete Teilkopfschäden "
              "je Leistungsbereich nach S-Kosten-Umlage (EUR p.\\,a., Beobachtungsjahr 2022, "
              "Tafelbereich Alter 0--100)",
              f"tab:herleitung{g}", kopf, ausr, zeilen)

# Anlage 3.1.1: Barwerte
longtable("gen_anlage_3_1_1.tex",
          "Leistungsbarwerte $A_x$ und Rentenbarwerte $a_x$ (in Profileinheiten)",
          "tab:barwerte",
          ["$x$", "$A_x$ M", "$a_x$ M", "$A_x$ F", "$a_x$ F"], "rrrrr",
          [[str(x), fmt(A["M"][x], 4), fmt(a["M"][x], 4),
            fmt(A["F"][x], 4), fmt(a["F"][x], 4)]
           for x in range(X_ERW, OMEGA + 1)])

# Anlage 5.2.1: gemittelte Barwerte
longtable("gen_anlage_5_2_1.tex",
          "Gemittelte Barwerte $A_{x+1/2}$, $a_{x+1/2}$ für die Bilanzdeckungsrückstellung",
          "tab:barwertehalb",
          ["$x$", "$A_{x+1/2}$ M", "$a_{x+1/2}$ M", "$A_{x+1/2}$ F", "$a_{x+1/2}$ F"],
          "rrrrr",
          [[str(x), fmt(A_h["M"][x], 4), fmt(a_h["M"][x], 4),
            fmt(A_h["F"][x], 4), fmt(a_h["F"][x], 4)]
           for x in range(X_ERW, OMEGA + 1)])

# Anhang 3: Beitragstabelle
longtable("gen_anhang_3.tex",
          "Tarifliche monatliche Beitragsraten $b_x$ (EUR/Monat, Einzelversicherung) "
          "und Jahresnettobeiträge $P_x$ (EUR p.\\,a.)",
          "tab:beitraege",
          ["$x$", "$P_x$ M", "$b_x$ M", "$P_x$ F", "$b_x$ F"], "rrrrr",
          [[str(x), fmt(P["M"][x], 2), fmt(b["M"][x], 2),
            fmt(P["F"][x], 2), fmt(b["F"][x], 2)]
           for x in range(X_ERW, OMEGA + 1)])

# Anlage 5.2.2: Negativitaetsnachweis (erstes m mit V >= 0)
longtable("gen_anlage_5_2_2.tex",
          "Nachweis nach \\S\\,8 Abs.\\,3 KVAV: erstes Vertragsjahr $m$ mit "
          "nichtnegativer gezillmerter Alterungsrückstellung, je Eintrittsalter",
          "tab:negativ",
          ["$x_e$", "$m$ Männer", "$m$ Frauen"], "rrr",
          [[str(x_e), str(negativ["M"][x_e]), str(negativ["F"][x_e])]
           for x_e in range(X_ERW, 76)])

# AR-Beispielverlauf (Anhang 5): Eintrittsalter 43 M, m = 0..30
longtable("gen_anhang_5_ar.tex",
          "Beispiel: Verlauf der gezillmerten Alterungsrückstellung, "
          "Männer, Eintrittsalter 43 (EUR)",
          "tab:bspar",
          ["$m$", "erreichtes Alter", "$V_{43+m}(b_{43})$"], "rrr",
          [[str(m), str(BSP_X + m), fmt(rnd(V("M", BSP_X, m), 2), 2)]
           for m in range(0, 31)])

# ------------------------------------------------ Konsole: Plausibilitaet
print("=== Kennzahlen VitalPlus ===")
print(f"G Maenner = {G['M']}, G Frauen = {G['F']}")
print(f"Wachstumsrate Fortschreibung 101-110: M {fmt((wachstum['M']-1)*100,2)} %, F {fmt((wachstum['F']-1)*100,2)} %")
print(f"K Kinder (0-15) = {K_KI}; K Jugendliche m/w = {K_JU_M}/{K_JU_F} (gesamt {K_JU})")
print(f"gamma M: {gamma['M']}")
print(f"gamma F: {gamma['F']}")
print(f"gamma K: {gamma['K']}")
print(f"Beitraege M: b_21={b['M'][21]}, b_43={b['M'][43]}, b_50={b['M'][50]}, b_65={b['M'][65]}, b_80={b['M'][80]}")
print(f"Beitraege F: b_21={b['F'][21]}, b_43={b['F'][43]}, b_50={b['F'][50]}, b_65={b['F'][65]}, b_80={b['F'][80]}")
print(f"Kinder b = {b_KI}; Jugend b m/w = {b_JU_M}/{b_JU_F}")
print(f"Barwerte M43: A={A['M'][43]}, a={a['M'][43]}; F43: A={A['F'][43]}, a={a['F'][43]}")
print(f"Negativitaet: max erstes m mit V>=0: M {max_neg['M']}, F {max_neg['F']}")
print(f"Beispiel M43: {bsp}")
for g in ("M", "F"):
    verl = [(x, b[g][x], b[g][x + 1]) for x in range(X_ERW, OMEGA) if b[g][x + 1] < b[g][x]]
    gross = [v for v in verl if v[1] - v[2] > 0.05]
    print(f"Monotonie b_x ({g}): {len(verl)} Abweichungen, davon > 5 Cent: {gross}")

# Plot-Koordinaten fuer pgfplots (Profil-Grafik k_x in Anlage 2.3.3)
with open(os.path.join(GEN, "gen_plot_kx.tex"), "w", encoding="utf-8") as f:
    f.write("% Automatisch erzeugt von kalkulation/pipeline.py\n")
    for g, farbe, name in (("M", "ffbkblau", "M\\\"anner"), ("F", "ffbkrot", "Frauen")):
        f.write(f"\\addplot+[{farbe},mark=*,mark size=1pt,mark options={{fill={farbe}}}] coordinates {{\n")
        f.write(" ".join(f"({x},{k[g][x]:.4f})" for x in range(X_ERW, OMEGA + 1)))
        f.write(f"}};\n\\addlegendentry{{{name}}}\n")

# Plot-Koordinaten der rechnungsmaessigen Kopfschaeden K_x (EUR p.a.), Anlage 2.3.3
# Dateiname bewusst NICHT 'gen_plot_Kx' (kollidiert unter Windows mit dem
# case-insensitiven 'gen_plot_kx.tex' des normierten Profils)
with open(os.path.join(GEN, "gen_plot_kopfschaeden.tex"), "w", encoding="utf-8") as f:
    f.write("% Automatisch erzeugt von kalkulation/pipeline.py\n")
    for g, farbe, name in (("M", "ffbkblau", "M\\\"anner"), ("F", "ffbkrot", "Frauen")):
        f.write(f"\\addplot+[{farbe},mark=*,mark size=1pt,mark options={{fill={farbe}}}] coordinates {{\n")
        f.write(" ".join(f"({x},{K_rechn[g][x]:.4f})" for x in range(X_ERW, OMEGA + 1)))
        f.write(f"}};\n\\addlegendentry{{{name}}}\n")
