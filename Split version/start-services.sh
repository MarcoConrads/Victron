#!/bin/sh
# Recreate persistent driver service links at every Venus OS boot.
set -eu

target=/data/dbus-modbus-drivers
for name in growatt ecoforest peblar; do
    service="$target/services/dbus-$name"
    link="/service/dbus-$name"
    if [ ! -x "$service/run" ] || [ ! -x "$service/log/run" ]; then
        echo "Missing service scripts: $service" >&2
        exit 1
    fi
    if [ -e "$link" ] || [ -L "$link" ]; then
        if [ ! -L "$link" ] || [ "$(readlink "$link")" != "$service" ]; then
            echo "Service belongs to another installation: $link" >&2
            exit 1
        fi
    fi
done

for name in growatt ecoforest peblar; do
    service="$target/services/dbus-$name"
    link="/service/dbus-$name"
    if [ ! -L "$link" ]; then
        if ! ln -s "$service" "$link"; then
            mount -o remount,rw /
            ln -s "$service" "$link"
        fi
    fi
    rm -f "$service/down"
    tries=0
    until [ -p "$service/supervise/ok" ] && [ -p "$service/log/supervise/ok" ]; do
        tries=$((tries + 1))
        if [ "$tries" -ge 15 ]; then
            echo "Supervisor did not discover $link" >&2
            exit 1
        fi
        sleep 1
    done
    svc -u "$link/log"
    svc -u "$link"
done
