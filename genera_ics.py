#!/usr/bin/env python3
"""
Genera livorno.ics con le partite IN CASA dell'US Livorno 1915.

Fonte: API pubblica del sito ufficiale uslivorno.com (nessuna chiave richiesta).
La stagione viene rilevata da sola, quindi lo script continua a funzionare
ad ogni cambio di stagione senza manutenzione.

Regola d'oro: una partita in casa gia' pubblicata non si perde mai.
Tre difese, in ordine:

1. casa o trasferta si legge dal campo apposito della fonte
   (acf.zaki_match_info.zaki_match_team_home.livorno) e non dal titolo:
   un titolo scritto in modo inatteso non fa piu' sparire una partita;
2. l'elenco nuovo viene FUSO con quello gia' pubblicato, per UID: una risposta
   parziale o un guasto della fonte possono solo aggiungere o correggere, mai
   cancellare. Si toglie solo cio' che la fonte dichiara esplicitamente in
   trasferta e cio' che e' passato da piu' di OBLIO;
3. il file completo viene validato prima di sostituire quello in uso: fra i
   controlli c'e' che nessuna partita gia' pubblicata sia sparita senza una
   ragione dichiarata, quindi anche un errore nella fusione qui si vede. La
   scrittura e' atomica: se qualcosa non torna resta il file di prima.

Le partite senza orario ufficiale diventano eventi "tutto il giorno":
appena il club pubblica l'orario, l'esecuzione successiva le converte.

Se la fonte non risponde, ogni richiesta viene ritentata; se non se ne cava
nulla il file resta quello di prima con un avviso, e diventa un errore rosso
solo se il calendario non si aggiorna da piu' di TOLLERANZA, cosi' un intoppo
passeggero del sito non fa scattare un allarme inutile.
"""
import html, http.client, json, os, re, sys, time, urllib.error, urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE         = "https://www.uslivorno.com/wp-json/wp/v2"
ROMA         = ZoneInfo("Europe/Rome")
DURATA       = timedelta(hours=2)
LUOGO        = "Stadio Armando Picchi, Livorno"
USCITA       = "livorno.ics"
TENTATIVI    = 4
ATTESE       = (3, 10, 30)         # secondi fra un tentativo e il successivo
TOLLERANZA   = timedelta(days=3)   # oltre questa eta' del file la fonte muta diventa un errore
STAGIONI     = 2                   # stagioni da guardare: la corrente piu' la precedente
OBLIO        = timedelta(days=400)  # dopo quanto una partita passata sparita dalla fonte si lascia andare
OBBLIGATORIE = ("UID", "DTSTART", "SUMMARY", "DTSTAMP")


class Temporaneo(Exception):
    """Fonte non disponibile o illeggibile: ha senso riprovare piu' tardi."""


def avvisa(testo):
    print(f"::warning::{testo}")


# --------------------------------------------------------------- lettura fonte

def chiedi(url):
    """Una richiesta con ritentativi: restituisce (dati, intestazioni)."""
    motivo = None
    for n in range(TENTATIVI):
        if n:
            time.sleep(ATTESE[min(n - 1, len(ATTESE) - 1)])
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "livorno-calendario"})
            with urllib.request.urlopen(req, timeout=30) as r:
                corpo, intestazioni = r.read(), r.headers
            if not corpo.strip():
                raise Temporaneo("risposta vuota")
            try:
                dati = json.loads(corpo)
            except json.JSONDecodeError:
                raise Temporaneo("risposta non JSON (%s)"
                                 % corpo[:120].decode("utf-8", "replace").replace("\n", " "))
            if not isinstance(dati, list):
                raise Temporaneo(f"atteso un elenco, arrivato {str(dati)[:120]}")
            return dati, intestazioni
        except urllib.error.HTTPError as e:
            motivo = f"HTTP {e.code}"
        except Temporaneo as e:
            motivo = str(e)
        except (OSError, http.client.HTTPException) as e:
            motivo = f"rete: {e}"
        print(f"tentativo {n + 1}/{TENTATIVI} fallito - {motivo}", file=sys.stderr)
    raise Temporaneo(f"{motivo} su {url}")


