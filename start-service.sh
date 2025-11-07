#!/data/data/com.termux/files/usr/bin/bash

# Start script for Tidal Troi UI
set -e

cd ~/tidal-troi-ui/backend

# Activate virtual environment
source venv/bin/activate

# Start the backend server
echo "Starting Tidal Troi UI backend on port 8001..."
nohup python -m uvicorn api.main:app --host 0.0.0.0 --port 8001 > ~/tidal-troi-ui.log 2>&1 &

echo $! > ~/tidal-troi-ui.pid
echo "Service started with PID $(cat ~/tidal-troi-ui.pid)"
echo "Logs: ~/tidal-troi-ui.log"
echo "Access at: http://localhost:8001"