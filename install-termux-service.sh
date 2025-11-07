#!/data/data/com.termux/files/usr/bin/bash

# Install as Termux service using Termux:Boot
set -e

echo "Installing Tidal Troi UI as a Termux service..."

# Install Termux:Boot if not installed
if ! command -v termux-wake-lock &> /dev/null; then
    echo "Please install Termux:Boot from F-Droid or Google Play"
    echo "https://wiki.termux.com/wiki/Termux:Boot"
    exit 1
fi

# Create boot script directory
mkdir -p ~/.termux/boot

# Create boot script
cat > ~/.termux/boot/start-tidal-troi.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash

# Acquire wake lock to prevent sleep
termux-wake-lock

# Wait for network
sleep 10

# Start Tidal Troi UI
cd ~/tidal-troi-ui
./start-service.sh
EOF

chmod +x ~/.termux/boot/start-tidal-troi.sh
chmod +x ~/tidal-troi-ui/start-service.sh
chmod +x ~/tidal-troi-ui/stop-service.sh
chmod +x ~/tidal-troi-ui/restart-service.sh

echo "Service installed!"
echo "The app will start automatically when you boot your device"
echo "Make sure Termux:Boot is enabled in your Android settings"