# Calendario partite in casa dell'US Livorno 1915

Genera `livorno.ics` con le sole partite **casalinghe** del Livorno,
leggendole dall'API pubblica del sito ufficiale `uslivorno.com`.

Si rigenera ogni giorno da solo: quando la Lega ufficializza un orario o sposta
una partita, il calendario si aggiorna senza che si debba toccare niente.

## Iscriversi al calendario

Incollare questo indirizzo come *calendario con abbonamento*
(iPhone: Impostazioni → App → Calendario → Account → Aggiungi account → Altro):

```
webcal://alepog.github.io/livorno-calendario/livorno.ics
```

(in alternativa `https://raw.githubusercontent.com/alepog/livorno-calendario/main/livorno.ics`)

## La promessa: una partita in casa non si perde mai

Il calendario non dipende dalla buona giornata del sito della società.
Tre difese, in ordine:

1. **casa o trasferta si legge dal campo apposito della fonte**
   (`acf.zaki_match_info.zaki_match_team_home.livorno`), non dal titolo della
   partita: se un giorno il titolo arriva scritto in un altro modo — "U.S.
   Livorno 1915 vs …", un refuso, un nome nuovo — la partita resta al suo posto.
   Il titolo è solo un ripiego per quando il campo manca, e se non si capisce
   nemmeno dal titolo la partita viene **tenuta** con un avviso, non scartata;
2. **il nuovo elenco viene fuso con quello già pubblicato**, confrontando gli
   UID: una risposta parziale o un guasto della fonte possono solo aggiungere o
   correggere, mai cancellare. Si toglie una partita solo se la fonte dichiara
   esplicitamente che si gioca in trasferta, oppure se è passata da più di 400
   giorni (`OBLIO`, così il file non cresce all'infinito). Una partita futura
   che scompare dall'elenco resta nel calendario, con un avviso che invita a
   controllare se è stata spostata o annullata;
3. **il file viene validato prima di sostituire quello in uso** (involucro,
   campi obbligatori, UID unici, righe entro i 75 ottetti, nessun UID perso per
   strada) e scritto in modo atomico. Se un controllo non passa, il workflow
   diventa rosso e resta pubblicata la versione precedente.

Se la fonte non risponde, ogni richiesta viene ritentata quattro volte (attese
5/20/60 secondi) su rete giù, timeout, errori HTTP, risposta vuota o non JSON.
Se non se ne cava nulla il file resta quello di prima e l'esecuzione finisce
**verde con un avviso**: diventa rossa solo se il calendario non si aggiorna da
più di tre giorni (`TOLLERANZA`), così un intoppo passeggero non manda un
allarme inutile ma un guasto vero sì.

### Chi lo rigenera, e perché non solo GitHub

`uslivorno.com` sta su SiteGround, che risponde alle richieste in arrivo dai
server di GitHub con la propria pagina di controllo anti-bot
(`/.well-known/sgcaptcha/…`) al posto del JSON. Misurato il 18/09/2026 con una
diagnosi apposita lanciata da un runner: **20 richieste su 20 respinte, con
qualunque User-Agent**. È l'indirizzo dei datacenter a essere filtrato, non il
modo di presentarsi; da una connessione normale le stesse richieste passano.

Così il lavoro lo fa il Mac e GitHub fa la guardia:

- **il Mac**, ogni giorno alle 8:30, con l'agente installato da
  `locale/installa.sh`: legge la fonte, rigenera `livorno.ics` e lo pubblica sul
  repo, da cui GitHub Pages lo serve al telefono;
- **il workflow su GitHub**, ogni giorno alle 06:00 UTC, prova comunque. Se il
  filtro lo respinge resta verde con un avviso e non tocca il file, ma il suo
  controllo di anzianità continua a valere: se il Mac stesse fermo per più di
  tre giorni diventerebbe rosso e arriverebbe la mail. È la sentinella che
  sorveglia il Mac — e se un giorno il filtro sparisse, GitHub ricomincerebbe a
  fare il lavoro da sé.

Nessuna pagina di controllo viene aggirata: si legge un endpoint pubblico, in
sola lettura, tre richieste al giorno, da una connessione normale.

### Installare o togliere la generazione dal Mac

```
git clone https://github.com/alepog/livorno-calendario.git ~/Claude/livorno-calendario
cd ~/Claude/livorno-calendario
git config credential."https://github.com".helper '!gh auth git-credential'
./locale/installa.sh              # 8:30; "./locale/installa.sh 7 15" per le 7:15
```

- eseguire subito senza aspettare domani:
  `launchctl kickstart -p gui/$UID/com.alepog.livorno-calendario`
- vedere com'è andata: `tail locale/ultima-esecuzione.log`
- togliere tutto: `./locale/disinstalla.sh` (il repo e il calendario restano)

## Dettagli che si notano usandolo

- La stagione viene rilevata automaticamente: nessuna manutenzione annuale.
  Durante il passaggio di stagione viene letta anche quella precedente, per le
  partite ancora da giocare (playoff, recuperi).
- Le partite senza orario ufficiale compaiono come eventi "tutto il giorno" e
  diventano eventi con orario appena il club lo pubblica.
- Ogni evento porta `SEQUENCE` e `LAST-MODIFIED`: crescono solo quando la
  partita cambia davvero, così i programmi di calendario capiscono cosa è
  stato aggiornato.
- Il `DTSTAMP` viene riscritto a ogni esecuzione riuscita: è il battito che fa
  capire, dal file stesso, quando la fonte è stata letta l'ultima volta. Per
  questo c'è un commit al giorno anche quando le partite non cambiano.

## Prove

```
python prova_genera_ics.py
```

Venticinque prove contro una finta fonte locale, senza rete: risposta parziale,
risposta vuota, HTTP 500, pagina di manutenzione e pagina anti-bot al posto del
JSON, data illeggibile, titolo inatteso, partita dichiarata in trasferta, cambio
di stagione, paginazione, righe lunghe, calendario vecchio, e i controlli che
intercettano sia una partita persa sia un file rotto. Girano anche in CI prima
di ogni generazione: se una fallisce, `livorno.ics` non viene toccato.

## Se il workflow smettesse di girare del tutto (facoltativo)

Il controllo di anzianità vive dentro lo script: se il workflow non partisse
più — cron disattivato da GitHub per inattività, repo sistemato male — nessuno
protesterebbe. Per coprire anche quel caso basta un guardiano esterno:

1. su [healthchecks.io](https://healthchecks.io) creare un check con periodo
   1 giorno e tolleranza 12 ore, e copiarne il *ping URL*;
2. nel repo: Settings → Secrets and variables → Actions → New repository
   secret, nome `HEALTHCHECK_URL`, valore quell'indirizzo.

Da quel momento ogni esecuzione riuscita manda un battito e ogni fallimento
manda un allarme; se i battiti si fermano, healthchecks.io scrive una mail.
Senza il segreto quei due passi vengono semplicemente saltati.
