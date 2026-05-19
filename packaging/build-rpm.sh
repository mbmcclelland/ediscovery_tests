#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build-rpm.sh — Build the dr-load-toolkit noarch RPM
#
# PREREQUISITES (install with: sudo dnf install <pkg>):
#   rpm-build          — rpmbuild command
#   python3            — Python 3.9+
#   python3-pip        — pip3 for building/downloading wheels
#   python3-setuptools — setuptools for the wheel build
#   python3-wheel      — wheel format support (pip install wheel if not in dnf)
#
# USAGE:
#   cd /root/scripts/ediscovery_tests-master
#   bash packaging/build-rpm.sh
#
# OUTPUT:
#   packaging/output/dr-load-toolkit-<version>-1.noarch.rpm
#
# IDEMPOTENT: Safe to run multiple times. Cleans the rpmbuild working tree on
# each run to avoid stale artifact issues.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Locate repo root ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Read version from __version__.py ─────────────────────────────────────────
VERSION="$(python3 -c "import sys; sys.path.insert(0, '${REPO_ROOT}'); from __version__ import __version__; print(__version__)")"
echo ">> Building dr-load-toolkit version ${VERSION}"

# ── Verify prerequisites ──────────────────────────────────────────────────────
for cmd in rpmbuild python3 pip3; do
    command -v "${cmd}" > /dev/null 2>&1 || {
        echo "ERROR: '${cmd}' not found. Install rpm-build and python3-pip."
        exit 1
    }
done

# Ensure wheel is available (pip subcommand, not necessarily a standalone pkg)
python3 -c "import wheel" 2>/dev/null || {
    echo ">> 'wheel' package not found — installing via pip..."
    pip3 install --quiet wheel
}

# ── Set up rpmbuild tree ──────────────────────────────────────────────────────
RPMBUILD_DIR="${HOME}/rpmbuild"
for d in BUILD BUILDROOT RPMS SOURCES SPECS SRPMS; do
    mkdir -p "${RPMBUILD_DIR}/${d}"
done

OUTPUT_DIR="${SCRIPT_DIR}/output"
mkdir -p "${OUTPUT_DIR}"

SOURCES_DIR="${RPMBUILD_DIR}/SOURCES"
WHEELS_DIR="${SOURCES_DIR}/wheels"

# Clean previous wheel cache to avoid mixing versions across builds
rm -rf "${WHEELS_DIR}"
mkdir -p "${WHEELS_DIR}"

# ── Step 1: Build the dr-load-toolkit wheel ───────────────────────────────────
echo ">> Building dr-load-toolkit wheel..."
cd "${REPO_ROOT}"

# Build a wheel from the repo source tree.
# Output goes directly into the SOURCES/wheels directory.
python3 -m pip wheel . \
    --wheel-dir "${WHEELS_DIR}" \
    --no-deps \
    --quiet

# setup.cfg name = ediscovery-tests, so pip produces ediscovery_tests-*.whl
WHEEL_FILE="$(ls "${WHEELS_DIR}"/ediscovery_tests-*.whl 2>/dev/null | head -1)"
if [[ -z "${WHEEL_FILE}" ]]; then
    WHEEL_FILE="$(ls "${WHEELS_DIR}"/*.whl 2>/dev/null | head -1)"
fi
[[ -z "${WHEEL_FILE}" ]] && { echo "ERROR: wheel build produced no .whl file"; exit 1; }
echo ">> Wheel: $(basename "${WHEEL_FILE}")"

# ── Step 2: Download runtime dependency wheels ────────────────────────────────
echo ">> Downloading runtime dependency wheels..."
# Parse install_requires from setup.cfg and download all transitive deps.
# We do NOT download build-only deps (pytest, locust, etc.) that are listed
# in requirements.txt but not in setup.cfg install_requires — only the runtime
# subset needed to run dr-load on the target host matters here.
#
# Runtime deps (from setup.cfg install_requires):
RUNTIME_DEPS=(
    "requests>=2.31.0"
    "python-dotenv>=1.0.0"
    "pydantic>=2.5.0"
    "typer>=0.9.0"
    "rich>=13.0.0"
    "psycopg2-binary>=2.8.0"
)

