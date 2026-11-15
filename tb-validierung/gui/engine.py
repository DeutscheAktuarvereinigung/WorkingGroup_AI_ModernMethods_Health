"""Prüfmaschine der GUI für die TB-Validierung.

Dieses Modul führt die Prüf-Logik des Validierungsnotebooks aus, OHNE sie zu
kopieren: Die Code-Zellen der Notebook-Abschnitte 2 bis 7 (Setup,
Prüf-Framework, PDF-Ingestion, deterministische Checks, LLM-Anbindung,
LLM-Checks) werden je Dokument in einem eigenen Namensraum ausgeführt. Danach
wird in diesem Namensraum nur die Funktion ``llm_json`` ersetzt, über die alle
Sprachmodell-Checks ihre Anfragen stellen. Damit laufen die Sprachmodell-Checks

* im Modus ``"live"`` gegen die Anthropic-API (Standardmodell Claude Sonnet 5.5),
* im Modus ``"notfall"`` aus den gespeicherten Antworten des Nachweis-Laufs
  (``llm_cache.json`` des Notebooks, nur lesend, ohne Netzwerk) – auf Wunsch
  im Tempo eines echten Live-Laufs (``notfall_verzoegerung_s="live"``).

Live-Beschleunigung: Vor dem eigentlichen Lauf geht jeder ausgewählte
Sprachmodell-Check einmal im „Sammeldurchlauf“ durch. Dabei werden seine
Anfragen nur notiert (Antwort = minimale, schema-gültige Attrappe). Alle
gesammelten Anfragen starten sofort parallel im Hintergrund, während die
deterministischen Checks laufen. Im echten Durchlauf bedient ``llm_json`` die
Checks dann aus den fertigen Antworten. Die Check-Logik selbst bleibt
unverändert.

Verbindliche Schnittstelle für die GUI:
    DOKUMENTE, STANDARDMODELL, REFERENZMODELL,
    CheckInfo, BefundGUI, CheckErgebnis, Ereignis,
    lade_pruefstrecke(dokument) -> Pruefstrecke,
    Pruefstrecke.checks(), Pruefstrecke.laufe(...),
    api_schluessel_vorhanden().
"""
from __future__ import annotations

import builtins
import contextlib
import copy
import hashlib
import io
import json
import linecache
import os
import random
import re
import sys
import threading
import time
import types
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as warte_auf_zukunft
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

import anthropic
import httpx      # Transportschicht des Anthropic-SDK (Zeitlimits, Verbindungsfehler)
import pymupdf    # = fitz (das Notebook importiert denselben Modulinhalt als „fitz“)

# =============================================================================
# Pfade und Konstanten
# =============================================================================
GUI_ORDNER = Path(__file__).resolve().parent
TB_ORDNER = GUI_ORDNER.parent
NOTEBOOK_ORDNER = TB_ORDNER / "validierungsnotebook"
NOTEBOOK_PFAD = NOTEBOOK_ORDNER / "TB_Validierung.ipynb"
REFERENZ_CACHE_PFAD = NOTEBOOK_ORDNER / "llm_cache.json"   # nur lesen!
NORMTEXT_KOPIE_PFAD = NOTEBOOK_ORDNER / "normtexte.json"   # Gesetzestexte (L-04), nur lesen
# Quelle der Gesetzestexte für L-04 (Tests setzen None: nur die gespeicherte Kopie)
NORMTEXT_QUELLE = os.environ.get("TB_NORMTEXT_QUELLE", "https://www.gesetze-im-internet.de")
SYNTHETISCHE_TB_ORDNER = TB_ORDNER / "synthetische-tb"
REFERENZ_CSV_ORDNER = SYNTHETISCHE_TB_ORDNER / "kalkulation" / "out"
REFERENZ_DB_PFAD = REFERENZ_CSV_ORDNER / "rechnungsgrundlagen.db"
FEHLERPROTOKOLL_PFAD = SYNTHETISCHE_TB_ORDNER / "Fehlerprotokoll.md"

# Die beiden Prüfobjekte (layoutgleich; die fehlerhafte Fassung enthält 13
# dokumentierte Fehler F01–F13, siehe Fehlerprotokoll).
DOKUMENTE = {
    "fehlerhaft": SYNTHETISCHE_TB_ORDNER / "TB_VitalPlus_fehlerhaft.pdf",
    "fehlerfrei": SYNTHETISCHE_TB_ORDNER / "TB_VitalPlus.pdf",
}
# Prüfberichte des Nachweis-Laufs (Notebook, Juli 2026) – nur lesen.
REFERENZBERICHTE = {
    "fehlerhaft": NOTEBOOK_ORDNER / "pruefbericht_TB_VitalPlus_fehlerhaft.json",
    "fehlerfrei": NOTEBOOK_ORDNER / "pruefbericht_TB_VitalPlus.json",
}

STANDARDMODELL = "claude-sonnet-5-5"   # Live-Demo: Claude Sonnet 5.5
REFERENZMODELL = "claude-sonnet-5"     # Modell des Nachweis-Laufs (Cache-Schlüssel)
MAX_LLM_AUFRUFE = 400                  # Sicherheitsobergrenze je Prüflauf (live)
# Gleichzeitige Sprachmodell-Anfragen (Standard für laufe). Die Laufzeit wird
# von den langen Einzelanfragen (L-02 ca. 20 s, L-04 ca. 28 s) bestimmt; bei
# nur 8 gleichzeitigen Anfragen starten diese erst spät. Rate-Limits (429)
# behandelt das SDK selbst (Wartezeit laut Retry-After).
MAX_PARALLEL_STANDARD = 24

# Server-seitiger Fallback bei Ablehnungen durch die Sicherheitsfilter
# (fallbacks="default", Beta „server-side-fallback-2026-07-01“): nur für die
# Modelle der 5er-Generation außer Haiku (Sonnet, Opus, Fable). Andere
# Modellnamen aus der Seitenleiste (z. B. Claude Haiku 5.5 – dort gibt es
# keinen Fallback) werden ohne die Fallback-Parameter angefragt.
_FALLBACK_MODELL_RE = re.compile(r"^claude-(?:sonnet|opus|fable)-5(?:$|[-.@])")


def hat_server_fallback(modell: str) -> bool:
    """True, wenn für das Modell der server-seitige Fallback angefragt wird."""
    return bool(_FALLBACK_MODELL_RE.match(str(modell or "").strip()))


# Zeitlimits des Anthropic-Clients: Verbindungsaufbau höchstens 10 s (ohne
# Netz scheitert eine Anfrage so schnell), sonst 240 s (u. a. zwischen zwei
# Datenpaketen des Antwortstroms; beobachtete Einzelanfragen dauern bis etwa
# 32 s). Das SDK wiederholt Verbindungsfehler, 429 und 5xx vor Beginn des
# Antwortstroms selbst (hier 2-mal).
CLIENT_ZEITLIMIT = httpx.Timeout(240.0, connect=10.0)
CLIENT_WIEDERHOLUNGEN = 2
# Eigene Wiederholungen für vorübergehende Fehler, die das SDK NICHT
# wiederholt (Abbruch oder Fehlermeldung mitten im Antwortstrom) bzw. die
# auch nach dessen Wiederholungen bestehen (überlastet, Störung, Rate-Limit):
# Wartezeiten vor dem 2. und 3. Versuch.
WIEDERHOLUNG_WARTEZEITEN_S = (3.0, 8.0)

# Notfallmodus mit realistischem Tempo (laufe(..., notfall_verzoegerung_s=
# "live")): typische Antwortzeit je Anfrage im Live-Lauf mit Claude Sonnet 5.5
# (gemessen Oktober 2026), je Anfrage zufällig um ±30 % gestreut. Ein
# Notfall-Lauf sieht damit auf der Leinwand aus wie ein Live-Lauf.
LIVE_ANTWORTZEITEN_S = {"L-01": 4.5, "L-02": 20.0, "L-03": 5.0, "L-04": 28.0,
                        "L-05": 5.0, "L-06": 10.0}
