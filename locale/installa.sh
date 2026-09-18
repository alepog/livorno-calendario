#!/bin/zsh
# Installa il LaunchAgent che ogni giorno rigenera e pubblica il calendario.
# Uso:  ./locale/installa.sh [ora] [minuti]        (default 8:30)
set -eu
ORA=${1:-8}
MINUTI=${2:-30}
REPO="${0:A:h}/.."
REPO="${REPO:A}"
ETICHETTA="com.alepog.livorno-calendario"
PLIST="$HOME/Library/LaunchAgents/$ETICHETTA.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLI
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$ETICHETTA</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>$REPO/locale/aggiorna.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>$ORA</integer>
        <key>Minute</key><integer>$MINUTI</integer>
    </dict>
    <key>StandardOutPath</key><string>$REPO/locale/ultima-esecuzione.log</string>
    <key>StandardErrorPath</key><string>$REPO/locale/ultima-esecuzione.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLI

chmod +x "$REPO/locale/aggiorna.sh"
launchctl bootout "gui/$UID/$ETICHETTA" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$PLIST"
echo "installato: ogni giorno alle $(printf '%02d:%02d' "$ORA" "$MINUTI")"
echo "  agente:  $PLIST"
echo "  log:     $REPO/locale/ultima-esecuzione.log"
echo "  subito:  launchctl kickstart -p gui/$UID/$ETICHETTA"
echo "  via:     ./locale/disinstalla.sh"
