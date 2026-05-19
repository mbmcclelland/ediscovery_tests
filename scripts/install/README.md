# Install scripts

Versioned copies of the install tooling for the **Digital Reef product
itself** (`install.bin`). Use these in preference to anything left under
`/root/scripts/misc/` — those are pre-v0.07 and may have drifted.

> **Installing the `dr-load` toolkit?** That is a separate step. You
> have two options:
> - **Development / test VM:** `pip install -e .` in the repo root after
>   creating a venv (see [QA_README §1](../../QA_README.md)).
> - **Managed production host:** Install the RPM — see
>   [`packaging/README.md`](../../packaging/README.md).

## `dr_installprep.sh`

Run once on a fresh RHEL 9.x VM before the eDiscovery install. Installs
OS packages, disables SELinux, configures firewalld/chronyd, and
optionally reboots.

```bash
sudo ./scripts/install/dr_installprep.sh              # prompt before reboot
sudo ./scripts/install/dr_installprep.sh --reboot     # reboot unprompted
sudo ./scripts/install/dr_installprep.sh --no-reboot  # skip the reboot
```

Differences from the original (pre-v0.07) script:

- **Adds `python3-devel` and `gcc`** to the dnf list. `pip install
  gevent` fails without these (BUG_LOG B22).
- **Reboot is gated** behind `--reboot` / `--no-reboot` / a prompt. The
  original auto-rebooted at the end of the chain (B4) — operators on
  SSH sessions lost their shells unannounced.
- **Idempotent SELinux backup**: re-running no longer overwrites the
  true original with the already-modified file (B5).
- **`set -euo pipefail`**: a failed `dnf install` stops the script
  instead of silently rolling into the reboot.
- **Enables atd** (the queue dr-load admin --lifetime relies on).

## `dr_install.sh`

Silent installer wrapper. Detects the "10 GB rollback with zero signal"
failure mode (B17a) and surfaces it as a distinct non-zero exit:

```bash
sudo ./scripts/install/dr_install.sh                  # /tmp/install.bin + /tmp/response.txt
sudo ./scripts/install/dr_install.sh /path/install.bin /path/response.txt
```

| Exit code | Meaning |
|---|---|
| 0 | Install succeeded; registry has products, AHS/bin/setup.pl present |
| 1 | install.bin or response.txt missing |
| 2 | Installer rolled back (registry shows empty `<products/>`) |
| 3 | Incomplete install (registry OK but `/home/auraria/AHS/bin/setup.pl` missing) |
| 4 | install.bin returned non-zero |

Live progress: `tail -f /var/log/dr_install.log`. Expect ~15–20 minutes.