STREUUNG_JE_CHECK = 0.3    # ±30 % bei Antwortzeiten je Check ("live" oder dict)
STREUUNG_FEST = 0.4        # ±40 % bei einer festen Antwortzeit (Zahl)

# Status-Werte (identisch zum Notebook)
BESTANDEN = "BESTANDEN"
WARNUNG = "WARNUNG"
FEHLER = "FEHLER"
UEBERSPRUNGEN = "ÜBERSPRUNGEN"
FEHLGESCHLAGEN = "FEHLGESCHLAGEN"

# PyMuPDF ist nicht thread-sicher. Jeder Zugriff auf ein fitz-Dokument (Laden,
# Seitenbilder, Zeichenpfade) läuft deshalb unter dieser gemeinsamen Sperre.
# Die GUI sollte sie ebenfalls nutzen, wenn sie selbst mit fitz rendert.
FITZ_SPERRE = threading.RLock()

# Ein einfacher deutscher Satz je Check für das Publikum (am Code der
# Check-Funktionen des Notebooks geprüft).
ERKLAERUNGEN = {
    "V-01": "Findet Verweise, die ins Leere zeigen („Abschnitt ??“).",
    "V-02": "Prüft, ob jeder genannte Abschnitt, jede Anlage und jede "
            "Gleichungsnummer im Dokument wirklich vorkommt.",
    "V-03": "Vergleicht das Inhaltsverzeichnis mit den echten Überschriften: "
            "Stimmen Titel und Seitenzahlen?",
    "V-04": "Prüft, ob jedes häufig benutzte Formelzeichen im "
            "Symbolverzeichnis erklärt ist.",
    "V-05": "Rechnet in den Tafeln nach: Ist (q+w) die Summe aus q und w, und "
            "passt der angegebene Rechnungszins zu den Tabellenwerten?",
    "V-06": "Meldet Stellen, an denen ein Beitrag bei höherem Eintrittsalter "
            "sinkt – außer die TB begründet den Rückgang selbst (z. B. Wegfall "
            "von Zuschlägen ab Alter 65).",
    "V-07": "Gleicht jede Tabellenzelle mit den Werten aus der Kalkulation ab.",
    "V-08": "Prüft, ob ein benannter Parameter (z. B. der Grundkopfschaden G) "
            "überall im Dokument denselben Wert hat.",
    "V-09": "Prüft, ob Fachbegriffe mit dem richtigen Paragrafen belegt sind "
            "und der Sicherheitszuschlag mindestens 5 % beträgt.",
    "V-10": "Prüft, ob jede genannte Rahmen-TB im Register steht – und zwar "
            "in derselben Version.",
    "V-11": "Prüft, ob Änderungsnummer und Gültigkeitsdatum überall gleich "
            "sind und die Änderungshistorie aktuell ist.",
    "V-12": "Prüft die Alterstafeln auf fehlende Alter, das angegebene "
            "Endalter und unmögliche Werte.",
    "V-13": "Gleicht Sterbe- und Stornowahrscheinlichkeiten sowie Kopfschäden "
            "Zelle für Zelle mit der Referenzdatenbank ab.",
    "L-01": "Das Modell sucht eindeutige Tippfehler im Fließtext; Python prüft, "
            "ob das Wort wirklich so im Dokument steht.",
    "L-02": "Das Modell schreibt Beispielrechnungen als Formel ab; Python "
            "rechnet nach und vergleicht mit dem gedruckten Ergebnis.",
    "L-03": "Das Modell vergleicht Abschnitte mit den gleichnummerigen Anlagen "
            "und der Beispielrechnung auf widersprüchliche Werte.",
    "L-04": "Das Modell schlägt die zitierten Paragrafen selbst auf "
            "gesetze-im-internet.de nach (Werkzeugaufruf) und prüft, ob die "
            "zitierte Stelle den Sachverhalt regelt.",
    "L-05": "Das Modell liest Seiten mit Formeln als Bild und prüft Vorzeichen "
            "und Aufbau gegen den erklärenden Text.",
    "L-06": "Das Modell liest die Kurven ohne Kenntnis der Sollwerte ab; "
            "Python vergleicht mit der Tabelle.",
}


# =============================================================================
# Datenstrukturen der Schnittstelle
# =============================================================================
@dataclass
class CheckInfo:
    """Beschreibung eines Checks für die Auswahlliste der GUI."""
    id: str
    titel: str
    kategorie: str          # "dokumentintern" / "dokumentextern"
    methode: str            # "deterministisch" | "LLM"
    erklaerung: str         # ein einfacher deutscher Satz für Laien


@dataclass
class BefundGUI:
    """Ein einzelner Befund (entspricht Befund im Notebook)."""
    check_id: str
    beschreibung: str
    seite: int | None       # PDF-Seite (1-basiert), falls lokalisierbar
    schwere: str            # "FEHLER" | "WARNUNG"


@dataclass
class CheckErgebnis:
    """Ergebnis eines Checks (Status-Ableitung wie im Runner des Notebooks)."""
    id: str
    titel: str
    methode: str
    status: str             # BESTANDEN | WARNUNG | FEHLER | ÜBERSPRUNGEN | FEHLGESCHLAGEN
    befunde: list[BefundGUI] = field(default_factory=list)
    hinweis: str = ""
    dauer_s: float = 0.0
    llm_anfragen: int = 0   # Zahl der Modellanfragen dieses Checks


@dataclass
class Ereignis:
    """Fortschrittsmeldung des Prüflaufs (siehe Pruefstrecke.laufe).

    Zusätzlich zur Schnittstelle tragen alle Ereignisse den Gesamtstand der
    im Hintergrund laufenden Sprachmodell-Anfragen (llm_beantwortet von
    llm_gesamt), damit die GUI ihn auch während der deterministischen Checks
    anzeigen kann.
    """
    art: str                # "prefetch" | "start" | "llm_fortschritt" | "ergebnis" | "fertig"
    check_id: str | None
    erledigt: int
    gesamt: int
    ergebnis: CheckErgebnis | None = None
    text: str = ""
    llm_beantwortet: int = 0
    llm_gesamt: int = 0


class SprachmodellFehler(RuntimeError):
    """Verständliche Fehlermeldung rund um einen Sprachmodell-Aufruf.

    voruebergehend: ein erneuter Versuch kann gelingen (überlastet, Störung,
                    Abbruch mitten im Antwortstrom).
    verbindung:     keine Verbindung zur API (auch nach den Wiederholungen
                    des SDK) – die übrigen Anfragen des Laufs enden sofort.
    """

    def __init__(self, text: str, *, voruebergehend: bool = False,
                 verbindung: bool = False):
        super().__init__(text)
        self.voruebergehend = voruebergehend
        self.verbindung = verbindung


KEINE_VERBINDUNG = ("Keine Verbindung zur Anthropic-API – Notfallschalter in der "
                    "Seitenleiste verwenden.")


class _LaufAbgebrochen(Exception):
    """Der Prüflauf wurde abgebrochen (z. B. weil die GUI neu geladen hat)."""


