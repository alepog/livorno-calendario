#!/usr/bin/env python3
"""
Prove di genera_ics.py contro una finta fonte locale: nessuna rete, nessun
segreto, si lancia con "python prova_genera_ics.py".

La promessa da difendere e' una sola: una partita in casa gia' pubblicata non
si perde mai, qualunque cosa combini il sito della societa'.
"""
import contextlib, io, json, os, re, tempfile, threading, unittest, warnings
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import genera_ics as g

OGGI = date.today()


def fra(giorni, ora="20:30:00"):
    return f"{OGGI + timedelta(days=giorni):%Y-%m-%d} {ora}"


def partita(pid, titolo, data, casa=True, flag=True):
    """Una partita come la restituisce l'API: flag=False simula il campo assente."""
    e = {"id": pid, "title": {"rendered": titolo}, "link": f"https://x.it/{pid}",
         "acf": {"zaki_match_date": data}}
    if flag:
        e["acf"]["zaki_match_info"] = {"zaki_match_team_home": {"livorno": casa},
                                       "zaki_match_team_guest": {"livorno": not casa}}
    return e


class Fonte:
    """Stato della finta fonte: ogni prova lo riscrive come le serve."""
    stagioni = [{"id": 191, "name": "2026/2027"}, {"id": 190, "name": "2025/2026"}]
    partite = {}
    modo = "ok"          # ok | vuoto | cinquecento | nonjson | antibot | paginato


class Sportello(BaseHTTPRequestHandler):
    viste = []           # le intestazioni delle richieste arrivate, per poterle controllare

    def log_message(self, *a):
        pass

    def rispondi(self, codice, corpo, pagine=1):
        self.send_response(codice)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("X-WP-TotalPages", str(pagine))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        Sportello.viste.append(dict(self.headers))
        if Fonte.modo == "vuoto":
            return self.rispondi(200, b"")
        if Fonte.modo == "cinquecento":
            return self.rispondi(500, b'{"code":"guasto"}')
        if Fonte.modo == "nonjson":
            return self.rispondi(200, b"<html>manutenzione</html>")
        if Fonte.modo == "antibot":      # cio' che il sito ha davvero risposto il 18/09
            return self.rispondi(200, b'<html><head><meta http-equiv="refresh" '
                                      b'content="0;/.well-known/sgcaptcha/?r=%2Fwp-json%2F">')
        pezzi = urlparse(self.path)
        query = parse_qs(pezzi.query)
        if pezzi.path.endswith("/season"):
            return self.rispondi(200, json.dumps(Fonte.stagioni).encode())
        elenco = Fonte.partite.get(query.get("season", ["191"])[0], [])
        if Fonte.modo == "paginato" and elenco:
            meta = (len(elenco) + 1) // 2
            pagina = int(query.get("page", ["1"])[0])
            fetta = elenco[:meta] if pagina == 1 else elenco[meta:]
            return self.rispondi(200, json.dumps(fetta).encode(), pagine=2)
        return self.rispondi(200, json.dumps(elenco).encode())


def esegui():
    """Lancia main() come fa il workflow: restituisce (codice di uscita, stampato)."""
    uscita, codice = io.StringIO(), 0
    with contextlib.redirect_stdout(uscita), contextlib.redirect_stderr(io.StringIO()):
        try:
            g.main()
        except SystemExit as e:
            codice = e.code or 0
    return codice, uscita.getvalue()


def contenuto(newline=None):
    """Il calendario sul disco. newline="" per conservare le CRLF."""
    with open(g.USCITA, encoding="utf-8", newline=newline) as f:
        return f.read()


def riscrivi(testo):
    with open(g.USCITA, "w", encoding="utf-8", newline="") as f:
        f.write(testo)


def uid(pid):
    return f"livorno-{pid}@uslivorno.com"


