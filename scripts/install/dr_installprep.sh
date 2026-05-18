#!/usr/bin/bash
# Digital Reef host prep for a fresh RHEL 9.x VM.
#
# Installs all OS-level dependencies the eDiscovery install needs, then
# (optionally) reboots. Run as root.
#
# v0.07 changes vs the original /root/scripts/misc/dr_installprep.sh:
#   * Added python3-devel + gcc (needed by `pip install gevent`).
#   * Reboot is gated behind --reboot (default: prompt). Operators on
#     SSH sessions lost their shell to an unannounced reboot before.
#   * Idempotent: SELinux config backup is only created if absent
#     (B5 — second runs no longer overwrite the "original" backup with
#     the already-modified file).
#   * Uses `set -euo pipefail` so a failed step stops the script
#     instead of silently sliding into the reboot.
#
# Usage:
#   sudo ./dr_installprep.sh              # interactive; prompts before reboot
#   sudo ./dr_installprep.sh --reboot     # reboot without prompting
#   sudo ./dr_installprep.sh --no-reboot  # skip the reboot entirely

set -euo pipefail

REBOOT="ask"
for arg in "$@"; do
    case "$arg" in
        --reboot)    REBOOT="yes" ;;
        --no-reboot) REBOOT="no" ;;
        -h|--help)
            grep '^#' "$0" | head -25
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must be run as root (try sudo)." >&2
    exit 1
fi

echo "--- Installing OS packages ---"
dnf install -y epel-release
/usr/bin/crb enable
dnf install -y \
    ftp chkconfig screen nfs-utils chrony \
    perl-File-Copy perl-FindBin perl-Switch perl-lib \
    openldap-servers \
    net-tools bind-utils dejavu-sans-fonts.noarch \
    postgresql postgresql-server \
    NetworkManager-tui initscripts expect \
    python3-devel gcc                    # for `pip install gevent`
dnf install -y elrepo-release
dnf install -y kmod-hfs.x86_64 kmod-hfsplus.x86_64 hfsplus-tools.x86_64
dnf install -y kernel-modules-extra

echo "--- SELinux ---"
# B5 fix: only back up if there's no backup already, so reruns don't
# overwrite the true original with an already-disabled file.
if [ ! -f /etc/selinux/config.original ]; then
    cp /etc/selinux/config /etc/selinux/config.original
fi
sed -i 's/SELINUX=enforcing/SELINUX=disabled/g' /etc/selinux/config
cp /etc/selinux/config /etc/selinux/config-Aft-Script

echo "--- Services ---"
systemctl enable --now chronyd
tuned-adm profile throughput-performance
systemctl stop firewalld    || true
systemctl unmask firewalld  || true
systemctl disable firewalld || true

# Make sure atd (used by `dr-load admin --lifetime`) is enabled.
systemctl enable --now atd

echo ""
echo "=== Host prep complete ==="
echo "If this is a fresh VM, a reboot is required to fully disable SELinux."
echo ""

case "$REBOOT" in
    yes)
        echo "Rebooting now (--reboot passed)..."
        sleep 2
        reboot now
        ;;
    no)
        echo "Skipping reboot (--no-reboot passed). SELinux mode in effect:"
        getenforce || true
        ;;
    ask)
        read -p "Reboot now? [y/N] " yn
        case "$yn" in
            [Yy]*) reboot now ;;
            *)     echo "Skipping reboot. Run 'shutdown -r now' when ready." ;;
        esac
        ;;
esac
