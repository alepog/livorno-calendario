#!/usr/bin/env python3
"""
Genera livorno.ics con le partite IN CASA dell'US Livorno 1915.

Fonte: API pubblica del sito ufficiale uslivorno.com (nessuna chiave richiesta).
La stagione viene rilevata da sola, quindi lo script continua a funzionare
ad ogni cambio di stagione senza manutenzione.

Le partite senza orario ufficiale diventano eventi "tutto il giorno":
appena il club pubblica l'orario, l'esecuzione successiva le converte.

Se la fonte non risponde o risponde male, ogni richiesta viene ritentata.
Se non se ne cava nulla il file resta quello di prima: solo un avviso finche'
il calendario e' recente, un errore se e' fermo da piu' di TOLLERANZA, cosi'
un intoppo passeggero del sito non fa scattare un allarme inutile.
"""
import html, http.client, json, re, sys, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE       = "https://www.uslivorno.com/wp-json/wp/v2"
ROMA       = ZoneInfo("Europe/Rome")
DURATA     = timedelta(hours=2)
LUOGO      = "Stadio Armando Picchi, Livorno"
USCITA     = "livorno.ics"
TENTATIVI  = 4
ATTESE     = (3, 10, 30)         # secondi fra un tentativo e il successivo
TOLLERANZA = timedelta(days=3)   # oltre questa eta' del file la fonte muta diventa un errore


class Temporaneo(Exception):
    """Fonte non disponibile o illeggibile: ha senso riprovare piu' tardi."""


def leggi(url):
    motivo = None
    for n in range(TENTATIVI):
        if n:
            time.sleep(ATTESE[min(n - 1, len(ATTESE) - 1)])
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "livorno-calendario"})
            with urllib.request.urlopen(req, timeout=30) as r:
                corpo = r.read()
            if not corpo.strip():
                raise Temporaneo("risposta vuota")
            try:
                return json.loads(corpo)
            except json.JSONDecodeError:
                inizio = corpo[:120].decode("utf-8", "replace").replace("\n", " ")
                raise Temporaneo(f"risposta non JSON ({inizio})")
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code not in (403, 408, 425, 429):
                raise                     # richiesta sbagliata: ritentare non serve
            motivo = f"HTTP {e.code}"
        except Temporaneo as e:
            motivo = str(e)
        except (OSError, http.client.HTTPException) as e:
            motivo = f"rete: {e}"
        print(f"tentativo {n + 1}/{TENTATIVI} fallito - {motivo}", file=sys.stderr)
    raise Temporaneo(f"{motivo} su {url}")


def stagione():
    righe = leggi(f"{BASE}/season?per_page=1&orderby=id&order=desc&_fields=id,name")
    if not righe:
        raise Temporaneo("elenco stagioni vuoto")
    return righe[0]["id"], righe[0].get("name", "?")


def partite(season_id):
    dati = leggi(f"{BASE}/match?season={season_id}&per_page=100&_fields=id,title,acf,link")
    out = []
    for e in dati:
        titolo = html.unescape(re.sub("<[^>]+>", "", e["title"]["rendered"])).strip()
        titolo = titolo.replace("\u2013", "-").replace("\u2014", "-")
        titolo = re.sub(r"\s+", " ", titolo)
        if not titolo.lower().startswith("livorno"):
            continue                      # trasferta: si scarta
        grezza = (e.get("acf") or {}).get("zaki_match_date")
        if not grezza:
            continue
        try:
            quando = datetime.strptime(grezza, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        out.append({
            "id": e["id"],
            "titolo": titolo,
            "quando": quando,
            "da_definire": quando.hour == 0 and quando.minute == 0,
            "link": e.get("link", ""),
        })
    return sorted(out, key=lambda x: x["quando"])


def esc(s):
    return (s.replace("\\", "\\\\").replace(";", "\;")
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


def ics(elenco, nome_stagione):
    ora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR",
         "VERSION:2.0",
         "PRODID:-//uslivorno-casa//IT",
         "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH",
         f"X-WR-CALNAME:Livorno - Partite in casa",
         f"X-WR-CALDESC:Partite casalinghe US Livorno 1915 - stagione {nome_stagione}",
         "X-WR-TIMEZONE:Europe/Rome",
         "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
         "X-PUBLISHED-TTL:PT12H"]
    for p in elenco:
        L += ["BEGIN:VEVENT",
              f"UID:livorno-{p['id']}@uslivorno.com",
              f"DTSTAMP:{ora}"]
        if p["da_definire"]:
            g = p["quando"].date()
            L += [f"DTSTART;VALUE=DATE:{g:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{g + timedelta(days=1):%Y%m%d}",
                  piega("SUMMARY:" + esc(p["titolo"] + " (orario da definire)"))]
        else:
            ini = p["quando"].replace(tzinfo=ROMA).astimezone(timezone.utc)
            fin = ini + DURATA
            L += [f"DTSTART:{ini:%Y%m%dT%H%M%SZ}",
                  f"DTEND:{fin:%Y%m%dT%H%M%SZ}",
                  piega("SUMMARY:" + esc(p["titolo"]))]
        L += [piega("LOCATION:" + esc(LUOGO))]
        if p["link"]:
            L += [piega("DESCRIPTION:" + esc(p["link"]))]
        L += ["END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def eta_calendario():
    """Da quanto e' fermo livorno.ics, letto dal suo DTSTAMP piu' recente."""
    try:
        with open(USCITA, encoding="utf-8") as f:
            testo = f.read()
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
        print(f"::warning::fonte inutilizzabile ({motivo}): {USCITA} lasciato invariato, "
              f"generato {int(eta.total_seconds() // 3600)} ore fa")
        sys.exit(0)
    stato = "assente o senza DTSTAMP" if eta is None else f"fermo da {eta.days} giorni"
    print(f"::error::fonte inutilizzabile ({motivo}) e {USCITA} {stato}")
    sys.exit(1)


def main():
    try:
        sid, nome = stagione()
        elenco = partite(sid)
    except Temporaneo as e:
        rinuncia(str(e))                  # non ritorna
        return
    print(f"stagione {nome} (id {sid}) - partite in casa: {len(elenco)}")
    if not elenco:
        rinuncia("nessuna partita in casa nei dati ricevuti")
    for p in elenco:
        q = "tutto il giorno" if p["da_definire"] else f"{p['quando']:%H:%M}"
        print(f"  {p['quando']:%d/%m/%Y}  {q:>15}  {p['titolo']}")
    with open(USCITA, "w", encoding="utf-8", newline="") as f:
        f.write(ics(elenco, nome))
    print(f"scritto {USCITA}")


if __name__ == "__main__":
    main()
