# dr-load-toolkit RPM Packaging

This directory contains everything needed to build and deploy the `dr-load-toolkit` RPM
for RHEL 9 / Rocky Linux 9 hosts.

---

## What is in this directory

| File | Purpose |
|---|---|
| `dr-load.spec` | RPM spec file — defines the package name, version, dependencies, install steps, and file manifest |
| `build-rpm.sh` | Idempotent build script — builds the wheel, downloads runtime deps, runs rpmbuild |
| `systemd/dr-load-recorder.service` | systemd unit for the recorder daemon |
| `dr-load-recorder.env.example` | Template for `/etc/sysconfig/dr-load-recorder` — edit before enabling the daemon |
| `output/` | Build output directory — the `.rpm` file lands here after a successful build |

---

## Build prerequisites

Install on the **build host** (typically the same RHEL 9 VM where you develop):

```bash
sudo dnf install rpm-build python3 python3-pip python3-setuptools
```

The build script will auto-install the `wheel` Python package if it is not present.

---

## How to build the RPM

From the repo root:

```bash
bash packaging/build-rpm.sh
```

On success you will see:

```
======================================================================
SUCCESS: dr-load-toolkit-0.14-1.el9.x86_64.rpm
  Full path:  /root/scripts/ediscovery_tests-master/packaging/output/dr-load-toolkit-0.14-1.el9.x86_64.rpm
======================================================================
```

The script is idempotent — you can run it multiple times. Each run re-downloads the
dependency wheels and rebuilds the package from scratch.

**Build artifacts** also land in `~/rpmbuild/RPMS/x86_64/` (the standard rpmbuild tree).

---

## How to install on a fresh RHEL 9 host

**Prerequisites** — the target host must already have the Digital Reef application installed
(via `scripts/install/dr_install.sh`). The `auraria` service account and NFS mount must
exist before you install this package.

Copy the RPM to the target host, then:

```bash
sudo dnf install dr-load-toolkit-0.14-1.el9.x86_64.rpm
```

`dnf` resolves the declared RPM dependencies (`at`, `python3`, `python3-pip`,
`python3-setuptools`) from the host's configured repos. No internet access is needed for
the Python packages — they are bundled inside the RPM.

Verify the install:

```bash
dr-load --version
# Expected output: dr-load 0.14

dr-load preflight
# Expected output: connectivity and auth checks against the configured DR server
```

---

## How to configure the recorder daemon

Before enabling the daemon, edit its environment file:

```bash
sudo vi /etc/sysconfig/dr-load-recorder
```

At minimum, set:

```bash
DR_HOST=https://<your-dr-server>:8443
DR_ORG=training          # or your org name
DR_USER=DRSysAdmin
DR_PASSWORD=<password>
DR_VERIFY_SSL=false      # for lab/self-signed cert environments
```

See the comments in `/etc/sysconfig/dr-load-recorder` for all available variables.

---

## How to enable and start the recorder daemon

The daemon is **disabled by default** — it does not start on install. Enable it explicitly
when you are ready to run a load-test campaign:

```bash
# Enable and start now (persists across reboots)
sudo systemctl enable --now dr-load-recorder

# Check status
sudo systemctl status dr-load-recorder

# Watch live logs
sudo journalctl -u dr-load-recorder -f
# or
sudo tail -f /var/log/dr-load-recorder.log
```

To stop and disable:

```bash
sudo systemctl disable --now dr-load-recorder
```

---

## Verify the full stack

After install and daemon start, run this sequence to confirm everything works:

```bash
# 1. CLI is on PATH and reports the correct version
dr-load --version

# 2. Preflight confirms connectivity to the DR server
dr-load preflight

# 3. Recorder daemon is running
sudo systemctl status dr-load-recorder

# 4. Start a campaign and confirm the daemon writes metrics
dr-load campaign new "smoke-test" --scenario indexing --users 5
dr-load record status
dr-load campaign end

# 5. Generate a report
dr-load report --audience self
```

---

## Upgrade notes

When a new version of `dr-load-toolkit` is released:

1. Rebuild the RPM with `bash packaging/build-rpm.sh` (after bumping `__version__.py`).
2. On the target host: `sudo dnf upgrade dr-load-toolkit-<new-version>-1.el9.x86_64.rpm`
3. The file `/etc/sysconfig/dr-load-recorder` is marked `%config(noreplace)` — your local
   edits are preserved across upgrades. Check the new `.env.example` in packaging/ for any
   new variables added in this release.

---

## Uninstall

```bash
sudo systemctl disable --now dr-load-recorder   # stop daemon first
sudo dnf remove dr-load-toolkit
```

**Note:** Uninstall does not delete the SQLite store at `/var/lib/dr-load-recorder/store.db`
or the log at `/var/log/dr-load-recorder.log`. Remove those manually if desired.
