# dr-load-toolkit RPM Packaging

**Audience.** A sysadmin deploying the `dr-load` toolkit to one or more
RHEL 9 / Rocky Linux 9 hosts. Written so a junior sysadmin can follow it
end-to-end; senior sysadmins can skip to the section they need.

**Glossary:**
- **RPM** — Red Hat Package Manager. A self-contained installable archive (`.rpm` file) that `dnf` can install, upgrade, and remove cleanly.
- **spec file** — the recipe that describes what goes into an RPM.
- **systemd** — the service manager on RHEL 9. It starts, stops, and monitors the recorder daemon.
- **logrotate** — a standard Linux tool that rotates log files on a schedule to prevent unbounded growth.
- **DNF repo** — a directory served over HTTP that `dnf` can pull packages from automatically.

---

## What is in this directory

| File | Purpose |
|---|---|
| `dr-load.spec` | RPM spec file — defines the package name, version, dependencies, install steps, and file manifest |
| `build-rpm.sh` | Idempotent build script — builds the wheel, downloads runtime deps, runs rpmbuild |
| `systemd/dr-load-recorder.service` | systemd unit for the recorder daemon |
| `dr-load-recorder.env.example` | Template for `/etc/sysconfig/dr-load-recorder` — edit before enabling the daemon |
| `logrotate/dr-load-recorder` | logrotate config for `/var/log/dr-load-recorder.log` |
| `output/` | Build output directory — the `.rpm` file lands here after a successful build |

---

## Before you install: one-time browser step

**This step is easy to miss.** The Digital Reef server has a permission
check that cannot be bypassed from the CLI: DRSysAdmin must already be
a member of the target org before the CLI can create projects in it.

After installing the Digital Reef application (via
[`scripts/install/dr_install.sh`](../scripts/install/README.md)):

1. Open `https://<host>:8443/ediscovery/` in a browser and log in as
   `DRSysAdmin`.
2. Go to **Express Provisioning** (Resource Manager).
3. Create the `training` org, an `admin` user, and add `DRSysAdmin` as
   **Organization Administrator** in that org.

