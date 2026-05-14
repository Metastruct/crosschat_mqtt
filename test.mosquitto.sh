#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/mosquitto"

if [ ! -f passwd ]; then
    if command -v mosquitto_passwd &> /dev/null; then
        echo "Generating password file from passwd_plain..."
        while IFS=: read -r user pass; do
            [[ -z "$user" ]] && continue
            if [ -f passwd ]; then
                mosquitto_passwd -b passwd "$user" "$pass"
            else
                mosquitto_passwd -c -b passwd "$user" "$pass"
            fi
        done < passwd_plain
    else
        echo "ERROR: passwd file missing and mosquitto_passwd not found."
        echo "Install mosquitto tools or generate passwd manually."
        exit 1
    fi
fi

echo "Starting Mosquitto MQTT broker..."
exec /sbin/mosquitto -c mosquitto.conf