# =============================================================================
# Hilfsfunktionen
# =============================================================================
def api_schluessel_vorhanden() -> bool:
    """True, wenn ANTHROPIC_API_KEY (oder ersatzweise ANTHROPIC_AUTH_TOKEN, das
    das SDK ebenfalls akzeptiert) gesetzt ist. Der Wert wird nie
    zurückgegeben. Eine Anmeldung nur über ein Profil („ant auth login“)
    wird nicht erkannt – siehe README."""
    return bool(os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def lade_referenzbericht(dokument: str) -> dict:
    """Prüfbericht des Nachweis-Laufs zum Dokument (JSON, nur lesend)."""
    return json.loads(REFERENZBERICHTE[dokument].read_text(encoding="utf-8"))


def anfrage_schluessel(modell: str, auftrag: str, text: str, schema: dict,
                       bild_b64: str | None, werkzeuge=None) -> str:
    """Cache-Schlüssel exakt nach dem Rezept des Notebooks (Zelle 12): Anfragen
    mit Werkzeugen enthalten zusätzlich die sortierten Werkzeugnamen."""
    bild_hash = hashlib.sha256(bild_b64.encode("ascii")).hexdigest() if bild_b64 else None
    teile = [modell, auftrag, text, schema, bild_hash]
    if werkzeuge:
        teile.append(sorted(w.name for w in werkzeuge))
    return hashlib.sha256(
        json.dumps(teile, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def attrappe_aus_schema(schema: dict):
    """Minimale, schema-gültige Antwort für den Sammeldurchlauf:
    object -> alle Pflichtfelder, array -> [], string -> "", number/integer
    -> 0, boolean -> false, enum -> erster Wert."""
    if not isinstance(schema, dict):
        return None
    if "enum" in schema:
        return schema["enum"][0] if schema["enum"] else None
    if "const" in schema:
        return schema["const"]
    for kombi in ("anyOf", "oneOf"):
        if schema.get(kombi):
            return attrappe_aus_schema(schema[kombi][0])
    typ = schema.get("type")
    if isinstance(typ, list):
        typ = next((t for t in typ if t != "null"), None)
    if typ == "object" or (typ is None and "properties" in schema):
        eigenschaften = schema.get("properties", {})
        return {feld: attrappe_aus_schema(eigenschaften.get(feld, {}))
                for feld in schema.get("required", [])}
    return {"array": [], "string": "", "number": 0, "integer": 0,
            "boolean": False}.get(typ)


@dataclass(frozen=True)
class _Anfrage:
    """Eine Sprachmodell-Anfrage, wie sie ein Check an llm_json stellt."""
    schluessel: str
    auftrag: str
    text: str
    schema: dict = field(hash=False, compare=False)
    max_tokens: int = 8000
    bild_b64: str | None = field(default=None, repr=False)
    # Werkzeuge (Werkzeug-Objekte des Notebooks), die Claude aufrufen darf
    werkzeuge: tuple = field(default=(), hash=False, compare=False, repr=False)


def _neuer_client():
    """Anthropic-Client für den Live-Modus (Tests ersetzen diese Funktion
    durch eine Attrappe). Der API-Schlüssel kommt aus der Umgebung."""
    _sdk_aufwaermen()
    return anthropic.Anthropic(max_retries=CLIENT_WIEDERHOLUNGEN,
                               timeout=CLIENT_ZEITLIMIT)


# Erster Live-Lauf nach dem Programmstart: Das Anthropic-SDK baut beim ersten
# Gebrauch intern Typinformationen auf. Geschieht das in vielen Threads
# zugleich (bis zu 24 parallele Anfragen), verschluckt es sich gelegentlich:
# beobachtet „AttributeError: 'NoneType' object has no attribute 'append'“ in
# accumulate_event – die ersten Sprachmodell-Checks enden dann violett, ein
# zweiter Lauf klappt. Abhilfe: einmal je Prozess vorab, in einem einzigen
# Thread und ohne Netzwerk, eine vollständige Antwort (Denken, Text,
# Werkzeugaufruf) durch denselben Streaming-Pfad schicken.
_AUFWAERM_SPERRE = threading.Lock()
_aufgewaermt = False


def _schein_antwort(_anfrage: httpx.Request) -> httpx.Response:
    """Lokale SSE-Antwort für das Aufwärmen (kein Netzwerk)."""
    def blockfolge(index, start, *deltas):
        return ([("content_block_start", {"index": index, "content_block": start})]
                + [("content_block_delta", {"index": index, "delta": d}) for d in deltas]
                + [("content_block_stop", {"index": index})])
    ereignisse = (
        [("message_start", {"message": {
            "id": "msg_aufwaermen", "type": "message", "role": "assistant",
            "model": STANDARDMODELL, "content": [], "stop_reason": None,
            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}})]
        + blockfolge(0, {"type": "thinking", "thinking": "", "signature": ""},
                     {"type": "thinking_delta", "thinking": "."},
                     {"type": "signature_delta", "signature": "x"})
        + blockfolge(1, {"type": "text", "text": ""}, {"type": "text_delta", "text": "{}"})
        + blockfolge(2, {"type": "tool_use", "id": "toolu_aufwaermen", "name": "w", "input": {}},
                     {"type": "input_json_delta", "partial_json": "{\"a\": \"b\"}"})
        + [("message_delta", {"delta": {"stop_reason": "end_turn", "stop_sequence": None},
                              "usage": {"output_tokens": 1}}),
           ("message_stop", {})])
    roh = "".join(f"event: {art}\ndata: {json.dumps({'type': art, **daten})}\n\n"
                  for art, daten in ereignisse)
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                          content=roh.encode("utf-8"))


def _sdk_aufwaermen() -> None:
    """Einmal je Prozess (siehe oben); Fehler hier sind unerheblich."""
    global _aufgewaermt
    with _AUFWAERM_SPERRE:
        if _aufgewaermt:
            return
        try:
            schein = anthropic.Anthropic(
                api_key="aufwaermen", base_url="http://aufwaermen.invalid", max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(_schein_antwort)))
            with schein.beta.messages.stream(
                model=STANDARDMODELL, max_tokens=16, system="s",
                messages=[{"role": "user", "content": [{"type": "text", "text": "x"}]}],
                output_config={"format": {"type": "json_schema", "schema": {
                    "type": "object", "properties": {}, "additionalProperties": False}}},
                tools=[{"name": "w", "description": "w", "input_schema": {
                    "type": "object", "properties": {"a": {"type": "string"}}}}],
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"},
            ) as strom:
                strom.get_final_message()
        except Exception:
            pass
        _aufgewaermt = True


def _kurz(text, n: int = 200) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _api_fehler_text(fehler: anthropic.APIStatusError, modell: str) -> tuple[str, bool]:
    """(verständlicher Text, vorübergehend?) zu einer Fehlermeldung der API.

    Maßgeblich ist der Fehlertyp im Antwortkörper ({"error": {"type": …}}),
    denn ein Fehler mitten im Antwortstrom (z. B. overloaded_error) kommt
    nach einem HTTP-200-Kopf an – der Statuscode ist dann 200. Fehlt der
    Typ, entscheidet der Statuscode."""
    typ, meldung = None, ""
    koerper = fehler.body
    if isinstance(koerper, dict):
        innen = koerper.get("error") if isinstance(koerper.get("error"), dict) else koerper
        typ, meldung = innen.get("type"), str(innen.get("message") or "")
    status = fehler.status_code
    if typ == "overloaded_error" or status == 529:
        return "Das Sprachmodell ist derzeit überlastet.", True
    if typ == "rate_limit_error" or status == 429:
        return "Zu viele Anfragen an das Sprachmodell (Rate-Limit).", True
    if typ == "api_error" or (typ is None and status >= 500):
        return "Störung bei Anthropic (Serverfehler).", True
    if typ == "authentication_error" or status == 401:
        return "Der API-Schlüssel wurde abgelehnt.", False
    if typ == "permission_error" or status == 403:
        return f"Keine Berechtigung für das Modell „{modell}“.", False
    if typ == "not_found_error" or status == 404:
        return (f"Das Modell „{modell}“ ist nicht verfügbar – bitte den "
                f"Modellnamen prüfen."), False
    if typ == "request_too_large" or status == 413:
        return "Die Anfrage ist für das Sprachmodell zu groß.", False
    if typ == "invalid_request_error" or status == 400:
        return ("Die Anthropic-API hat die Anfrage als ungültig abgelehnt"
                + (f": {_kurz(meldung, 140)}" if meldung else ".")), False
    # Unbekannter Fehler; mitten im Antwortstrom (Status 200) lohnt ein neuer Versuch.
    return f"Die Anthropic-API meldet einen Fehler ({typ or status}).", status == 200


def _json_aus_antwort(inhalt: list):
    """JSON-Text der Antwort. Normalfall: erster text-Block (nach dem
    thinking-Block). Enthält die Antwort einen fallback-Block, hat der
    server-seitige Fallback übernommen. Gelesen wird dann der Text nach dem
    letzten fallback-Block (alle text-Blöcke dort verkettet). Lehnte der
    Sicherheitsfilter erst mitten in der Ausgabe ab, setzt das Fallback-Modell
    das bereits gestreamte Teilstück nur fort – dann ergeben erst alle
    text-Blöcke zusammen das JSON (Rückfall)."""
    typen = [getattr(b, "type", None) for b in inhalt]
    texte = [b.text for b, t in zip(inhalt, typen) if t == "text"]
    if not texte:
        raise SprachmodellFehler("Die Antwort des Sprachmodells enthält keinen Text.")
    if "fallback" in typen:
        letzter = max(i for i, t in enumerate(typen) if t == "fallback")
        nach_fallback = "".join(b.text for b, t in zip(inhalt[letzter + 1:],
                                                       typen[letzter + 1:]) if t == "text")
        kandidaten = [nach_fallback, "".join(texte)]
    else:
        kandidaten = texte[:1]
    for kandidat in kandidaten:
        try:
            return json.loads(kandidat)
        except json.JSONDecodeError:
            continue
    raise SprachmodellFehler("Die Antwort des Sprachmodells ist kein gültiges JSON.")


def _live_anfrage(client, modell: str, anfrage: _Anfrage, system: str,
                  werkzeug_ergebnisse: Callable | None = None, max_runden: int = 5) -> dict:
    """Stellt eine Anfrage live an die Anthropic-API (Streaming, Structured
    Outputs) und liefert das geparste JSON. Fehler werden als verständliche
    SprachmodellFehler weitergereicht (mit Kennzeichen „vorübergehend“ bzw.
    „Verbindung“ für die Wiederholungslogik in _Lauf._beantworte).

    Werkzeuge (Tool Use): Hat die Anfrage Werkzeuge, darf Claude sie aufrufen;
    werkzeug_ergebnisse (Funktion des Notebooks) führt die Aufrufe aus, die
    Ergebnisse gehen zurück an Claude – bis die JSON-Antwort vorliegt
    (höchstens max_runden Runden mit Werkzeugaufrufen)."""
    inhalt = [{"type": "text", "text": f"{anfrage.auftrag}\n\n---\n\n{anfrage.text}"}]
    if anfrage.bild_b64:
        inhalt.insert(0, {"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": anfrage.bild_b64}})
    nachrichten = [{"role": "user", "content": inhalt}]
    # Server-seitiger Fallback bei Ablehnungen nur für Modelle, die ihn kennen.
    fallback = ({"betas": ["server-side-fallback-2026-07-01"],
                 "extra_body": {"fallbacks": "default"}}
                if hat_server_fallback(modell) else {})
    werkzeuge = list(anfrage.werkzeuge or ())
    try:
        for runde in range(max_runden + 1):
            zusatz = {}
            if werkzeuge:
                zusatz["tools"] = [w.definition() for w in werkzeuge]
                if runde == max_runden:
                    zusatz["tool_choice"] = {"type": "none"}   # jetzt antworten
            # Kein thinking-Parameter: Sonnet 5.5 denkt adaptiv ({"type": "disabled"}
            # wäre dort ein Fehler 400).
            with client.beta.messages.stream(
                model=modell,
                max_tokens=max(2 * anfrage.max_tokens, 32000),
                system=system,
                messages=nachrichten,
                output_config={"format": {"type": "json_schema", "schema": anfrage.schema}},
                **fallback,
                **zusatz,
            ) as strom:
                antwort = strom.get_final_message()
            if antwort.stop_reason != "tool_use" or not werkzeuge or werkzeug_ergebnisse is None:
                break
            # Antwort unverändert anhängen (inkl. Denk-Blöcken), dann alle
            # Ergebnisse gemeinsam in EINER Nachricht zurück
            nachrichten.append({"role": "assistant", "content": antwort.content})
            nachrichten.append({"role": "user",
                                "content": werkzeug_ergebnisse(werkzeuge, antwort.content)})
    except anthropic.APIStatusError as fehler:
        # Auch Fehlermeldungen mitten im Antwortstrom (SSE-Ereignis „error“).
        text, voruebergehend = _api_fehler_text(fehler, modell)
        raise SprachmodellFehler(text, voruebergehend=voruebergehend) from fehler
    except anthropic.APITimeoutError as fehler:
        # (Unterklasse von APIConnectionError, daher zuerst) – auch nach den
        # Wiederholungen des SDK keine Antwort: wie ein Verbindungsausfall.
        raise SprachmodellFehler(
            "Zeitüberschreitung bei der Verbindung zur Anthropic-API – "
            "Notfallschalter in der Seitenleiste verwenden.", verbindung=True) from fehler
    except anthropic.APIConnectionError as fehler:
        raise SprachmodellFehler(KEINE_VERBINDUNG, verbindung=True) from fehler
    except httpx.HTTPError as fehler:
        # Abbruch oder Zeitüberschreitung WÄHREND des Antwortstroms: Das SDK
        # wiederholt hier nicht und reicht die httpx-Ausnahme roh durch.
        raise SprachmodellFehler(
            "Die Verbindung zur Anthropic-API ist während der Antwort abgebrochen.",
            voruebergehend=True) from fehler
    except anthropic.APIError as fehler:
        raise SprachmodellFehler(
            f"Fehler bei der Anfrage an das Sprachmodell: {_kurz(fehler)}") from fehler
    except Exception as fehler:
        # Unerwarteter Fehler im SDK selbst (z. B. beim ersten Gebrauch in
        # vielen Threads zugleich): ein erneuter Versuch gelingt in aller Regel.
        raise SprachmodellFehler(
            f"Unerwarteter Fehler im Anthropic-SDK ({type(fehler).__name__}: "
            f"{_kurz(fehler, 120)}).", voruebergehend=True) from fehler

    if antwort.stop_reason == "refusal":
        kategorie = getattr(getattr(antwort, "stop_details", None), "category", None)
        raise SprachmodellFehler(
            "Das Sprachmodell hat die Anfrage abgelehnt (Sicherheitsfilter"
            + (f", Kategorie „{kategorie}“" if kategorie else "") + ").")
    if antwort.stop_reason == "max_tokens":
        raise SprachmodellFehler(
            "LLM-Antwort wurde abgeschnitten (max_tokens erreicht).")
    return _json_aus_antwort(list(antwort.content))


