#!/usr/bin/env bash
#
# scripts/demo-capture.sh
#
# Capture the three hero screens of the v0.15 demo as ANSI-preserved
# text files. Run AFTER scripts/demo-prep.sh has populated /tmp/demo.db.
#
# Replay any captured screen with `cat /tmp/demo-captures/<file>` and
# the terminal will re-render the colors as if the live command had
# just run. Use as a fallback if the SUT or recorder misbehaves on
# stage.
#
# Usage:
#   ./scripts/demo-capture.sh                # capture to /tmp/demo-captures/
#   ./scripts/demo-capture.sh --store PATH   # use a non-default store
#   ./scripts/demo-capture.sh --out DIR      # capture to a non-default dir

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_STORE=/tmp/demo.db
OUT_DIR=/tmp/demo-captures
ORG=training

while [[ $# -gt 0 ]]; do
    case "$1" in
        --store) DEMO_STORE="$2"; shift 2 ;;
        --out)   OUT_DIR="$2";   shift 2 ;;
        -h|--help) sed -n '3,16p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$REPO_ROOT"
source .venv/bin/activate

mkdir -p "$OUT_DIR"

# `script` preserves ANSI escapes — `cat <file>` replays them as if the
# terminal had run the command live. -q = quiet (no header/footer noise).

echo ">> Capturing dashboard..."
script -q -c "dr-load admin dashboard --rich --org $ORG" \
    "$OUT_DIR/dashboard.ansi" > /dev/null

echo ">> Capturing recorder status..."
script -q -c "dr-load record status --rich --store $DEMO_STORE" \
    "$OUT_DIR/record-status.ansi" > /dev/null

echo ">> Capturing report (audience=mgmt)..."
script -q -c "dr-load report --store $DEMO_STORE --audience mgmt" \
    "$OUT_DIR/report-mgmt.ansi" > /dev/null

echo ">> Capturing report (audience=capacity)..."
script -q -c "dr-load report --store $DEMO_STORE --audience capacity" \
    "$OUT_DIR/report-capacity.ansi" > /dev/null

cat <<EOF

=============================================================
Captures saved to: $OUT_DIR/

Replay any on stage if the live demo glitches:

  cat $OUT_DIR/dashboard.ansi
  cat $OUT_DIR/record-status.ansi
  cat $OUT_DIR/report-mgmt.ansi
  cat $OUT_DIR/report-capacity.ansi
=============================================================
EOF
