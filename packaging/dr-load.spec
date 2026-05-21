# _version may be overridden by build-rpm.sh via --define; the literal
# below is the fallback used when the spec is invoked directly. Keep
# this value in sync with __version__.py.
%{!?_version: %define _version 0.15}
%define _pkgname dr-load-toolkit
%define _recorder_user auraria
%define _sysconfig_dir %{_sysconfdir}/sysconfig
%define _wheels_dir %{_datadir}/dr-load/wheels
%define _testload_dir %{_datadir}/dr-load/testload
%define _recorder_state /var/lib/dr-load-recorder
%define _recorder_log /var/log/dr-load-recorder.log

Name:           %{_pkgname}
Version:        %{_version}
Release:        1%{?dist}
Summary:        Digital Reef eDiscovery load-test CLI and recorder daemon
License:        Proprietary
URL:            https://www.digitalreefinc.com
# NOTE: Although the dr-load source itself is pure Python, bundled wheels
# include compiled extensions (pydantic-core, charset-normalizer) that are
# architecture-specific.  We therefore omit BuildArch: noarch so rpmbuild
# correctly generates an x86_64 package.
# If a truly noarch build is required, replace pydantic with pydantic v1
# (pure Python) and pin charset-normalizer to a pure-Python wheel.

# ── Runtime requirements ─────────────────────────────────────────────────────
# Python 3.9+ — matches python_requires in setup.cfg.
# pip + setuptools needed for the %post wheel install step.
# atd (at daemon) is used by dr-load admin --lifetime for job scheduling.
Requires:       python3 >= 3.9
Requires:       python3-pip
Requires:       python3-setuptools
Requires:       at

# ── Build-time requirements ──────────────────────────────────────────────────
# python3-wheel: needed to build a wheel from the source tree.
# rpm-build: assumed present on any build host.
BuildRequires:  python3
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools

%description
dr-load is the Digital Reef eDiscovery load-test and administration CLI.
It ships seven verb-groups:

  preflight   Validate connectivity and auth to a DR server
  indexing    Indexing load scenarios (Locust-backed)
  browsing    Browsing load scenarios (Locust-backed)
  admin       12 subcommands for org/project/job lifecycle management
  record      Start/stop/status the background metric recorder daemon
  campaign    Named test campaign lifecycle (new/adjust/event/end/list/show)
  report      Render campaign reports from the SQLite TSDB

The recorder daemon (dr-load-recorder.service) samples DR API metrics every
10 seconds and writes them to a local SQLite store for later reporting.

%prep
# Nothing to prep — source is installed directly from the build host's
# working copy via the build-rpm.sh script, which stages files under SOURCES.
# The install section below does the real work.

%build
# The wheel is pre-built by build-rpm.sh and provided in SOURCE1.
# No compilation needed for a pure-Python package.

%install
rm -rf %{buildroot}

# ── 1. Install the dr-load wheel into the buildroot via pip ─────────────────
# --no-index: no network access; use only our bundled wheels.
# --find-links: point pip at the wheels cache baked into the source tarball.
# --root: install into buildroot so rpmbuild can build the file manifest.
# --prefix: /usr — consistent with RPM-owned site-packages.
# Install the dr-load wheel first (no-deps: test deps excluded from runtime).
pip3 install \
    --no-index \
    --find-links=%{_sourcedir}/wheels \
    --root=%{buildroot} \
    --prefix=/usr \
    --no-warn-script-location \
    --no-deps \
    %{_sourcedir}/wheels/ediscovery_tests-*.whl

# Then install only the runtime dependency wheels from the bundled cache.
# Test-only deps (pytest, locust, psycopg2-binary) are intentionally excluded
# — they live in setup.cfg install_requires but are not needed at runtime on
# the target host. Only the CLI runtime subset is bundled here.
pip3 install \
    --no-index \
    --find-links=%{_sourcedir}/wheels \
    --root=%{buildroot} \
    --prefix=/usr \
    --no-warn-script-location \
    "requests>=2.31.0" \
    "python-dotenv>=1.0.0" \
    "pydantic>=2.5.0" \
    "typer>=0.9.0" \
    "rich>=13.0.0"

# ── 2. Systemd unit ──────────────────────────────────────────────────────────
install -D -m 0644 %{_sourcedir}/systemd/dr-load-recorder.service \
    %{buildroot}%{_unitdir}/dr-load-recorder.service

# ── 3. Environment-file template ─────────────────────────────────────────────
install -D -m 0640 %{_sourcedir}/dr-load-recorder.env.example \
    %{buildroot}%{_sysconfig_dir}/dr-load-recorder

