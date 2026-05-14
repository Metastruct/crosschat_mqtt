#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

if ! command -v mosquitto_passwd &> /dev/null; then
    echo "ERROR: mosquitto_passwd not found. Install mosquitto package first."
    echo "  Debian/Ubuntu: sudo apt install mosquitto"
    echo "  RHEL/CentOS:   sudo dnf install mosquitto"
    exit 1
fi

rm -f passwd

while IFS=: read -r user pass; do
    if [[ -z "$user" ]]; then
        continue
    fi
    if [[ -f passwd ]]; then
        mosquitto_passwd -b passwd "$user" "$pass"
    else
        mosquitto_passwd -c -b passwd "$user" "$pass"
    fi
    echo "Added user: $user"
done < passwd_plain

echo "Password file generated at: $SCRIPT_DIR/passwd"

echo ""
echo ""

/sbin/mosquitto -c mosquitto.conf $*

