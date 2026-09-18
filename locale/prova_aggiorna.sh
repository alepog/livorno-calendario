#!/bin/zsh
# Prove di locale/aggiorna.sh su repository finti in una cartella temporanea:
# nessuna rete, nessun GitHub, generatore sostituito da un finto.
#
#   ./locale/prova_aggiorna.sh
set -u
QUI="${0:A:h}"
BASE=$(mktemp -d /tmp/prova-aggiorna.XXXXXX)
passate=0
fallite=0

va_bene() {   # va_bene "descrizione" condizione_gia_valutata
    if [ "$2" = "si" ]; then
        print -r -- "  ok    $1"
        passate=$((passate + 1))
    else
        print -r -- "  NO    $1"
        fallite=$((fallite + 1))
    fi
}

prepara() {   # un remoto finto, il clone "mac" e il clone "altro"
    cd /
    rm -rf "$BASE"
    mkdir -p "$BASE"
    git init --quiet --bare "$BASE/remoto.git"
    git clone --quiet "$BASE/remoto.git" "$BASE/mac"
    cd "$BASE/mac"
    git config user.name Prova
    git config user.email prova@esempio.it
    mkdir -p locale
    cp "$QUI/aggiorna.sh" locale/
    print "prima versione" > livorno.ics
    git add -A
    git commit --quiet -m "inizio"
    git branch --quiet -M main
    git push --quiet -u origin main
    git clone --quiet "$BASE/remoto.git" "$BASE/altro"
    cd "$BASE/altro"
    git config user.name Altro
    git config user.email altro@esempio.it
    cd "$BASE/mac"
}

pubblicato() {   # il contenuto di livorno.ics sul remoto
    git -C "$BASE/mac" show "origin/main:livorno.ics" 2>/dev/null
}

lancia() {   # lancia aggiorna.sh col generatore finto passato come primo argomento
    GENERA="$1" RAMO=main ./locale/aggiorna.sh > "$BASE/detto.txt" 2>&1
    esito=$?
    git -C "$BASE/mac" fetch --quiet origin
}

print "prove di aggiorna.sh in $BASE"

print "\n1) caso normale: genera e pubblica"
prepara
lancia 'print nuova > livorno.ics'
va_bene "esce con 0" "$([ $esito -eq 0 ] && print si)"
va_bene "il remoto ha la versione nuova" "$([ "$(pubblicato)" = "nuova" ] && print si)"

print "\n2) niente da fare: stesso contenuto, nessun commit"
prepara
prima=$(git rev-parse origin/main)
lancia 'print "prima versione" > livorno.ics'
va_bene "esce con 0" "$([ $esito -eq 0 ] && print si)"
va_bene "dice che non c'era nulla da pubblicare" \
    "$(grep -q 'nessuna modifica' "$BASE/detto.txt" && print si)"
va_bene "il remoto non si e' mosso" "$([ "$(git rev-parse origin/main)" = "$prima" ] && print si)"

print "\n3) corsa persa: un altro pubblica nel frattempo"
prepara
cd "$BASE/altro"
print "versione dell-altro" > livorno.ics
git add livorno.ics && git commit --quiet -m "dall'altro" && git push --quiet
cd "$BASE/mac"
lancia 'print "versione del mac" > livorno.ics'
va_bene "esce con 0" "$([ $esito -eq 0 ] && print si)"
va_bene "il remoto ha la versione del mac" \
    "$([ "$(pubblicato)" = "versione del mac" ] && print si)"
va_bene "il commit dell-altro non e' stato perso" \
    "$(git log origin/main --oneline | grep -q "dall'altro" && print si)"

print "\n4) si riprende da un rebase rimasto a meta'"
prepara
cd "$BASE/altro"
print "versione dell-altro" > livorno.ics
git add livorno.ics && git commit --quiet -m "dall'altro" && git push --quiet
cd "$BASE/mac"
print "versione locale" > livorno.ics          # divergenza voluta
git add livorno.ics && git commit --quiet -m "dal mac"
git fetch --quiet origin
git rebase origin/main > /dev/null 2>&1        # conflitto: repo lasciato a meta'
va_bene "il repo e' davvero incartato" \
    "$(git status --porcelain | grep -q '^UU' && print si)"
lancia 'print "versione buona" > livorno.ics'
va_bene "esce con 0" "$([ $esito -eq 0 ] && print si)"
va_bene "il remoto ha la versione buona" \
    "$([ "$(pubblicato)" = "versione buona" ] && print si)"
va_bene "il repo e' tornato pulito" \
    "$([ -z "$(git status --porcelain --untracked-files=no)" ] && print si)"

print "\n5) generazione fallita: non si pubblica niente"
prepara
prima=$(git rev-parse origin/main)
lancia 'false'
va_bene "esce con 1" "$([ $esito -eq 1 ] && print si)"
va_bene "lo dice chiaramente" \
    "$(grep -q 'generazione fallita' "$BASE/detto.txt" && print si)"
va_bene "il remoto non si e' mosso" "$([ "$(git rev-parse origin/main)" = "$prima" ] && print si)"

print "\n6) modifiche umane in corso su altri file: non si tocca niente"
prepara
print "appunti" >> locale/aggiorna.sh
prima=$(git rev-parse origin/main)
lancia 'print nuova > livorno.ics'
va_bene "esce con 1" "$([ $esito -eq 1 ] && print si)"
va_bene "spiega perche' si ferma" \
    "$(grep -q 'modifiche locali' "$BASE/detto.txt" && print si)"
va_bene "il remoto non si e' mosso" "$([ "$(git rev-parse origin/main)" = "$prima" ] && print si)"

cd /
rm -rf "$BASE"
print "\npassate: $passate   fallite: $fallite"
[ $fallite -eq 0 ] || exit 1