# =============================================================================
# Kompatibilität der Textextraktion (PyMuPDF 1.27.2.2 des Nachweis-Laufs)
# =============================================================================
# Der Nachweis-Lauf (Prüfberichte und llm_cache.json, Juli 2026) lief mit
# PyMuPDF 1.27.2.2. Ab PyMuPDF 1.28 landen die großen Betragsstriche |…| des
# Formelsatzes (Unicode U+20D2) in derselben Textzeile wie der vorangehende
# Text; unter 1.27.2.2 begann mit dem ersten Betragsstrich einer Zeile eine
# neue Zeile. Betroffen sind nur zwei Sätze („… falls |1 − AF| > 0,05“ auf
# den Seiten 51/52), sie verändern aber die Texte, die L-01, L-02 und L-04
# an das Sprachmodell senden – die gespeicherten Antworten würden dann nicht
# mehr gefunden. Diese Schicht stellt das Zeilenbild von 1.27.2.2 wieder her
# (nur beim Einlesen des PDFs, Notebook-Code bleibt unverändert). Unter
# PyMuPDF 1.27 ist sie wirkungslos. Abschalten: False setzen.
PYMUPDF_KOMPATIBILITAET = True
_BETRAGSSTRICH_RE = re.compile("⃒+")


def _zeilenbild_wie_pymupdf_1_27(text: str) -> str:
    """Fügt vor dem ersten Betragsstrich-Lauf (U+20D2) einer Zeile einen
    Zeilenumbruch ein, sofern davor Text steht (Zeilenbild von 1.27.2.2)."""
    if "⃒" not in text:
        return text
    zeilen = []
    for zeile in text.split("\n"):
        m = _BETRAGSSTRICH_RE.search(zeile)
        if m and m.start() > 0:
            zeile = zeile[: m.start()] + "\n" + zeile[m.start():]
        zeilen.append(zeile)
    return "\n".join(zeilen)


