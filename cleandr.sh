#! /usr/bin/bash
#
# cleandr.sh — destructive teardown of a DR install.
#
# Usage:
#   bash cleandr.sh              # remove DR + dr-tools RPM + user state
#   bash cleandr.sh --keeprpm    # leave the dr-tools RPM installed
#
# Removes (in order):
#   1. drd service stopped
#   2. license.lic preserved to /root/license.lic
#   3. /home/auraria/AHS*, /data/{doc,index}storage/*, scratch dirs
#   4. dr-tools RPM (unless --keeprpm) — see §dr-tools-removal below
#   5. ~/.dr-tools/ user state for $SUDO_USER (and root if owned)
#   6. ~/.config/systemd/user/dr-tools-{retention,recur}-*.{service,timer}
#      + systemctl --user daemon-reload
#
# Run as root (or via sudo). The script is destructive and unrecoverable
# for items 1-3; items 4-6 are recoverable by reinstalling the RPM and
# re-creating saved jobs.
set -euo pipefail

KEEPRPM=false
for arg in "$@"; do
    case "$arg" in
        --keeprpm) KEEPRPM=true ;;
        -h|--help)
            sed -n '2,21p' "$0"; exit 0 ;;
        *) echo "[cleandr] unknown arg: $arg" >&2; exit 2 ;;
    esac
done

# ---- 0. SELinux disable (v0.19.1) ----------------------------------------
# DR's file-system layout (`/home/auraria/AHS`, `/data/{doc,index}storage`)
# and the wildfly EE container both trip up SELinux MAC policies; under
# `enforcing` the install runs but countless requests fail with cryptic
# "AVC denied" entries in audit.log. The supported configuration is
# SELINUX=disabled.
#
# Two-stage disable:
#   1. runtime: `setenforce 0` flips enforcing → permissive immediately.
#      RHEL 8/9 doesn't allow runtime "disabled"; permissive is as close
#      as we get without a reboot, and it's enough for the installer.
#   2. persistent: edit `/etc/selinux/config` so the post-reboot state
#      is disabled too.
#
# Safe on hosts where SELinux is already disabled (getenforce → no-op).
# Safe on hosts without selinux-utils installed (`command -v` gate).
if command -v getenforce >/dev/null 2>&1; then
    cur=$(getenforce 2>/dev/null || echo "Unknown")
    if [ "$cur" != "Disabled" ]; then
        echo "[cleandr] SELinux state: $cur — switching to permissive runtime"
        setenforce 0 2>/dev/null \
            || echo "[cleandr] warning: setenforce 0 failed (kernel may have selinux=0 already)"
    else
        echo "[cleandr] SELinux already disabled — no runtime change needed"
    fi
    if [ -f /etc/selinux/config ]; then
        if ! grep -qE '^SELINUX=disabled[[:space:]]*$' /etc/selinux/config; then
            echo "[cleandr] setting SELINUX=disabled in /etc/selinux/config (effective after reboot)"
            sed -i.bak 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config
        fi
    fi
fi

# ---- 1. Stop drd --------------------------------------------------------
SYSTEMD_LOG_LEVEL=debug systemctl stop drd 2>/dev/null || true

# ---- 2. License preservation (dr_freshinstall.exp expects it here) ------
\cp -v /home/auraria/AHS/conf/license.lic /root/license.lic 2>/dev/null \
  || \cp -v license.lic /root/license.lic 2>/dev/null \
  || echo "[cleandr] warning: no license.lic found to preserve"