def leggi(url):
    """Legge un endpoint seguendo la paginazione di WordPress."""
    dati, intestazioni = chiedi(f"{url}&page=1")
    try:
        pagine = int(intestazioni.get("X-WP-TotalPages") or 1)
    except ValueError:
        pagine = 1
    for p in range(2, pagine + 1):
        altri, _ = chiedi(f"{url}&page={p}")
        dati += altri
    return dati


def stagioni():
    righe = leggi(f"{BASE}/season?per_page=100&_fields=id,name")
    if not righe:
        raise Temporaneo("elenco stagioni vuoto")
    righe.sort(key=lambda r: r.get("id") or 0, reverse=True)
    return [(r["id"], r.get("name") or "?") for r in righe if r.get("id")]


# ------------------------------------------------------ casa, trasferta, orari

def dove(e, titolo):
    """(in casa?, lo dice la fonte?): in casa e' True/False, None se non si capisce."""
    info = (e.get("acf") or {}).get("zaki_match_info") or {}
    casa = (info.get("zaki_match_team_home") or {}).get("livorno")
    ospite = (info.get("zaki_match_team_guest") or {}).get("livorno")
    if isinstance(casa, bool) and isinstance(ospite, bool) and casa != ospite:
        return casa, True                        # campo apposito della fonte: fa fede
    primo = re.split(r"\s*-\s*", titolo, maxsplit=1)[0]
    if "livorno" in primo.lower():
        return True, False                       # ripiego sul titolo: il Livorno e' il primo
    if "-" in titolo and "livorno" in titolo.lower():
        return False, False
    return None, False