@contextlib.contextmanager
def _textextraktion_wie_nachweislauf():
    """Ersetzt während des Einlesens Page.get_text("text") durch eine Fassung
    mit dem Zeilenbild von PyMuPDF 1.27.2.2 (siehe oben). Läuft unter der
    fitz-Sperre; danach ist alles wie zuvor."""
    if not PYMUPDF_KOMPATIBILITAET:
        yield
        return
    original = pymupdf.Page.get_text

    def get_text(seite, option="text", *args, **kwargs):
        ergebnis = original(seite, option, *args, **kwargs)
        if option == "text" and isinstance(ergebnis, str):
            ergebnis = _zeilenbild_wie_pymupdf_1_27(ergebnis)
        return ergebnis

    with FITZ_SPERRE:
        pymupdf.Page.get_text = get_text
        try:
            yield
        finally:
            pymupdf.Page.get_text = original


@contextlib.contextmanager
def _pymupdf_meldungen_nach(ziel):
    """PyMuPDF schreibt eigene Meldungen (z. B. den Hinweis „The `fitz` API is
    deprecated“ beim „import fitz“ der Setup-Zelle) in einen beim Import
    festgelegten Ausgabestrom – redirect_stdout erreicht sie nicht. Für die
    Dauer des Ladens werden sie ins Ladeprotokoll umgeleitet."""
    if not hasattr(pymupdf, "_g_out_message"):
        yield
        return
    alt = pymupdf._g_out_message
    pymupdf._g_out_message = ziel
    try:
        yield
    finally:
        pymupdf._g_out_message = alt


# =============================================================================
# Notebook laden
# =============================================================================
_UEBERSCHRIFT_RE = re.compile(r"^##\s*(\d+)\s*\|\s*(.*)$")


def _zellen_quelltext(zelle: dict) -> str:
    quelle = zelle.get("source", "")
    return "".join(quelle) if isinstance(quelle, list) else str(quelle)


def notebook_code_zellen(pfad: Path = NOTEBOOK_PFAD) -> list[tuple[int, str]]:
    """Code-Zellen der Abschnitte „## 2 | Setup“ bis „## 7 | LLM-gestützte
    Checks“ (ohne Konfiguration, Ausführung und Bericht), identifiziert über
    die Markdown-Überschriften. Rückgabe: [(Zellindex, Quelltext), ...]."""
    zellen = json.loads(Path(pfad).read_text(encoding="utf-8"))["cells"]
    start = abschnitt7 = None
    ende = len(zellen)
    for i, zelle in enumerate(zellen):
        if zelle.get("cell_type") != "markdown":
            continue
        zeilen = _zellen_quelltext(zelle).strip().splitlines()
        m = _UEBERSCHRIFT_RE.match(zeilen[0].strip()) if zeilen else None
        if not m:
            continue
        nummer, titel = int(m.group(1)), m.group(2)
        if start is None:
            if nummer == 2 and titel.startswith("Setup"):
                start = i
        elif abschnitt7 is None:
            if nummer == 7 and "LLM" in titel:
                abschnitt7 = i
        else:
            ende = i          # nächste Überschrift nach Abschnitt 7
            break
    if start is None or abschnitt7 is None:
        raise RuntimeError(
            f"Notebook-Aufbau nicht erkannt: Überschriften „## 2 | Setup“ und "
            f"„## 7 | LLM-gestützte Checks“ nicht gefunden ({pfad}).")
    return [(i, _zellen_quelltext(zellen[i])) for i in range(start + 1, ende)
            if zellen[i].get("cell_type") == "code"]


# =============================================================================
# Prüflauf (Zustand eines einzelnen Aufrufs von laufe)
# =============================================================================
def _verzoegerungsplan(wert) -> tuple[dict[str, float], float, float]:
    """Simulierte Antwortzeit im Notfallmodus aus notfall_verzoegerung_s:
    (Sekunden je Check-ID, Sekunden für alle übrigen Checks, Streuung).

    * Zahl (auch als Text, z. B. "1.5") – feste Zeit je Anfrage, ±40 %.
    * "live" – gemessene Live-Antwortzeiten je Check (LIVE_ANTWORTZEITEN_S), ±30 %.
    * dict {Check-ID: Sekunden} – eigene Zeiten je Check, ±30 %; nicht
      genannte Checks antworten sofort.
    """
    if wert is None:
        return {}, 0.0, STREUUNG_FEST
    if isinstance(wert, str) and wert.strip().lower() == "live":
        return dict(LIVE_ANTWORTZEITEN_S), 0.0, STREUUNG_JE_CHECK
    if isinstance(wert, dict):
        try:
            je_check = {str(k): max(0.0, float(v)) for k, v in wert.items()}
        except (TypeError, ValueError):
            raise ValueError(f"Ungültige Antwortzeiten je Check: {wert!r}") from None
        return je_check, 0.0, STREUUNG_JE_CHECK
    try:
        return {}, max(0.0, float(wert)), STREUUNG_FEST
    except (TypeError, ValueError):
        raise ValueError(f"Ungültige notfall_verzoegerung_s „{wert}“ – erlaubt: Zahl "
                         f"(Sekunden), \"live\" oder dict je Check-ID") from None