# ---- 3. Remove DR install + scratch dirs --------------------------------
rm -rfv /home/auraria/AHS*
rm -rfv /var/.com.zerog.registry.xml
rm -rfv /tmp/cbe* cpuinfo.txt artemis* install.dir.*
rm -rfv /data/docstorage/*
rm -rfv /data/indexstorage/*

# ---- 3b. Drop the 4 DR postgres databases (v0.17.2 / QA-v0171-4) --------
# Without this step, the InstallAnywhere installer skips populating
# `mgmtcustomeruser` and `mgmtcustomer` on the second-and-subsequent
# install of the same host (the schema is already present from the
# previous install, so the installer's CREATE-IF-MISSING data-init
# path doesn't fire). The result is a "schema present, zero rows"
# state where createSession works (auraria-rf has the credentials)
# but `userManager/changeUserPassword` fails with MgmtException:
# "User does not exist" because the management bean does a real
# table lookup that finds nothing.
#
# Dropping the DBs here forces the installer to recreate them from
# scratch, including the DRSysAdmin / super_system_customer seed rows.
# Safe to run when DBs don't exist (--if-exists no-ops).
if command -v psql >/dev/null 2>&1; then
    for db in auraria_mgmt auraria_admin auraria_activemq dr_history; do
        echo "[cleandr] dropping postgres DB: $db"
        sudo -u postgres dropdb --if-exists "$db" 2>/dev/null \
            || echo "[cleandr]   (skipped — $db may not exist or postgres is down)"
    done
else
    echo "[cleandr] warning: psql not found; skipping postgres-DB cleanup."
    echo "[cleandr]   On a re-installed host this can cause"
    echo "[cleandr]   userManager/changeUserPassword to return"
    echo "[cleandr]   'User does not exist' (QA-v0171-4)."
fi

# ---- 4. dr-tools RPM (v0.15+) -------------------------------------------
# §dr-tools-removal
if [ "$KEEPRPM" = "true" ]; then
    echo "[cleandr] --keeprpm: leaving dr-tools RPM installed"
else
    if rpm -q dr-tools >/dev/null 2>&1; then
        echo "[cleandr] removing dr-tools RPM"
        dnf -y remove dr-tools 2>&1 | tail -5
    else
        echo "[cleandr] dr-tools RPM not installed; skipping"
    fi
fi

# ---- 5. Per-user dr-tools state (jobs, runs, logs) ----------------------
# When run via sudo, $SUDO_USER is the invoker. When run as root directly,
# remove root's own state. Either way, only touch state that belongs to a
# real user account.
TARGET_HOMES=()
if [ -n "${SUDO_USER:-}" ]; then
    sudo_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
    [ -n "$sudo_home" ] && TARGET_HOMES+=("$sudo_home")
fi
[ "${EUID:-1}" = "0" ] && TARGET_HOMES+=("/root")
# De-dup
declare -A SEEN
for h in "${TARGET_HOMES[@]}"; do
    [ -n "$h" ] && SEEN["$h"]=1
done
for home in "${!SEEN[@]}"; do
    if [ -d "$home/.dr-tools" ]; then
        echo "[cleandr] removing $home/.dr-tools"
        rm -rf "$home/.dr-tools"
    fi
    # Per-user systemd timers we installed.
    units_dir="$home/.config/systemd/user"
    if [ -d "$units_dir" ]; then
        echo "[cleandr] removing dr-tools-* timers under $units_dir"
        rm -fv "$units_dir"/dr-tools-retention-*.service \
               "$units_dir"/dr-tools-retention-*.timer \
               "$units_dir"/dr-tools-recur-*.service \
               "$units_dir"/dr-tools-recur-*.timer 2>/dev/null || true
        # daemon-reload the user manager if one exists.
        if [ -n "${SUDO_USER:-}" ]; then
            sudo -u "$SUDO_USER" systemctl --user daemon-reload 2>/dev/null || true
        else
            systemctl --user daemon-reload 2>/dev/null || true
        fi
    fi
done

echo
echo "[cleandr] done. To rebuild DR:"
echo "    expect -f dr_freshinstall.exp"
echo "    python playwright_fresh_init.py"
echo "    python qa_create_org_admin.py    # if admin@training got dropped"
if [ "$KEEPRPM" = "true" ]; then
    echo "    (dr-tools RPM left installed)"
else
    echo "    sudo dnf install ./packaging/rpmbuild/RPMS/x86_64/dr-tools-*.rpm"
fi