def presenti():
    """UID nel calendario scritto sul disco."""
    return set(re.findall(r"^UID:(.+)$", g.srotola(contenuto()), re.M))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Sportello)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        g.BASE = f"http://127.0.0.1:{cls.server.server_port}/wp-json/wp/v2"
        g.ATTESE = (0, 0, 0)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.prima = os.getcwd()
        self.dove = tempfile.mkdtemp()
        os.chdir(self.dove)
        Fonte.modo = "ok"
        Fonte.stagioni = [{"id": 191, "name": "2026/2027"}, {"id": 190, "name": "2025/2026"}]
        Fonte.partite = {"191": [
            partita(1, "Livorno - Pianese", fra(7, "17:30:00")),
            partita(2, "Pianese - Livorno", fra(14), casa=False),
            partita(3, "Livorno-Gubbio", fra(21, "00:00:00")),
            partita(4, "Livorno - Pescara", fra(-7, "15:00:00")),
        ], "190": []}

    def tearDown(self):
        os.chdir(self.prima)

    def calendario_iniziale(self):
        """Parte da un calendario appena generato, come quello in produzione."""
        codice, _ = esegui()
        self.assertEqual(codice, 0)
        return presenti()


class ProvaLetturaFonte(Base):
    def test_tiene_solo_le_partite_in_casa(self):
        codice, detto = esegui()
        self.assertEqual(codice, 0, detto)
        self.assertEqual(presenti(), {uid(1), uid(3), uid(4)})

    def test_orario_convertito_in_utc_e_tutto_il_giorno(self):
        esegui()
        testo = contenuto()
        atteso = (datetime.strptime(fra(7, "17:30:00"), "%Y-%m-%d %H:%M:%S")
                  .replace(tzinfo=g.ROMA).astimezone(timezone.utc))
        self.assertIn(f"DTSTART:{atteso:%Y%m%dT%H%M%SZ}", testo)
        self.assertIn(f"DTSTART;VALUE=DATE:{OGGI + timedelta(days=21):%Y%m%d}", testo)
        self.assertIn("(orario da definire)", testo)

    def test_si_presenta_come_un_client_normale(self):
        """Il filtro anti-bot del sito rifiuta le richieste anonime: ci si presenta
        con uno User-Agent compatibile coi browser che dice anche chi siamo."""
        Sportello.viste.clear()
        esegui()
        self.assertTrue(Sportello.viste)
        for intestazioni in Sportello.viste:
            self.assertIn("Mozilla/5.0", intestazioni.get("User-Agent", ""))
            self.assertIn("livorno-calendario", intestazioni.get("User-Agent", ""))
            self.assertIn("json", intestazioni.get("Accept", ""))

    def test_paginazione(self):
        Fonte.modo = "paginato"
        esegui()
        self.assertEqual(presenti(), {uid(1), uid(3), uid(4)})

    def test_titolo_inatteso_ma_flag_in_casa(self):
        """Il caso che il vecchio codice perdeva: titolo che non inizia per Livorno."""
        Fonte.partite["191"] = [partita(9, "U.S. Livorno 1915 vs Pianese", fra(5))]
        codice, _ = esegui()
        self.assertEqual(codice, 0)
        self.assertEqual(presenti(), {uid(9)})

    def test_flag_assente_si_ripiega_sul_titolo(self):
        Fonte.partite["191"] = [partita(10, "Livorno - Vado", fra(5), flag=False),
                                partita(11, "Vado - Livorno", fra(9), flag=False)]
        esegui()
        self.assertEqual(presenti(), {uid(10)})

    def test_senza_indizi_la_tiene_e_avvisa(self):
        Fonte.partite["191"] = [partita(12, "Amichevole di gala", fra(5), flag=False)]
        codice, detto = esegui()
        self.assertEqual(codice, 0)
        self.assertEqual(presenti(), {uid(12)})
        self.assertIn("non deducibile", detto)


