#!/bin/bash

DRIVER="peblar_ev_charger.py"
TARGET_DIR="/opt/victronenergy/dbus-modbus-client"
MAIN_FILE="$TARGET_DIR/dbus-modbus-client.py"
IMPORT_LINE="import peblar_ev_charger"

echo "=== Peblar EV Charger Installer ==="

# Check if driver file exists
if [ ! -f "$DRIVER" ]; then
    echo "ERROR: $DRIVER not found in the current directory"
    exit 1
fi

# Check if target directory exists
if [ ! -d "$TARGET_DIR" ]; then
    echo "ERROR: $TARGET_DIR not found"
    exit 1
fi

echo "Copying driver..."
cp "$DRIVER" "$TARGET_DIR/"

# Create backup
echo "Creating backup..."
cp "$MAIN_FILE" "$MAIN_FILE.bak"

# Check if import already exists
if grep -q "^$IMPORT_LINE" "$MAIN_FILE"; then
    echo "Import already exists"
else
    echo "Adding import to dbus-modbus-client.py"

    # Insert after the last import line
    sed -i "/^import /a $IMPORT_LINE" "$MAIN_FILE"
fi

echo "Restarting service..."

# Restart Victron service
if command -v svc >/dev/null 2>&1; then
    svc -t /service/dbus-modbus-client
else
    service dbus-modbus-client restart
fi

echo "Installation complete"
