# RPM spec for `dr-tools` — bundles dr_tui + dr-load and their deps into
# a self-contained venv under /opt/dr-tools.
#
# Build flow:
#   make wheels   # builds dist/wheelhouse with every dep as a .whl
#   make srpm     # tars the source + wheelhouse, then rpmbuild --bs
#   make rpm      # rpmbuild --bb against the tarball
#
# The package is **offline-installable** — every dependency wheel is
# shipped inside the source tarball, so no internet access is required
# at install time on the target host.

%global py3 /usr/bin/python3
%global drroot /opt/dr-tools
# v0.17.10 — REEF-A-TUI ("Ratatouille") rebrand. The collection of
# Digital-Reef ops tools (dr_tui, dr-load, DR_freshinstall.py, the
# expect installer, cleandr) is collectively named REEF-A-TUI. The
# Python venv stays at /opt/dr-tools/venv for backward compatibility
# (it's where every existing wrapper / shebang points), but the
# user-facing tool scripts also land under /opt/digitalreef/scripts/
# reef-a-tui/ so admins can `cd` into one canonical place to read,
# diff, or hand-edit them.
%global reefroot /opt/digitalreef/scripts/reef-a-tui

# Self-contained venv — disable auto-generated debuginfo subpackage
# (only relevant for C source; our payload is Python + prebuilt wheels).
%global debug_package %{nil}

# Disable RPM's auto-discovery of Python deps (we use a self-contained
# venv, so system-level Python deps would just cause spurious failures).
AutoReqProv: no

Name:           dr-tools
Version:        %{?version}%{!?version:0.07}
Release:        1%{?dist}
Summary:        Digital Reef eDiscovery load tester + Textual TUI dashboard
License:        Proprietary
URL:            https://github.com/mbmcclelland/ediscovery_tests
Source0:        %{name}-%{version}.tar.gz

BuildArch:      x86_64
# Most pure-Python wheels build fine on any arch, but psutil + psycopg2
# ship C extensions — pin to x86_64 since that's our lab target. To
# rebuild for arm64, regenerate the wheelhouse on an arm64 host.

BuildRequires:  python3 >= 3.9
BuildRequires:  python3-pip
# rpmbuild also needs the standard /usr/bin/install + /bin/mkdir from
# coreutils, which is always present.

Requires:       python3 >= 3.9
Requires:       glibc
# psutil + psycopg2 link against glibc; everything else is pure-Python.

%description
dr-tools packages two Digital Reef eDiscovery utilities into a single
self-contained Python venv at /opt/dr-tools/venv with launcher scripts
on PATH:

  dr-load   Headless load-test CLI — preflight, background monitoring,
            merged CSV reports for the eDiscovery REST API.
  dr_tui    Textual TUI dashboard — landing page with live License,
            Realm Node Status, system metrics, log stream, and top
            processes; per-org drill-down with full CRUD on storage
            depots, system users, and system groups.

