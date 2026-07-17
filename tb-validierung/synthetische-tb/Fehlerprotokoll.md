# Fehlerprotokoll – TB_VitalPlus_fehlerhaft.pdf (Exemplar V-17b)

Die fehlerhafte Zweitvariante (92 Seiten, Layout identisch zur sauberen Fassung) enthält **13 absichtlich eingebaute Fehler** als
Prüfobjekt für das Validierungs-Notebook (Phase 3). Die saubere Variante
(`TB_VitalPlus.pdf`) ist frei von diesen Fehlern. Erzeugung reproduzierbar
über `kalkulation/erzeuge_fehlervariante.py` (Quellen: `tex_fehlerhaft/`).
Kennung der Variante: Titelseite trägt unauffällig „Exemplar V-17b".

| Nr. | Kategorie (Prüf-Katalog Phase 3) | Ort | Fehler | Korrekt wäre |
|---|---|---|---|---|
| F01 | dokumentintern: Korrektheit berechneter Werte | Anhang 3, Beitragstabelle, Alter 50, Spalte b_x Männer | 653,33 EUR (Zahlendreher) | 635,33 EUR (folgt aus Gl. der Beitragsformel mit A_50/a_50 aus Anlage 3.1.1) |
| F02 | dokumentextern: Gesetzeskonformität + dokumentintern: Konsistenz | Anlage 2.4, Zeile Sicherheitszuschlag | σ = 4,5 % (alle Spalten) | 5,0 % — Widerspruch zur Festsetzung σ = 5,0 % (Gleichung am Anfang derselben Anlage) und Verstoß gegen § 7 KVAV (mind. 5 % der Bruttoprämie) |
| F03 | dokumentextern: Gesetze/Paragrafen | Abschnitt 2.1, erster Satz | „Höchstrechnungszins … gemäß § 4 VAG" | § 4 KVAV |
| F04 | dokumentintern: interne Verlinkungen | Abschnitt 5.2 (Bilanzdeckungsrückstellung), Verweis auf gemittelte Barwerte | Verweis auf nicht existierendes Label (`sec:anlage523`) → erscheint als „Abschnitt ??" | Verweis auf Anlage 5.2 |
| F05a | dokumentintern: Rechtschreibung | Abschnitt 5.1, erster Satz | „Alterungsrückstelung" | Alterungsrückstellung |
| F05b | dokumentintern: Rechtschreibung | Abschnitt 3.2, erster Satz | „Äquivalenzprinizip" | Äquivalenzprinzip |
| F05c | dokumentintern: Rechtschreibung | Abschnitt 1.1, „Versicherungsform" | „Krankheitskostenvollversichrung" | Krankheitskostenvollversicherung |
| F06 | dokumentintern: Vollständigkeit Glossar | Symbolverzeichnis (Abschnitt 0.3) | Eintrag für DQ_x fehlt, Symbol wird aber in Abschnitten 2.2.3/3.1 und Anlage 2.2 verwendet | Eintrag „DQ_x = v·(1−(q+w)_x)" |
| F07 | dokumentintern: Konsistenz benannter Parameter | Anlage 2.3.3, Einleitungstext | G^M = 1910,0070 EUR (Zahlendreher) | 1901,0070 EUR (wie die Festsetzungs-Gleichung in derselben Anlage, Anlage 2.3.2 und Anhang 5) |
| F08 | dokumentintern: Korrektheit berechneter Werte | Anlage 2.2 (Männer), Zeile Alter 50, Spalte (q+w)_x | 0,037271 | 0,036271 = q_50 + w_50 = 0,001271 + 0,035 (DQ-Spalte 0,938392 passt zum korrekten Wert) |
| F09 | dokumentintern: Konsistenz Label/Rechnung | Anlage 2.1, Zins Frauen | „2,2 %" | 2,0 % (alle Frauen-Barwerte/Beiträge sind mit 2,0 % gerechnet; analog Fehlerbild Beispielkalkulation_ALT.csv) |
| F10 | dokumentintern: Inhaltsverzeichnis | Inhaltsverzeichnis, Anlagen-Eintrag | IHV zeigt „Anlage 3.1: Grundwerte der Versicherungstechnik" | „Anlage 3.1: Versicherungstechnische Grundwerte" (so lautet die Überschrift im Dokument) |
| F11 | dokumentintern: Korrektheit berechneter Werte | Anhang 5, Schritt 3 | P_43 = 4676,48 EUR (Zahlendreher) | 4667,48 = 1901,0070·44,1833/17,9953 |
| F12 | dokumentintern: Korrektheit der Formeln | Abschnitt 5.1, Gl. der Alterungsrückstellung | „… − [12·(1−(σ+Ω_x))·b **+** γ_x]·a_x" (Vorzeichen gedreht) | „… − [12·(1−(σ+Ω_x))·b **−** γ_x]·a_x"; die Zahlen in Anhang 5 folgen der korrekten Formel und widersprechen damit der abgedruckten |
| F13 | dokumentintern: Konsistenz Grafik ↔ Tabelle | Anlage 2.3.3, Profil-Grafik | Frauen-Kurve um Faktor 1,5 überhöht (z. B. k_40 ≈ 1,5 statt 1,0) | Kurve muss den Tabellenwerten k_x der Frauen entsprechen |

## Abdeckung des Prüf-Katalogs (Phase 3)

- Rechtschreibprüfung: F05a–c
- korrekte interne Verlinkungen: F04
- Vollständigkeit Glossar/Formelbestandteile: F06
- Korrektheit berechneter Werte anhand der Formeln: F01, F08, F11, (F12)
- Korrektheit erwähnter Gesetze/Paragrafen: F02 (§ 7 KVAV), F03 (§ 4 KVAV/VAG)
- Abgleich mit Werten aus CSV/Datenbank: F01, F07, F08, F09 (gegen `kalkulation/out/*.csv`)
- Korrektheit des Inhaltsverzeichnisses: F10
- Konsistenz Abschnitt ↔ Anlage: F02, F07, F09
- Konsistenz Grafik ↔ Tabelle (Vision): F13

Hinweis: Die sauberen Referenzwerte aller Tabellen liegen maschinenlesbar
unter `kalkulation/out/` (CSV, Semikolon, Dezimalpunkt).
