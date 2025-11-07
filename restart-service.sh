#!/data/data/com.termux/files/usr/bin/bash

# Restart script for Tidal Troi UI
cd ~/tidal-troi-ui
./stop-service.sh
sleep 2
./start-service.sh