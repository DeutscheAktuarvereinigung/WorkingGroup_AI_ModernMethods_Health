"""Tests der Prüfmaschine (engine.py) – ohne Netzwerk und ohne API-Schlüssel.

Aufruf:   python tests/test_engine_replay.py      (aus dem Ordner gui/)
          (pytest funktioniert ebenfalls, ist aber nicht nötig)

Geprüft wird:
1. Notfall-/Replay-Modus, alle 19 Checks, beide Dokumente: Status und
   Befunde (Beschreibung, Seite, Schwere) stimmen je Check exakt mit den
   Prüfberichten des Nachweis-Laufs überein; Ereignisfolge ist schlüssig.
2. Live-Modus mit einer Attrappe des Anthropic-Clients (kein Netzwerk):
   Sammeldurchlauf + paralleler Vorabruf liefern dieselben Ergebnisse wie der
   Replay; jede eindeutige Anfrage wird genau einmal gestellt; der
   Referenz-Cache wird im Live-Modus nicht angefasst; die Anfrage-Parameter
   (Modell, Streaming-Beta, Fallback, kein thinking) stimmen.
3. Live-Modus ohne API-Schlüssel, Fehlerbehandlung (Ablehnung, Rate-Limit,
   Verbindungsfehler, Fehler mitten im Antwortstrom, eigene Wiederholungen,
   Fallback-Blöcke, …), Client-Einstellungen, fehlende Cache-Einträge,
   Abbruch eines Laufs, Standard von 24 parallelen Anfragen.
4. Notfallmodus im Tempo eines Live-Laufs (notfall_verzoegerung_s="live").
5. Notebook, Cache, Prüfberichte, PDFs und Fehlerprotokoll bleiben unverändert.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import threading
import time
import traceback
import types
from pathlib import Path

import anthropic
import httpx

sys.dont_write_bytecode = True          # keine __pycache__-Ordner im Repo
GUI_ORDNER = Path(__file__).resolve().parents[1]
if str(GUI_ORDNER) not in sys.path:
    sys.path.insert(0, str(GUI_ORDNER))

import engine  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Dateien, die niemals verändert werden dürfen
GESCHUETZT = [engine.NOTEBOOK_PFAD, engine.REFERENZ_CACHE_PFAD,
              *engine.REFERENZBERICHTE.values(), *engine.DOKUMENTE.values(),
              engine.FEHLERPROTOKOLL_PFAD, engine.NORMTEXT_KOPIE_PFAD]

_STRECKEN: dict = {}
_REPLAY: dict = {}     # dokument -> {check_id: CheckErgebnis} aus Test 1


def strecke(dokument: str) -> engine.Pruefstrecke:
    if dokument not in _STRECKEN:
        _STRECKEN[dokument] = engine.lade_pruefstrecke(dokument)
    return _STRECKEN[dokument]


def alle_ids(s: engine.Pruefstrecke) -> list[str]:
    return [c.id for c in s.checks()]


def durchlaufen(s, ids, **kwargs):
    """Führt laufe() vollständig aus: ({id: CheckErgebnis}, [Ereignis])."""
    ereignisse = list(s.laufe(ids, **kwargs))
    ergebnisse = {e.check_id: e.ergebnis for e in ereignisse if e.art == "ergebnis"}
    return ergebnisse, ereignisse


def befund_liste(ergebnis):
    return [(b.beschreibung, b.seite, b.schwere) for b in ergebnis.befunde]


def hash_dateien() -> dict:
    return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in GESCHUETZT}


# =============================================================================
# Attrappe des Anthropic-Clients (kein Netzwerk)
# =============================================================================
class _Strom:
    def __init__(self, nachricht):
        self._nachricht = nachricht

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return self._nachricht


def _nachricht(text, stop_reason="end_turn", stop_details=None):
    return types.SimpleNamespace(
        stop_reason=stop_reason, stop_details=stop_details,
        content=[types.SimpleNamespace(type="thinking", thinking=""),
                 types.SimpleNamespace(type="text", text=text)])


class AttrappenClient:
    """Imitiert client.beta.messages.stream(...) und beantwortet jede Anfrage
    mit der Antwort des Nachweis-Laufs (eigene, nur gelesene Kopie des Caches)."""

    def __init__(self, cache: dict, system: str, verzoegerung_s: float = 0.05):
        self.cache = cache
        self.system = system
        self.verzoegerung_s = verzoegerung_s
        self.schluessel: list[str] = []
        self.sperre = threading.Lock()
        self.aktiv = 0
        self.max_aktiv = 0
        self.parameterfehler: list[str] = []
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(stream=self._stream))

    def _pruefe(self, bedingung, meldung):
        if not bedingung:
            with self.sperre:
                self.parameterfehler.append(meldung)

    def _stream(self, **kw):
        self._pruefe(kw.get("model") == engine.STANDARDMODELL, f"model={kw.get('model')}")
        self._pruefe(kw.get("betas") == ["server-side-fallback-2026-07-01"], "betas")
        self._pruefe(kw.get("extra_body") == {"fallbacks": "default"}, "extra_body")
        self._pruefe("thinking" not in kw, "thinking gesetzt")
        self._pruefe(kw.get("max_tokens", 0) >= 32000, "max_tokens < 32000")
        self._pruefe(kw.get("system") == self.system, "system-Prompt")
        inhalt = kw["messages"][0]["content"]
        bild = None
        if inhalt[0]["type"] == "image":
            bild = inhalt[0]["source"]["data"]
            self._pruefe(inhalt[0]["source"]["media_type"] == "image/png", "media_type")
        auftrag, text = inhalt[-1]["text"].split("\n\n---\n\n", 1)
        schema = kw["output_config"]["format"]["schema"]
        self._pruefe(kw["output_config"]["format"]["type"] == "json_schema", "format")
        # Werkzeuge (L-04): vollständige, strikte Definitionen; Schlüssel mit Werkzeugnamen
        werkzeuge = [types.SimpleNamespace(name=w["name"]) for w in kw.get("tools", [])]
        self._pruefe(all(w.get("strict") is True and w.get("input_schema", {}).get("type") == "object"
                         and w.get("description") for w in kw.get("tools", [])), "Werkzeug-Definition")
        schluessel = engine.anfrage_schluessel(engine.REFERENZMODELL, auftrag, text,
                                               schema, bild, werkzeuge)
        with self.sperre:
            self.schluessel.append(schluessel)
            self.aktiv += 1
            self.max_aktiv = max(self.max_aktiv, self.aktiv)
        try:
            time.sleep(self.verzoegerung_s)
        finally:
            with self.sperre:
                self.aktiv -= 1
        return _Strom(_nachricht(json.dumps(self.cache[schluessel], ensure_ascii=False)))


class _CacheWaechter(dict):
    """Schlägt Alarm, sobald jemand den Referenz-Cache liest."""

    def _verboten(self, *args, **kwargs):
        raise AssertionError("Referenz-Cache wurde im Live-Modus angefasst!")

    __getitem__ = __contains__ = __iter__ = __len__ = get = keys = items = values = _verboten


class _Ersetzt:
    """Kontextmanager: ersetzt Attribute eines Moduls/Objekts vorübergehend."""

    def __init__(self, ziel, **ersatz):
        self.ziel, self.ersatz, self.alt = ziel, ersatz, {}

    def __enter__(self):
        for name, wert in self.ersatz.items():
            self.alt[name] = getattr(self.ziel, name)
            setattr(self.ziel, name, wert)

    def __exit__(self, *args):
        for name, wert in self.alt.items():
            setattr(self.ziel, name, wert)


def _referenz_cache_kopie() -> dict:
    return json.loads(engine.REFERENZ_CACHE_PFAD.read_text(encoding="utf-8"))


# =============================================================================
# Tests
# =============================================================================
def test_replay_gegen_referenzberichte():
    """Notfall-Modus, alle Checks, beide Dokumente == Referenz-Prüfberichte."""
    abweichungen = []
    for dokument in engine.DOKUMENTE:
        s = strecke(dokument)
        ids = alle_ids(s)
        assert len(ids) == 19, f"{dokument}: {len(ids)} Checks statt 19"
        ergebnisse, ereignisse = durchlaufen(s, ids, modus="notfall")
        _REPLAY[dokument] = ergebnisse
        bericht = engine.lade_referenzbericht(dokument)
        referenz = {c["id"]: c for c in bericht["checks"]}
        assert list(ergebnisse) == [c["id"] for c in bericht["checks"]], "Reihenfolge"

        # Ereignisfolge: prefetch* -> (start, llm_fortschritt*, ergebnis)* -> fertig
        arten = [e.art for e in ereignisse]
        assert arten[-1] == "fertig" and arten.count("fertig") == 1
        assert arten.count("start") == arten.count("ergebnis") == 19
        erstes_start = arten.index("start")
        assert all(a == "prefetch" for a in arten[:erstes_start])
        assert "prefetch" not in arten[erstes_start:]
        assert [e.check_id for e in ereignisse if e.art == "start"] == ids

        print(f"\n  {dokument}: {Path(bericht['dokument']).name}")
        print(f"  {'Check':6} {'Referenz':15} {'Engine':15} {'Befunde':>7}  {'LLM':>4}  Ergebnis")
        n_fehler = n_warn = 0
        for cid in ids:
            e, r = ergebnisse[cid], referenz[cid]
            soll = [(b["beschreibung"], b["seite"], b["schwere"]) for b in r["befunde"]]
            gleich = e.status == r["status"] and befund_liste(e) == soll
            if not gleich:
                abweichungen.append(f"{dokument} {cid}: Status {e.status} (Soll {r['status']}), "
                                    f"{len(e.befunde)} Befunde (Soll {len(soll)}) – {e.hinweis[:120]}")
            n_fehler += sum(b.schwere == engine.FEHLER for b in e.befunde)
            n_warn += sum(b.schwere == engine.WARNUNG for b in e.befunde)
            print(f"  {cid:6} {r['status']:15} {e.status:15} {len(e.befunde):>7}  "
                  f"{e.llm_anfragen:>4}  {'OK' if gleich else 'ABWEICHUNG'}")
        z = bericht["zusammenfassung"]
        print(f"  Summe: {n_fehler} Fehler, {n_warn} Warnungen "
              f"(Referenz: {z['fehler']} Fehler, {z['warnungen']} Warnungen)")
        assert (n_fehler, n_warn) == (z["fehler"], z["warnungen"]), "Summen weichen ab"
    assert not abweichungen, "Abweichungen:\n" + "\n".join(abweichungen)


def _erwartete_anfragen(s: engine.Pruefstrecke) -> list[str]:
    """Unabhängige Zählung: Die LLM-Checks laufen direkt (ohne Engine-Ablauf)
    mit einem protokollierenden llm_json, das aus dem Cache antwortet."""
    ns = s._ns
    cache = _referenz_cache_kopie()
    protokoll = []

    def llm_json(auftrag, text, schema, max_tokens=8000, bild_b64=None, werkzeuge=None):
        schluessel = engine.anfrage_schluessel(engine.REFERENZMODELL, auftrag, text,
                                               schema, bild_b64, werkzeuge)
        protokoll.append(schluessel)
        return json.loads(json.dumps(cache[schluessel]))

    weiche = ns["llm_json"]
    ns["llm_json"] = llm_json
    try:
        for eintrag in ns["CHECKS"]:
            if eintrag["methode"] == "LLM":
                eintrag["fn"](s.dok)
    finally:
        ns["llm_json"] = weiche
    return protokoll


def test_live_attrappe_parallel():
    """Live-Modus mit Client-Attrappe: gleiche Ergebnisse wie der Replay,
    jede eindeutige Anfrage genau einmal, parallel, ohne Referenz-Cache."""
    for dokument in engine.DOKUMENTE:
        s = strecke(dokument)
        ids = alle_ids(s)
        if dokument not in _REPLAY:
            _REPLAY[dokument] = durchlaufen(s, ids, modus="notfall")[0]
        erwartet = _erwartete_anfragen(s)
        client = AttrappenClient(_referenz_cache_kopie(), s._ns["_LLM_SYSTEM"])
        echter_cache = s._ns["_llm_cache"]
        s._ns["_llm_cache"] = _CacheWaechter()
        try:
            with _Ersetzt(engine, _neuer_client=lambda: client,
                          api_schluessel_vorhanden=lambda: True):
                start = time.time()
                ergebnisse, ereignisse = durchlaufen(s, ids, modus="live",
                                                     modell=engine.STANDARDMODELL,
                                                     max_parallel=8)
                dauer = time.time() - start
        finally:
            s._ns["_llm_cache"] = echter_cache

        assert not client.parameterfehler, f"Parameterfehler: {client.parameterfehler[:5]}"
        n_live, n_eindeutig = len(client.schluessel), len(set(client.schluessel))
        assert n_live == n_eindeutig == len(set(erwartet)), (
            f"{dokument}: {n_live} Live-Anfragen, {n_eindeutig} eindeutig, "
            f"erwartet {len(set(erwartet))} eindeutige")
        assert set(client.schluessel) == set(erwartet), "andere Anfragen als erwartet"
        assert client.max_aktiv > 1, "Anfragen liefen nicht parallel"
        assert client.max_aktiv <= 8, "mehr als max_parallel gleichzeitig"
        # Vorabruf vor dem ersten Check gestartet
        prefetch = [e for e in ereignisse if e.art == "prefetch"]
        assert prefetch and prefetch[-1].check_id is None
        assert prefetch[-1].llm_gesamt == len(set(erwartet))
        assert ereignisse[-1].llm_beantwortet == ereignisse[-1].llm_gesamt
        # Ergebnisse identisch zum Replay
        replay = _REPLAY[dokument]
        for cid in ids:
            e, r = ergebnisse[cid], replay[cid]
            assert e.status == r.status, f"{dokument} {cid}: {e.status} != {r.status} ({e.hinweis})"
            assert befund_liste(e) == befund_liste(r), f"{dokument} {cid}: Befunde abweichend"
            # Hinweis gleich bis auf den Modellnamen (L-06 kürzt auf 700 Zeichen,
            # daher Vergleich über die gemeinsame Länge)
            h_live = e.hinweis.replace(engine.STANDARDMODELL, engine.REFERENZMODELL)
            n = min(len(h_live), len(r.hinweis))
            assert h_live[:n] == r.hinweis[:n] and n >= len(r.hinweis) - 10, \
                f"{dokument} {cid}: Hinweis abweichend"
            assert e.llm_anfragen == r.llm_anfragen
        n_llm = sum(e.llm_anfragen for e in ergebnisse.values())
        assert n_llm == len(erwartet), f"llm_anfragen {n_llm} != {len(erwartet)}"
        print(f"\n  {dokument}: {n_live} Live-Anfragen (= {n_eindeutig} eindeutige, "
              f"{len(erwartet)} Aufrufe insgesamt), max. {client.max_aktiv} gleichzeitig, "
              f"{dauer:.1f} s, 19/19 Checks identisch zum Replay")


def test_live_ohne_schluessel():
    s = strecke("fehlerhaft")

    def kein_client():
        raise AssertionError("Client darf ohne Schlüssel nicht erzeugt werden")

    with _Ersetzt(engine, _neuer_client=kein_client,
                  api_schluessel_vorhanden=lambda: False):
        ergebnisse, ereignisse = durchlaufen(s, ["L-01", "V-01"], modus="live")
    assert list(ergebnisse) == ["V-01", "L-01"], "Notebook-Reihenfolge"
    assert ergebnisse["V-01"].status == engine.FEHLER
    assert ergebnisse["L-01"].status == engine.UEBERSPRUNGEN
    assert ergebnisse["L-01"].hinweis == "Kein API-Schlüssel gesetzt"
    assert not any(e.art == "prefetch" for e in ereignisse)


def test_live_fehlerbehandlung():
    """Gezielte Fehlerklassen -> verständliche SprachmodellFehler."""
    anfrage = engine._Anfrage("x", "Auftrag", "Text", {"type": "object"}, 4000, None)
    anf = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def client_mit(verhalten):
        def stream(**kw):
            if isinstance(verhalten, BaseException):
                raise verhalten
            return _Strom(verhalten)
        return types.SimpleNamespace(beta=types.SimpleNamespace(
            messages=types.SimpleNamespace(stream=stream)))

    faelle = [
        (_nachricht("{}", "refusal", types.SimpleNamespace(category="cyber")), "abgelehnt"),
        (_nachricht("{}", "max_tokens"), "abgeschnitten"),
        (_nachricht("kein json"), "kein gültiges JSON"),
        (anthropic.RateLimitError("rate", response=httpx.Response(429, request=anf),
                                  body=None), "Rate-Limit"),
        (anthropic.AuthenticationError("auth", response=httpx.Response(401, request=anf),
                                       body=None), "API-Schlüssel"),
        (anthropic.APIStatusError("overloaded", response=httpx.Response(529, request=anf),
                                  body=None), "überlastet"),
        (anthropic.APIStatusError("bad", response=httpx.Response(400, request=anf),
                                  body=None), "als ungültig abgelehnt"),
        (anthropic.NotFoundError("nf", response=httpx.Response(404, request=anf), body={
            "type": "error", "error": {"type": "not_found_error", "message": "model: x"}}),
         "ist nicht verfügbar"),
        (anthropic.InternalServerError("ise", response=httpx.Response(500, request=anf),
                                       body=None), "Störung bei Anthropic"),
        (anthropic.APIConnectionError(request=anf), "Keine Verbindung"),
        (httpx.RemoteProtocolError("peer closed connection"), "während der Antwort abgebrochen"),
        (httpx.ReadTimeout("read timed out"), "während der Antwort abgebrochen"),
    ]
    faelle.append((anthropic.APITimeoutError(request=anf), "Zeitüberschreitung"))
    for verhalten, erwartet in faelle:
        try:
            engine._live_anfrage(client_mit(verhalten), engine.STANDARDMODELL, anfrage, "sys")
        except engine.SprachmodellFehler as fehler:
            assert erwartet in str(fehler), f"„{erwartet}“ fehlt in „{fehler}“"
            assert "Error code" not in str(fehler) and "{" not in str(fehler), str(fehler)
            # Verbindungsausfall (auch Zeitüberschreitung): Hinweis auf den Notfallschalter
            if isinstance(verhalten, anthropic.APIConnectionError):
                assert fehler.verbindung and "Notfallschalter" in str(fehler), str(fehler)
        else:
            raise AssertionError(f"Kein SprachmodellFehler für {erwartet}")
    # Erfolgsfall: erster Text-Block nach dem thinking-Block
    assert engine._live_anfrage(client_mit(_nachricht('{"a": 1}')), engine.STANDARDMODELL,
                                anfrage, "sys") == {"a": 1}

    # Ende-zu-Ende: API-Fehler im Vorabruf -> Check FEHLGESCHLAGEN mit Klartext
    # (Rate-Limit ist vorübergehend: eigene Wiederholungen, hier ohne Wartezeit)
    s = strecke("fehlerhaft")
    fehlerclient = client_mit(anthropic.RateLimitError(
        "rate", response=httpx.Response(429, request=anf), body=None))
    with _Ersetzt(engine, _neuer_client=lambda: fehlerclient,
                  api_schluessel_vorhanden=lambda: True,
                  WIEDERHOLUNG_WARTEZEITEN_S=(0.01, 0.01)):
        ergebnisse, _ = durchlaufen(s, ["L-04"], modus="live")
    e = ergebnisse["L-04"]
    assert e.status == engine.FEHLGESCHLAGEN and "Rate-Limit" in e.hinweis, e.hinweis


# --- Echter SDK-Client mit httpx.MockTransport (kein Netzwerk) --------------
def _sse(*ereignisse) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n"
                   for e in ereignisse).encode("utf-8")


_START = {"type": "message_start", "message": {
    "id": "msg_test", "type": "message", "role": "assistant", "model": engine.STANDARDMODELL,
    "content": [], "stop_reason": None, "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 1}}}


def _sse_erfolg(text: str) -> bytes:
    return _sse(_START,
                {"type": "content_block_start", "index": 0,
                 "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0,
                 "delta": {"type": "text_delta", "text": text}},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn",
                                                    "stop_sequence": None},
                 "usage": {"output_tokens": 5}},
                {"type": "message_stop"})


class _AbbrechenderStrom(httpx.SyncByteStream):
    """Liefert den Anfang eines Antwortstroms und bricht dann ab."""

    def __iter__(self):
        yield _sse(_START)
        raise httpx.RemoteProtocolError("peer closed connection without sending "
                                        "complete message body")


def _sdk_client(antworten: list):
    """Anthropic-Client des SDK, dessen Transport die vorbereiteten Antworten
    der Reihe nach liefert (kein Netzwerk, Platzhalter-Schlüssel)."""
    zaehler = {"n": 0}

    def bearbeite(anfrage: httpx.Request) -> httpx.Response:
        art = antworten[min(zaehler["n"], len(antworten) - 1)]
        zaehler["n"] += 1
        kopf = {"content-type": "text/event-stream"}
        if art == "abbruch":
            return httpx.Response(200, headers=kopf, stream=_AbbrechenderStrom())
        if art == "ueberlastet":
            return httpx.Response(200, headers=kopf, content=_sse(_START, {
                "type": "error", "error": {"type": "overloaded_error",
                                           "message": "Overloaded"}}))
        return httpx.Response(200, headers=kopf, content=_sse_erfolg(art))

    client = anthropic.Anthropic(
        api_key="attrappe-ohne-netz", max_retries=0, base_url="http://attrappe.invalid",
        http_client=httpx.Client(transport=httpx.MockTransport(bearbeite)))
    return client, zaehler


def test_fehler_mitten_im_antwortstrom():
    """Abbruch bzw. SSE-Fehlerereignis nach HTTP 200: verständliche Meldung,
    als vorübergehend gekennzeichnet; der Lauf wiederholt und hat Erfolg."""
    anfrage = engine._Anfrage("x", "Auftrag", "Text", {"type": "object"}, 4000, None)
    for art, erwartet in (("abbruch", "während der Antwort abgebrochen"),
                          ("ueberlastet", "überlastet")):
        client, _ = _sdk_client([art])
        try:
            engine._live_anfrage(client, engine.STANDARDMODELL, anfrage, "sys")
        except engine.SprachmodellFehler as fehler:
            assert erwartet in str(fehler) and fehler.voruebergehend, str(fehler)
            assert "200" not in str(fehler), str(fehler)
        else:
            raise AssertionError(f"Kein SprachmodellFehler für {art}")
    # Erfolg über den echten SDK-Stream
    client, _ = _sdk_client(['{"ok": true}'])
    assert engine._live_anfrage(client, engine.STANDARDMODELL, anfrage, "sys") == {"ok": True}
    # Wiederholung im Lauf: 1. Abbruch, 2. überlastet, 3. Erfolg
    client, zaehler = _sdk_client(["abbruch", "ueberlastet", '{"fehler": []}'])
    s = strecke("fehlerhaft")
    with _Ersetzt(engine, _neuer_client=lambda: client, api_schluessel_vorhanden=lambda: True,
                  WIEDERHOLUNG_WARTEZEITEN_S=(0.01, 0.01)):
        lauf = engine._Lauf(s, "live", engine.STANDARDMODELL, 2, 0.0)
        try:
            ergebnis = lauf._beantworte(anfrage)
        finally:
            lauf.beenden()
    assert ergebnis == {"fehler": []} and zaehler["n"] == 3 and lauf.live_aufrufe == 3


def _verbindungsfehler(anf, ursache):
    """APIConnectionError mit httpx-Ursache, wie das SDK ihn auslöst."""
    try:
        raise anthropic.APIConnectionError(request=anf) from ursache
    except anthropic.APIConnectionError as fehler:
        return fehler


def test_keine_verbindung_beendet_restliche_anfragen():
    """Ganz ohne Verbindung (keine einzige Antwort, wiederholt scheitert schon
    der Verbindungsaufbau) enden die übrigen Anfragen sofort."""
    anf = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    aufrufe = []

    def stream(**kw):
        aufrufe.append(1)
        time.sleep(0.05)
        raise _verbindungsfehler(anf, httpx.ConnectError("keine Verbindung", request=anf))

    client = types.SimpleNamespace(beta=types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=stream)))
    s = strecke("fehlerhaft")
    with _Ersetzt(engine, _neuer_client=lambda: client, api_schluessel_vorhanden=lambda: True,
                  WIEDERHOLUNG_WARTEZEITEN_S=(0.01, 0.01)):
        ergebnisse, ereignisse = durchlaufen(s, ["L-01", "L-04"], modus="live", max_parallel=2)
    gesamt = [e for e in ereignisse if e.art == "prefetch"][-1].llm_gesamt
    for cid in ("L-01", "L-04"):
        e = ergebnisse[cid]
        assert e.status == engine.FEHLGESCHLAGEN and "Keine Verbindung" in e.hinweis, e.hinweis
        assert "Notfallschalter in der Seitenleiste" in e.hinweis, e.hinweis
    assert len(aufrufe) <= 6 < gesamt, (len(aufrufe), gesamt)
    assert ereignisse[-1].llm_beantwortet == 0, "fehlgeschlagene Anfragen sind keine Antworten"


def test_einzelne_abbrueche_beenden_den_lauf_nicht():
    """Das Netz funktioniert, aber einzelne Verbindungen brechen ab (z. B. ein
    Firmen-Proxy unter Last): nur diese Anfragen werden wiederholt, alle
    Checks laufen durch, nichts wird als „keine Verbindung“ abgebrochen."""
    anf = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    s = strecke("fehlerhaft")
    basis = AttrappenClient(_referenz_cache_kopie(), s._ns["_LLM_SYSTEM"], verzoegerung_s=0.01)
    zaehler = {"n": 0, "abbrueche": 0}
    sperre = threading.Lock()

    def stream(**kw):
        with sperre:
            zaehler["n"] += 1
            n = zaehler["n"]
        if n in (3, 6, 7, 12):              # mitten im Lauf: Verbindungen brechen ab
            with sperre:
                zaehler["abbrueche"] += 1
            ursache = (httpx.ReadError("Verbindung zurückgesetzt") if n != 7
                       else httpx.ConnectError("Proxy überlastet", request=anf))
            raise _verbindungsfehler(anf, ursache)
        return basis._stream(**kw)

    client = types.SimpleNamespace(beta=types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=stream)))
    ids = ["L-01", "L-02", "L-03", "L-04"]
    with _Ersetzt(engine, _neuer_client=lambda: client, api_schluessel_vorhanden=lambda: True,
                  WIEDERHOLUNG_WARTEZEITEN_S=(0.01, 0.01)):
        ergebnisse, ereignisse = durchlaufen(s, ids, modus="live", max_parallel=4)
    assert zaehler["abbrueche"] == 4
    for cid in ids:
        assert ergebnisse[cid].status == _REPLAY_STATUS["fehlerhaft"][cid], (cid, ergebnisse[cid].hinweis)
    assert ereignisse[-1].llm_beantwortet == ereignisse[-1].llm_gesamt


def test_fallback_und_modellwahl():
    """Fallback-Parameter nur für Modelle mit server-seitigem Fallback; ein
    Fallback mitten in der Ausgabe setzt das JSON aus allen Text-Blöcken
    zusammen."""
    gesendet = []

    def stream(**kw):
        gesendet.append(kw)
        return _Strom(_nachricht('{"a": 1}'))

    client = types.SimpleNamespace(beta=types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=stream)))
    anfrage = engine._Anfrage("x", "Auftrag", "Text", {"type": "object"}, 4000, None)
    engine._live_anfrage(client, "claude-sonnet-5-5", anfrage, "sys")
    engine._live_anfrage(client, "claude-haiku-5-5", anfrage, "sys")
    assert gesendet[0]["betas"] == ["server-side-fallback-2026-07-01"]
    assert gesendet[0]["extra_body"] == {"fallbacks": "default"}
    assert "betas" not in gesendet[1] and "extra_body" not in gesendet[1]
    # 5er-Generation außer Haiku: mit Fallback; Haiku und ältere Modelle: ohne
    for modell in ("claude-sonnet-5-5", "claude-sonnet-5", "claude-opus-5-5",
                   "claude-opus-5", "claude-fable-5-1", "claude-fable-5", " claude-opus-5-5 "):
        assert engine.hat_server_fallback(modell), modell
    for modell in ("claude-haiku-5-5", "claude-haiku-4-5", "claude-sonnet-4-6",
                   "claude-opus-4-8", "claude-sonnet-50", "", None):
        assert not engine.hat_server_fallback(modell), modell

    def block(typ, text=None):
        return types.SimpleNamespace(type=typ, text=text)

    # Fallback mitten in der Ausgabe: Teilstück + Fortsetzung
    assert engine._json_aus_antwort([block("thinking"), block("text", '{"fehler": ['),
                                     block("fallback"), block("text", ']}')]) == {"fehler": []}
    # Fortsetzung allein gültig (Teilstück verworfen)
    assert engine._json_aus_antwort([block("text", "abc"), block("fallback"),
                                     block("text", '{"b": 2}')]) == {"b": 2}
    # Fallback vor der Ausgabe
    assert engine._json_aus_antwort([block("fallback"), block("thinking"),
                                     block("text", '{"c": 3}')]) == {"c": 3}
    # Mehrere Text-Blöcke nach dem (letzten) Fallback werden verkettet
    assert engine._json_aus_antwort([block("text", '{"x": '), block("fallback"),
                                     block("text", '{"d": '), block("fallback"),
                                     block("text", '{"e": '), block("text", "5}")]) == {"e": 5}
    # Weder Fortsetzung noch Gesamttext gültig -> verständlicher Fehler
    try:
        engine._json_aus_antwort([block("text", "abc"), block("fallback"), block("text", "x")])
    except engine.SprachmodellFehler as fehler:
        assert "kein gültiges JSON" in str(fehler)
    else:
        raise AssertionError("ungültiges JSON nicht erkannt")


def test_client_einstellungen_und_wiederholungen():
    """Client mit kurzem Verbindungs-Zeitlimit; eigene Wiederholungen nur bei
    vorübergehenden Fehlern (z. B. Serverfehler), nicht bei dauerhaften
    (z. B. unbekanntes Modell)."""
    erzeugt = []
    with _Ersetzt(engine, anthropic=types.SimpleNamespace(
            Anthropic=lambda **kw: erzeugt.append(kw) or kw)):
        # test_app.py ersetzt _neuer_client durch eine Netzwerksperre
        getattr(engine, "_neuer_client_echt", engine._neuer_client)()
    kw = erzeugt[-1]          # davor ggf. der Offline-Client aus _sdk_aufwaermen()
    assert kw["max_retries"] == 2, kw
    assert kw["timeout"].connect == 10.0 and kw["timeout"].read == 240.0, kw["timeout"]
    assert "api_key" not in kw, "API-Schlüssel kommt aus der Umgebung"

    anf = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    anfrage = engine._Anfrage("x", "Auftrag", "Text", {"type": "object"}, 4000, None)
    s = strecke("fehlerhaft")
    for ausnahme, versuche, erwartet in (
            (anthropic.InternalServerError("ise", response=httpx.Response(500, request=anf),
                                           body=None), 3, "Störung bei Anthropic"),
            (anthropic.APIStatusError("api", response=httpx.Response(200, request=anf), body={
                "type": "error", "error": {"type": "api_error", "message": "x"}}),
             3, "Störung bei Anthropic"),
            (anthropic.NotFoundError("nf", response=httpx.Response(404, request=anf), body={
                "type": "error", "error": {"type": "not_found_error", "message": "model"}}),
             1, "nicht verfügbar"),
            (anthropic.BadRequestError("bad", response=httpx.Response(400, request=anf), body={
                "type": "error", "error": {"type": "invalid_request_error",
                                           "message": "max_tokens: zu groß"}}),
             1, "als ungültig abgelehnt: max_tokens: zu groß")):
        aufrufe = []

        def stream(**kw):
            aufrufe.append(1)
            raise ausnahme

        client = types.SimpleNamespace(beta=types.SimpleNamespace(
            messages=types.SimpleNamespace(stream=stream)))
        with _Ersetzt(engine, _neuer_client=lambda: client,
                      api_schluessel_vorhanden=lambda: True,
                      WIEDERHOLUNG_WARTEZEITEN_S=(0.01, 0.01)):
            lauf = engine._Lauf(s, "live", "claude-sonnet-5-5", 2)
            try:
                lauf._beantworte(anfrage)
            except engine.SprachmodellFehler as fehler:
                assert erwartet in str(fehler), str(fehler)
                assert not lauf.keine_verbindung
            else:
                raise AssertionError(f"kein Fehler für {type(ausnahme).__name__}")
            finally:
                lauf.beenden()
        assert len(aufrufe) == versuche, (type(ausnahme).__name__, len(aufrufe))


def test_max_parallel_standard():
    """Standard: 24 gleichzeitige Anfragen (statt 8)."""
    import inspect
    standard = inspect.signature(engine.Pruefstrecke.laufe).parameters["max_parallel"].default
    assert standard == engine.MAX_PARALLEL_STANDARD == 24, standard
    s = strecke("fehlerhaft")
    client = AttrappenClient(_referenz_cache_kopie(), s._ns["_LLM_SYSTEM"], verzoegerung_s=0.2)
    with _Ersetzt(engine, _neuer_client=lambda: client, api_schluessel_vorhanden=lambda: True):
        ergebnisse, _ = durchlaufen(s, ["L-01", "L-03"], modus="live")
    assert not client.parameterfehler, client.parameterfehler[:5]
    assert 8 < client.max_aktiv <= 24, client.max_aktiv
    assert all(ergebnisse[c].status == _REPLAY_STATUS["fehlerhaft"][c] for c in ergebnisse)


_REPLAY_STATUS = {"fehlerhaft": {"L-01": engine.FEHLER, "L-02": engine.FEHLER,
                                 "L-03": engine.WARNUNG, "L-04": engine.FEHLER,
                                 "L-05": engine.FEHLER, "L-06": engine.FEHLER,
                                 "V-01": engine.FEHLER}}


def test_notfall_tempo_wie_live():
    """notfall_verzoegerung_s: Zahl (±40 %), "live" (gemessene Antwortzeiten
    je Check, ±30 %) oder dict je Check-ID; ungültige Werte -> ValueError."""
    plan = engine._verzoegerungsplan
    assert plan("live") == (engine.LIVE_ANTWORTZEITEN_S, 0.0, 0.3)
    assert plan(" LIVE ")[0]["L-04"] == 28.0 and plan("live")[0]["L-02"] == 20.0
    assert plan(1.5) == ({}, 1.5, 0.4) and plan("0.5") == ({}, 0.5, 0.4)
    assert plan(None) == ({}, 0.0, 0.4) and plan(-2) == ({}, 0.0, 0.4)
    assert plan({"L-04": 2, "L-01": "0.5"}) == ({"L-04": 2.0, "L-01": 0.5}, 0.0, 0.3)
    s = strecke("fehlerhaft")
    for ungueltig in ("schnell", {"L-04": "lang"}, [1, 2]):
        try:
            s.laufe(["L-04"], modus="notfall", notfall_verzoegerung_s=ungueltig)
        except ValueError:
            pass
        else:
            raise AssertionError(f"kein ValueError für {ungueltig!r}")
    lauf = engine._Lauf(s, "notfall", engine.STANDARDMODELL, 4, "live")
    assert lauf.verzoegerung_fuer("L-04") == 28.0 and lauf.verzoegerung_fuer("V-01") == 0.0
    lauf.beenden()

    # Streuung je Anfrage: Grenzen ±30 % bei "live"
    grenzen = []

    def gleichverteilt(a, b):
        grenzen.append((round(a, 6), round(b, 6)))
        return 1.0

    # Verkürzter Live-Takt (Faktor 1/50): alle Sprachmodell-Checks; Ergebnisse
    # wie im Replay, Dauer bestimmt von der längsten Antwortzeit (L-04).
    verkuerzt = {k: v / 50 for k, v in engine.LIVE_ANTWORTZEITEN_S.items()}
    ids = ["V-01", "L-01", "L-02", "L-03", "L-04", "L-05", "L-06"]
    with _Ersetzt(engine, LIVE_ANTWORTZEITEN_S=verkuerzt,
                  random=types.SimpleNamespace(uniform=gleichverteilt)):
        start = time.time()
        ergebnisse, ereignisse = durchlaufen(s, ids, modus="notfall",
                                             notfall_verzoegerung_s="live")
        dauer = time.time() - start
    assert set(grenzen) == {(0.7, 1.3)}, set(grenzen)
    assert dauer >= verkuerzt["L-04"], f"{dauer:.2f} s < {verkuerzt['L-04']:.2f} s"
    assert dauer < 5, f"{dauer:.2f} s"
    for cid in ids:
        assert ergebnisse[cid].status == _REPLAY_STATUS["fehlerhaft"][cid], cid
    assert ereignisse[-1].llm_beantwortet == ereignisse[-1].llm_gesamt == 65

    # dict: nur die genannten Checks antworten verzögert
    with _Ersetzt(engine, random=types.SimpleNamespace(uniform=lambda a, b: 1.0)):
        start = time.time()
        ergebnisse, _ = durchlaufen(s, ["L-01", "L-06"], modus="notfall",
                                    notfall_verzoegerung_s={"L-06": 0.6})
        dauer = time.time() - start
    assert dauer >= 0.6, f"{dauer:.2f} s"
    assert ergebnisse["L-01"].dauer_s < 0.4, ergebnisse["L-01"].dauer_s
    assert ergebnisse["L-06"].status == engine.FEHLER


def test_api_schluessel_erkennung():
    """ANTHROPIC_API_KEY oder ersatzweise ANTHROPIC_AUTH_TOKEN zählt als
    vorhanden (geprüft mit einer Attrappe der Umgebung, die echte Umgebung
    wird weder gelesen noch verändert)."""
    for umgebung, erwartet in (({}, False), ({"ANTHROPIC_API_KEY": ""}, False),
                               ({"ANTHROPIC_API_KEY": "x"}, True),
                               ({"ANTHROPIC_AUTH_TOKEN": "x"}, True),
                               ({"ANDERES": "x"}, False)):
        with _Ersetzt(engine, os=types.SimpleNamespace(environ=umgebung)):
            ergebnis = engine.api_schluessel_vorhanden()
        assert ergebnis is erwartet, (sorted(umgebung), ergebnis)


def test_warten_auf_zukunft_mit_timeouterror():
    """Eine in der Zukunft gespeicherte TimeoutError wird weitergereicht und
    nicht mit dem Warte-Zeitlimit verwechselt (kein endloses Warten)."""
    from concurrent.futures import Future
    s = strecke("fehlerhaft")
    lauf = engine._Lauf(s, "notfall", engine.STANDARDMODELL, 1, 0.0)
    zukunft = Future()
    zukunft.set_exception(TimeoutError("Socket-Zeitlimit"))
    ergebnis = {}

    def warten():
        try:
            lauf._warte(zukunft)
        except BaseException as fehler:   # noqa: BLE001
            ergebnis["fehler"] = fehler

    faden = threading.Thread(target=warten, daemon=True)
    faden.start()
    faden.join(timeout=3)
    lauf.beenden()
    assert not faden.is_alive(), "_warte hängt"
    assert isinstance(ergebnis.get("fehler"), TimeoutError), ergebnis
    # Erfolgreiche bzw. fehlgeschlagene Zukünfte im Fortschritt
    gut = Future()
    gut.set_result({})
    lauf.antworten = {"a": gut, "b": zukunft}
    lauf.vorgemerkt = {"X": ["a", "b"]}
    assert lauf.fortschritt("X") == (1, 2)


def test_modellname_im_hinweis_je_lauf():
    """Der Modellname im Hinweis gehört zum jeweiligen Lauf; der geteilte
    Notebook-Namensraum bleibt unverändert."""
    s = strecke("fehlerhaft")
    vorher = s._ns["MODELL"]
    ergebnisse, _ = durchlaufen(s, ["L-06"], modus="notfall")
    assert engine.REFERENZMODELL in ergebnisse["L-06"].hinweis
    assert engine.STANDARDMODELL not in ergebnisse["L-06"].hinweis
    assert s._ns["MODELL"] == vorher == engine.STANDARDMODELL


def test_identische_anfragen_nur_einmal():
    """Doppelte Anfragen (auch über Checks hinweg) gehen nur einmal live
    hinaus; im Sammeldurchlauf unbekannte Anfragen werden synchron gestellt."""
    s = strecke("fehlerhaft")
    aufrufe = []

    def stream(**kw):
        aufrufe.append(kw["messages"][0]["content"][-1]["text"])
        return _Strom(_nachricht('{"fehler": []}'))

    client = types.SimpleNamespace(beta=types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=stream)))
    schema = {"type": "object", "properties": {"fehler": {"type": "array"}},
              "required": ["fehler"], "additionalProperties": False}
    with _Ersetzt(engine, _neuer_client=lambda: client,
                  api_schluessel_vorhanden=lambda: True):
        lauf = engine._Lauf(s, "live", engine.STANDARDMODELL, 4, 0.0)
        try:
            a = lauf.anfrage("Auftrag A", "Text", schema, 100, None)
            lauf.vormerken("X", [a, a])
            lauf.vormerken("Y", [a])
            r1 = lauf.bearbeiter_fuer("X")("Auftrag A", "Text", schema, 100, None)
            r2 = lauf.bearbeiter_fuer("Y")("Auftrag A", "Text", schema, 100, None)
            r3 = lauf.bearbeiter_fuer("Y")("Auftrag B", "Text", schema, 100, None)
        finally:
            lauf.beenden()
    assert r1 == r2 == r3 == {"fehler": []}
    assert len(aufrufe) == 2, aufrufe
    assert lauf.anfragen_je_check == {"X": 1, "Y": 2}
    assert lauf.fortschritt("X") == (2, 2)


def test_notfall_fehlender_eintrag():
    s = strecke("fehlerhaft")
    echter_cache = s._ns["_llm_cache"]
    s._ns["_llm_cache"] = {}
    try:
        ergebnisse, _ = durchlaufen(s, ["L-04"], modus="notfall")
    finally:
        s._ns["_llm_cache"] = echter_cache
    assert ergebnisse["L-04"].status == engine.UEBERSPRUNGEN
    assert ergebnisse["L-04"].hinweis == "Keine gespeicherte Antwort für diese Anfrage"


def test_abbruch_und_verzoegerung():
    """Ein abgebrochener Lauf (Generator geschlossen) endet sauber; danach
    funktioniert die Prüfstrecke normal weiter."""
    s = strecke("fehlerhaft")
    lauf = s.laufe(["V-01", "L-05"], modus="notfall", notfall_verzoegerung_s=0.5,
                   max_parallel=2)
    for ereignis in lauf:
        if ereignis.art == "llm_fortschritt":
            break
    start = time.time()
    lauf.close()
    assert time.time() - start < 3, "Abbruch dauert zu lange"
    # Simulierte Antwortzeit im Notfall-Modus (2 Anfragen à 0,3 s ± 40 %)
    start = time.time()
    ergebnisse, ereignisse = durchlaufen(s, ["L-06"], modus="notfall",
                                         notfall_verzoegerung_s=0.3)
    assert time.time() - start >= 0.15, "Verzögerung wirkt nicht"
    assert ergebnisse["L-06"].status == engine.FEHLER
    assert ergebnisse["L-06"].llm_anfragen == 2


def test_schema_attrappe_und_erklaerungen():
    schema = {"type": "object", "properties": {
        "a": {"type": "array"}, "b": {"type": "string", "enum": ["x", "y"]},
        "c": {"type": "integer"}, "d": {"type": "boolean"},
        "e": {"type": "object", "properties": {"f": {"type": "number"}}, "required": ["f"]}},
        "required": ["a", "b", "c", "d", "e"]}
    assert engine.attrappe_aus_schema(schema) == {"a": [], "b": "x", "c": 0, "d": False,
                                                  "e": {"f": 0}}
    infos = strecke("fehlerhaft").checks()
    assert [i.methode for i in infos].count("LLM") == 6
    assert all(i.erklaerung and i.erklaerung in engine.ERKLAERUNGEN.values() for i in infos)


def test_werkzeugschleife():
    """Tool Use im Live-Modus: Claude ruft „gesetzestext“ auf, die Engine führt
    beide Aufrufe aus und schickt die Ergebnisse in EINER Nachricht zurück;
    die Antwort mit den Denk-Blöcken bleibt unverändert im Verlauf."""
    s = strecke("fehlerhaft")
    werkzeug = s._ns["GESETZESTEXT_WERKZEUG"]
    anfrage = engine._Anfrage("k", "Auftrag", "Text", {"type": "object"}, 8000, None, (werkzeug,))
    aufrufe = types.SimpleNamespace(
        stop_reason="tool_use", stop_details=None,
        content=[types.SimpleNamespace(type="thinking", thinking=""),
                 types.SimpleNamespace(type="tool_use", id="t1", name="gesetzestext",
                                       input={"gesetz": "KVAV", "paragraf": "4"}),
                 types.SimpleNamespace(type="tool_use", id="t2", name="gesetzestext",
                                       input={"gesetz": "KVAV", "paragraf": "999"})])
    gesendet = []

    def stream(**kw):
        gesendet.append(copy.deepcopy({k: v for k, v in kw.items() if k != "messages"})
                        | {"messages": list(kw["messages"])})
        return _Strom(aufrufe if len(gesendet) == 1 else _nachricht('{"a": 1}'))

    client = types.SimpleNamespace(beta=types.SimpleNamespace(
        messages=types.SimpleNamespace(stream=stream)))
    alte_quelle = s._ns["NORMTEXT_QUELLE"]
    s._ns["NORMTEXT_QUELLE"] = None          # kein Netzwerk: gespeicherte Kopie
    try:
        ergebnis = engine._live_anfrage(client, engine.STANDARDMODELL, anfrage, "System",
                                        s._ns["werkzeug_ergebnisse"])
    finally:
        s._ns["NORMTEXT_QUELLE"] = alte_quelle
    assert ergebnis == {"a": 1} and len(gesendet) == 2
    erste, zweite = gesendet
    assert [w["name"] for w in erste["tools"]] == ["gesetzestext"]
    assert erste["tools"][0]["strict"] is True and "tool_choice" not in erste
    assert len(zweite["messages"]) == 3
    assert zweite["messages"][1] == {"role": "assistant", "content": aufrufe.content}
    rueck = zweite["messages"][2]
    assert rueck["role"] == "user" and [r["tool_use_id"] for r in rueck["content"]] == ["t1", "t2"]
    assert "3,5 Prozent" in rueck["content"][0]["content"]
    assert "gespeicherte Kopie" in rueck["content"][0]["content"]
    assert rueck["content"][1].get("is_error") is True


def test_gesetzestext_aus_kopie():
    """Ohne Internet liefert „gesetzestext“ den Wortlaut aus normtexte.json;
    ungültige Eingaben werden als verständlicher Fehler gemeldet."""
    ns = strecke("fehlerfrei")._ns
    alte_quelle = ns["NORMTEXT_QUELLE"]
    ns["NORMTEXT_QUELLE"] = None
    try:
        text = ns["gesetzestext"]("VAG", "4")
        assert "Feststellung der Aufsichtspflicht" in text and "gesetze-im-internet.de" in text
        assert "(1) Die sonstigen Zuschläge umfassen" in ns["gesetzestext"]("KVAV", "§ 8")
        for gesetz, paragraf in (("StGB", "1"), ("KVAV", "8; DROP"), ("KVAV", "999")):
            try:
                ns["gesetzestext"](gesetz, paragraf)
                raise AssertionError(f"kein Fehler für {gesetz} {paragraf}")
            except ValueError:
                pass
    finally:
        ns["NORMTEXT_QUELLE"] = alte_quelle
    assert ns["NORMTEXT_KOPIE_AKTUALISIEREN"] is False, "die Demo schreibt nichts ins Repo"


# =============================================================================
# Ausführung ohne pytest
# =============================================================================
def main() -> int:
    vorher = hash_dateien()
    tests = [test_replay_gegen_referenzberichte, test_live_attrappe_parallel,
             test_live_ohne_schluessel, test_live_fehlerbehandlung,
             test_fehler_mitten_im_antwortstrom, test_keine_verbindung_beendet_restliche_anfragen,
             test_einzelne_abbrueche_beenden_den_lauf_nicht,
             test_fallback_und_modellwahl, test_client_einstellungen_und_wiederholungen,
             test_warten_auf_zukunft_mit_timeouterror, test_modellname_im_hinweis_je_lauf,
             test_identische_anfragen_nur_einmal, test_notfall_fehlender_eintrag,
             test_abbruch_und_verzoegerung, test_max_parallel_standard,
             test_notfall_tempo_wie_live, test_api_schluessel_erkennung,
             test_schema_attrappe_und_erklaerungen, test_werkzeugschleife,
             test_gesetzestext_aus_kopie]
    fehlgeschlagen = 0
    for test in tests:
        start = time.time()
        try:
            test()
            print(f"[OK]     {test.__name__} ({time.time() - start:.1f} s)")
        except Exception:
            fehlgeschlagen += 1
            print(f"[FEHLER] {test.__name__}")
            traceback.print_exc()
    nachher = hash_dateien()
    geaendert = [p.name for p in GESCHUETZT if vorher[p] != nachher[p]]
    if geaendert:
        fehlgeschlagen += 1
        print(f"[FEHLER] geschützte Dateien verändert: {geaendert}")
    else:
        print(f"[OK]     {len(GESCHUETZT)} geschützte Dateien unverändert")
    if fehlgeschlagen:
        print(f"\n{fehlgeschlagen} Prüfung(en) fehlgeschlagen")
        return 1
    print(f"\nAlle {len(tests)} Tests bestanden, geschützte Dateien unverändert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
