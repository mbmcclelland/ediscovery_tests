#!/usr/bin/env bash
#
# scripts/demo-prep.sh
#
# Pre-stages /tmp/demo.db with believable real data for the 30-min dev demo.
# Runs ~8 min total: starts the recorder, opens a campaign, submits one
# small import job, sprinkles in mid-flight adjustments + annotations,
# then stops cleanly.
#
# After completion the store has:
#   - ~50 samples per signal (8 min @ 10s tick)
#   - 1 campaign with 4 events (START, ADJUST, ANNOTATE, END)
#   - Real CPU / Memory / Disk / Indexing-rate metrics from the live SUT
#
# The live demo runs `dr-load report` etc. against this store. Operator
# can also leave the recorder running by passing `--keep-running`.
#
# Usage:
#   ./scripts/demo-prep.sh                 # default 8-min pre-stage, stops at end
#   ./scripts/demo-prep.sh --keep-running  # daemon stays up after pre-stage
#   ./scripts/demo-prep.sh --store PATH    # override store location

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_STORE=/tmp/demo.db
DEMO_CAMPAIGN=q2-soak
KEEP_RUNNING=0
ORG=training
CONNECTOR=training-import-nfs-local

# ── Argument parsing ─────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep-running)
            KEEP_RUNNING=1
            shift
            ;;
        --store)
            DEMO_STORE="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '3,25p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

cd "$REPO_ROOT"
source .venv/bin/activate

# ── Clean prior state ────────────────────────────────────────────────────
echo ">> [setup] Cleaning prior demo state..."
DEMO_DIR="$(dirname "$DEMO_STORE")"
DEMO_STEM="$(basename "$DEMO_STORE" .db)"
/bin/rm -f "$DEMO_STORE" \
            "$DEMO_DIR/${DEMO_STEM}.pid" \
            "$DEMO_DIR/${DEMO_STEM}.log" 2>/dev/null || true

# ── Run ──────────────────────────────────────────────────────────────────
echo ">> [1/7] Starting recorder (10s tick, store=$DEMO_STORE)..."
dr-load record start --store "$DEMO_STORE" --tick 10

# Let the daemon settle and write a few baseline samples
sleep 30

echo ">> [2/7] Opening campaign '$DEMO_CAMPAIGN' (10 initial users)..."
dr-load campaign new "$DEMO_CAMPAIGN" \
    --scenario indexing \
    --users 10 \
    --note "demo prep — pre-staged data for 30-min dev presentation" \
    --store "$DEMO_STORE"

# Baseline window (so the campaign has an opening period of stability)
echo ">> [3/7] Accumulating baseline samples (60s)..."
sleep 60

echo ">> [4/7] Submitting small import job (demo-prep-small)..."
dr-load admin create-project demo-prep-small \
    --org "$ORG" \
    -d "demo prep, do not delete" \
    --lifetime 1h \
    > /dev/null
dr-load admin create-import-job demo-prep-small \
    -c "$CONNECTOR" \
    --path /small \
    --org "$ORG" \
    > /dev/null

# Wait for indexing to be visible in the recorder's docs/min signal
sleep 60

echo ">> [5/7] Mid-flight ADJUST + ANNOTATE..."
dr-load campaign adjust --users 25 --note "ramped to 25 users" --store "$DEMO_STORE"
sleep 30
dr-load campaign event "added 4GB heap to JBoss" --store "$DEMO_STORE"

# Let the small job finish (calibration: ~4 min)
echo ">> [6/7] Letting the small job finish (~3 min)..."
sleep 180

dr-load campaign adjust --users 50 --note "ramp to peak" --store "$DEMO_STORE"
sleep 30

# ── Teardown ─────────────────────────────────────────────────────────────
if [[ "$KEEP_RUNNING" -eq 1 ]]; then
    echo ">> [7/7] Pre-stage complete. Recorder still running."
    echo "         Stop it manually before the next prep: dr-load record stop --store $DEMO_STORE"
else
    echo ">> [7/7] Stopping recorder..."
    dr-load record stop --store "$DEMO_STORE" > /dev/null
fi

# Clean up the demo project so we don't pollute the org.
# delete-project cancels any pending at-job by default (--cancel-schedule),
# so the --lifetime 1h at-job queued by create-project is also removed here.
dr-load admin delete-project demo-prep-small --org "$ORG" > /dev/null 2>&1 || true

# ── Summary ──────────────────────────────────────────────────────────────
cat <<EOF

=============================================================
Demo store ready: $DEMO_STORE
Campaign:         $DEMO_CAMPAIGN

Preview the three hero screens before the demo:

  dr-load admin dashboard --rich --org $ORG
  dr-load record status --rich --store $DEMO_STORE
  dr-load report --store $DEMO_STORE --audience mgmt

Next: capture them as backup with scripts/demo-capture.sh
=============================================================
EOF
