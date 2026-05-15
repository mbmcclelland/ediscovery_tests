# DR Web UI walkthrough — grant Connectors permission to admin@training

> ## ⚠ Historical — no longer required as of v0.15.2
>
> This walkthrough was written during QA-16 under the (incorrect)
> theory that admin@training's role was missing connector
> permissions in DR 5.5.3.2. **The v0.15.2 systemScope discovery
> proved the actual root cause was on our side** — we were
> auto-injecting `"systemScope": True` into every request, which made
> DR check against super-system permissions rather than the org-context
> role's permissions. The default Organization Administrator role
> actually has full connector access.
>
> **You do NOT need to perform this role grant for default installs.**
> The Job Scheduler tab and all of dr_tui's connector-aware features
> work out of the box for both DRSysAdmin and admin@training.
>
> This document is preserved for the rare case where someone DOES
> need to customize role permissions for a non-default DR setup
> (e.g. tighter security policy, custom roles), and as a reference
> for the DR Web UI's role-management workflow.

---

**When to use (now):** customising DR's role permissions for security
hardening, non-default access patterns, or supplementary roles beyond
the defaults. **NOT needed** to make dr-tools work.

**When the doc thought you needed it (historical):** the dr_tui Job
Scheduler's New Job wizard reports `PERMISSION_DENIED` (or
`PROJECT_NOT_ACTIVATED Project 0 not activated`) on Browse / Count
/ Save. *In v0.15.2+, the fix for that is `pip install -U dr-tools`
or `dnf upgrade dr-tools` — not this walkthrough.*

**What this does:** copies the default Organization Administrator
role into a custom role, adds the missing `Connectors` permissions,
and reassigns admin@training to the new role.

**Time:** ~3 minutes in the Web UI.

**Prerequisites:**
- DRSysAdmin's password is set to `password` (already done by
  `playwright_fresh_init.py`).
- admin@training exists with password `password` (created during
  QA-16 — see `qa_create_org_admin.py`).
- DR is reachable at `https://192.168.58.128:8443/ediscovery/` and
  `drd` is active.

---

## Step 1 — Log into the DR Web UI as DRSysAdmin

1. Open `https://192.168.58.128:8443/ediscovery/` (accept the
   self-signed cert).
2. Username: `DRSysAdmin`, password: `password`.
3. The Home / Organizations landing page should appear with the
   `training` tile.

## Step 2 — Open the training org's Role Permissions

1. Right-click the `training` tile **OR** click its hamburger menu
   `≡`.
2. Choose **Settings**.
3. In the left navigation, expand **General** → click **Role
   Permissions**. (Documented as: *"Home > selected Organization >
   menu or right-click > Settings > General > Role Permissions"*
   per DR PDF "Add, Edit, or Copy a Role".)