class ProvaNonSiPerdeNulla(Base):
    def test_risposta_parziale_conserva_il_resto(self):
        tutte = self.calendario_iniziale()
        Fonte.partite["191"] = [partita(1, "Livorno - Pianese", fra(7, "17:30:00"))]
        codice, detto = esegui()
        self.assertEqual(codice, 0, detto)
        self.assertEqual(presenti(), tutte)
        self.assertIn("non e' piu' nell'elenco della fonte", detto)

    def test_data_illeggibile_conserva_il_pubblicato(self):
        tutte = self.calendario_iniziale()
        Fonte.partite["191"] = [partita(1, "Livorno - Pianese", "data sbagliata"),
                                partita(3, "Livorno-Gubbio", fra(21, "00:00:00")),
                                partita(4, "Livorno - Pescara", fra(-7, "15:00:00"))]
        codice, detto = esegui()
        self.assertEqual(codice, 0)
        self.assertEqual(presenti(), tutte)
        self.assertIn("la data non si legge", detto)

    def test_fonte_vuota_lascia_il_file_intatto(self):
        self.calendario_iniziale()
        prima = contenuto()
        Fonte.modo = "vuoto"
        codice, detto = esegui()
        self.assertEqual(codice, 0)
        self.assertEqual(contenuto(), prima)
        self.assertIn("::warning::fonte inutilizzabile", detto)

    def test_guasto_del_sito_lascia_il_file_intatto(self):
        self.calendario_iniziale()
        for modo in ("cinquecento", "nonjson", "antibot"):
            with self.subTest(modo=modo):
                prima = contenuto()
                Fonte.modo = modo
                codice, _ = esegui()
                self.assertEqual(codice, 0)
                self.assertEqual(contenuto(), prima)

    def test_pagina_antibot_riconosciuta_e_spiegata(self):
        """Il guasto vero del 18/09: il file resta, e il log dice di chi e' la colpa."""
        self.calendario_iniziale()
        prima = contenuto()
        Fonte.modo = "antibot"
        codice, detto = esegui()
        self.assertEqual(codice, 0)
        self.assertEqual(contenuto(), prima)
        self.assertIn("pagina anti-bot", detto)

    def test_nessuna_partita_in_casa_non_svuota_il_calendario(self):
        tutte = self.calendario_iniziale()
        Fonte.partite["191"] = [partita(2, "Pianese - Livorno", fra(14), casa=False)]
        codice, detto = esegui()
        self.assertEqual(codice, 0)
        self.assertEqual(presenti(), tutte)
        self.assertIn("nessuna partita in casa", detto)

    def test_fonte_muta_e_calendario_vecchio_diventa_rosso(self):
        self.calendario_iniziale()
        vecchio = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y%m%dT%H%M%SZ")
        testo = contenuto()
        riscrivi(re.sub(r"DTSTAMP:\d{8}T\d{6}Z", f"DTSTAMP:{vecchio}", testo))
        Fonte.modo = "vuoto"
        codice, detto = esegui()
        self.assertEqual(codice, 1)
        self.assertIn("::error::", detto)
        self.assertIn("fermo da 10 giorni", detto)


class ProvaAggiornamenti(Base):
    def test_orario_pubblicato_aggiorna_evento_e_alza_sequence(self):
        self.calendario_iniziale()
        Fonte.partite["191"][2] = partita(3, "Livorno-Gubbio", fra(21, "18:00:00"))
        codice, detto = esegui()
        self.assertEqual(codice, 0)
        testo = g.srotola(contenuto())
        blocco = next(b for b in testo.split("BEGIN:VEVENT") if uid(3) in b)
        self.assertIn("SEQUENCE:1", blocco)
        self.assertNotIn("orario da definire", blocco)
        self.assertIn("cambiata:", detto)

    def test_seconda_esecuzione_non_cambia_nulla(self):
        self.calendario_iniziale()
        prima = contenuto()
        esegui()
        senza_stampo = lambda t: re.sub(r"DTSTAMP:\d{8}T\d{6}Z", "", t)
        self.assertEqual(senza_stampo(contenuto()),
                         senza_stampo(prima))

    def test_trasferta_dichiarata_toglie_la_partita(self):
        self.calendario_iniziale()
        Fonte.partite["191"][0] = partita(1, "Pianese - Livorno", fra(7, "17:30:00"), casa=False)
        codice, detto = esegui()
        self.assertEqual(codice, 0)
        self.assertNotIn(uid(1), presenti())
        self.assertIn("si gioca in trasferta", detto)

    def test_partita_passata_molto_vecchia_si_lascia_andare(self):
        """Il file non cresce all'infinito: dopo OBLIO il passato sparito dalla fonte esce."""
        self.calendario_iniziale()
        antico = (datetime.now(timezone.utc) - timedelta(days=500)).strftime("%Y%m%dT%H%M%SZ")
        testo = contenuto("").replace(
            f"DTSTART:{(datetime.strptime(fra(-7, '15:00:00'), '%Y-%m-%d %H:%M:%S').replace(tzinfo=g.ROMA).astimezone(timezone.utc)):%Y%m%dT%H%M%SZ}",
            f"DTSTART:{antico}")
        riscrivi(testo)
        Fonte.partite["191"] = [partita(1, "Livorno - Pianese", fra(7, "17:30:00"))]
        codice, detto = esegui()
        self.assertEqual(codice, 0)
        self.assertNotIn(uid(4), presenti())      # 500 giorni fa: fuori
        self.assertIn(uid(3), presenti())         # futuro sparito dalla fonte: dentro

    def test_cambio_stagione_tiene_il_futuro_della_precedente(self):
        Fonte.stagioni = [{"id": 192, "name": "2027/2028"}] + Fonte.stagioni
        Fonte.partite["192"] = [partita(20, "Livorno - Carrarese", fra(300, "15:00:00"))]
        Fonte.partite["191"] = [partita(21, "Livorno - Playoff", fra(30, "20:00:00")),
                                partita(22, "Livorno - Vecchia", fra(-60, "15:00:00"))]
        codice, detto = esegui()
        self.assertEqual(codice, 0, detto)
        self.assertEqual(presenti(), {uid(20), uid(21)})
        self.assertIn("2027/2028", contenuto())


