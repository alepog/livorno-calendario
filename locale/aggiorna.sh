#!/bin/zsh
# Genera livorno.ics da questo computer e lo pubblica sul repo.
#
# Perche' da qui e non solo da GitHub: il sito della societa' (SiteGround)
# risponde alle richieste in arrivo dai server di GitHub con la propria pagina
# di controllo anti-bot invece del JSON. Il 18/09/2026 una diagnosi lanciata da
# un runner ha incassato 20 rifiuti su 20, con qualunque User-Agent; da una
# connessione normale le stesse richieste passano. Il workflow su GitHub resta
# attivo e qualche volta ce la fa, quindi i due possono pubblicare a pochi
# secondi uno dall'altro: livorno.ics e' un file generato, percio' in caso di
# divergenza vince sempre il remoto e lo si rigenera, invece di mettersi a
# fondere due versioni dello stesso file.
#
# Lo lancia l'agente installato da locale/installa.sh; a mano:
#   ./locale/aggiorna.sh
set -u
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$HOME/bin:$PATH"
cd "${0:A:h}/.." || exit 1

RAMO=${RAMO:-main}
GENERA=${GENERA:-"python3 genera_ics.py"}   # le prove lo sostituiscono

adesso() { date "+%Y-%m-%d %H:%M:%S"; }

echo "=== $(adesso) avvio in $(pwd) ==="

# Niente rebase o merge lasciati a meta' da un'esecuzione precedente.
git rebase --abort 2>/dev/null
git merge --abort 2>/dev/null

# Il solo file che questo script si permette di scartare e' il calendario: se
# qualcuno ha modifiche in corso su altro, ci si ferma senza toccare niente.
altre=$(git status --porcelain --untracked-files=no | grep -v 'livorno\.ics')
if [ -n "$altre" ]; then
    echo "$(adesso) modifiche locali che non riguardano il calendario, mi fermo:"
    echo "$altre"
    exit 1
fi

# Un giro completo: 0 fatto, 1 problema di git, 2 generazione fallita, 3 corsa persa.
pubblica() {
    git fetch --quiet origin || return 1
    git checkout --quiet --force -B "$RAMO" "origin/$RAMO" || return 1
    eval "$GENERA" || return 2
    if [ -z "$(git status --porcelain livorno.ics)" ]; then
        echo "$(adesso) nessuna modifica da pubblicare"
        return 0
    fi
    git add livorno.ics || return 1
    git commit --quiet -m "Aggiornato calendario partite in casa (dal Mac)" || return 1
    git push --quiet origin "$RAMO" || return 3
    echo "$(adesso) pubblicato su GitHub"
    return 0
}

for tentativo in 1 2 3; do
    pubblica
    esito=$?
    [ $esito -eq 0 ] && exit 0
    if [ $esito -eq 2 ]; then
        echo "$(adesso) generazione fallita: il calendario resta quello di prima"
        exit 1
    fi
    echo "$(adesso) tentativo $tentativo non andato (codice $esito): riallineo e riprovo"
    sleep 5
done

echo "$(adesso) non riuscito per tre volte: niente pubblicato, si riprova domani"
exit 1