class _Lauf:
    """Hält die Sprachmodell-Antworten eines Prüflaufs (nur im Speicher)."""

    def __init__(self, strecke: "Pruefstrecke", modus: str, modell: str,
                 max_parallel: int, notfall_verzoegerung_s: float | str | dict = 0.0):
        self.strecke = strecke
        self.modus = modus
        self.modell = modell
        # Schlüssel für die Zuordnung Anfrage -> Antwort; im Notfall-Modus
        # identisch mit dem Schlüssel des Referenz-Caches.
        self.schluessel_modell = modell if modus == "live" else REFERENZMODELL
        self.max_parallel = max(1, int(max_parallel))
        self._verzoegerung_je_check, self._verzoegerung_sonst, self._streuung = \
            _verzoegerungsplan(notfall_verzoegerung_s)
        self.abbruch = threading.Event()
        self.sperre = threading.Lock()
        self.antworten: dict[str, Future] = {}
        self.vorgemerkt: dict[str, list[str]] = {}     # Check-ID -> Schlüssel
        self.vorab: dict[str, _Anfrage] = {}           # eindeutige Vorab-Anfragen
        self.anfragen_je_check: Counter = Counter()
        self.live_aufrufe = 0
        self.keine_verbindung = False      # nach dem ersten Verbindungsfehler gesetzt
        self._executor: ThreadPoolExecutor | None = None
        self._client = None
        ns = strecke._ns
        self._ueberspringen = ns["CheckUebersprungen"]
        self._system = ns["_LLM_SYSTEM"]
        self._max_aufrufe = int(ns.get("MAX_LLM_AUFRUFE") or MAX_LLM_AUFRUFE)
        self._werkzeug_ergebnisse = ns.get("werkzeug_ergebnisse")   # Tool Use (Notebook)
        self._max_runden = int(ns.get("MAX_WERKZEUG_RUNDEN") or 5)

    # ----------------------------------------------------------- Grundlagen
    def hinderungsgrund(self) -> str | None:
        """Warum keine Sprachmodell-Anfragen möglich sind (None = möglich)."""
        if self.modus == "live" and not api_schluessel_vorhanden():
            return "Kein API-Schlüssel gesetzt"
        return None

    def anfrage(self, auftrag, text, schema, max_tokens, bild_b64,
                werkzeuge=None) -> _Anfrage:
        return _Anfrage(anfrage_schluessel(self.schluessel_modell, auftrag, text,
                                           schema, bild_b64, werkzeuge),
                        auftrag, text, schema, max_tokens, bild_b64,
                        tuple(werkzeuge or ()))

    def verzoegerung_fuer(self, check_id: str | None) -> float:
        """Typische simulierte Antwortzeit (Sekunden, ohne Streuung) einer
        Anfrage des Checks im Notfallmodus."""
        return self._verzoegerung_je_check.get(check_id, self._verzoegerung_sonst)

    def _beantworte(self, anfrage: _Anfrage, check_id: str | None = None) -> dict:
        """Beschafft die Antwort auf eine Anfrage (läuft im Thread-Pool oder
        synchron): Notfall = Referenz-Cache, Live = Anthropic-API. check_id
        (der Check, der die Anfrage zuerst gestellt hat) bestimmt im
        Notfallmodus die simulierte Antwortzeit."""
        if self.abbruch.is_set():
            raise _LaufAbgebrochen("Prüflauf abgebrochen.")
        if self.modus == "notfall":
            basis = self.verzoegerung_fuer(check_id)
            if basis and self.abbruch.wait(
                    basis * random.uniform(1 - self._streuung, 1 + self._streuung)):
                raise _LaufAbgebrochen("Prüflauf abgebrochen.")
            cache = self.strecke._referenz_cache()
            if anfrage.schluessel not in cache:
                raise self._ueberspringen("Keine gespeicherte Antwort für diese Anfrage")
            return copy.deepcopy(cache[anfrage.schluessel])
        # Live: niemals den Referenz-Cache lesen oder schreiben.
        for versuch in range(len(WIEDERHOLUNG_WARTEZEITEN_S) + 1):
            with self.sperre:
                if self.keine_verbindung:
                    # Ein früherer Versuch hat schon keine Verbindung bekommen:
                    # die übrigen Anfragen enden sofort statt einzeln zu warten.
                    raise SprachmodellFehler(KEINE_VERBINDUNG, verbindung=True)
                if self.live_aufrufe >= self._max_aufrufe:
                    raise self._ueberspringen(
                        f"Sicherheitslimit von {self._max_aufrufe} Sprachmodell-"
                        f"Anfragen je Lauf erreicht.")
                self.live_aufrufe += 1
                if self._client is None:
                    self._client = _neuer_client()
                client = self._client
            try:
                return _live_anfrage(client, self.modell, anfrage, self._system,
                                     self._werkzeug_ergebnisse, self._max_runden)
            except SprachmodellFehler as fehler:
                if fehler.verbindung:
                    self.keine_verbindung = True
                    raise
                if not fehler.voruebergehend or versuch >= len(WIEDERHOLUNG_WARTEZEITEN_S):
                    raise
                # Vorübergehender Fehler: kurz warten (abbrechbar), neu versuchen.
                pause = WIEDERHOLUNG_WARTEZEITEN_S[versuch] * random.uniform(0.8, 1.2)
                if self.abbruch.wait(pause):
                    raise _LaufAbgebrochen("Prüflauf abgebrochen.") from None
        raise AssertionError("nicht erreichbar")

    # --------------------------------------------------- Vorabruf (parallel)
    def vormerken(self, check_id: str, anfragen: list[_Anfrage]):
        """Merkt die gesammelten Anfragen eines Checks vor und gibt alle noch
        unbekannten sofort in den Thread-Pool (laufen parallel im Hintergrund,
        identische Anfragen nur einmal)."""
        self.vorgemerkt[check_id] = [a.schluessel for a in anfragen]
        if self.modus == "live" and anfragen:
            _sdk_aufwaermen()      # vor dem ersten parallelen Abruf (siehe dort)
        with self.sperre:
            for a in anfragen:
                if a.schluessel in self.vorab:
                    continue
                self.vorab[a.schluessel] = a
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(max_workers=self.max_parallel,
                                                        thread_name_prefix="TB-LLM")
                self.antworten[a.schluessel] = self._executor.submit(
                    self._beantworte, a, check_id)

    @staticmethod
    def _beantwortet(zukunft: Future | None) -> bool:
        """Liegt eine Antwort vor? Fehlgeschlagene Anfragen zählen nicht."""
        return (zukunft is not None and zukunft.done() and not zukunft.cancelled()
                and zukunft.exception() is None)

    def fortschritt(self, check_id: str) -> tuple[int, int]:
        """(beantwortete, gesamte) Vorab-Anfragen eines Checks."""
        schluessel = self.vorgemerkt.get(check_id, [])
        fertig = sum(1 for s in schluessel if self._beantwortet(self.antworten.get(s)))
        return fertig, len(schluessel)

    def gesamtfortschritt(self) -> tuple[int, int]:
        """(beantwortete, gesamte) eindeutige Vorab-Anfragen des ganzen Laufs."""
        fertig = sum(1 for s in list(self.vorab)
                     if self._beantwortet(self.antworten.get(s)))
        return fertig, len(self.vorab)

    # ------------------------------------------------ echter Durchlauf
    def _warte(self, zukunft: Future):
        """Wartet (abbrechbar) auf eine Antwort. Fertig-Sein und Ergebnis
        werden getrennt abgefragt: Steckt in der Zukunft selbst eine
        TimeoutError (z. B. ein Socket-Zeitlimit), darf sie nicht mit dem
        Warte-Zeitlimit verwechselt werden – sonst kreiste die Schleife ewig."""
        while not zukunft.done():
            warte_auf_zukunft([zukunft], timeout=0.2)
            if self.abbruch.is_set() and not zukunft.done():
                raise _LaufAbgebrochen("Prüflauf abgebrochen.")
        if zukunft.cancelled():
            raise _LaufAbgebrochen("Prüflauf abgebrochen.")
        return zukunft.result()

    def bearbeiter_fuer(self, check_id: str) -> Callable:
        """llm_json-Bearbeiter für den echten Durchlauf eines Checks."""
        def echt(auftrag, text, schema, max_tokens, bild_b64, werkzeuge=None):
            grund = self.hinderungsgrund()
            if grund:
                raise self._ueberspringen(grund)
            anfrage = self.anfrage(auftrag, text, schema, max_tokens, bild_b64, werkzeuge)
            with self.sperre:
                self.anfragen_je_check[check_id] += 1
                zukunft = self.antworten.get(anfrage.schluessel)
                neu = zukunft is None
                if neu:
                    zukunft = self.antworten[anfrage.schluessel] = Future()
            if neu:
                # Im Sammeldurchlauf nicht vorhergesehene Anfrage: synchron stellen.
                try:
                    zukunft.set_result(self._beantworte(anfrage, check_id))
                except Exception as fehler:
                    zukunft.set_exception(fehler)
            return copy.deepcopy(self._warte(zukunft))
        return echt

    def beenden(self):
        self.abbruch.set()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)


