# Digital Reef eDiscovery REST API — programming guide

**Audience:** Anyone (specifically: a future Claude session) building
new features against this codebase. This is the file to consult
**first** when adding a new endpoint, fixing an "I get
PERMISSION_DENIED" bug, or composing a multi-call recipe.

**Source of truth:** This document distills three days of
mitmproxy-driven discovery (May 11–14, 2026), the captured
`/tmp/dr_proxy_capture*.json` archive, the DR 5.5.3.1 PDF
documentation under `/data/import/Digital Reef PDFs/`, and the
v0.15.2 systemScope discovery. When in doubt, **capture a working
Web-UI session** (recipe in §13) before guessing.

---

## Table of contents

1. [Architecture: HTTPS, sessions, rolling tokens](#1-architecture)
2. [The `EDiscoveryClient` wrapper](#2-the-EDiscoveryClient-wrapper)
3. [Authentication & session lifecycle](#3-authentication--session-lifecycle)
4. [`contextHandle` — what to send when](#4-contexthandle--what-to-send-when)
5. [`systemScope` — the one flag that broke everything](#5-systemscope--the-one-flag-that-broke-everything)
6. [Permission model — who can call what](#6-permission-model)
7. [Endpoint reference by feature area](#7-endpoint-reference-by-feature-area)
8. [Composing recipes — multi-call patterns](#8-composing-recipes)
9. [Async tasks (SRI / WorkBasket)](#9-async-tasks)
10. [Quirks, anti-patterns, and gotchas](#10-quirks-anti-patterns-and-gotchas)
11. [Adding a new endpoint to `data.py`](#11-adding-a-new-endpoint)
12. [Adding a new TUI screen / modal](#12-adding-a-new-tui-feature)
13. [Debugging recipes when things go wrong](#13-debugging-recipes)
14. [Where things live — code map](#14-code-map)

---

## 1. Architecture

| Layer | What it does |
|---|---|
| **DR Web UI** | Angular app served from `/ediscovery/` on port 8443. Renders the JS bundle at `/home/auraria/AHS/jboss/standalone/tmp/.../main.js`. Calls the REST API via `restService.post(endpoint, data)`. Wraps every body in `DrWsRequestMessage(data, contextHandle)`. |
| **REST API** | JBoss/Wildfly Java application server. Every endpoint is a `POST /ediscovery/rest/<resourceManager>/<operation>`. JSON request body, JSON response. |
| **Auth** | Stateless rolling-token. `realmManager/createSession` returns the initial token; every subsequent response refreshes it. Token carries `<sig>|<userName>|<currentCustomer>|<unixTs>||<deviceID>`. |
| **Permission interceptor** | `com.auraria.service.appsvr.ejb.SecureObjectInterceptor` — runs server-side on every endpoint. Reads (a) the authenticated user, (b) the request's `contextHandle`, (c) the `systemScope` flag, (d) the operation name. Either lets it through or raises `PERMISSION_DENIED`. |
| **Permission catalog** | Defined in DR's database. Read via `permissionManager/getSecureObjectGroups` (catalog) and `permissionManager/getCombinedUserRole` (per-user). |
| **`auraria_mgmt` Postgres DB** | Where everything ultimately persists. The `helpers/monitor.py` `JobPoller` polls it directly for load-test observability. |

All requests go to `https://<host>:8443/ediscovery/rest/<endpoint>`.
SSL cert is self-signed in lab. The Python client uses
`verify=False` + an `InsecureRequestWarning` suppressed at the
warnings filter level.

---

## 2. The `EDiscoveryClient` wrapper

Defined in `helpers/api_client.py`. Single source of truth for talking
to DR.

```python
from config import Config, OrgUserConfig
from helpers.api_client import EDiscoveryClient, APIError

# DRSysAdmin client
sys_client = EDiscoveryClient(Config())
sys_client.login(password="password")

# org-scoped client (admin@training)
org_client = EDiscoveryClient(OrgUserConfig())
org_client.login()    # password resolved from .env

# basic call
resp = sys_client.post("realmManager/listOrganizations", extra_body={
    "startIndex": 0, "count": 0, "filters": [],
})

# bare-bool / 204 endpoints (pauseTask, resumeTask)
ok = sys_client.post_raw("taskManager/pauseTask", {
    "taskHandle": h, "systemScope": True,
})
# resp.status_code == 200, resp.text might be "true" or "false"
```

**Key behaviours:**

| Behaviour | Where | Note |
|---|---|---|
| `Authorization` header = raw session token | `_check_status` → `self.session.headers["Authorization"] = new_token` | Rolling tokens refreshed on every response |
| Auto-adds `contextHandle: self.cfg.organization` | `post()` line 147 | For sys: `super_system_customer`. For org user: their org name. |
| **Does NOT auto-add `systemScope`** (v0.15.2+) | `post()` line 147 | Was `True` pre-v0.15.2; that single field was the root cause of every `PERMISSION_DENIED`. |
| Raises `APIError` on `status: FAILURE` | `_check_status` | `e.error_code` + `e.extended_status` carry the server's reason |
| HTTP 204 / empty body → returns `{}` | `post()` line 163 | "D1" fix from v0.06 for endpoints like `cancelTask` |
| `verify=False` + InsecureRequestWarning silenced | Constructor | Self-signed lab cert |

**`APIError` shape:**

```python
try:
    client.post(...)
except APIError as e:
    print(e.status)           # "FAILURE"
    print(e.error_code)       # "PERMISSION_DENIED"
    print(e.extended_status)  # human-readable details
    print(e.raw)              # full response dict
```

---

## 3. Authentication & session lifecycle

### 3.1 Login

```python
client.login(password="password")
# Internally posts realmManager/createSession with:
#   {"requestHandle": null, "userDeviceID": "<uuid4>",
#    "drWsClientContext": {"username": "...", "organizationName": "..."}}
#
# Response includes a sessionToken — client stores it and uses it
# as the Authorization header on every subsequent request.
```

The `drWsClientContext` field in `createSession` selects who you're
authenticating as. The `Config` class hardcodes `DRSysAdmin` /
`super_system_customer`; `OrgUserConfig` reads `DR_ORG_USERNAME` /
`DR_ORG_ORGANIZATION` from `~/.env`.

### 3.2 Token format

```
<base64-sig>|<userName>|<currentCustomer>|<unixTimestamp>||<deviceUUID>
```

Six pipe-separated parts (note the `||` for the empty 5th part).
The third field is the **current customer/org context** — gets
rewritten by `realmManager/initializeOrganization` (see §4.2).

To inspect:

```python
parts = client.session.headers["Authorization"].split("|")
print("current customer:", parts[2])
```

### 3.3 Rolling tokens

Every successful response (in `_check_status`) carries a fresh
`sessionToken`. `EDiscoveryClient.post()` swaps the Authorization
header for that new token on every call. Side effect: a token saved
from a previous call may have rotated; always read
`client.session.headers["Authorization"]`.

### 3.4 Logout

```python
client.logout()
# POST realmManager/destroySession
```

Server invalidates the token. Subsequent calls raise APIError with
`error_code: SESSION_EXPIRED`.

---

## 4. `contextHandle` — what to send when

`contextHandle` is THE most-asked-about field. It selects the
"realm of operation" for the call. **It's NOT always the org name.**

### 4.1 Three valid values

| Value | When to use | Example endpoints |
|---|---|---|
| **`super_system_customer`** | System-realm operations. The DRSysAdmin's home customer. | `listOrganizations`, `getLicenseInfo`, `listNodes`, `getMailServerConfig` (Realm Settings), `listJobs`, `listRealmTasks` |
| **Org name** (e.g. `"training"`) | Org-level reads after `initializeOrganization`. | `adminOrgManager/listConnectors`, `orgManager/listProjects`, `orgManager/getNfsMounts`, `adminOrgManager/listRoles` |
| **Project handle** (e.g. `"254"`) | Project-level writes — the indexing chain. | `orgManager/createDataArea`, `orgManager/createCorpus`, `corpusManager/createRepresentation`, `connectorManager/exploreConnector` (when an active project exists) |

### 4.2 `realmManager/initializeOrganization`

Before any org-scoped REST call, DRSysAdmin must "switch context" to
the target org:

```python
client.post("realmManager/initializeOrganization",
            extra_body={"organizationName": "training"},
            check=False)  # check=False because the response sometimes has no status field
```

**After this call:**
- Token's 3rd field flips from `super_system_customer` to `training`.
- Server-side session is now "in" the training org context.
- Subsequent `contextHandle: "training"` calls succeed.

For an org user (`admin@training`), the session is already in their
org's context — `initializeOrganization` is a no-op (but harmless).

Helper in `dr_tui/data.py`:

```python
drdata.ensure_org_context(client, "training")
# Wraps realmManager/initializeOrganization with check=False
```

### 4.3 Project-context "activation"

For endpoints that operate on a SPECIFIC PROJECT (the entire indexing
chain), `contextHandle` should be the project's numeric handle as a
string:

```python
# The captured v0.10+ Web UI flow does this:
client.post("orgManager/createDataArea", extra_body={
    "contextHandle": "254",         # ← project handle
    "connectorHandle": "...",
    ...
})
```

**For `exploreConnector` specifically — use the org name, not the
project handle.** This is the v0.16.0 correction to the earlier
v0.14.9 rule. Live evidence (DR 5.5.3.2, 2026-05-14):

| ctx value | DRSysAdmin | admin@&lt;org&gt; |
|---|---|---|
| `<org name>` (e.g. `"training"`) | ✓ 12 entries | ✓ 12 entries |
| `<project handle>` (e.g. `"254"`) | ✗ `PROJECT_NOT_ACTIVATED Project 0 not activated` | n/a (we have no test where it's needed) |

The Web UI capture that motivated v0.14.9 had a project pre-selected
in the same session (which "activates" it server-side); our TUI never
does that, and the no-good workaround `ecaManager/selectProject`
returns 500. The fix is simply: **for browse, use the org name.**
For the indexing chain that *follows* the browse, the project handle
works because by then we've created the data area and the server has
its own activation path.

**Rule of thumb (v0.16.0):**

| Operation | `contextHandle` |
|---|---|
| `connectorManager/exploreConnector` | org name |
| `adminOrgManager/listConnectors`     | org name |
| `orgManager/createDataArea`          | project handle |
| `orgManager/createCorpus`            | project handle |
| `corpusManager/createRepresentation` | project handle |
| `realmManager/listOrganizations`     | `"super_system_customer"` + `systemScope: true` |

---

## 5. `systemScope` — the one flag that broke everything

**Read this section before touching any new endpoint.**

`systemScope` is a boolean field in the request body. It declares
"I'm acting as a system-level user, not an org user." DR's
`SecureObjectInterceptor` reads it and chooses which permission set
to check the call against:

| `systemScope` value | Permission set checked |
|---|---|
| Not present, or `false` | The caller's **org-context** role (after `initializeOrganization`) |
| `true` | The caller's **super-system** permissions (only IT Administrator has these, and the list is narrower than you'd expect) |

### 5.1 The v0.15.2 root cause

Pre-v0.15.2, `helpers/api_client.py:post()` injected
`"systemScope": True` into **every** request:

```python
# BAD — the pre-v0.15.2 default:
body = {"contextHandle": self.cfg.organization, "systemScope": True}
```

This caused DRSysAdmin to be denied for `exploreConnector`,
`createDataArea`, and most of the indexing chain, even though the
Web UI worked fine for the same user. The Web UI **never sets
`systemScope` for those endpoints**. Removing the auto-inject
unblocked the entire Job Scheduler feature.

### 5.2 When to set `systemScope: true`

Set it explicitly in `extra_body` for these endpoint families:

- **Realm Settings** — `realmManager/getMailServerConfig`,
  `setSplashMessage`, `setPasswordPolicy`, `getInactivityTimeout`,
  etc.
- **System-wide reads** — `realmManager/listJobs`,
  `realmManager/listRealmTasks`, `realmManager/listEmailIdsToNotify`,
  `realmManager/listOrganizations`
- **Task control** — `taskManager/cancelTask`, `pauseTask`,
  `resumeTask` (BUT NOT `updateJobPriority` — captured shape omits it)
- **System Storage operations** — `realmManager/listRemoteNFSStorageAreas`,
  `realmManager/createRemoteNFSStorageArea`
- **System Users / Groups** — `realmManager/listSystemUsers`,
  `createSystemUser`, etc.

### 5.3 When NOT to set `systemScope`

Anything that operates on org-or-project-scoped objects:

- `connectorManager/exploreConnector` ← the canonical example
- `connectorManager/getNFSConnector`, `getConnector`
- `adminOrgManager/listConnectors` (works either way actually, but
  the Web UI doesn't set it)
- `orgManager/createDataArea`, `createCorpus`, `deleteCorpus`,
  `deleteDataArea`
- `corpusManager/createRepresentation`
- `corpusSetManager/getCorpusSetByName`, `addCorpus`
- `orgManager/listProjects` (uses ORG_USERS_NAME / orgName instead)
- `orgManager/getNfsMounts`

### 5.4 The diagnostic test

If you get `PERMISSION_DENIED` and you're sure the user SHOULD be
able to perform the operation:

1. Capture a working Web UI session (see §13.3).
2. Diff the captured body against what your code is sending.
3. If your body has `systemScope: true` and the Web UI's doesn't,
   remove `systemScope` from your `extra_body`.

Existing data-layer functions that explicitly send
`systemScope: True` are correct — they're calls that need it. The
audit at v0.15.2 found 34 such call sites, all genuine.

---

## 6. Permission model

DR's permission system is a 4-tuple: `(user, role, action, secureObject)`.

- **User** — `userName` in the auth header.
- **Role** — assigned to the user; each role has a set of action grants.
- **Action** — e.g. `CREATE`, `DELETE`, `VIEW`.
- **Secure object** — e.g. `CONNECTOR`, `PROJECT_DATA_AREA`, `CORPUS`,
  `PASSWORD_AND_USER_LOGOUT_POLICY`.

The catalog of secure objects + their permitted actions is read via
`permissionManager/getSecureObjectGroups`. Sample entries:

```
group=SETTINGS                 secureObjectType=CONNECTOR
  permissionLevel=ORGANIZATION
  organizationViewState=true, organizationCreateState=true, organizationDeleteState=true

group=COMMON_OTHER             secureObjectType=CONNECTOR_ACCESS
  permissionLevel=PROJECT
  projectViewState=true
```

**Permission levels:**
- `SYSTEM` — checked when `systemScope: true` is on the request
- `ORGANIZATION` — checked against the user's role in the org
  selected by `initializeOrganization`
- `PROJECT` — checked against the user's role within the project

For most endpoints there's only one applicable level — `systemScope`
selects which.

### 6.1 Roles in DR 5.5.3.2 (default install)

System-level (only DRSysAdmin gets these by default):

- **IT Administrator** — system-config admin (storage, virus defs,
  realm settings, system roles + users)
- **System Administrator** — same minus storage CRUD
- **System Manager** — read-mostly + some IT functions
- **System Member** — read-only

Org-level (assigned to org users; the v0.15.2 capture confirmed
DRSysAdmin can ALSO operate in org mode after
`initializeOrganization`, despite being a system user):

- **Organization Administrator** — full org admin
- **Project Administrator** — project ops
- **Project Member** — project reads
- **Claimant** — minimal

You can copy a role and add permissions via the Web UI (docs/DR_ROLE_SETUP.md).

---

## 7. Endpoint reference by feature area

Body shapes captured live and verified working. Every endpoint here
has at least one example call in the codebase — search `data.py` for
the endpoint name to see ours.

### 7.1 Authentication

| Endpoint | Body | Returns | Notes |
|---|---|---|---|
| `realmManager/createSession` | `{userDeviceID, drWsClientContext: {username, organizationName}}` | `{sessionToken, needSecurityCode}` | HTTP Basic auth header carries the password. Token used as Authorization on every subsequent call. |
| `realmManager/destroySession` | `{}` | 200 | Logout. |
| `userManager/getCurrentUser` | `{}` | `{user: {userName, customerName, roles, ...}}` | Useful to discover whether the session is currently in `super_system_customer` vs an org context. |

### 7.2 Realm Settings (all `systemScope: true`)

`docs/endpoints_v0.08.md` has the full body shapes. Quick summary:

| Read | Write | Effect |
|---|---|---|
| `getMailServerConfig` | `createMailServerConfig` | Upsert (no separate update endpoint) |
| `getSplashMessage` | `setSplashMessage` | Login banner |
| `getPasswordPolicy` | `setPasswordPolicy` | All 8 fields required every call |
| `getInactivityTimeout` | `setInactivityTimeout` | 204 No Content on success |
| `listSystemRoles` | (custom flow) | Read predefined sys roles |
| `getLicenseInfo` | — | License attributes (read-only) |
| `listNodes` + `getNodeStatus` | `createNode` | Realm nodes |

**Gotcha:** the `set*` responses don't echo the persisted values
reliably (the v0.14.7 finding). Always follow up with a `get*` to
read back the canonical state if you care. The `set_*` fetchers in
`dr_tui/data.py` already do this for the caller.

### 7.3 Organizations

| Endpoint | Body | Notes |
|---|---|---|
| `realmManager/listOrganizations` | `{startIndex, count, filters, systemScope: true}` | DRSysAdmin only |
| `realmManager/initializeOrganization` | `{organizationName, systemScope?}` | Context switch. Two-call pattern in Web UI: once plain, once with `systemScope: false`. Either works. |
| `orgManager/listUsers` | `{contextHandle: <org>, organizationName: <org>}` | List users in an org |
| `orgManager/createUser` | (see `qa_create_org_admin.py` for the full body) | DRSysAdmin can call this in some cases; org-admin role required generally. |
| `realmManager/listSystemUsers` | `{systemScope: true}` | System users only |

### 7.4 Connectors

| Endpoint | Body | When |
|---|---|---|
| `adminOrgManager/listConnectors` | `{contextHandle: <org>, organizationName: <org>}` | Org's connector list. Works for DRSysAdmin post-`initializeOrganization`. |
| `connectorManager/getNFSConnector` | `{contextHandle: <org>, handle: <conn-handle>}` | Single-connector details |
| `connectorManager/getConnector` | `{contextHandle: <conn-handle>}` | Note: contextHandle here is the connector handle (quirk) |
| `connectorManager/exploreConnector` | `{contextHandle: <org name>, connectorType, connectorName, remoteHost, remotePath, organizationName, parentPath}` | **MUST NOT have `systemScope`.** **`contextHandle` MUST be the org name** — using a project handle on a non-activated session returns `PROJECT_NOT_ACTIVATED Project 0 not activated` (see §4.3). DRSysAdmin must call `initializeOrganization` first. |
| `connectorManager/validateNFSConnector` | (capture v0.07) | Pre-create validation |
| `orgManager/createNFSConnector` | (capture v0.07) | Create new NFS connector |
| `adminOrgManager/deactivateConnectors` | `{contextHandle: <org>, handles: [<names>], systemScope: false}` | **Sends connector NAMES, not handles** (DR API quirk). Soft-delete. |
| `orgManager/deleteConnector` | (capture v0.07) | Hard delete |

### 7.5 Projects

| Endpoint | Body |
|---|---|
| `realmManager/listProjects` | `{contextHandle: super_system_customer, systemScope: true, startIndex, count, filters}` |
| `realmManager/listSystemUserProjectsByUserName` | `{userName, contextHandle: super_system_customer, ...}` |
| `orgManager/listUserProjectsForAllOrgs` | `{contextHandle: <org>, ...}` (org user view) |
| `ecaManager/createCase` | (creates an org's project) |
| `projectManager/listTasks` | `{contextHandle: <project-handle>, projectHandle: <same>, filters, startIndex, count}` |
| `projectManager/getUpdateStatus` | `{contextHandle, projectHandle: 0, timestamp, updateStatusTypes: [...]}` | Web UI uses this to refresh on its 30s tick. |

### 7.6 Indexing chain (the load-test workflow)

Reference implementation: `locustfile_indexing.py`. Wrapped in
`dr_tui/data.py` as `submit_indexing_job()`. **Five POSTs** in order:

```python
# 1. Create data area (pin a path on a connector inside a project)
da = client.post("orgManager/createDataArea", extra_body={
    "contextHandle": project_handle,          # ← project handle!
    "connectorHandle": connector_handle,
    "name": "<unique>_data",
    "description": "",
    "mode": "IMPORT",
    "path": "/data/import/some/subfolder",
    "skippedDirectories": [],
})
data_area_handle = da["dataArea"]["handle"]

# 2. Look up the AllCorpora corpus set (default container)
cs = client.post("corpusSetManager/getCorpusSetByName", extra_body={
    "contextHandle": project_handle,
    "projectHandle": project_handle,
    "corpusSetName": "AllCorpora",
})
corpus_set_handle = cs["corpusSet"]["handle"]   # may be empty on some realms — that's OK

# 3. Create a corpus from the data area
corp = client.post("orgManager/createCorpus", extra_body={
    "contextHandle": project_handle,
    "name": "<unique>",
    "description": "",
    "brand": True,
    "dataAreaHandles": [data_area_handle],
    "loadFileName": "", "loadFileType": "EDRM_XML", "loadFileProfileId": -1,
    "attributes": [{"name": "projecthandle", "value": project_handle}],
})
corpus_handle = corp["corpus"]["handle"]

# 4. Add corpus to AllCorpora (best-effort; skip if no corpus_set_handle)
if corpus_set_handle:
    client.post("corpusSetManager/addCorpus", extra_body={
        "contextHandle": project_handle,
        "corpusHandle": corpus_handle,
        "corpusSetHandle": corpus_set_handle,
    })

# 5. Start indexing — returns the running task handle
rep = client.post("corpusManager/createRepresentation", extra_body={
    "contextHandle": project_handle,
    "corpusHandle": corpus_handle,
    "attributes": [{"name": "projecthandle", "value": project_handle}],
    "scanAttributes": [
        {"name": "batchNumber", "value": "<unique>"},
        {"name": "projecthandle", "value": project_handle},
    ],
    "taskDescription": "Creating representation Analytic Index for <unique>",
    "typeList": ["CONTENT_INDEX", "VECTOR_SET"],
    "enablePatternDetection": True,
})
task_handle = rep["taskHandle"]
```

**None of these calls take `systemScope`.** They're project-scoped.

### 7.7 Task control

| Endpoint | Body | systemScope | Notes |
|---|---|---|---|
| `realmManager/listJobs` | `{contextHandle: super_system_customer, systemScope: true, count, ...}` | `true` | Active jobs only |
| `realmManager/listRealmTasks` | `{contextHandle: super_system_customer, count, filters: [...]}` | `true` (in our shape) | Realm-wide tasks list. `SYNTAXERROR EQUALS false` sentinel filter == "show all". |
| `realmManager/listOperationTypes` | `{contextHandle: super_system_customer, startIndex, count: 0, filters: []}` | (not needed) | Enum catalogue of `operationType` values (DOCUMENT_ADD_FROM_FILE_LIST, etc.) |
| `taskManager/pauseTask` | `{taskHandle, contextHandle: super_system_customer, systemScope: true}` | `true` | Returns bare `true`/`false` — use `post_raw` |
| `taskManager/resumeTask` | same shape | `true` | same |
| `taskManager/cancelTask` | `{taskHandle, systemScope: true}` | **`true` is mandatory** | Without it: HTTP 500 with NullPointerException |
| `taskManager/updateJobPriority` | `{requestHandle, priority: "HIGH"\|"NORMAL"\|"LOW", taskHandle}` | **(must NOT send)** | Captured shape is minimal — no contextHandle, no systemScope |
| `taskManager/getSRITaskLog` | `{numLines: 1000, taskSri: "<instance-id>"}` | — | Returns `logLines: [str]`. `taskSri` must be discovered first (see §9.1) |
| `taskManager/getTasks` | `{taskHandles: [<h>], includeDrDebug: true, includeResourceStatistics: false}` | — | Full task detail with `currentStatus[]` sections. Includes the AE "Instance ID" (= taskSri) inside `currentStatus → "Service Node Debug State" → "Instance ID"`. |

### 7.8 Storage

`docs/endpoints_v0.06.md` has the full CRUD. Quick reference:

| Endpoint | systemScope |
|---|---|
| `realmManager/listRemoteNFSStorageAreas` | `true` |
| `realmManager/createRemoteNFSStorageArea` | `true` |
| `realmManager/updateRemoteNFSStorageArea` | `true` |
| `realmManager/deleteRemoteNFSStorageArea` | `true` |
| `realmManager/getSystemStorageDepot` | `true` |
| `realmManager/getVirusDefinitions` | `true` |

---

## 8. Composing recipes

### 8.1 List connectors as DRSysAdmin

```python
from helpers.api_client import EDiscoveryClient
from config import Config
from dr_tui import data as drdata

client = EDiscoveryClient(Config())
client.login()
drdata.ensure_org_context(client, "training")    # <-- the magic
conns = drdata.list_connectors(client, "training")
```

### 8.2 Run an indexing job end-to-end as DRSysAdmin

```python
client = EDiscoveryClient(Config())
client.login()
drdata.ensure_org_context(client, "training")
result = drdata.submit_indexing_job(
    client,
    project_handle="254",
    connector_handle="0000ecde4878812053604308ac25ef767566612e",
    path="/data/import/payroll",
    dataset_name="payroll-2026",
)
print(result["task_handle"])   # poll listRealmTasks until operationState == "SUCCESS"
```

### 8.3 Poll a running task until done

```python
import time
while True:
    rows, _ = drdata.list_realm_tasks(client)
    me = next((r for r in rows if (r.raw or {}).get("handle") == task_handle), None)
    if me and me.state != "RUNNING":
        print(f"Done: {me.state}")
        break
    time.sleep(5)
```

### 8.4 Tail a running task's AE log

```python
sri = drdata.get_task_sri(client, task_handle=h)
if sri:
    lines = drdata.get_sri_task_log(client, task_sri=sri, num_lines=1000)
    for ln in lines:
        print(ln)
```

`taskSri` is the AE worker's "Instance ID" — only available while
the task is still running. After the task ends, the SRI lookup
returns None and the log is gone from that endpoint.

### 8.5 Set a realm setting + read it back

```python
from dr_tui import data as drdata

old = drdata.get_password_policy(client)
new = drdata.PasswordPolicy(enforce_strong=True, min_length=12,
    min_uppercase=2, min_lowercase=1, min_numbers=1, min_symbols=0,
    expiration_days=60)
confirmed = drdata.set_password_policy(client, policy=new)
# confirmed is read back via a follow-up get — v0.14.7 fix —
# because set responses don't echo persisted state reliably.
print(confirmed)
```

### 8.6 Cancel a job with confirmation (TUI pattern)

```python
# inside a ModalScreen handler:
app.push_screen(
    ConfirmModal(title="Cancel?", message=f"Cancel {job.job}?",
                 confirm_label="Cancel Job"),
    lambda ok: ok and self.run_worker(
        lambda: drdata.cancel_task(client, task_handle=h),
        thread=True, exclusive=False, group="job-action",
    ),
)
```

### 8.7 Schedule a recurring indexing job (the v0.15 feature)

```python
from dr_tui import scheduler as drsch

job = drsch.JobDefinition(
    name="nightly-payroll", org="training",
    project_handle="254", connector_name="import-training-nfs-local",
    connector_handle="0000ecde…", connector_type="NFS",
    remote_host="192.168.58.128", remote_path="/data/import",
    path="/data/import/payroll/2026",
    retention_seconds=7*86400,
    schedule="3x-day",      # or any RECUR_PRESETS key, or raw OnCalendar
)
drsch.save_job(job)
# Wire up the systemd timer:
unit, err = drsch.schedule_recurring_job(
    job_slug=job.slug(), on_calendar=job.schedule, job_name=job.name,
)
# unit == "dr-tools-recur-nightly-payroll"
# err == None means the timer is active
```

---

## 9. Async tasks

Some endpoints return immediately with a "scheduled" status, while
the actual work happens on a background DR component (the
"ServiceRequestInstance" or SRI). These tasks have their own
lifecycle log accessible via `taskManager/getSRITaskLog`.

### 9.1 Finding the `taskSri` for a running task

The SRI is the **AE worker's instance ID** — it's NOT the task
handle. Two-step lookup:

```python
# Step 1: getTasks with includeDrDebug=true to get currentStatus[]
resp = client.post("taskManager/getTasks", extra_body={
    "taskHandles": [task_handle],
    "includeDrDebug": True,
    "includeResourceStatistics": False,
})

# Step 2: find the "Service Node Debug State" section → "Instance ID"
for t in resp.get("tasks", []):
    for sec in t.get("currentStatus", []):
        if sec.get("name") == "Service Node Debug State":
            for kv in sec.get("data", []):
                if kv.get("name") == "Instance ID":
                    sri = kv.get("value")
                    break
```

Helper in `dr_tui/data.py`: `get_task_sri(client, task_handle=h)`.
Returns None if the SRI section isn't present (task already finished
or never started).

### 9.2 PROJECT_NOT_ACTIVATED — what it really means

When the SRI worker runs and finds it can't determine a project
context (e.g. you called `exploreConnector` outside a project page
flow), it raises:

```
ServiceRequestInstanceException: Project 0 not activated
```

This is the **async** failure. The **sync** equivalent is
`PERMISSION_DENIED`. Which one you get depends on whether the
synchronous interceptor or the async worker rejects first — race
condition with the request thread.

**Both are the same root cause: wrong session context.** Almost
always fixed by:
- ensuring `initializeOrganization` was called for the org
- not setting `systemScope: true`
- if available, sending `contextHandle: <project-handle>` instead of
  the org name

---

## 10. Quirks, anti-patterns, and gotchas

### 10.1 Sticky permission errors

| Symptom | Real cause |
|---|---|
| `PERMISSION_DENIED ... exploreConnector` (or createDataArea, etc.) — user IS in the right role | You're sending `systemScope: true`. The Web UI doesn't. Don't. (v0.15.2 fix) |
| `User X does not have permission to perform listConnectors` | (a) Did you call `initializeOrganization` first? (b) If yes, the user genuinely lacks the Connectors role permission — copy "Organization Administrator" → custom role with Connectors grant. |
| `User drsysadmin does not have permission to perform createCustomerUser` | DRSysAdmin can't create org users directly via REST. Use the Web UI or `qa_create_org_admin.py`. |
| `PROJECT_NOT_ACTIVATED Project 0 not activated` | Same as PERMISSION_DENIED really — async branch. Drop `systemScope: true`. |

### 10.2 Response-body lies

| Endpoint | Lie | Workaround |
|---|---|---|
| `setPasswordPolicy` | Response field values are zeros/false regardless of what was written | Follow up with `getPasswordPolicy` to read canonical state |
| `setSplashMessage` | Response `enabled` is wrong | Follow up with `getSplashMessage` |
| `setInactivityTimeout` | Returns 204 No Content (no echo to be wrong) | Return the input value verbatim |
| `createMailServerConfig` | Mostly correct but masked by our input-fallback | Follow up with `getMailServerConfig` for honesty |

All four `set_*` fetchers in `dr_tui/data.py` already do the
follow-up read — copy that pattern for any new `set_*` we add.

### 10.3 Bare-bool / 204 responses

`taskManager/pauseTask` and `resumeTask` return plain `true` or
`false` (not a JSON object). `cancelTask` returns 204 No Content.
Use `client.post_raw()` or handle the empty-body case in `post()` —
the "D1 fix" in `helpers/api_client.py:163`:

```python
if resp.status_code == 204 or not resp.content:
    return {}
```

### 10.4 The `handles` field that takes names

`adminOrgManager/deactivateConnectors` sends connector **names** in
a field called `handles`. Captured shape:

```json
{"contextHandle": "training", "handles": ["import-training-nfs-local"],
 "systemScope": false}
```

This is a DR API quirk — naming is misleading. Other endpoints with
`handles` arrays do take real handles. Always check captures.

### 10.5 contextHandle = connector handle (weird one)

`connectorManager/getConnector` and `listReferencesToConnector` take
`contextHandle: <connector-handle>` — i.e. the contextHandle is the
connector itself, not an org or project. One-off quirk.

### 10.6 SYNTAXERROR EQUALS false sentinel filter

`realmManager/listRealmTasks` requires a `filters` array. The Web UI
sends `[{"attribute": "SYNTAXERROR", "operator": "EQUALS", "value":
"false"}]` as a "give me everything" pseudo-filter. Replicate this
in any new code that lists realm tasks — sending `filters: []`
returns empty.

### 10.7 Status field naming inconsistency

Responses use `"status": "SUCCESS"` for the outer envelope. Some
endpoints (CRUD on Connectors, virus defs) use `"opStatus"` or
`"status": "AVAILABLE"` for the operational state. Always check
captures before assuming a status enum.

### 10.8 Rolling-token edge case: stale capture replay

If you replay a captured request body verbatim with the old captured
Authorization header, you'll get `SESSION_EXPIRED`. The token in
captures rotates every response; you can't reuse them. Always
re-login when reproducing.

---

## 11. Adding a new endpoint

Five-step recipe:

### Step 1 — Capture the working flow

Start mitmproxy reverse-proxy mode (no cert install needed by the
user — they accept the warning once):

```bash
.venv/bin/mitmdump -s proxy_logger.py \
  --mode reverse:https://192.168.58.128:8443 \
  --listen-host 0.0.0.0 --listen-port 8091 \
  --set ssl_insecure=true --set keep_host_header=true \
  > /tmp/mitmdump.log 2>&1 &
```

User browses to `https://<host>:8091/ediscovery/` and performs the
operation. Capture lands in `/tmp/dr_proxy_capture.json`.

### Step 2 — Inspect the captured request body

```python
import json
with open("/tmp/dr_proxy_capture.json") as f: calls = json.load(f)
for c in calls:
    if c.get("endpoint") == "<your-endpoint>":
        print(json.dumps(c["request_body"], indent=2))
        # Notice what fields ARE there and what AREN'T (especially
        # systemScope — its absence is informative).
```

### Step 3 — Add a fetcher to `dr_tui/data.py`

```python
def your_new_op(client: EDiscoveryClient, *, kwarg1: str) -> WhateverType:
    """One-line description.

    Captured body shape: <document briefly>. Returns: <shape>.
    """
    resp = client.post(
        "managerName/operationName",
        extra_body={
            # ONLY the fields the Web UI sends. Don't add systemScope
            # unless captures show it.
            "fieldFromCapture": kwarg1,
            ...
        },
    )
    # Parse the response shape captured in step 2.
    return ...
```

### Step 4 — Write a pilot test

Add to `tests/test_dr_tui_*.py` (the relevant module). Use the
Textual `Pilot` harness if it's UI-side; use a direct `EDiscoveryClient`
mock if it's data-layer only. Offline tests should NOT hit the live
API — use captures or mocks.

### Step 5 — Wire it into the TUI

Add a button or tree leaf to the appropriate sub-view in
`dr_tui/app.py`. Use the existing pattern:

```python
def on_button_pressed(self, evt):
    if evt.button.id == "your-button":
        self.run_worker(self._your_op_blocking, thread=True,
                        exclusive=False, group="your-op")

def _your_op_blocking(self):
    client = self.app.sys_client or self.app.org_client
    try:
        result = drdata.your_new_op(client, kwarg1="...")
        self.app.call_from_thread(self._post_status_ok, "done")
    except APIError as e:
        self.app.call_from_thread(self._post_status, f"{e.error_code}: {e.extended_status[:80]}")
```

---

## 12. Adding a new TUI feature

### 12.1 New modal

Pattern: subclass `ModalScreen[Optional[dict]]`, define `compose()`
+ `on_button_pressed()` + `action_cancel()`. Existing models to copy:

| For… | Copy from |
|---|---|
| Simple form + Save/Cancel | `MailServerFormModal` |
| Form with validation + retention/units | `NewJobModal` |
| Master/detail viewer | `JobsMonitorModal` |
| Confirm destructive action | `ConfirmModal` |
| Read-only log tail | `TaskLogModal` / `LogViewerModal` |

Mount with `app.push_screen(MyModal(...), self._my_callback)`. The
callback receives whatever the modal calls `self.dismiss(...)` with
(or `None` if dismissed without a result).

### 12.2 New tab

Add a `TabPane` to `DashboardScreen.compose()` matching the existing
pattern (Tree on the left, `ContentSwitcher` of `Vertical` sub-views
on the right). Each sub-view has its own action row. Tree leaves
carry `data={"kind": "<sub-view-id>"}`; routing goes through
`on_tree_node_selected` → `_load_view(kind, org)`.

Examples to copy: System Settings (`tab-sys`), Organizations (`tab-orgs`),
Job Scheduler (`tab-scheduler`).

### 12.3 Threading rules

**Never call the API from the UI thread.** All `client.post()` calls
must happen on a worker thread spawned by `self.run_worker(fn,
thread=True, ...)`. The worker calls `app.call_from_thread(...)` to
update UI from the result.

The TUI status bar updater `self._post_status(msg)` is safe from both
threads (uses an internal queue).

### 12.4 Markup safety

Any user-controlled text fed to `RichLog.write()` or `Static.update()`
when `markup=True` (the default) must be wrapped in
`rich.markup.escape()` first — otherwise log lines containing
literal `[...]` brackets (Java argv dumps, file paths with
hyphens, etc.) crash the renderer with `MarkupError`. v0.13.2 fix.

For long-form read-only output, use `RichLog(markup=False)` —
`TaskLogModal` and `LogViewerModal` both do.

### 12.5 Accessibility

The beta-user persona is colour-blind. Existing patterns:

| Cue | Bad | Good |
|---|---|---|
| Status enum | `[red]FAILURE[/]` (red alone) | `[red]✗ FAILURE[/]` (glyph + colour) |
| Important row marker | `[yellow b]<name>[/]` (yellow alone) | `[yellow b]* <name>[/]` (asterisk + bold + colour) |

Use `_status_glyph()` (in `dr_tui/app.py`) for status cells.

### 12.6 Lazy-loading Tree pattern (v0.16.0)

The connector browser in `NewJobModal` (re-introduced in v0.16.0) is
the canonical example of how to wire a Textual `Tree` against a paged
or expensive REST endpoint. The same shape works any time you have
"folder-like" data that's too big to pre-walk (corpora, datasets,
projects with deep nesting, etc.).

**Node data shape:**

```python
node.data = {
    "path":   "<absolute identifier — what the API needs>",
    "loaded": bool,   # children already fetched?
    "leaf":   bool,   # file/terminal node?
    "kind":   "marker" | "error" | None,  # for sentinel rows
}
```

**Lifecycle:**

1. **Initial load** — `_reload_tree()` resets the root, sets
   `root.data = {"path": <api id>, "loaded": False}`, and calls
   `root.expand()` to fire `on_tree_node_expanded` for the first
   batch.
2. **Lazy expand** — `on_tree_node_expanded` checks
   `data.get("loaded")` to avoid double-fires, flips the glyph
   `▸ → ▾`, adds a `loading…` placeholder, and runs a worker
   thread.
3. **Worker** — calls the REST endpoint, catches `APIError` and
   bare exceptions, then `call_from_thread` to the UI.
4. **UI fill** — sorts dirs before files, adds child nodes with
   their own `data["loaded"] = False`, removes the placeholder.
5. **Error** — replaces the placeholder with a red `⚠` chip *on
   the failing node* AND writes a longer message to a dedicated
   error pane. Both are needed: the chip shows "what folder
   broke", the pane explains why.
6. **Selection** — `on_tree_node_selected` reads `node.data["path"]`
   and writes it to whatever Input/state field needs it. Sentinel
   rows (`kind in ("marker", "error")`) are skipped.

**Why threading matters here:** `connectorManager/exploreConnector`
is async on the server side and can take 5+ seconds on slow NFS
mounts. Calling it on the UI thread freezes the entire TUI. The
placeholder makes the wait visible without a spinner widget.

See `NewJobModal._reload_tree`, `on_tree_node_expanded`,
`_fetch_and_fill`, `_tree_fill`, `_tree_show_error`, and
`on_tree_node_selected` in `dr_tui/app.py` for the full reference
implementation. Pilot coverage:
`tests/test_dr_tui_scheduler.py::test_newjob_modal_v016_tree_browser`.

---

## 13. Debugging recipes

### 13.1 Inspect what's on the wire

Force urllib3 debug logging — see every request line:

```python
import http.client, logging
http.client.HTTPConnection.debuglevel = 1
logging.basicConfig(level=logging.DEBUG, format="%(message)s")
logging.getLogger("urllib3").setLevel(logging.DEBUG)
```

Or run via mitmproxy in reverse-proxy mode (§11.1).

### 13.2 Inspect the AHS server log

```bash
tail -f /home/auraria/AHS/output/192.168.58.128_SERVER.log | \
  grep -E "ERROR|permission|<your-endpoint>"
```

Permission errors appear as:

```
ERROR [SecureObjectInterceptor] (default task-N) User <U> does not have
permission to perform <op> operation.
```

Often preceded by:

```
WARN [SecureObjectInterceptor] Action [<ACTION>] NOT permitted on
object [<context>] by user [<U>]
```

(NOT permitted line tells you which secureObject was checked — useful
for figuring out which role grant is missing.)

### 13.3 Compare against a working Web UI flow

Three-step diff:

1. Capture the Web UI's working call (§11.1).
2. Capture our REST call (also routed through the proxy via
   `DR_BASE_URL=https://localhost:8091/ediscovery/rest`).
3. Byte-diff the two request bodies. Anything you're sending that the
   Web UI doesn't is suspect.

This is the v0.15.2 discovery flow — every PERMISSION_DENIED
mystery was solved this way.

### 13.4 Postgres for ground truth

If the REST result looks wrong but you can't see why, peek into the
DB:

```bash
sudo -u auraria psql -d auraria_mgmt
\dt
SELECT handle, representation_state FROM datamining_corpus_representation;
SELECT * FROM ediscovery_workbasket ORDER BY date_started DESC LIMIT 10;
```

The DB schema isn't documented but the table names are
self-explanatory.

### 13.5 Reading the JS bundle

DR's Angular bundle is at:
```
/home/auraria/AHS/jboss/standalone/tmp/vfs/temp/*/main.js
```

13 MB minified-ish but `python3 -c "with open(p) as f: t=f.read(); print(t[i:j])"` works fine. Grep for endpoint names to find call sites.

### 13.6 Pilot suite as a regression net

```bash
.venv/bin/python -m pytest \
    tests/test_dr_tui_dashboard_layout.py \
    tests/test_dr_tui_depot_modal.py \
    tests/test_dr_tui_scheduler.py
```

19 tests, ~12 s, offline (no DR needed). **Always run before
committing.** New endpoints / modals get a new test in the
appropriate file.

---

## 14. Code map

```
helpers/api_client.py           ← EDiscoveryClient, APIError, login, post, rolling tokens
config.py                       ← Config + OrgUserConfig (reads ~/.env)

dr_tui/
  data.py                       ← All synchronous fetchers — search this file first
                                   for "have we called this endpoint before?"
  app.py                        ← Every screen + modal. ~3500 lines but heavily
                                   sectioned.
  scheduler.py                  ← JobDefinition, RunRecord, systemd timer helpers
  cli_jobrun.py                 ← Standalone CLI that fires the indexing chain
  cli_jobdel.py                 ← Standalone CLI for retention cleanup
  metrics.py                    ← Local-host CPU/Mem/Disk/Net psutil helpers
  help.py                       ← F2 doc-pane loader

docs/
  endpoints_v0.05.md            ← Read-path endpoint reference (login era)
  endpoints_v0.06.md            ← Write-path + job-control endpoints
  endpoints_v0.08.md            ← System Settings (advanced) endpoints
  API_PROGRAMMING_GUIDE.md      ← THIS FILE
  QA_TEST_PLAN.md               ← Test plan for QA Engineer
  RUNBOOK.md                    ← Symptom → fix cookbook
  DR_ROLE_SETUP.md              ← (Historical) Web UI role-grant walkthrough

tests/
  test_dr_tui_dashboard_layout.py   ← Pilot harness for DashboardScreen + F-keys
  test_dr_tui_depot_modal.py        ← All form modals offline tests
  test_dr_tui_scheduler.py          ← Scheduler + NewJobModal pilot

proxy_logger.py                  ← mitmproxy addon for capturing DR REST traffic
locustfile_indexing.py           ← Load test (the original working indexing
                                    chain — reference for shapes)
```

When in doubt, **grep `data.py` first** for an existing pattern.
Almost every new feature can be assembled from existing fetchers
plus a thin UI veneer.

---

*Last updated: 2026-05-14 (v0.15.2). Future updates: append at the
bottom or update the relevant section inline; bump the date.*
