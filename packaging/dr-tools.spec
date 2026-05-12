# RPM spec for `dr-tools` — bundles dr-tui + dr-load and their deps into
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
  dr-tui    Textual TUI dashboard — landing page with live License,
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

# Drop launcher scripts in /usr/bin so dr-tui / dr-load are on PATH.
mkdir -p %{buildroot}/usr/bin
cat > %{buildroot}/usr/bin/dr-tui <<'EOF'
#!/bin/sh
exec /opt/dr-tools/venv/bin/dr-tui "$@"
EOF
cat > %{buildroot}/usr/bin/dr-load <<'EOF'
#!/bin/sh
exec /opt/dr-tools/venv/bin/dr-load "$@"
EOF
chmod 0755 %{buildroot}/usr/bin/dr-tui %{buildroot}/usr/bin/dr-load

# Drop a sample .env so a fresh install has something to copy from.
mkdir -p %{buildroot}%{drroot}/share
install -m 0644 .env.example %{buildroot}%{drroot}/share/env.example

%files
%defattr(-,root,root,-)
%doc README.md CHANGELOG.md DR_Workflow_Guide.md docs/endpoints_v0.05.md docs/endpoints_v0.06.md
%license __version__.py
%{drroot}/venv
%{drroot}/share/env.example
/usr/bin/dr-tui
/usr/bin/dr-load

%post
echo "dr-tools installed to %{drroot}/venv"
echo "  dr-tui and dr-load are now on PATH"
echo "  copy %{drroot}/share/env.example → ~/.env (or /etc/dr-tools/.env)"
echo "  and edit the DR_HOST / DR_USER / DR_PASS values."

%postun
# Nothing to clean up — the venv lives under our own /opt/dr-tools tree
# and is fully removed by RPM's automatic file management.

%changelog
* Tue May 12 2026 Mac McClelland <mmcclelland@digitalreefinc.com> - 0.07-1
- Initial RPM packaging
- Self-contained venv install at /opt/dr-tools/venv
- /usr/bin/dr-tui and /usr/bin/dr-load launchers
- Bundled wheelhouse (offline-installable)
