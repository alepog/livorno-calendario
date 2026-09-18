#!/bin/zsh
# Genera livorno.ics da questo computer e lo pubblica sul repo.
#
# Perche' da qui e non solo da GitHub: il sito della societa' (SiteGround)
# risponde alle richieste in arrivo dai server di GitHub con la propria pagina
# di controllo anti-bot invece del JSON - provato il 18/09/2026, 20 richieste su
# 20, con qualunque User-Agent. Da una connessione normale le stesse richieste
# passano senza problemi.
#
# Lo lancia il LaunchAgent installato da locale/installa.sh; a mano si lancia
# come qualsiasi script:  ./locale/aggiorna.sh
set -u
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$HOME/bin:$PATH"
cd "${0:A:h}/.." || exit 1

adesso() { date "+%Y-%m-%d %H:%M:%S"; }
echo "=== $(adesso) avvio in $(pwd) ==="

if ! git pull --rebase --quiet; then
    echo "$(adesso) git pull non riuscito: mi fermo senza toccare niente"
    exit 1
fi

if ! python3 genera_ics.py; then
    echo "$(adesso) generazione fallita: il calendario resta quello di prima"
    exit 1
fi

if [ -z "$(git status --porcelain livorno.ics)" ]; then
    echo "$(adesso) nessuna modifica da pubblicare"
    exit 0
fi

git add livorno.ics
git commit --quiet -m "Aggiornato calendario partite in casa (dal Mac)" || {
    echo "$(adesso) commit non riuscito"; exit 1; }

for tentativo in 1 2 3; do
    if git push --quiet; then
        echo "$(adesso) pubblicato su GitHub"
        exit 0
    fi
    echo "$(adesso) push non riuscito (tentativo $tentativo), riallineo e riprovo"
    git pull --rebase --quiet || true
    sleep 5
done
echo "$(adesso) push fallito tre volte: il commit resta in locale, si ripartira' domani"
exit 1
