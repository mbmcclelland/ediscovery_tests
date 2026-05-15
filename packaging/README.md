# Packaging dr-tools

Two distribution paths for `dr-tools` (the `dr_tui` + `dr-load`
console-scripts bundle):

| Path | Audience | Internet at install time? | Build host requirements |
|---|---|---|---|
| **RPM** (`dr-tools-VERSION-1.el9.x86_64.rpm`) | Production / lab / air-gapped hosts | **No** (wheels bundled) | `rpmbuild`, `python3 >= 3.9`, `pip` |
| **`install.sh`** | Dev boxes, quick one-liner | **Yes** (downloads tarball, pip installs) | `python3 >= 3.9`, `curl`, `sudo` |

Either way the result is identical:

- A self-contained venv at `/opt/dr-tools/venv` (RPM) or
  `/opt/dr-tools/venv` (shell installer).
- Launcher scripts on `PATH`:
  - `/usr/bin/dr_tui` and `/usr/bin/dr-load` (RPM)
  - `/usr/local/bin/dr_tui` and `/usr/local/bin/dr-load` (shell)
- A sample `.env.example` at `/opt/dr-tools/share/env.example` (RPM
  only; with the shell path you copy from your local checkout).

The bundled venv keeps the OS Python and any system-Python apps
unaffected.

---

## RPM build (recommended for distribution)

From a checkout on a Rocky/RHEL/Fedora host with `rpmbuild`:

```bash
cd packaging
make rpm
```

This:

1. **`make wheels`** — `pip wheel`s every runtime dep into
   `../dist/wheelhouse/*.whl`. Takes ~30 s on first run; subsequent
   runs hit pip's cache.
2. **`make tarball`** — bundles the source tree + wheelhouse into
   `rpmbuild/SOURCES/dr-tools-VERSION.tar.gz`. Excludes `.git`, `.venv`,
   `tests`, `misc`, etc.
3. **`make srpm`** — `rpmbuild -bs` to produce a `.src.rpm` you can
   redistribute and rebuild elsewhere.
4. **`make rpm`** — `rpmbuild -bb` to produce the binary
   `dr-tools-VERSION-1.elN.x86_64.rpm` ready for `dnf install`.

Output:

```
packaging/rpmbuild/SRPMS/dr-tools-0.07-1.el9.src.rpm
packaging/rpmbuild/RPMS/x86_64/dr-tools-0.07-1.el9.x86_64.rpm
```

### Installing the RPM on a target host

```bash
sudo dnf install ./dr-tools-0.07-1.el9.x86_64.rpm
# or for upgrade:
sudo dnf upgrade ./dr-tools-0.07-1.el9.x86_64.rpm
```

The post-install message points you at `/opt/dr-tools/share/env.example`
— copy it to wherever you keep config (`~/.env`, `/etc/dr-tools/.env`,
…) and edit `DR_HOST` / `DR_USER` / `DR_PASS`.

### Uninstall

```bash
sudo dnf remove dr-tools
```

`/opt/dr-tools` is owned by the RPM, so RPM cleanly removes it.

### Architecture notes

The spec is currently `BuildArch: x86_64` because `psutil` and
`psycopg2-binary` ship C extensions. To build for `aarch64`, generate
the wheelhouse on an arm64 host (`make wheels`) and re-run
`make rpm` there — change `BuildArch` in `dr-tools.spec` accordingly.

The RPM declares `AutoReqProv: no` and pins only `glibc` + `python3`
at the system level. All Python deps live in the venv, isolated from
the system Python.

### Verifying the build before install

```bash
# Inspect contents:
rpm -qlp packaging/rpmbuild/RPMS/x86_64/dr-tools-0.07-1.el9.x86_64.rpm | head -20

# Confirm declared deps + scripts:
rpm -qip packaging/rpmbuild/RPMS/x86_64/dr-tools-0.07-1.el9.x86_64.rpm
```

---

## Shell installer (one-liner)

For dev hosts or anywhere you don't want to build an RPM. **Requires
internet access at install time** — it downloads the source tarball
from GitHub and `pip install`s into a fresh venv.

Local checkout:

```bash
bash packaging/install.sh           # install
bash packaging/install.sh uninstall # remove
```

Remote one-liner (no checkout needed):

```bash
curl -sSL https://github.com/mbmcclelland/ediscovery_tests/raw/v0.06/packaging/install.sh | bash
```

The installer prefers `${PYTHON}` from the environment, else `python3`
from `PATH`. Python 3.9+ is required.

---

## Quick sanity-check after install

```bash
which dr_tui dr-load
dr_tui --help     # should print Textual usage / no traceback
dr-load preflight # verifies REST connectivity once .env is in place
```

---

## Bumping the version

1. Update `__version__.py` (the spec reads from there via `make`).
2. Add a `%changelog` entry at the top of `packaging/dr-tools.spec`.
3. Commit + tag (e.g. `git tag v0.07.1`), then rebuild:

```bash
cd packaging
make clean
make rpm
```

`Makefile`'s `VERSION` is auto-discovered from `__version__.py`, so no
hardcoded version string needs touching for normal bumps.