pip3 download \
    --dest "${WHEELS_DIR}" \
    --only-binary :all: \
    --python-version 3.9 \
    --platform manylinux2014_x86_64 \
    --quiet \
    "${RUNTIME_DEPS[@]}" || {
    echo "WARNING: some binary wheels not available for manylinux2014_x86_64 platform."
    echo "         Falling back to source-compatible download (no platform filter)..."
    pip3 download \
        --dest "${WHEELS_DIR}" \
        --quiet \
        "${RUNTIME_DEPS[@]}"
}

echo ">> Wheels in cache: $(ls "${WHEELS_DIR}"/*.whl | wc -l)"

# ── Step 3: Stage additional SOURCES ─────────────────────────────────────────
echo ">> Staging SOURCES..."

# Systemd unit
install -D -m 0644 "${SCRIPT_DIR}/systemd/dr-load-recorder.service" \
    "${SOURCES_DIR}/systemd/dr-load-recorder.service"

# Environment file template
install -m 0644 "${SCRIPT_DIR}/dr-load-recorder.env.example" \
    "${SOURCES_DIR}/dr-load-recorder.env.example"

# Fixture testload data
install -d "${SOURCES_DIR}/testload"
install -m 0644 "${REPO_ROOT}/tests/fixtures/testload/doc1.txt" "${SOURCES_DIR}/testload/"
install -m 0644 "${REPO_ROOT}/tests/fixtures/testload/doc2.txt" "${SOURCES_DIR}/testload/"

# ── Step 4: Copy spec file ─────────────────────────────────────────────────────
echo ">> Copying spec to rpmbuild SPECS..."
cp "${SCRIPT_DIR}/dr-load.spec" "${RPMBUILD_DIR}/SPECS/dr-load.spec"

# ── Step 5: Run rpmbuild ──────────────────────────────────────────────────────
echo ">> Running rpmbuild (version=${VERSION} from __version__.py)..."
rpmbuild -bb \
    --define "_topdir ${RPMBUILD_DIR}" \
    --define "_sourcedir ${SOURCES_DIR}" \
    --define "_version ${VERSION}" \
    "${RPMBUILD_DIR}/SPECS/dr-load.spec" 2>&1 | tee /tmp/rpmbuild.log

# ── Step 6: Collect output ────────────────────────────────────────────────────
# Search all arch subdirs — the package may build as x86_64 if bundled wheels
# include compiled extensions (pydantic-core, charset-normalizer .so files).
RPM_FILE="$(find "${RPMBUILD_DIR}/RPMS" -name "dr-load-toolkit-*.rpm" | head -1)"
if [[ -z "${RPM_FILE}" ]]; then
    echo "ERROR: RPM not found under ${RPMBUILD_DIR}/RPMS/"
    echo "       Check /tmp/rpmbuild.log for details."
    exit 1
fi

cp "${RPM_FILE}" "${OUTPUT_DIR}/"
echo ""
echo "======================================================================"
echo "SUCCESS: $(basename "${RPM_FILE}")"
echo "  Full path:  ${OUTPUT_DIR}/$(basename "${RPM_FILE}")"
echo ""
echo "Verify contents:"
echo "  rpm -qpl ${OUTPUT_DIR}/$(basename "${RPM_FILE}")"
echo ""
echo "Verify declared deps:"
echo "  rpm -qpR ${OUTPUT_DIR}/$(basename "${RPM_FILE}")"
echo ""
echo "Install on target host:"
echo "  sudo dnf install ${OUTPUT_DIR}/$(basename "${RPM_FILE}")"
echo "======================================================================"