class ProvaSorgente(unittest.TestCase):
    def test_niente_escape_ambigue_nel_sorgente(self):
        """Le escape non valide oggi sono un warning, da Python 3.14 un errore.
        Si compila il sorgente da zero: la cache dei .pyc le nasconderebbe."""
        casa = os.path.dirname(os.path.abspath(__file__))
        for nome in ("genera_ics.py", "prova_genera_ics.py"):
            with self.subTest(file=nome), warnings.catch_warnings():
                warnings.simplefilter("error")
                with open(os.path.join(casa, nome), encoding="utf-8") as f:
                    compile(f.read(), nome, "exec")


class ProvaFileValido(Base):
    def test_righe_entro_75_ottetti_e_srotolabili(self):
        lungo = "Livorno - Societa' Sportiva Dilettantistica dal Nome Lunghissimo 1915"
        Fonte.partite["191"] = [partita(30, lungo, fra(3, "19:00:00"))]
        esegui()
        testo = contenuto("")
        for riga in testo.split("\r\n"):
            self.assertLessEqual(len(riga.encode("utf-8")), 75, riga)
        self.assertIn(f"SUMMARY:{lungo}".replace(",", "\\,"), g.srotola(testo))

    def test_niente_file_temporaneo_in_giro(self):
        esegui()
        self.assertFalse(os.path.exists(g.USCITA + ".tmp"))
        self.assertEqual(sorted(os.listdir(".")), [g.USCITA])

    def test_la_verifica_intercetta_una_partita_persa(self):
        esegui()
        testo = contenuto("")
        guai = g.verifica(testo, {uid(1), uid(3), uid(4), uid(99)})
        self.assertTrue(any("partite perse per strada" in x for x in guai), guai)
        self.assertEqual(g.verifica(testo, {uid(1), uid(3), uid(4)}), [])

    def test_la_verifica_intercetta_una_sparizione_senza_motivo(self):
        """Rete di sicurezza sulla fusione: se un UID pubblicato esce dal file
        senza essere fra quelli tolti di proposito, il controllo lo grida."""
        esegui()
        testo = contenuto("")
        guai = g.verifica(testo, {uid(1), uid(3), uid(4)},
                          pubblicati={uid(1), uid(3), uid(4), uid(7)}, tolti=set())
        self.assertTrue(any("scomparse senza una ragione" in x for x in guai), guai)
        self.assertEqual(g.verifica(testo, {uid(1), uid(3), uid(4)},
                                    pubblicati={uid(1), uid(3), uid(4), uid(7)},
                                    tolti={uid(7)}), [])

    def test_la_verifica_intercetta_un_file_rotto(self):
        self.assertTrue(g.verifica("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", set()))
        rotto = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nEND:VEVENT\r\n"
                 "END:VCALENDAR\r\n")
        guai = g.verifica(rotto, {"x"})
        self.assertTrue(any("DTSTART" in x for x in guai), guai)


if __name__ == "__main__":
    unittest.main(verbosity=2)
