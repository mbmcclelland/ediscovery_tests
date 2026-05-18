#!/usr/bin/bash
# Digital Reef silent installer wrapper.
#
# Replaces the autoexpect-generated dr_install_fullnode.exp for unattended
# installs. Fixes the "10 GB rollback with zero signal" failure mode by:
#   * forcing the InstallAnywhere debug logs to a persistent path
#   * verifying the installer registry has products afterwards
#   * verifying /home/auraria/AHS/bin/setup.pl was actually written
#
# Usage:  sudo ./dr_install.sh [/path/to/install.bin] [/path/to/response.txt]
#         (defaults: /tmp/install.bin and /tmp/response.txt)
#
# Exit codes:
#   0  success
#   1  install.bin / response.txt missing
#   2  installer rolled back (empty <products/> in registry)
#   3  setup.pl missing post-install (incomplete install)
#   4  install.bin returned non-zero exit code
set -u

INSTALL_BIN="${1:-/tmp/install.bin}"
RESPONSE_FILE="${2:-/tmp/response.txt}"
LOG_FILE="/var/log/dr_install.log"
REGISTRY="/var/.com.zerog.registry.xml"
AHS_SETUP="/home/auraria/AHS/bin/setup.pl"

if [ ! -f "$INSTALL_BIN" ]; then
    echo "ERROR: install.bin not found: $INSTALL_BIN" >&2
    exit 1
fi
if [ ! -f "$RESPONSE_FILE" ]; then
    echo "ERROR: response file not found: $RESPONSE_FILE" >&2
    exit 1
fi

# Truncate log so we can `tail -f` it during the run.
: >"$LOG_FILE"
chmod 0644 "$LOG_FILE"

{
    echo "=== Digital Reef install starting at $(date -Is) ==="
    echo "install.bin:   $INSTALL_BIN"
    echo "response file: $RESPONSE_FILE"
    echo "log file:      $LOG_FILE"
} | tee -a "$LOG_FILE"

# InstallAnywhere debug flags. lax.debug.level=3 is verbose; we capture
# everything to LOG_FILE so a rollback no longer evaporates the evidence.
export LAX_DEBUG=true
export _JAVA_OPTIONS="-Dlax.debug.level=3 -Dlax.debug.all=true"

# Run installer from /tmp because install.bin uses relative ./ paths.
INSTALL_DIR="$(dirname "$INSTALL_BIN")"
RUN_NAME="$(basename "$INSTALL_BIN")"

cd "$INSTALL_DIR" || { echo "ERROR: cd $INSTALL_DIR failed" | tee -a "$LOG_FILE"; exit 1; }

echo "--- launching installer ---" | tee -a "$LOG_FILE"
"./${RUN_NAME}" -i silent -f "$RESPONSE_FILE" -jvmxms 4g -jvmxmx 4g >>"$LOG_FILE" 2>&1
RC=$?
echo "--- installer exited rc=$RC at $(date -Is) ---" | tee -a "$LOG_FILE"

if [ "$RC" -ne 0 ]; then
    echo "FAILURE: install.bin exited non-zero ($RC). See $LOG_FILE" >&2
    exit 4
fi

# --- post-install verification ---------------------------------------

if [ ! -f "$REGISTRY" ]; then
    echo "FAILURE: $REGISTRY was not written — install never ran the registry step" | tee -a "$LOG_FILE" >&2
    exit 2
fi

# Empty <products/> means InstallAnywhere rolled back. The opening
# self-closing tag is the unambiguous tell — a successful install replaces
# it with <products><product .../></products>.
if grep -qE '<products[[:space:]]*/>' "$REGISTRY"; then
    echo "FAILURE: installer rolled back (registry shows empty <products/>)" | tee -a "$LOG_FILE" >&2
    echo "       Inspect $LOG_FILE for the root cause." | tee -a "$LOG_FILE" >&2
    echo "       Common causes: SELinux not disabled, firewalld enabled, NetworkManager-tui missing," | tee -a "$LOG_FILE" >&2
    echo "       hostname not in /etc/hosts, or postgres not reachable." | tee -a "$LOG_FILE" >&2
    exit 2
fi

if [ ! -f "$AHS_SETUP" ]; then
    echo "FAILURE: $AHS_SETUP missing — install completed registration but not the AHS tree" | tee -a "$LOG_FILE" >&2
    exit 3
fi

echo "SUCCESS: Digital Reef installed at /home/auraria/AHS (registry OK, setup.pl present)" | tee -a "$LOG_FILE"
echo "Next: 'systemctl start drd' then verify https://$(hostname -I | awk '{print $1}'):8443/ediscovery/" | tee -a "$LOG_FILE"
exit 0
