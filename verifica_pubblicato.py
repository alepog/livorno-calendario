#!/usr/bin/env python3
"""
Confronta il calendario PUBBLICATO con i dati della societa', adesso.

Non tocca niente: scarica l'ics da GitHub Pages come fa l'iPhone, rilegge la
fonte, e dice partita per partita se coincidono. Serve a rispondere alla
domanda "posso fidarmi di quello che vedo sul telefono?".

  python3 verifica_pubblicato.py

Esce con 0 se tutto torna, con 1 se c'e' una differenza.
"""
import re
import sys
from datetime import datetime, timezone

import genera_ics as g

PUBBLICATO = "https://alepog.github.io/livorno-calendario/livorno.ics"


def scarica(url):
    import urllib.request
    req = urllib.request.Request(url, headers=g.INTESTAZIONI)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def eventi_pubblicati_online(testo):
    """UID -> (data, ora o None) di cio' che il telefono scarica adesso."""
    fuori = {}
    for blocco in re.findall(r"BEGIN:VEVENT\n(.*?)\nEND:VEVENT", g.srotola(testo), re.S):
        uid = re.search(r"^UID:(.+)$", blocco, re.M)
        avvio = re.search(r"^DTSTART(?:;[^:]*)?:(\S+)$", blocco, re.M)
        if not (uid and avvio):
            continue
        v = avvio.group(1)
        if v.endswith("Z"):
            q = (datetime.strptime(v, "%Y%m%dT%H%M%SZ")
                 .replace(tzinfo=timezone.utc).astimezone(g.ROMA))
            fuori[uid.group(1)] = (q.date(), q.strftime("%H:%M"))
        else:
            fuori[uid.group(1)] = (datetime.strptime(v[:8], "%Y%m%d").date(), None)
    return fuori


def leggibile(x):
    if x is None:
        return "assente"
    giorno, ora = x
    return f"{giorno:%d/%m/%Y} " + (ora if ora else "da definire")


def main():
    partite, _, stagione = g.raduna()
    online = eventi_pubblicati_online(scarica(PUBBLICATO))

    print(f"stagione {stagione}   in casa secondo la societa': {len(partite)}   "
          f"eventi sul calendario: {len(online)}")
    print(f"{'partita':<34}{'societa':<24}{'calendario':<24}esito")
    guai = []
    for uid, p in sorted(partite.items(), key=lambda x: x[1]["quando"]):
        atteso = (p["quando"].date(), None if p["da_definire"] else f'{p["quando"]:%H:%M}')
        trovato = online.get(uid)
        if trovato is None:
            esito, guai = "MANCA", guai + [uid]
        elif trovato == atteso:
            esito = "ok"
        else:
            esito, guai = "DIVERSO", guai + [uid]

        print(f'{p["titolo"][:33]:<34}{leggibile(atteso):<24}{leggibile(trovato):<24}{esito}')

    per_troppo = set(online) - set(partite)
    for uid in sorted(per_troppo):
        print(f"{uid[:33]:<34}{'non in elenco':<24}"
              f"{leggibile(online[uid]):<24}in piu' (tenuto di proposito)")

    eta = g.eta_calendario()
    if eta is not None:
        print(f"\nil file in locale e' stato generato {int(eta.total_seconds() // 3600)} ore fa")
    if guai:
        print(f"DIFFERENZE: {len(guai)} -> {', '.join(guai)}")
        sys.exit(1)
    print("tutto coincide" + (f", piu' {len(per_troppo)} evento/i tenuti dopo essere spariti "
                              f"dalla fonte" if per_troppo else ""))



if __name__ == "__main__":
    main()