4. You'll see four predefined roles listed: **Project
   Administrator**, **Organization Administrator** (this one is
   greyed out — can't be edited directly), **Claimant**, **Project
   Member**.

## Step 3 — Copy the Organization Administrator role

The default Organization Administrator role **cannot be edited or
deleted** (DR design rule). The pattern is to copy it and edit the
copy.

1. Hover over the **Organization Administrator** row → click the
   ellipsis menu `…` → **Copy**.
2. Name the copy: **`Org Admin + Connectors`** (or any descriptive
   name — must be unique inside the org).
3. Click **OK**. The new role appears in the list with the same
   default permissions as Organization Administrator.

## Step 4 — Enable Connectors permissions on the new role

The Role Permissions page shows a matrix: rows = "Secure Object
Types" (grouped by category — System, Settings, Project, etc.);
columns = action checkboxes (View, Add/Edit, Delete, …).

1. Select the **`Org Admin + Connectors`** row you just created.
2. Scroll to the **Settings** group → find the **Connectors** row
   (`fa fa-plug` icon).
3. Check the boxes for these three actions (they may already be
   checked depending on the parent role — verify all three are on):
   - ☑ **View** (`organizationViewState`)
   - ☑ **Add/Edit** (`organizationCreateState`)
   - ☑ **Delete** (`organizationDeleteState`)
4. *(Optional but recommended)* also enable, in the same Settings
   group, **Project Data Areas**'s **View** + **Add/Edit** — this is
   what `submit_indexing_job` will need when the user actually clicks
   Run Now or Schedule. Per DR PDF "Add or Edit a Project Data
   Area": *"Requires Organization - Project Data Areas - Add/Edit
   Permissions"*.
5. *(Optional, for retention deletes via `dr_job_delete`)* enable
   **Corpora** → **Add/Edit** + **Delete**.
6. Click **Save** / **Apply** at the bottom of the matrix.

## Step 5 — Assign admin@training to the new role

1. From the same Settings drawer for the training org, navigate to
   **Settings → General → Users** (one entry up from Role
   Permissions).
2. Find the `admin` row → click its `…` menu → **Edit**.
3. In the **Role** dropdown, change from **Organization
   Administrator** to **`Org Admin + Connectors`**.
4. Click **OK** / **Apply**.
5. Sign out of the DR Web UI (top-right user icon → Logout).

## Step 6 — Verify from a shell

Back at the CLI:

```bash
cd /home/auraria/scripts/ediscovery_tests
.venv/bin/python - <<'EOF'
import os, sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from config import OrgUserConfig
from helpers.api_client import EDiscoveryClient
from dr_tui import data as drdata
client = EDiscoveryClient(OrgUserConfig())
client.login()
drdata.ensure_org_context(client, "training")
conns = drdata.list_connectors(client, "training")
print(f"OK listConnectors: {len(conns)} connector(s)")
entries = drdata.explore_connector(client,
    org_name="training", connector_name=conns[0].name,
    connector_type="NFS", remote_host=conns[0].host,
    remote_path=conns[0].path, parent_path=conns[0].path,
    project_handle="254")
print(f"OK exploreConnector: {len(entries)} entries under {conns[0].path}")
for e in entries[:5]:
    print(f"  {'🗀' if not e.leaf else '🗎'} {e.name}")
EOF
```

**Expected:**

```
OK listConnectors: 1 connector(s)
OK exploreConnector: 12 entries under /data/import
  🗀 Dave White Collected Hard Drive 2023-07-24
  🗀 deletedcustomerstorage
  🗀 Digital Reef PDFs
  🗀 DM24000212315
  🗀 drmanual
```

If both lines print: **dr_tui's Job Scheduler will work end-to-end.**
The TUI's dual-login at startup will pick up `org_client` (because
admin@training now exists and has the right role), so `Browse`,
`Count files`, `Schedule`, and `Run now` will all succeed.

## Step 7 — Verify from dr_tui

```bash
.venv/bin/dr_tui
```

- Log in as DRSysAdmin.
- Tab → **Job Scheduler** → click **New Job**.
- The yellow "using DRSysAdmin session" warning from v0.14.10 should
  be **gone** (because the dual-login now succeeded and the modal has
  an org client).
- Pick a folder in the file tree on the right — it should populate.
- Click **Count files** — should report counts after a few seconds.

---

## What if the Web UI shows a different role layout?

The exact menu placement varies slightly between DR 5.5.3.x point
releases. If you can't find "Role Permissions" under General, look
for it under **Provisioning** or **Security**. The decisive thing is:

- You're inside the **training organization's Settings**, not
  System Settings.
- You're editing **Organization Role Permissions** (not System Role
  Permissions).
- The permission you want is in the **Settings** group, named
  **Connectors**, with the `fa fa-plug` icon.

The secureObjectType is `CONNECTOR`, permissionLevel `ORGANIZATION` —
useful if you need to confirm via the DR REST API.

---

## Alternative: I can drive this via Playwright

If clicking through the Web UI is painful (or if you need to do this
on multiple DR installs), I can extend `qa_create_org_admin.py` to
also drive the Role Permissions page. Just ask.