def estrai(e):
    """(partita, trasferta certa): la partita se e' in casa, altrimenti None."""
    uid = f'livorno-{e["id"]}@uslivorno.com'
    titolo = html.unescape(re.sub("<[^>]+>", "", (e.get("title") or {}).get("rendered", "")))
    titolo = re.sub(r"\s+", " ", titolo.replace("\u2013", "-").replace("\u2014", "-")).strip()
    casa, lo_dice_la_fonte = dove(e, titolo)
    if casa is False:
        return None, lo_dice_la_fonte
    if casa is None:
        avvisa(f'{uid} "{titolo}": casa o trasferta non deducibile, '
               f"la tengo per non rischiare di perderla")
    grezza = (e.get("acf") or {}).get("zaki_match_date")
    try:
        quando = datetime.strptime(grezza, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        avvisa(f'{uid} "{titolo}" e in casa ma la data non si legge ({grezza!r}): '
               f"per ora non entra nel calendario")
        return None, False
    return {"uid": uid,
            "titolo": titolo,
            "quando": quando,
            "da_definire": quando.hour == 0 and quando.minute == 0,
            "link": e.get("link") or ""}, False


def raduna():
    """Partite in casa: tutta la stagione in corso, piu' le sole partite ancora
    da giocare delle stagioni precedenti (copre il passaggio di stagione).
    Restituisce (partite per UID, UID dichiarati in trasferta, nome stagione)."""
    partite, trasferte, nome, lette = {}, set(), None, 0
    for sid, nome_stagione in stagioni():
        grezze = leggi(f"{BASE}/match?season={sid}&per_page=100&_fields=id,title,acf,link")
        if not grezze:
            continue
        corrente = nome is None
        if corrente:
            nome = nome_stagione
        for e in grezze:
            if not e.get("id"):
                continue
            p, in_trasferta = estrai(e)
            if p and (corrente or p["quando"].date() >= date.today()):
                partite[p["uid"]] = p
            elif in_trasferta:
                trasferte.add(f'livorno-{e["id"]}@uslivorno.com')
        lette += 1
        if lette == STAGIONI:
            break
    return partite, trasferte, (nome or "?")


# ------------------------------------------------------------------ testo ICS

def esc(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;")
             .replace(",", "\\,").replace("\n", "\\n"))


def piega(riga):
    """Le righe ICS non possono superare i 75 ottetti."""
    b = riga.encode("utf-8")
    if len(b) <= 75:
        return riga
    pezzi, cur = [], b""
    for ch in riga:
        c = ch.encode("utf-8")
        if len(cur) + len(c) > (75 if not pezzi else 74):
            pezzi.append(cur.decode("utf-8"))
            cur = b""
        cur += c
    pezzi.append(cur.decode("utf-8"))
    return "\r\n ".join(pezzi)


def srotola(testo):
    """Rimette insieme le righe piegate, per poter rileggere un ICS."""
    return testo.replace("\r\n", "\n").replace("\n ", "").replace("\n\t", "")


def righe_evento(p):
    R = [f'UID:{p["uid"]}']
    if p["da_definire"]:
        g = p["quando"].date()
        R += [f"DTSTART;VALUE=DATE:{g:%Y%m%d}",
              f"DTEND;VALUE=DATE:{g + timedelta(days=1):%Y%m%d}",
              "SUMMARY:" + esc(p["titolo"] + " (orario da definire)")]
    else:
        ini = p["quando"].replace(tzinfo=ROMA).astimezone(timezone.utc)
        R += [f"DTSTART:{ini:%Y%m%dT%H%M%SZ}",
              f"DTEND:{ini + DURATA:%Y%m%dT%H%M%SZ}",
              "SUMMARY:" + esc(p["titolo"])]
    R += ["LOCATION:" + esc(LUOGO)]
    if p["link"]:
        R += ["DESCRIPTION:" + esc(p["link"])]
    return R


def ics(eventi, nome_stagione):
    L = ["BEGIN:VCALENDAR",
         "VERSION:2.0",
         "PRODID:-//uslivorno-casa//IT",
         "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH",
         "X-WR-CALNAME:Livorno - Partite in casa",
         f"X-WR-CALDESC:Partite casalinghe US Livorno 1915 - stagione {nome_stagione}",
         "X-WR-TIMEZONE:Europe/Rome",
         "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
         "X-PUBLISHED-TTL:PT12H"]
    for righe in eventi:
        L += ["BEGIN:VEVENT"] + righe + ["END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(piega(r) for r in L) + "\r\n"


# ------------------------------------------------ cio' che e' gia' pubblicato

def eventi_pubblicati():
    """UID -> proprieta' degli eventi che stanno in livorno.ics adesso."""
    try:
        with open(USCITA, encoding="utf-8") as f:
            testo = srotola(f.read())
    except OSError:
        return {}
    fuori = {}
    for blocco in re.findall(r"BEGIN:VEVENT\n(.*?)\nEND:VEVENT", testo, re.S):
        righe = [r for r in blocco.split("\n") if ":" in r]
        prop = {r.split(":", 1)[0]: r.split(":", 1)[1] for r in righe}
        if prop.get("UID"):
            fuori[prop["UID"]] = {"righe": righe, "prop": prop}
    return fuori


def giorno_di(pubblicato):
    """La data di un evento gia' pubblicato, letta dal suo DTSTART."""
    for chiave, valore in pubblicato["prop"].items():
        if chiave.split(";")[0] == "DTSTART":
            v = valore.strip()
            try:
                if v.endswith("Z"):
                    return (datetime.strptime(v, "%Y%m%dT%H%M%SZ")
                            .replace(tzinfo=timezone.utc).astimezone(ROMA).date())
                return datetime.strptime(v[:8], "%Y%m%d").date()
            except ValueError:
                return None
    return None


def firma(righe):
    """Cio' che conta di un evento: fuori i campi di servizio."""
    return tuple(sorted(r for r in righe
                        if not r.startswith(("DTSTAMP", "SEQUENCE", "LAST-MODIFIED"))))


def unisci(partite, trasferte, pubblicati, ora):
    """Fonde la fonte col file in uso: si aggiunge e si corregge, non si cancella.
    Restituisce (eventi in ordine di data, UID che il file deve contenere,
    UID togli di proposito da cio' che era pubblicato)."""
    limite = date.today() - OBLIO
    eventi, tolti = [], set()
    for uid, p in partite.items():
        righe = righe_evento(p)
        prima = pubblicati.get(uid)
        seq, ultima = 0, ora
        if prima:
            try:
                seq = int(prima["prop"].get("SEQUENCE", 0))
            except ValueError:
                seq = 0
            if firma(prima["righe"]) == firma(righe):
                ultima = prima["prop"].get("LAST-MODIFIED") or ora
            else:
                seq += 1
                print(f'  cambiata: {p["titolo"]} -> {p["quando"]:%d/%m/%Y %H:%M}')
        elif pubblicati:
            print(f'  nuova: {p["titolo"]} -> {p["quando"]:%d/%m/%Y %H:%M}')
        eventi.append((p["quando"].date(),
                       righe + [f"DTSTAMP:{ora}", f"SEQUENCE:{seq}", f"LAST-MODIFIED:{ultima}"]))
    for uid, prima in pubblicati.items():
        if uid in partite:
            continue
        if uid in trasferte:
            avvisa(f"{uid} per la fonte ora si gioca in trasferta: lo tolgo dal calendario")
            tolti.add(uid)
            continue
        g = giorno_di(prima)
        if g is None:
            avvisa(f"{uid} nel calendario senza una data leggibile: lo tolgo")
            tolti.add(uid)
            continue
        if g < limite:
            tolti.add(uid)
            continue                     # passato remoto: si lascia andare
        if g >= date.today():
            avvisa(f"{uid} ({g:%d/%m/%Y}) non e' piu' nell'elenco della fonte: lo tengo "
                   f"comunque, verifica se e' stata spostata o annullata")
        eventi.append((g, prima["righe"]))
    eventi.sort(key=lambda x: x[0])
    finali = [righe for _, righe in eventi]
    attesi = {r.split(":", 1)[1] for righe in finali for r in righe if r.startswith("UID:")}
    return finali, attesi, tolti


# ----------------------------------------------------------------- validazione

def verifica(testo, attesi, pubblicati=frozenset(), tolti=frozenset()):
    """Controlla il file prima di pubblicarlo.
    attesi: UID che devono esserci. pubblicati: UID che c'erano prima.
    tolti: i soli UID che si possono essere persi, perche' via di proposito."""
    guai = []
    if not testo.endswith("\r\n"):
        guai.append("il file non finisce con CRLF")
    for riga in testo.split("\r\n"):
        if len(riga.encode("utf-8")) > 75:
            guai.append(f"riga piu' lunga di 75 ottetti: {riga[:40]}...")
    srotolato = srotola(testo)
    if not srotolato.startswith("BEGIN:VCALENDAR") or "END:VCALENDAR" not in srotolato:
        guai.append("involucro VCALENDAR incompleto")
    blocchi = re.findall(r"BEGIN:VEVENT\n(.*?)\nEND:VEVENT", srotolato, re.S)
    if not (len(blocchi) == srotolato.count("BEGIN:VEVENT") == srotolato.count("END:VEVENT")):
        guai.append("BEGIN e END:VEVENT non bilanciati")
    trovati = []
    for blocco in blocchi:
        chiavi = [r.split(":", 1)[0].split(";", 1)[0] for r in blocco.split("\n") if ":" in r]
        for obbligatoria in OBBLIGATORIE:
            if obbligatoria not in chiavi:
                guai.append(f"evento senza {obbligatoria}: {blocco[:60]}...")
        m = re.search(r"^UID:(.+)$", blocco, re.M)
        if m:
            trovati.append(m.group(1))
    if len(set(trovati)) != len(trovati):
        guai.append("UID duplicati nel file")
    if not trovati:
        guai.append("nessun evento nel file")
    perse = set(attesi) - set(trovati)
    if perse:
        guai.append("partite perse per strada: " + ", ".join(sorted(perse)))
    svanite = set(pubblicati) - set(trovati) - set(tolti)
    if svanite:
        guai.append("partite pubblicate e ora scomparse senza una ragione: "
                    + ", ".join(sorted(svanite)))
    return guai


# ----------------------------------------------------------- esiti e scrittura

def eta_calendario():
    """Da quanto e' fermo livorno.ics, letto dal suo DTSTAMP piu' recente."""
    try:
        with open(USCITA, encoding="utf-8") as f:
            testo = srotola(f.read())
    except OSError:
        return None
    stampi = re.findall(r"^DTSTAMP:(\d{8}T\d{6}Z)", testo, re.MULTILINE)
    if not stampi:
        return None
    ultimo = max(datetime.strptime(s, "%Y%m%dT%H%M%SZ") for s in stampi)
    return datetime.now(timezone.utc) - ultimo.replace(tzinfo=timezone.utc)


def rinuncia(motivo):
    """Niente dati usabili: il file resta com'e'.
    Un intoppo passeggero e' solo un avviso, un calendario fermo da giorni un errore."""
    eta = eta_calendario()
    if eta is not None and eta <= TOLLERANZA:
        avvisa(f"fonte inutilizzabile ({motivo}): {USCITA} lasciato invariato, "
               f"generato {int(eta.total_seconds() // 3600)} ore fa")
        sys.exit(0)
    stato = "assente o senza DTSTAMP" if eta is None else f"fermo da {eta.days} giorni"
    print(f"::error::fonte inutilizzabile ({motivo}) e {USCITA} {stato}")
    sys.exit(1)


def scrivi(testo):
    """Scrittura atomica: il file in uso non resta mai a meta'."""
    tmp = USCITA + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(testo)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, USCITA)


def riassunto(eventi):
    for righe in eventi:
        prop = {r.split(":", 1)[0]: r.split(":", 1)[1] for r in righe}
        avvio = next(v for k, v in prop.items() if k.split(";")[0] == "DTSTART")
        titolo = prop.get("SUMMARY", "?").replace("\\,", ",").replace("\\;", ";")
        if avvio.endswith("Z"):
            q = (datetime.strptime(avvio, "%Y%m%dT%H%M%SZ")
                 .replace(tzinfo=timezone.utc).astimezone(ROMA))
            print(f"  {q:%d/%m/%Y}  {q:%H:%M}".ljust(30) + titolo)
        else:
            g = datetime.strptime(avvio[:8], "%Y%m%d")
            print(f"  {g:%d/%m/%Y}  tutto il giorno".ljust(30) + titolo)


def main():
    ora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pubblicati = eventi_pubblicati()
    try:
        partite, trasferte, nome = raduna()
    except Temporaneo as e:
        rinuncia(str(e))                  # non ritorna
        return
    if not partite:
        rinuncia("nessuna partita in casa nei dati ricevuti")
    print(f"stagione {nome} - in casa dalla fonte: {len(partite)}, "
          f"nel calendario in uso: {len(pubblicati)}")
    eventi, attesi, tolti = unisci(partite, trasferte, pubblicati, ora)
    testo = ics(eventi, nome)
    guai = verifica(testo, attesi, pubblicati, tolti)
    if guai:
        for g in guai:
            print(f"::error::{g}")
        print(f"::error::{USCITA} NON toccato: resta la versione precedente")
        sys.exit(1)
    riassunto(eventi)
    scrivi(testo)
    print(f"scritto {USCITA}: {len(eventi)} partite in casa")


if __name__ == "__main__":
    main()