This is the only step that cannot be done from the command line.
After it is done once, all CLI operations work without a browser.
See [QA_README §7.5](../QA_README.md#75-no-role-handle) for the root cause
and [BUG_LOG B36](../BUG_LOG.md) for the filed issue.

---

## How to build the RPM

**Prerequisites** — install on the build host (typically the same RHEL 9
VM where you develop):

```bash
sudo dnf install rpm-build python3 python3-pip python3-setuptools
```

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

The script is idempotent — you can run it multiple times. Each run
re-downloads the dependency wheels and rebuilds from scratch.

Build artifacts also land in `~/rpmbuild/RPMS/x86_64/` (the standard
rpmbuild output tree).

**Architecture note:** The RPM builds as `x86_64`, not `noarch`, because
two bundled wheels (`pydantic-core`, `charset-normalizer`) contain
compiled `.so` extensions. If a noarch build is ever needed, those two
deps would need to be replaced with pure-Python alternatives.

---

## How to install on a target host

The target host must already have the Digital Reef application installed.
The `auraria` service account and the NFS mount must exist before the
package is installed.

Copy the RPM to the target host and install it:

```bash
sudo dnf install /path/to/dr-load-toolkit-0.14-1.el9.x86_64.rpm
```

`dnf` resolves the declared RPM dependencies (`at`, `python3`,
`python3-pip`, `python3-setuptools`) from the host's configured repos.
No internet access is needed for the Python packages — they are bundled
in the RPM.

Verify the install:

```bash
dr-load --version
# Expected output:
dr-load 0.14
```

---

## Verify connectivity (preflight)

Run the preflight check immediately after install to confirm the CLI can
reach the Digital Reef server:

```bash
export DR_BASE_URL='https://192.168.58.128:8443/ediscovery/rest'
export DR_USERNAME=DRSysAdmin
export DR_PASSWORD=password
export DR_ORGANIZATION=super_system_customer
export DR_VERIFY_SSL=false

dr-load preflight
```

A passing preflight looks like this:

```
[PASS] app_reachable      HTTP 200 from https://192.168.58.128:8443/ediscovery/
[PASS] auth               Logged in as DRSysAdmin (super_system_customer)
[PASS] realm_status       AVAILABLE
[PASS] connector_uuid     training-import-nfs-local found (handle=000084ba...)
[PASS] nfs_path           /data/import/testload exists and is readable
[PASS] org_user_auth      admin@training authenticated successfully
All 6 checks passed.
```

If any check shows `[FAIL]`, the line tells you what is wrong. The most
common first-run failures:

| Check that failed | Cause | Fix |
|---|---|---|
| `app_reachable` | Wrong `DR_BASE_URL` or the server is down | Confirm `DR_BASE_URL` and check that JBoss is running |
| `auth` | Wrong `DR_PASSWORD`, or it contains a shell special character | Put the password in single quotes: `export DR_PASSWORD='my$pass'` |
| `connector_uuid: not found` | The connector name or org is wrong, or DRSysAdmin is not yet Org Admin | Complete the [browser Express Provisioning step](#before-you-install-one-time-browser-step) first |
| `nfs_path` | Test fixture not staged | Run `sudo dr-load admin stage-testload` |

---

## How to configure the recorder daemon

Before enabling the daemon, populate its environment file:

```bash
sudo vi /etc/sysconfig/dr-load-recorder
```

At minimum, set:

```bash
DR_HOST=https://<your-dr-server>:8443
DR_ORG=training          # or your org name
DR_USER=DRSysAdmin
DR_PASSWORD=<password>
DR_VERIFY_SSL=false      # for lab / self-signed cert environments
```

See the comments in `/etc/sysconfig/dr-load-recorder` for all available
variables including `DR_STORE_PATH` (SQLite store location) and
`DR_TICK_INTERVAL` (sample interval in seconds, default 10).

---

## How to enable and start the recorder daemon

The daemon is **disabled by default** — it does not start on install.
Enable it explicitly when you are ready to begin a load-test campaign.

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

Run this sequence after install and daemon start to confirm everything
works end-to-end:

```bash
# 1. CLI is on PATH and reports the correct version
dr-load --version

# 2. Preflight confirms connectivity to the DR server
dr-load preflight

# 3. Recorder daemon is running
sudo systemctl status dr-load-recorder

# 4. Start a campaign and confirm the daemon writes metrics
dr-load campaign new "smoke-test" --scenario indexing --users 5
sleep 15
dr-load record status
dr-load campaign end

# 5. Generate a report
dr-load report --audience self
```

If step 5 shows a GREEN verdict with non-empty System and Throughput
sections, the full stack is healthy.

---

## Log rotation

The RPM does not install the logrotate config automatically (it is
included in the `packaging/logrotate/` directory for operator review).
Install it manually after confirming the log path:

```bash
sudo cp packaging/logrotate/dr-load-recorder /etc/logrotate.d/dr-load-recorder
```

The default configuration rotates daily, keeps 14 compressed copies, and
sends SIGHUP to the daemon after rotation so it reopens the log file
without restarting. Verify it with a dry run:

```bash
sudo logrotate -d /etc/logrotate.d/dr-load-recorder
```

If you change the log path via `DR_LOG_PATH` in
`/etc/sysconfig/dr-load-recorder`, update the path at the top of the
logrotate config to match.

---

## About `psycopg2-binary` in the wheel bundle

The built RPM includes a `psycopg2-binary` wheel at
`/usr/share/dr-load/wheels/`. This wheel is **not** automatically
installed — it is included as a convenience for operators who want to
query the Postgres database offline for diagnostic purposes.

To install it manually on an air-gapped host:

```bash
pip install --no-index --find-links=/usr/share/dr-load/wheels/ psycopg2-binary
```

The `dr-load` CLI itself does not require `psycopg2-binary` — it reads
all state through the REST API.

---

## Upgrade notes

When a new version of `dr-load-toolkit` is released:

1. Rebuild the RPM with `bash packaging/build-rpm.sh` after bumping
   `__version__.py`.
2. On the target host: `sudo dnf upgrade /path/to/dr-load-toolkit-<new-version>-1.el9.x86_64.rpm`
3. `/etc/sysconfig/dr-load-recorder` is marked `%config(noreplace)` —
   your local edits are preserved. Check the new `.env.example` in
   `packaging/` for any new variables added in this release.

---

## Uninstall

```bash
sudo systemctl disable --now dr-load-recorder   # stop daemon first
sudo dnf remove dr-load-toolkit
```

The SQLite store at `/var/lib/dr-load-recorder/store.db` and the log at
`/var/log/dr-load-recorder.log` are **not** removed automatically.
Delete them manually if desired:

```bash
sudo rm -rf /var/lib/dr-load-recorder /var/log/dr-load-recorder.log
```

---

## Signing for production

The RPM ships **unsigned** (`Signature: (none)` in `rpm -qpi` output).
For internal distribution, sign it with your organization's GPG key
before publishing to a DNF repository.

**One-time setup (on the build host):**

```bash
# 1. Generate a GPG key if you do not already have one
gpg --full-generate-key
# Choose: RSA and RSA, 4096 bits, no expiry (or set one per your policy)
# Use a name and email that identifies this as a package-signing key

# 2. Export the public key for distribution to target hosts
gpg --export --armor "Your Name" > dr-load-signing-key.asc

# 3. Tell rpm how to sign with this key (~/.rpmmacros)
cat >> ~/.rpmmacros << 'EOF'
%_signature gpg
%_gpg_name  Your Name
EOF
```

**Sign the RPM:**

```bash
rpm --addsign packaging/output/dr-load-toolkit-0.14-1.el9.x86_64.rpm
# Prompts for the GPG passphrase
```

Verify the signature:

```bash
rpm --checksig packaging/output/dr-load-toolkit-0.14-1.el9.x86_64.rpm
# Expected: dr-load-toolkit-0.14-1.el9.x86_64.rpm: digests signatures OK
```

**Distribute the public key to target hosts:**

```bash
# On each target host (run once):
sudo rpm --import dr-load-signing-key.asc
```

After this, `dnf` will verify the signature automatically when installing
or upgrading from a signed repo.

---

## Appendix: setting up an internal DNF repository

Serving the RPM from a local HTTP server lets you use `dnf install
dr-load-toolkit` and `dnf upgrade` instead of copying files manually.

**Prerequisites on the repo host:**

```bash
sudo dnf install createrepo_c nginx
```

**Build and publish:**

```bash
# 1. Rebuild the RPM (and sign it if applicable)
bash packaging/build-rpm.sh

# 2. Copy to the repo directory
sudo mkdir -p /var/www/html/dr-load/el9/x86_64
sudo cp packaging/output/dr-load-toolkit-0.14-1.el9.x86_64.rpm \
    /var/www/html/dr-load/el9/x86_64/

# 3. Generate (or update) the repo metadata
sudo createrepo_c /var/www/html/dr-load/el9/x86_64/

# 4. If the RPM is signed, sign the repodata too
gpg --detach-sign --armor \
    /var/www/html/dr-load/el9/x86_64/repodata/repomd.xml

# 5. Serve with NGINX (minimal config)
cat | sudo tee /etc/nginx/conf.d/dr-load-repo.conf << 'EOF'
server {
    listen 80;
    server_name repo.internal.example.com;
    root /var/www/html;
    autoindex on;
}
EOF
sudo systemctl enable --now nginx
```

**On each target host** — add a repo file:

```bash
cat | sudo tee /etc/yum.repos.d/dr-load.repo << 'EOF'
[dr-load]
name=dr-load-toolkit
baseurl=http://repo.internal.example.com/dr-load/el9/x86_64/
enabled=1
gpgcheck=1
gpgkey=http://repo.internal.example.com/dr-load-signing-key.asc
EOF
```

After that, installs and upgrades work through the normal `dnf` flow:

```bash
sudo dnf install dr-load-toolkit
sudo dnf upgrade dr-load-toolkit
```

Run `sudo createrepo_c --update /var/www/html/dr-load/el9/x86_64/`
each time you publish a new RPM version.
