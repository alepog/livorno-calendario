#!/usr/bin/env python3
"""
Genera livorno.ics con le partite IN CASA dell'US Livorno 1915.

Fonte: API pubblica del sito ufficiale uslivorno.com (nessuna chiave richiesta).
La stagione viene rilevata da sola, quindi lo script continua a funzionare
ad ogni cambio di stagione senza manutenzione.

Le partite senza orario ufficiale diventano eventi "tutto il giorno":
appena il club pubblica l'orario, l'esecuzione successiva le converte.
"""
import html, json, re, sys, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE    = "https://www.uslivorno.com/wp-json/wp/v2"
ROMA    = ZoneInfo("Europe/Rome")
DURATA  = timedelta(hours=2)
LUOGO   = "Stadio Armando Picchi, Livorno"
USCITA  = "livorno.ics"


def leggi(url):
    req = urllib.request.Request(url, headers={"User-Agent": "livorno-calendario"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def stagione():
    righe = leggi(f"{BASE}/season?per_page=1&orderby=id&order=desc&_fields=id,name")
    if not righe:
        raise SystemExit("impossibile determinare la stagione corrente")
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


def main():
    sid, nome = stagione()
    elenco = partite(sid)
    print(f"stagione {nome} (id {sid}) - partite in casa: {len(elenco)}")
    if not elenco:
        raise SystemExit("nessuna partita in casa trovata: non sovrascrivo il file")
    for p in elenco:
        q = "tutto il giorno" if p["da_definire"] else f"{p['quando']:%H:%M}"
        print(f"  {p['quando']:%d/%m/%Y}  {q:>15}  {p['titolo']}")
    with open(USCITA, "w", encoding="utf-8", newline="") as f:
        f.write(ics(elenco, nome))
    print(f"scritto {USCITA}")


if __name__ == "__main__":
    main()
