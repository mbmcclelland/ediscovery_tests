"""
DEPRECATED — superseded by `dr-load admin` in v0.04+.

This script used to debug the createDataArea + createCorpus +
createRepresentation chain inline, replicating the Edge-recorded
browser flow with hardcoded per-install handle defaults. Those
defaults silently broke on any host that wasn't the one they were
captured on (BUG_LOG B14a).

The same workflow is now in `helpers/admin_ops.py`. The equivalent
CLI:

    dr-load admin create-project NAME --org ORG
    dr-load admin create-import-job NAME -c training-import-nfs-local \\
        --path /testload --org ORG
    # ... wait for indexing ...
    dr-load admin delete-project NAME --org ORG

See QA_README.md §4 for worked examples.

If you need the legacy version, check it out from git history before
the v0.08 commit.
"""

from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write(__doc__)
    sys.stderr.write("\nRefusing to run — use `dr-load admin` instead.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
