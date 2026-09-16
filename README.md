# Calendario partite in casa dell'US Livorno 1915

Genera `livorno.ics` con le sole partite **casalinghe** del Livorno,
leggendole dall'API pubblica del sito ufficiale `uslivorno.com`.

Un workflow lo rigenera ogni giorno: quando la Lega ufficializza un orario
o sposta una partita, il file si aggiorna da solo.

## Iscriversi al calendario

Incollare questo indirizzo come *calendario con abbonamento*
(iPhone: Impostazioni → App → Calendario → Account → Aggiungi account → Altro):

```
https://raw.githubusercontent.com/alepog/livorno-calendario/main/livorno.ics
```

## Note

- La stagione viene rilevata automaticamente: nessuna manutenzione annuale.
- Le partite senza orario ufficiale compaiono come eventi "tutto il giorno"
  e diventano eventi con orario appena il club lo pubblica.
- Casa/trasferta si deduce dal titolo: viene tenuto solo ciò che inizia
  con "Livorno".
