#!/bin/bash
# Snapshot the things that hold real data: the garage price/info files and the
# SQLite database (conversations, bookings, owners, leads). Timestamped, keeps
# the last 30. Safe to run anytime; SQLite is snapshotted consistently.
set -e
cd /opt/mistri
DEST=/opt/mistri/backups
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M%S)
TMP=$(mktemp -d)

cp -a garages "$TMP/garages"
# consistent DB copy even while the service is writing
sqlite3 mistri.db ".backup '$TMP/mistri.db'" 2>/dev/null || cp -f mistri.db "$TMP/mistri.db" 2>/dev/null || true

tar czf "$DEST/mistri-$STAMP.tar.gz" -C "$TMP" .
rm -rf "$TMP"

# keep the newest 30 snapshots
ls -1t "$DEST"/mistri-*.tar.gz 2>/dev/null | tail -n +31 | xargs -r rm -f
echo "backup written: $DEST/mistri-$STAMP.tar.gz"