# ── 4. Fixture data (canonical 2-doc testload corpus) ────────────────────────
install -d %{buildroot}%{_testload_dir}
install -m 0644 %{_sourcedir}/testload/doc1.txt %{buildroot}%{_testload_dir}/
install -m 0644 %{_sourcedir}/testload/doc2.txt %{buildroot}%{_testload_dir}/

# ── 4a. Logrotate config (daily rotation, 14d retention, restart on rotate) ──
install -D -m 0644 %{_sourcedir}/logrotate/dr-load-recorder \
    %{buildroot}%{_sysconfdir}/logrotate.d/dr-load-recorder

# ── 5. Bundled wheels cache (for offline pip install at %post time) ───────────
install -d %{buildroot}%{_wheels_dir}
cp %{_sourcedir}/wheels/*.whl %{buildroot}%{_wheels_dir}/

# ── 6. Runtime directories created at install time via %post; just ghost them ─
install -d %{buildroot}%{_recorder_state}

%pre
# Create the recorder state directory with correct ownership if it does not
# already exist.  Run silently on upgrade as well.
getent passwd %{_recorder_user} > /dev/null || {
    echo "WARNING: service account '%{_recorder_user}' does not exist on this host."
    echo "         The recorder daemon will fail to start."
    echo "         Create the account or adjust EnvironmentFile before enabling."
}

%post
# ── Enable atd (needed by dr-load admin --lifetime) ──────────────────────────
systemctl enable --now atd > /dev/null 2>&1 || true

# ── Create runtime directories ───────────────────────────────────────────────
install -d -m 0750 -o %{_recorder_user} -g %{_recorder_user} \
    %{_recorder_state} 2>/dev/null || true

install -d -m 0750 -o %{_recorder_user} -g %{_recorder_user} \
    $(dirname %{_recorder_log}) 2>/dev/null || true

# Touch log file so logrotate picks it up immediately
touch %{_recorder_log} && \
    chown %{_recorder_user}:%{_recorder_user} %{_recorder_log} 2>/dev/null || true

# ── Register unit with systemd (but do NOT enable or start) ──────────────────
# Operators enable it explicitly: systemctl enable --now dr-load-recorder
%systemd_post dr-load-recorder.service

%preun
%systemd_preun dr-load-recorder.service

%postun
%systemd_postun_with_restart dr-load-recorder.service

%files
%defattr(-,root,root,-)

# ── dr-load console script ───────────────────────────────────────────────────
%{_bindir}/dr-load

# ── Console scripts installed by bundled deps (pip adds these alongside dr-load)
# These are part of the runtime dep wheels: typer, python-dotenv, rich, etc.
%{_bindir}/dotenv
%{_bindir}/markdown-it
%{_bindir}/normalizer
%{_bindir}/pygmentize
%{_bindir}/typer

# ── All Python packages installed into site-packages by pip ──────────────────
# /usr/lib covers pure-Python packages.
# /usr/lib64 covers packages with compiled extensions (pydantic-core,
# charset-normalizer) that pip installs into the arch-specific lib64 path.
/usr/lib/python3.9/site-packages/
/usr/lib64/python3.9/site-packages/

# ── Systemd unit ─────────────────────────────────────────────────────────────
%{_unitdir}/dr-load-recorder.service

# ── Environment file (config — not replaced on upgrade) ──────────────────────
%config(noreplace) %{_sysconfig_dir}/dr-load-recorder

# ── Fixture data ──────────────────────────────────────────────────────────────
%{_testload_dir}/

# ── Logrotate config (root:root, mode 0644 — system config) ──────────────────
%config(noreplace) %{_sysconfdir}/logrotate.d/dr-load-recorder

# ── Bundled wheels cache ──────────────────────────────────────────────────────
%{_wheels_dir}/

# ── Runtime state dir (owned by package; contents managed by daemon) ─────────
%dir %attr(0750,%{_recorder_user},%{_recorder_user}) %{_recorder_state}

%changelog
* Mon May 19 2025 Digital Reef Packaging <packaging@digitalreefinc.com> - 0.14-1
- Initial RPM packaging for dr-load-toolkit v0.14
- Ships dr-load CLI console script at /usr/bin/dr-load
- Ships dr-load-recorder systemd unit (disabled by default)
- Bundles Python runtime wheels for offline install (no network required)
- Includes canonical 2-doc testload fixture corpus at /usr/share/dr-load/testload
- Environment file template at /etc/sysconfig/dr-load-recorder (config noreplace)