Both tools talk to the Digital Reef REST API at the host configured in
your .env (default https://192.168.58.128:8443/ediscovery/rest).

%prep
%setup -q

%build
# No-op. The wheels are pre-built. The RPM build is just a copy + venv
# initialisation step done in the install phase.

%install
rm -rf %{buildroot}

# Create the venv inside the buildroot.
mkdir -p %{buildroot}%{drroot}
%{py3} -m venv %{buildroot}%{drroot}/venv

# Install every shipped wheel into the venv. --no-index keeps pip
# strictly offline; --find-links points at the bundled wheelhouse.
%{buildroot}%{drroot}/venv/bin/pip install \
    --no-index \
    --find-links=dist/wheelhouse \
    --no-deps \
    dist/wheelhouse/*.whl

# The shebangs inside the venv point at the buildroot — rewrite them
# to the final install path so the scripts work on the target.
find %{buildroot}%{drroot}/venv/bin -type f \
    -exec sed -i 's|%{buildroot}%{drroot}|%{drroot}|g' {} \;

# Drop launcher scripts in /usr/bin so dr_tui / dr-load are on PATH.
# v0.19.2 — the canonical (underscore) wrapper is `dr_tui`; the
# legacy hyphen form `dr-tui` is now a symlink to it. Reverses the
# v0.17.10 layout where `dr-tui` was canonical and `dr_tui` the
# symlink. End behaviour identical (both work), but every doc and
# install-time banner now points at the underscore form first.
mkdir -p %{buildroot}/usr/bin
cat > %{buildroot}/usr/bin/dr_tui <<'EOF'
#!/bin/sh
# PuTTY (and some other older SSH clients) advertises TERM=xterm which
# lacks 256-color and confuses Textual's terminal-capability probes.
# Force xterm-256color when terminfo for it exists and TERM looks weak.
if [ "$TERM" = "xterm" ] && [ -f /usr/share/terminfo/x/xterm-256color ]; then
    TERM=xterm-256color
fi
# PuTTY swallows the kitty-keyboard handshake (CSI > 1 u) — keep
# Textual on the simpler ANSI input path unless the user explicitly
# wants enhancements via TEXTUAL_FEATURES=...
: "${TEXTUAL_FEATURES=}"
export TERM TEXTUAL_FEATURES
# /opt/dr-tools/venv/bin/dr-tui is the Python console_script entry
# point from setup.cfg — kept hyphenated there because that's where
# the venv bin name lives. The user-facing /usr/bin/dr_tui wrapper
# is what's documented; the system never asks you to type
# /opt/dr-tools/venv/bin/anything.
exec /opt/dr-tools/venv/bin/dr-tui "$@"
EOF
cat > %{buildroot}/usr/bin/dr-load <<'EOF'
#!/bin/sh
exec /opt/dr-tools/venv/bin/dr-load "$@"
EOF
# v0.15 — also ship the Job Scheduler CLIs (added in v0.13).
cat > %{buildroot}/usr/bin/dr-job-run <<'EOF'
#!/bin/sh
exec /opt/dr-tools/venv/bin/dr-job-run "$@"
EOF
cat > %{buildroot}/usr/bin/dr-job-delete <<'EOF'
#!/bin/sh
exec /opt/dr-tools/venv/bin/dr-job-delete "$@"
EOF

# v0.17.10 — REEF-A-TUI ("Ratatouille") collection. Drop the
# user-facing scripts into /opt/digitalreef/scripts/reef-a-tui/
# so admins can read, diff, or hand-tweak them in one canonical
# place. The Python venv stays at /opt/dr-tools/venv (every
# shebang points there); these files are the orchestration layer
# that the venv doesn't ship.
mkdir -p %{buildroot}%{reefroot}
install -m 0755 DR_freshinstall.py    %{buildroot}%{reefroot}/DR_freshinstall.py
install -m 0755 DR_freshinstall.exp   %{buildroot}%{reefroot}/DR_freshinstall.exp
install -m 0755 cleandr.sh            %{buildroot}%{reefroot}/cleandr.sh
install -m 0644 reef-a-tui-logo.txt   %{buildroot}%{reefroot}/reef-a-tui-logo.txt
install -m 0644 reef-a-tui-logo.go    %{buildroot}%{reefroot}/reef-a-tui-logo.go

# v0.19.2 — `dr-tui` (legacy hyphen alias) symlinks to `dr_tui`
# (canonical). Reverse of the v0.17.10 layout. The hyphen alias is
# kept for muscle memory + any user scripts that already call
# `dr-tui` directly; new users + every doc reference uses `dr_tui`.
ln -sf dr_tui %{buildroot}/usr/bin/dr-tui

# `dr_freshinstall` (canonical, v0.19.2) — entry point for the
# end-to-end fresh-install driver. The script lives at
# /opt/digitalreef/scripts/reef-a-tui/DR_freshinstall.py and uses
# the venv's Python interpreter (which has Rich, requests, urllib3,
# and the dr_tui.data helpers all pre-installed). The hyphen form
# `dr-freshinstall` is kept as a back-compat symlink.
cat > %{buildroot}/usr/bin/dr_freshinstall <<'EOF'
#!/bin/sh
# Launcher for the REEF-A-TUI ("Ratatouille") fresh-install driver.
# Run with no args for help; --force for the full destructive
# teardown + reinstall + 13 API-provisioning steps.
exec /opt/dr-tools/venv/bin/python3 \
    /opt/digitalreef/scripts/reef-a-tui/DR_freshinstall.py "$@"
EOF
chmod 0755 %{buildroot}/usr/bin/dr_freshinstall
ln -sf dr_freshinstall %{buildroot}/usr/bin/dr-freshinstall

chmod 0755 %{buildroot}/usr/bin/dr_tui \
            %{buildroot}/usr/bin/dr-load \
            %{buildroot}/usr/bin/dr-job-run \
            %{buildroot}/usr/bin/dr-job-delete

# Drop a sample .env so a fresh install has something to copy from.
mkdir -p %{buildroot}%{drroot}/share
install -m 0644 .env.example %{buildroot}%{drroot}/share/env.example

%files
%defattr(-,root,root,-)
%doc README.md CHANGELOG.md DR_Workflow_Guide.md docs/endpoints_v0.05.md docs/endpoints_v0.06.md docs/QA_TEST_PLAN.md docs/RUNBOOK.md docs/DR_ROLE_SETUP.md BETA_USER_README.md
%license __version__.py
# v0.15: own the /opt/dr-tools and share/ directories so `dnf remove`
# cleans them up too (rather than leaving an empty share/ behind).
%dir %{drroot}
%dir %{drroot}/share
%{drroot}/venv
%{drroot}/share/env.example
# v0.17.10 — REEF-A-TUI script collection.
%dir /opt/digitalreef
%dir /opt/digitalreef/scripts
%dir %{reefroot}
%{reefroot}/DR_freshinstall.py
%{reefroot}/DR_freshinstall.exp
%{reefroot}/cleandr.sh
%{reefroot}/reef-a-tui-logo.txt
%{reefroot}/reef-a-tui-logo.go
# v0.19.2 — `dr_tui` + `dr_freshinstall` are the canonical underscore
# wrappers; `dr-tui` + `dr-freshinstall` are legacy alias symlinks.
# `dr-load`, `dr-job-run`, `dr-job-delete` have no underscore form
# (the entry points were always hyphenated and there's no name
# collision to resolve).
/usr/bin/dr_tui
/usr/bin/dr-tui
/usr/bin/dr-load
/usr/bin/dr-job-run
/usr/bin/dr-job-delete
/usr/bin/dr_freshinstall
/usr/bin/dr-freshinstall

%post
cat <<'BANNER'

  ╭──────────────────────────────────────────────────────────────╮
  │  REEF-A-TUI installed — Digital Reef ops toolkit             │
  ╰──────────────────────────────────────────────────────────────╯

  On PATH (canonical names; hyphenated forms are aliases):
    dr_tui                       Textual TUI dashboard
    dr_freshinstall              End-to-end fresh-install driver
                                 (run with no args for help)
    dr-load                      Load-test CLI
    dr-job-run / dr-job-delete   Indexing-chain CLIs

  Scripts:    /opt/digitalreef/scripts/reef-a-tui/
  Venv:       /opt/dr-tools/venv
  Sample env: /opt/dr-tools/share/env.example

  Quick start:
    cp /opt/dr-tools/share/env.example  ~/.env
    $EDITOR ~/.env       # DR_HOST / DR_USER / DR_PASS
    dr_tui

  For a brand-new DR install from scratch:
    sudo dr_freshinstall --force

BANNER

%postun
# Nothing to clean up — the venv lives under our own /opt/dr-tools tree
# and is fully removed by RPM's automatic file management.

%changelog
* Tue May 12 2026 Mac McClelland <mmcclelland@digitalreefinc.com> - 0.07-1
- Initial RPM packaging
- Self-contained venv install at /opt/dr-tools/venv
- /usr/bin/dr-tui and /usr/bin/dr-load launchers
- Bundled wheelhouse (offline-installable)
