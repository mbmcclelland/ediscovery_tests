# QA execution log — v0.19.3

| | |
|---|---|
| **QA Engineer** | Jordan Park (returning from v0.17.1 cycle) |
| **Date** | 2026-05-15 |
| **Build under test** | commit `33b006f`, tag `v0.19.3` |
| **RPM under test** | `dr-tools-0.19.3-1.el9.x86_64` |

This is the running log for the v0.19.3 QA cycle. Tests are TC14–TC25 + REG1–REG4 per `QA-handover-v0.19.3.md`, plus the user-requested CRITICAL end-to-end indexing test on `192.168.58.128:/data/import/drmanual`.

## Pre-flight (captured at run start)

```
git: 33b006f / v0.19.3
RPM installed: dr-tools-0.19.3-1.el9.x86_64
drd: active, :8443 listening
training org: 3 connectors, 0 projects, 0 templates
pilot tests: 17/17 pass
```

## Tickets opened this cycle

(Tracked here; transcribed into the per-ticket section below as they're filed.)

| ID | Title | Severity | Status |
|---|---|---|---|
| QA-v019-1 | `dr_load --help` shows `Usage: dr-load` (Typer's argv-0) | Low | **WONTFIX** — Typer/Click reads prog name from `argv[0]`; the venv binary IS `dr-load` (setup.cfg). Cosmetic; help works. |
| QA-v019-2 | `dr_freshinstall --help` showed `usage: DR_freshinstall.py` | Low | **CLOSED in v0.19.4** — file renamed; banner now says `usage: dr_freshinstall` |
| QA-v019-3 | Default log path was `/tmp/dr-freshinstall-…log` | Low | **CLOSED in v0.19.4** — now `/tmp/dr_freshinstall-<TS>.log` |
| **QA-v019-4** | **CRITICAL: end-to-end indexing chain blocked** — `exploreConnector` returns `PROJECT_NOT_ACTIVATED` when the realm has 0 projects (v0.16.0 worked before but realm state changed); `create_project` blocked by NO_TEMPLATES (KNOWN_LIMITATION-1). Net: TUI is essentially unusable for the spec'd workflow on a fresh install. | **Critical** | open → Dev |

## Test results

| TC | Result | Notes |
|---|---|---|
| TC19 | PASS | 5 real wrappers + 5 symlinks correct direction |
| TC20 | PASS-with-notes | `--help` works for all 5; cosmetic argv-0 issue → QA-v019-1, -2 |
| TC21 | PASS | All 5 hyphen forms resolve to underscore canonicals |
| TC22 | PASS-with-notes | README + Workflow_Guide hits are log-filename refs (the file IS hyphenated on disk) → QA-v019-3 |
| TC23 | PASS (pilot-test) | `test_newjob_modal_v018_project_picker` covers the modal logic. Live: blocked because 0 projects exist → see QA-v019-4 |
| TC24 | PASS | `NO_TEMPLATES` APIError fires cleanly with actionable message — exactly as documented |
| TC25 | PASS | cleandr.sh Phase 0 SELinux block present with the spec'd shape |
| REG1 | PASS | ✗ count = 2, ERROR: FAIL count = 0 |
| REG2 | PASS | `_drd_api_ready('192.168.58.128')` → True |
| REG3 | PASS | postgres-drop iteration covers all 4 DBs with `--if-exists` |
| REG4 | PASS | `timeout=120` argument with QA-v0171-5 comment intact |

## QA-v019-4 — Critical detail

**Symptom:** the user's spec'd E2E test ("login as DRSysAdmin and index `192.168.58.128:/data/import/drmanual`") is BLOCKED on the current fresh-install state:

```
step 1: DRSysAdmin login OK
step 2: import connector → 192.168.58.128:/data/import
explore_connector: APIError PROJECT_NOT_ACTIVATED Project 0 not activated
```

**Root cause analysis:**

Live probe shows the server expects an "activated project" context that doesn't exist on a fresh install:

```
ctx='training'              → 200 FAILURE  Project 0 not activated
ctx=''                      → 200 FAILURE  User drsysadmin does not have permission
ctx='super_system_customer' → 200 FAILURE  User drsysadmin does not have permission
```

In v0.16.0 (commit `05b100b`) we proved `ctx='training'` returned 12 entries. The regression appears tied to the **realm having 0 projects** — DR's `exploreConnector` handler seems to need at least one active project context to function.

But creating a project is blocked by **NO_TEMPLATES** (v0.19.0 KNOWN_LIMITATION-1): a fresh org has 0 default templates; `ecaManager/createCase` rejects with `"No service with id = 0 found"`; we pre-empt with our clean APIError.

**Bootstrap chain (3 steps, all currently blocked):**

```
                        ✗  templateManager/copyMetaTemplateProfileEntries…
                        │  ownerHandle source not yet captured
                        ▼
0 templates  →  cannot create project
                        │
                        ▼
0 projects   →  cannot exploreConnector → cannot index → blocked
```

**Assigned to Dev:** investigate the template-bootstrap path via JS-bundle spelunking + live probing. The endpoint exists (`templateManager/copyMetaTemplateProfileEntriesToOrganizations`); we need to find:
1. Where the `ownerHandle` comes from (`realmManager/listMetaTemplateProfiles` or similar)
2. The minimum body shape that triggers the copy
3. Wire it into `create_project` so the v0.19.0 modal's `NO_TEMPLATES` becomes "transparently bootstrapped on first use"

**Acceptance:** after fix, an end-user can:
1. Open dr_tui as DRSysAdmin on a fresh install
2. Orgs → training → Projects → F7 → create project "qa-e2e" successfully
3. Job Scheduler → New Job → select project + connector + /data/import/drmanual → Run Now
4. Project + dataset appear in the DR Web UI / psql `mgmtproject` table

**Dev investigation result (session 2026-05-15):**

Tried during the v0.19.3 QA cycle:

| Probe | Result |
|---|---|
| `realmManager/listServices` | Returns 1 service: `handle=15`, name `"Digital Reef Default"`. Confirms services DO exist. |
| `templateManager/getMetaTemplateProfileEntries` | Exists, requires non-null `handle`. We don't have the META-profile handle to feed it. |
| `templateManager/listProfiles` / `realmManager/listMetaTemplateProfiles` | Don't exist (HTTP 500). |
| `orgManager/listTemplates(scope=SYSTEM_LEVEL)` | Returns 0 — realm template pool is empty. |
| `ecaManager/createCase` with `attributes=[{name:"Service",value:"15"}]` | Same "No service with id = 0 found" — the field name isn't "Service" OR multiple template-type entries are required, not just one. |

**Conclusion:** the template-bootstrap path requires either (a) further JS-bundle capture of the META-profile handle source, OR (b) running the existing `playwright_fresh_install.py phase_create_project` once with Chromium (which is the documented workaround). Neither is feasible in an unattended session without browser support installed.

**Status:** DEFERRED — external dependency. Tracking as KNOWN_LIMITATION-1 in `CHANGELOG.md` v0.19.0 entry. Next dev session should:
1. Capture a `templateManager/copyMetaTemplateProfileEntriesToOrganizations` call via mitmproxy reverse-proxy while clicking through the Web UI's "Save to Orgs" flow
2. Once the `ownerHandle` source is captured, wire it into `create_project` so the modal's `NO_TEMPLATES` becomes "transparently bootstrapped on first use"

The TUI itself is unaffected for any workflow that doesn't require fresh-org project creation — every other feature (System Settings CRUD, Job Scheduler for existing projects, Connector view, F3 Jobs Monitor) works correctly.

---

## 2026-05-15 capture pass — System Settings Web UI

User drove a System Settings exploration session through mitmproxy
reverse-proxy on :8091. 195 calls, 56 unique endpoints, ~749 KB
captured. Permanent artefact: `misc/syssettings-capture-20260515.json`.

### Did the capture close QA-v019-4?

**Partial.** The user's clicks did NOT trigger
`updateMetaTemplateProfileEntries` with a real payload — every
`getMetaTemplateProfileEntries` response in the capture is still
empty. So the entry-shape mystery is unresolved.

**However**, the capture DID confirm the `createTemplate` body shape
for META_TEMPLATE_PROFILE creation (matches what we already inferred)
and gave us the supporting endpoints (`copyToTemplate`,
`copyFromTemplate`, `exportTemplates`, `updateTemplate`,
`deleteTemplate`) that surround a complete template-management
workflow.

To fully close QA-v019-4, one more capture is still needed: drive
the Web UI through "add an entry to a meta-template profile and
save" so we see the populated `updateMetaTemplateProfileEntries`
body. Or alternatively: capture a successful end-to-end project
creation (which IS the lazy template-bootstrap path).

### 36 new endpoints captured — feature mapping

These body shapes are now available verbatim in
`misc/syssettings-capture-20260515.json` for future wrapping. Grouped
by what feature they'd enable.

#### A. Service management (system-wide compute resources)

| Endpoint | Body | Enables |
|---|---|---|
| `realmManager/listServices` | `{startIndex, count, descending, sortByFilter:"NAME"}` | Already wrapped at the helper level; can lift to dr_tui System Settings tree |
| `realmManager/createService` | `{serviceName, serviceDescription, serviceExpressNodes:[], serviceOcrNodes:[], serviceRealmNodes:[]}` | dr_tui System Settings → Services → New |
| `realmManager/deleteService` | `{handle}` | dr_tui System Settings → Services → F8 delete |
| `serviceManager/listProjectsForService` | (capture available) | Surface "which projects use this service" |

#### B. Template administration

| Endpoint | Body | Enables |
|---|---|---|
| `orgManager/createTemplate` | `{name, type, description, defaultTemplate, scope, ownerHandle, systemScope}` | Programmatic creation of any template type — needed for the QA-v019-4 fix |
| `orgManager/updateTemplate` | `{handle, name, description, defaultTemplate, type, systemScope}` | Rename / edit a template's metadata |
| `orgManager/deleteTemplate` | `{handle, taskDescription, systemScope}` | dr_tui template-delete |
| `templateManager/copyToTemplate` | `{fromHandle, toHandle, systemScope}` | Replicate an existing template into a fresh handle (the foundation of "Create from default") |
| `templateManager/copyFromTemplate` | `{fromHandle, toHandle, systemScope}` | Inverse direction |
| `templateManager/exportTemplates` | `{handles:[], templateType, allTemplates, projectHandle}` | Backup / migrate templates between realms |

#### C. Group + role administration

| Endpoint | Body | Enables |
|---|---|---|
| `adminOrgManager/createGroup` | `{name, description, roleHandles:[...], organizationName, systemScope:true}` | System Groups CRUD (we have list+delete, this completes the loop) |
| `adminOrgManager/addSystemGroupToOrg` | `{systemObjectName, orgNameRoleHandles:{<org>:<roleHandle>}}` | Bulk-attach a system group to an org with a role |
| `groupManager/listUsers` | (capture available) | Show members of a system group |
| `groupManager/setUsers` | `{groupHandle, userHandles:[...], systemScope:true}` | Add/remove members of a system group |
| `orgManager/deleteGroup` | (capture available) | Remove an org-level group |
| `orgManager/getRole` / `permissionManager/getSecureObjectGroups` | Inspect a role's permission grants | A "View role permissions" detail pane |

#### D. Connector validation + NFS mount discovery

| Endpoint | Body | Enables |
|---|---|---|
| `connectorManager/validateNFSConnector` | `{mountedConnectorMode:"CLASSIC", remoteHost, remotePath, readOnly, systemScope}` | Pre-create validation in NewConnectorModal — currently we skip this |
| `orgManager/getNfsMounts` | `{remoteHost, timeoutSeconds}` | Auto-populate a "share picker" dropdown when entering a new NFS connector |

#### E. Project-level features (handle from later — captured against project 1086 / 1119)

| Endpoint | Body | Enables |
|---|---|---|
| `projectManager/createTag` | `{name, description, displayValue:"#9900FF", projectHandle, enabled, systemScope}` | dr_tui per-project tag CRUD with a colour-picker |
| `projectManager/deleteTag` | (capture available) | Delete a project tag |
| `projectManager/listTags` | (capture available) | Display per-project tags |
| `projectManager/getAnalyticalSettings` | `{handle, systemScope}` | Read project analytical-settings template binding |
| `projectManager/listBillingReportSettings` | (capture available) | Billing-report UI |

#### F. Misc + legal/EULA + LDAP

| Endpoint | Use case |
|---|---|
| `userManager/acceptEula` | Accept the EULA on a first login (we currently bypass this by setting it server-side; this would let dr_tui's first-login flow handle it cleanly) |
| `realmManager/getAllFileTypes` | "What file types does DR understand?" — useful for indexing-config UIs |
| `orgManager/listLdapDomains` | Read configured LDAP integrations |
| `realmManager/listImportedCustomerUsersByUserName` | LDAP-imported user search |
| `realmManager/listImportedGroupsByGroupName` | LDAP-imported group search |
| `realmManager/listSystemUserOrgs` | Cross-org membership view for a given system user |
| `realmManager/listDeletedProjects` / `listDeletePendingProjects` | Project recycle-bin UIs |
| `realmManager/listCustomersForStorageFacility` / `storageAreaManager/countCustomersForFacility` | "Where is this storage used?" reverse lookup |
| `viewManager/validateName` | Server-side name-uniqueness check (used inline by the Web UI) |

### Suggested wrapper sweep (Dev next pass)

Add these helpers to `dr_tui/data.py` in priority order:

1. `create_org_group(client, *, org_name, name, description, role_handles)` — closes the group-CRUD circle
2. `validate_nfs_connector(client, *, org_name, host, path, read_only)` — let NewConnectorModal pre-validate
3. `get_nfs_mounts(client, *, host)` — populate a share-picker dropdown
4. `create_project_tag(client, *, project_handle, name, description, color, enabled=True)` — opens the door to per-project tag management
5. `list_realm_services()` + `create_realm_service()` + `delete_realm_service()` — adds Services to the System Settings tree

Each is a single ~15-line function. None blocks v0.20; they're each a discrete future ticket.

---



