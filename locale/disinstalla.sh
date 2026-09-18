#!/bin/zsh
# Toglie il LaunchAgent: il repo e il calendario restano dove sono.
set -u
ETICHETTA="com.alepog.livorno-calendario"
launchctl bootout "gui/$UID/$ETICHETTA" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$ETICHETTA.plist"
echo "rimosso $ETICHETTA"
