#!/bin/bash

DRIVER="peblar_ev_charger.py"
TARGET_DIR="/opt/victronenergy/dbus-modbus-client"
MAIN_FILE="$TARGET_DIR/dbus-modbus-client.py"
IMPORT_LINE="import peblar_ev_charger"

echo "=== Peblar EV Charger Installer ==="

if [ ! -f "$DRIVER" ]; then
    echo "ERROR: $DRIVER not found in the current directory"
    exit 1
fi

if [ ! -d "$TARGET_DIR" ]; then
    echo "ERROR: $TARGET_DIR not found"
    exit 1
fi

if [ ! -f "$MAIN_FILE" ]; then
    echo "ERROR: $MAIN_FILE not found"
    exit 1
fi

echo "Copying driver..."
cp "$DRIVER" "$TARGET_DIR/"

echo "Creating backup..."
cp "$MAIN_FILE" "$MAIN_FILE.bak"

if grep -q "^${IMPORT_LINE}$" "$MAIN_FILE"; then
    echo "Import already exists"
else
    echo "Adding import to dbus-modbus-client.py"

    TMP_FILE="$(mktemp)"

    awk -v newline="$IMPORT_LINE" '
    BEGIN { last_import = 0 }
    {
        lines[NR] = $0
        if ($0 ~ /^import[[:space:]]+/) {
            last_import = NR
        }
    }
    END {
        inserted = 0
        for (i = 1; i <= NR; i++) {
            print lines[i]
            if (i == last_import) {
                print newline
                inserted = 1
            }
        }
        if (inserted == 0) {
            print newline
        }
    }' "$MAIN_FILE" > "$TMP_FILE"

    mv "$TMP_FILE" "$MAIN_FILE"
fi

echo "Restarting service..."

if command -v svc >/dev/null 2>&1; then
    svc -t /service/dbus-modbus-client
else
    service dbus-modbus-client restart
fi

echo "Installation complete"
