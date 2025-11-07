#!/data/data/com.termux/files/usr/bin/bash

# Stop script for Tidal Troi UI
if [ -f ~/tidal-troi-ui.pid ]; then
    PID=$(cat ~/tidal-troi-ui.pid)
    if kill -0 $PID 2>/dev/null; then
        echo "Stopping Tidal Troi UI (PID: $PID)..."
        kill $PID
        rm ~/tidal-troi-ui.pid
        echo "Service stopped"
    else
        echo "Process not running"
        rm ~/tidal-troi-ui.pid
    fi
else
    echo "PID file not found"
fi