# =============================================================================
# Prüfstrecke: ein geladenes Dokument samt Notebook-Namensraum
# =============================================================================
class Pruefstrecke:
    """Ein Prüfobjekt mit eigenem, aus dem Notebook erzeugten Namensraum.

    Attribute: dokument ("fehlerhaft"/"fehlerfrei"), pdf_pfad, seitenzahl,
    dok (TBDokument des Notebooks), ladeprotokoll (unterdrückte Ausgaben).
    """

    def __init__(self, dokument: str):
        if dokument not in DOKUMENTE:
            raise ValueError(f"Unbekanntes Dokument „{dokument}“ – erlaubt: "
                             f"{', '.join(DOKUMENTE)}")
        self.dokument = dokument
        self.pdf_pfad = DOKUMENTE[dokument]
        self._lokal = threading.local()   # aktiver llm_json-Bearbeiter je Thread
        self._ns = self._notebook_ausfuehren()
        self.dok = self._ns["dok"]
        self.seitenzahl = self.dok.seitenzahl
        self._dok_absichern()
        # Die Check-Funktionen rufen die globale llm_json ihres Namensraums.
        self._ns["llm_json"] = self._baue_llm_weiche()

    # ------------------------------------------------------------ Laden
    def _notebook_ausfuehren(self) -> dict:
        modul = types.ModuleType(f"tb_validierung_notebook_{self.dokument}")
        ns = modul.__dict__
        # Konfiguration (ersetzt Zelle „## 1 | Konfiguration“) – absolute Pfade.
        ns.update({
            "__builtins__": builtins,
            "Path": Path,                         # wird in Zelle 1 importiert
            "TB_PDF_PFAD": self.pdf_pfad,
            "REFERENZ_CSV_ORDNER": REFERENZ_CSV_ORDNER,
            "REFERENZ_DB_PFAD": REFERENZ_DB_PFAD,
            "MODELL": STANDARDMODELL,
            "MAX_LLM_AUFRUFE": MAX_LLM_AUFRUFE,
            "LLM_CACHE_PFAD": REFERENZ_CACHE_PFAD,  # nur zum Lesen
            "BERICHT_PFAD": None,
            # L-04: Gesetzestexte live nachschlagen; ohne Internet die
            # gespeicherte Kopie (nur lesen – die Demo schreibt nichts ins Repo)
            "NORMTEXT_QUELLE": NORMTEXT_QUELLE,
            "NORMTEXT_KOPIE": NORMTEXT_KOPIE_PFAD,
            "NORMTEXT_KOPIE_AKTUALISIEREN": False,
        })
        sys.modules[modul.__name__] = modul      # für dataclasses & Tracebacks
        puffer = io.StringIO()
        with FITZ_SPERRE, _textextraktion_wie_nachweislauf(), \
                _pymupdf_meldungen_nach(puffer), contextlib.redirect_stdout(puffer):
            for index, quelltext in notebook_code_zellen():
                dateiname = f"<{NOTEBOOK_PFAD.name}, Zelle {index}>"
                linecache.cache[dateiname] = (len(quelltext), None,
                                              quelltext.splitlines(True), dateiname)
                exec(compile(quelltext, dateiname, "exec"), ns)
        self.ladeprotokoll = puffer.getvalue()
        fehlend = [n for n in ("CHECKS", "dok", "llm_json", "CheckUebersprungen",
                               "_LLM_SYSTEM") if n not in ns]
        if fehlend or not ns["CHECKS"]:
            raise RuntimeError(f"Notebook-Ausführung unvollständig, es fehlen: {fehlend}")
        return ns

    def _dok_absichern(self):
        """Die beiden fitz-Methoden, die Checks während des Laufs nutzen,
        laufen unter der fitz-Sperre und merken sich ihr (deterministisches)
        Ergebnis – Sammel- und echter Durchlauf rendern so nur einmal.
        Die Check-Logik bleibt unverändert."""
        dok = self.dok
        png_original, grafik_original = dok.seite_als_png_b64, dok.grafik_seiten
        png_cache: dict = {}
        grafik_cache: dict = {}

        def seite_als_png_b64(nummer: int, dpi: int = 120) -> str:
            with FITZ_SPERRE:
                if (nummer, dpi) not in png_cache:
                    png_cache[(nummer, dpi)] = png_original(nummer, dpi=dpi)
                return png_cache[(nummer, dpi)]

        def grafik_seiten(min_pfade: int = 40):
            with FITZ_SPERRE:
                if min_pfade not in grafik_cache:
                    grafik_cache[min_pfade] = grafik_original(min_pfade=min_pfade)
                return list(grafik_cache[min_pfade])

        dok.seite_als_png_b64 = seite_als_png_b64
        dok.grafik_seiten = grafik_seiten

    def _baue_llm_weiche(self) -> Callable:
        lokal = self._lokal
        ueberspringen = self._ns["CheckUebersprungen"]

        def llm_json(auftrag: str, text: str, schema: dict, max_tokens: int = 8000,
                     bild_b64: str | None = None, werkzeuge: list | None = None) -> dict:
            """Ersatz für llm_json des Notebooks (gleiche Signatur): leitet die
            Anfrage an den Bearbeiter des aktiven Prüflaufs weiter."""
            bearbeiter = getattr(lokal, "bearbeiter", None)
            if bearbeiter is None:
                raise ueberspringen("Kein Prüflauf aktiv – Sprachmodell nicht verbunden.")
            return bearbeiter(auftrag, text, schema, max_tokens, bild_b64, werkzeuge)
        return llm_json

    def _referenz_cache(self) -> dict:
        """Antworten des Nachweis-Laufs (vom Notebook aus llm_cache.json gelesen)."""
        return self._ns.get("_llm_cache", {})

    # ------------------------------------------------------- Schnittstelle
    def checks(self) -> list[CheckInfo]:
        """Alle Checks in Notebook-Reihenfolge (V-01 … V-13, L-01 … L-06)."""
        ergebnis = []
        for e in self._ns["CHECKS"]:
            erklaerung = ERKLAERUNGEN.get(e["id"])
            if not erklaerung:   # neue Notebook-Checks: erste Docstring-Zeile
                erklaerung = (e["fn"].__doc__ or "").strip().splitlines()[0:1]
                erklaerung = erklaerung[0] if erklaerung else e["titel"]
            ergebnis.append(CheckInfo(e["id"], e["titel"], e["kategorie"],
                                      e["methode"], erklaerung))
        return ergebnis

    def laufe(self, check_ids: list[str], modus: str = "live",
              modell: str = STANDARDMODELL, max_parallel: int = MAX_PARALLEL_STANDARD, *,
              notfall_verzoegerung_s: float | str | dict = 0.0) -> Iterator[Ereignis]:
        """Führt die ausgewählten Checks aus und liefert Ereignisse:

        * "prefetch"  – Sammeldurchlauf der Sprachmodell-Checks; erledigt/gesamt
                        = vorbereitete/ausgewählte LLM-Checks. Die Anfragen
                        jedes vorbereiteten Checks starten sofort parallel im
                        Hintergrund; das letzte prefetch-Ereignis (check_id
                        None) meldet ihre Gesamtzahl (Text und llm_gesamt).
                        Entfällt, wenn keine LLM-Checks gewählt sind oder im
                        Live-Modus kein API-Schlüssel gesetzt ist.
        * "start"     – ein Check beginnt; erledigt = bereits fertige Checks.
        * "llm_fortschritt" – ein Sprachmodell-Check wartet auf Antworten;
                        erledigt/gesamt = vorliegende/erwartete Antworten des Checks.
        * "ergebnis"  – ein Check ist fertig (CheckErgebnis in .ergebnis).
        * "fertig"    – Lauf abgeschlossen.

        Reihenfolge der Ergebnisse = Notebook-Reihenfolge der ausgewählten
        Checks. modus "live" fragt das Modell `modell` an (bis zu
        max_parallel Anfragen gleichzeitig); modus "notfall" spielt die
        Antworten des Nachweis-Laufs ab (kein Netzwerk). notfall_verzoegerung_s
        simuliert dabei optional eine Antwortzeit je Anfrage, damit der Ablauf
        natürlich wirkt:
          Zahl     – feste Sekunden je Anfrage (±40 %),
          "live"   – die gemessenen Live-Antwortzeiten je Check (±30 %, siehe
                     LIVE_ANTWORTZEITEN_S; ein Lauf aller 19 Checks dauert
                     dann mit 24 parallelen Anfragen etwa 30–45 s, mit 8
                     etwa 60–70 s – wie live),
          dict     – eigene Sekunden je Check-ID (±30 %).
        """
        if modus not in ("live", "notfall"):
            raise ValueError(f"Unbekannter Modus „{modus}“ – erlaubt: live, notfall")
        bekannt = {e["id"] for e in self._ns["CHECKS"]}
        unbekannt = [c for c in check_ids if c not in bekannt]
        if unbekannt:
            raise ValueError(f"Unbekannte Check-IDs: {unbekannt}")
        auswahl = set(check_ids)
        eintraege = [e for e in self._ns["CHECKS"] if e["id"] in auswahl]
        lauf = _Lauf(self, modus, modell, max_parallel, notfall_verzoegerung_s)
        return self._laufe(eintraege, lauf)

    # ---------------------------------------------------------- Ablauf
    def _laufe(self, eintraege: list[dict], lauf: _Lauf) -> Iterator[Ereignis]:
        def ereignis(art, check_id, erledigt, gesamt, ergebnis=None, text=""):
            beantwortet, alle = lauf.gesamtfortschritt()
            return Ereignis(art, check_id, erledigt, gesamt, ergebnis, text,
                            beantwortet, alle)

        # Der Modellname in den Prüfumfang-Hinweisen der Checks wird NICHT im
        # (von allen Sitzungen geteilten) Notebook-Namensraum umgestellt –
        # parallele Läufe würden sich sonst gegenseitig überschreiben. Die
        # Checks schreiben dort STANDARDMODELL; _fuehre_aus tauscht ihn je Lauf.
        gesamt = len(eintraege)
        llm_eintraege = [e for e in eintraege if e["methode"] == "LLM"]
        try:
            # 1) Sammeldurchlauf + paralleler Vorabruf aller Modellanfragen
            if llm_eintraege and lauf.hinderungsgrund() is None:
                for i, e in enumerate(llm_eintraege, start=1):
                    anfragen = self._sammle_anfragen(e, lauf)
                    lauf.vormerken(e["id"], anfragen)
                    yield ereignis("prefetch", e["id"], i, len(llm_eintraege),
                                   text=f"{e['id']}: {len(anfragen)} Anfragen vorbereitet")
                yield ereignis("prefetch", None, len(llm_eintraege), len(llm_eintraege),
                               text=f"{len(lauf.vorab)} Anfragen an das Sprachmodell "
                                    f"gestartet (bis zu {lauf.max_parallel} gleichzeitig)")
            # 2) Checks der Reihe nach (deterministische zuerst, wie im Notebook)
            ergebnisse = []
            for nr, e in enumerate(eintraege):
                yield ereignis("start", e["id"], nr, gesamt, text=e["titel"])
                ergebnis = yield from self._fuehre_aus(e, lauf, ereignis)
                ergebnisse.append(ergebnis)
                yield ereignis("ergebnis", e["id"], nr + 1, gesamt, ergebnis,
                               text=f"{e['id']} {e['titel']}: {ergebnis.status}")
            n_fehler = sum(b.schwere == FEHLER for r in ergebnisse for b in r.befunde)
            n_warnungen = sum(b.schwere == WARNUNG for r in ergebnisse for b in r.befunde)
            yield ereignis("fertig", None, gesamt, gesamt,
                           text=f"Prüfung abgeschlossen: {n_fehler} Fehler, "
                                f"{n_warnungen} Warnungen ({gesamt} Checks).")
        finally:
            lauf.beenden()

    def _sammle_anfragen(self, eintrag: dict, lauf: _Lauf) -> list[_Anfrage]:
        """Sammeldurchlauf: der Check läuft mit Attrappen-Antworten; seine
        Anfragen werden nur notiert. Ausnahmen werden bewusst ignoriert."""
        gesammelt: list[_Anfrage] = []

        def sammeln(auftrag, text, schema, max_tokens, bild_b64, werkzeuge=None):
            gesammelt.append(lauf.anfrage(auftrag, text, schema, max_tokens, bild_b64,
                                          werkzeuge))
            return attrappe_aus_schema(schema)

        self._lokal.bearbeiter = sammeln
        try:
            eintrag["fn"](self.dok)
        except Exception:
            pass
        finally:
            self._lokal.bearbeiter = None
        return gesammelt

    def _fuehre_aus(self, eintrag: dict, lauf: _Lauf, ereignis: Callable):
        """Führt einen Check in einem Hilfs-Thread aus, damit währenddessen
        Fortschritts-Ereignisse geliefert werden können (Generator)."""
        ablage: dict = {}

        def arbeit():
            self._lokal.bearbeiter = lauf.bearbeiter_fuer(eintrag["id"])
            try:
                ablage["ergebnis"] = self._rufe_check(eintrag)
            finally:
                self._lokal.bearbeiter = None

        faden = threading.Thread(target=arbeit, name=f"TB-Check {eintrag['id']}",
                                 daemon=True)
        faden.start()
        ist_llm = eintrag["methode"] == "LLM"
        letzter_stand, letzte_meldung = None, time.monotonic()
        while True:
            faden.join(timeout=0.2)
            if not faden.is_alive():
                break
            if ist_llm:
                stand = lauf.fortschritt(eintrag["id"])
                jetzt = time.monotonic()
                if stand != letzter_stand or jetzt - letzte_meldung >= 1.0:
                    letzter_stand, letzte_meldung = stand, jetzt
                    yield ereignis("llm_fortschritt", eintrag["id"], stand[0], stand[1],
                                   text=f"Sprachmodell: {stand[0]} von {stand[1]} "
                                        f"Antworten liegen vor")
        ergebnis = ablage.get("ergebnis") or CheckErgebnis(
            eintrag["id"], eintrag["titel"], eintrag["methode"], FEHLGESCHLAGEN,
            hinweis="Check-Ausführung unerwartet beendet.")
        ergebnis.llm_anfragen = lauf.anfragen_je_check[eintrag["id"]]
        # Modellname im Hinweis: der dieses Laufs (Notfall: Modell des Nachweis-Laufs)
        anzeige_modell = lauf.modell if lauf.modus == "live" else REFERENZMODELL
        if anzeige_modell != STANDARDMODELL:
            ergebnis.hinweis = ergebnis.hinweis.replace(STANDARDMODELL, anzeige_modell)
        return ergebnis

    def _rufe_check(self, eintrag: dict) -> CheckErgebnis:
        """Ruft die Check-Funktion auf; Status-Ableitung exakt wie im Runner
        des Notebooks (Zelle „## 8 | Ausführung“)."""
        ns = self._ns
        start = time.time()
        befunde, hinweis = [], ""
        try:
            befunde, hinweis = eintrag["fn"](self.dok)
            if any(b.schwere == ns["FEHLER"] for b in befunde):
                status = ns["FEHLER"]
            elif befunde:
                status = ns["WARNUNG"]
            else:
                status = ns["BESTANDEN"]
        except ns["CheckUebersprungen"] as grund:
            befunde, status, hinweis = [], ns["UEBERSPRUNGEN"], str(grund)
        except Exception as fehler:   # Check-Absturz soll den Lauf nicht stoppen
            befunde, status = [], ns["FEHLGESCHLAGEN"]
            hinweis = f"{type(fehler).__name__}: {fehler}"
        dauer = round(time.time() - start, 2)
        return CheckErgebnis(
            id=eintrag["id"], titel=eintrag["titel"], methode=eintrag["methode"],
            status=status,
            befunde=[BefundGUI(eintrag["id"], b.beschreibung, b.seite, b.schwere)
                     for b in befunde],
            hinweis=hinweis, dauer_s=dauer)

    # --------------------------------------------- Hilfen für die Anzeige
    def seitentext(self, nummer: int) -> str:
        """Normalisierter Text einer PDF-Seite (1-basiert)."""
        return self.dok.seiten[nummer - 1]["text"]

    def seite_als_png(self, nummer: int, dpi: int = 110) -> bytes:
        """Rendert eine PDF-Seite (1-basiert) als PNG – unter der fitz-Sperre."""
        with FITZ_SPERRE:
            return self.dok._doc[nummer - 1].get_pixmap(dpi=dpi).tobytes("png")


def lade_pruefstrecke(dokument: str) -> Pruefstrecke:
    """Lädt ein Prüfobjekt ("fehlerhaft" oder "fehlerfrei") und führt dazu die
    Notebook-Zellen aus. Teuer (einige Sekunden) – der Aufrufer cached."""
    return Pruefstrecke(dokument)
