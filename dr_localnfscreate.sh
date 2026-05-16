#!/usr/bin/env bash
#
# setup-nfs.sh
# Rocky Linux 9.5 — install/enable nfs-server, create /data export directories,
# add them to /etc/exports with no_root_squash, then (re)start the service.
#
# Usage: sudo ./setup-nfs.sh [allowed_clients]
#   allowed_clients defaults to "*" (any host). Override with a CIDR or hostname,
#   e.g.  sudo ./setup-nfs.sh 10.0.0.0/24
#
 
set -euo pipefail
 
# ---- must run as root ------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: this script must be run as root (try: sudo $0)" >&2
    exit 1
fi
 
# ---- config ----------------------------------------------------------------
CLIENTS="${1:-*}"
EXPORT_OPTS="rw,sync,no_root_squash,no_subtree_check"
DIRS=(
    /data/import
    /data/export
    /data/docstorage
    /data/indexstorage
)
EXPORTS_FILE="/etc/exports"
 
echo "==> Allowed clients: ${CLIENTS}"
echo "==> Export options : ${EXPORT_OPTS}"
 
# ---- 1. install nfs-utils (provides nfs-server.service) --------------------
if ! rpm -q nfs-utils >/dev/null 2>&1; then
    echo "==> Installing nfs-utils ..."
    dnf install -y nfs-utils
else
    echo "==> nfs-utils already installed."
fi
 
# ---- 2. create the export directories --------------------------------------
for d in "${DIRS[@]}"; do
    if [[ ! -d "$d" ]]; then
        echo "==> Creating $d"
        mkdir -p "$d"
    else
        echo "==> $d already exists"
    fi
    chown root:root "$d"
    chmod 0755 "$d"
done
 
# ---- 3. back up /etc/exports and add entries -------------------------------
touch "$EXPORTS_FILE"
cp -a "$EXPORTS_FILE" "${EXPORTS_FILE}.bak.$(date +%Y%m%d%H%M%S)"
 
for d in "${DIRS[@]}"; do
    entry="${d} ${CLIENTS}(${EXPORT_OPTS})"
    # Skip if an export line for this directory already exists.
    if grep -Eq "^[[:space:]]*${d}[[:space:]]" "$EXPORTS_FILE"; then
        echo "==> Export for $d already present, leaving alone"
    else
        echo "==> Adding export: $entry"
        echo "$entry" >> "$EXPORTS_FILE"
    fi
done
 
# ---- 4. enable + (re)start the NFS server ----------------------------------
echo "==> Enabling and starting nfs-server.service"
systemctl enable --now nfs-server
 
echo "==> Re-reading exports table"
exportfs -rav
 
echo "==> Restarting nfs-server"
systemctl restart nfs-server
 
# ---- 5. status -------------------------------------------------------------
echo
echo "==> Current exports:"
exportfs -v
echo
echo "==> nfs-server status:"
systemctl --no-pager --lines=3 status nfs-server || true
 
echo
echo "Done."