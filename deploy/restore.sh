#!/bin/bash
# Restore garages + database from a backup. With no argument it lists backups.
# It always snapshots the CURRENT state first, so a restore is itself undoable.
#
#   bash restore.sh                              # list backups
#   bash restore.sh mistri-20260912-1200.tar.gz  # restore that one
set -e
cd /opt/mistri
DEST=/opt/mistri/backups

if [ -z "$1" ]; then
  echo "Available backups (newest first):"
  ls -1t "$DEST"/mistri-*.tar.gz 2>/dev/null | sed 's#.*/##' || echo "  (none yet)"
  echo
  echo "To restore:  bash restore.sh <filename>"
  exit 0
fi

FILE="$DEST/$1"; [ -f "$FILE" ] || FILE="$1"
[ -f "$FILE" ] || { echo "Not found: $1"; exit 1; }

echo "Snapshotting current state first (so this restore is undoable)..."
bash /opt/mistri/backup.sh >/dev/null 2>&1 || true

TMP=$(mktemp -d)
tar xzf "$FILE" -C "$TMP"
[ -d "$TMP/garages" ] && rm -rf /opt/mistri/garages && cp -a "$TMP/garages" /opt/mistri/garages
[ -f "$TMP/mistri.db" ] && cp -f "$TMP/mistri.db" /opt/mistri/mistri.db
rm -rf "$TMP"

echo "Restored from: $1"
echo "Now restart the service:  sudo systemctl restart mistri"
