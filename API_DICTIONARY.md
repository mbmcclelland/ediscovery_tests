# Digital Reef eDiscovery — API Dictionary

**Version 0.15 · 2026-05-19**

---

## How to read this document

This is the ground-truth reference for every REST endpoint that the test
suite and the `dr-load admin` CLI exercise. Every entry has been
validated live against the build at `192.168.58.128:8443`. Request and
response shapes come from real server responses — no Swagger file is
served by this build (verified 404/500 on every conventional path).

**When to use this document:**

| You want to… | Use… |
|---|---|
| Call an endpoint you haven't used before | This document — §4 Endpoint reference |
| Understand what the server does behind each call (DB writes, transactions) | [`DR_Workflow_Guide.md`](DR_Workflow_Guide.md) |
| Get started quickly as an operator | [`QA_README.md`](QA_README.md) |
| Look up an error you are seeing | §6 Top 10 things to know + §3 Error format |
| Understand the scope and auth model | §1 Scope rules (read this first) |

**Structure of each endpoint entry:**

> **Purpose** — one sentence.
> **Scope** — system / org / project.
> *(caption for the JSON block)*
> Request JSON → Response JSON → Errors and quirks.

Read §1 (scope rules) before any endpoint, or project-scoped calls will
500 in surprising ways.

---

## Table of contents

1. [Scope rules — read this first](#1-scope-rules--read-this-first)
2. [Connection and auth model](#2-connection-and-auth-model)
3. [Error format](#3-error-format)
4. [Endpoint reference](#4-endpoint-reference)
   - [4.1 Authentication](#41-authentication)
   - [4.2 Realm-level (system scope)](#42-realm-level-system-scope)
   - [4.3 Organization scope](#43-organization-scope)
   - [4.4 Project scope](#44-project-scope)
   - [4.5 Import pipeline](#45-import-pipeline)
   - [4.6 Project deletion (two-phase)](#46-project-deletion-two-phase)
   - [4.7 Reports and billing](#47-reports-and-billing)
5. [Unwrapped and blocked endpoints](#5-unwrapped-and-blocked-endpoints)
6. [Top 10 things to know before calling this API](#6-top-10-things-to-know-before-calling-this-api)

---

## 1. Scope rules — read this first

Every request body must carry two fields: `contextHandle` and
`systemScope`. Getting these wrong is the most common cause of HTTP 500
errors with no useful error body.

The server has three scopes:

| Scope | `systemScope` | `contextHandle` | When to use |
|---|---|---|---|
| **System** | `true` | `"super_system_customer"` | Realm-level calls: `listOrganizations`, `createOrganization`, `getRealmStatus`. |
| **Org** | `false` | `"<org_name>"` e.g. `"training"` | Org-level calls: `listProjects`, `listConnectors`, `listTemplates`, `createCase`. |
| **Project** | `false` | `"<project_handle>"` e.g. `"1580"` | Project-level calls: `getIndexSettings`, `listTasks`, `listCorpusSets`. Also used for `createDataArea` and `createCorpus`. |

**The session context rule:** Setting `contextHandle` in the body alone
is not always sufficient. Many endpoints also require the session to have
been initialized into the correct scope via `realmManager/initializeOrganization`
first. Without the session-state call, you get HTTP 500 with no body.
`listCorpora` at system scope is the canonical example — it must be
called after `switch_to_org(api, org)`, not at default system scope.

**How `EDiscoveryClient` handles this automatically:**

The `EDiscoveryClient.post()` method in `helpers/api_client.py`
auto-derives `systemScope` from whether the caller overrides
`contextHandle`. If the `contextHandle` in the body matches the
configured system org (`super_system_customer`), `systemScope` is set to
`True`; otherwise it is set to `False`. Callers can also pass
`system_scope=True/False` explicitly to override.

---

## 2. Connection and auth model

```
Base URL:        https://<host>:8443/ediscovery/rest
TLS:             self-signed by default; client must accept (or pin a cert)
Content-Type:    application/json
Accept:          application/json
Auth header:     Authorization: <raw sessionToken from createSession>
                 (NOT "Bearer ..." — the token is the entire header value)
```

**Session lifecycle:**

1. `POST /realmManager/createSession` with HTTP Basic Auth plus a UUID
   `userDeviceID` in the JSON body. The server returns a `sessionToken`.
2. Every subsequent request sends `Authorization: <sessionToken>`.
3. The server **rolls** the token: every response may contain a fresh
   `sessionToken` field. The client must capture and use the latest one.
4. No explicit logout endpoint is used; sessions time out server-side.

`EDiscoveryClient` handles all of this transparently, including token
rolling.

---

## 3. Error format

The server uses two error vocabularies:

**Structured `status=FAILURE` JSON** (the preferred path):

```json
{
  "status": "FAILURE",
  "errorCode": "PERMISSION_DENIED",
  "extendedStatus": "User does not have permission to perform foo",
  "numberResults": 0,
  "sessionToken": "..."
}
```

`EDiscoveryClient.post()` raises `helpers.api_client.APIError` carrying
all four fields. Catch `APIError` for normal error flow.

**HTTP 5xx with non-JSON HTML body** (anti-pattern, but common):

When the server hits an internal error before its response handler can
build a JSON envelope — such as an unauthenticated endpoint call (BUG_LOG
B24) or a wrong-scope request — it returns an HTML error page. The client
surfaces this as `requests.exceptions.HTTPError(500, ...)`. Always check
`/home/auraria/AHS/output/192.168.58.128_SERVER.log` for the stack trace.

**Common `errorCode` values:**

| errorCode | Meaning |
|---|---|
| `PERMISSION_DENIED` | The caller lacks permission for this action |
| `CAE_ERROR` | Generic server crash — check `extendedStatus` for the actual exception |
| `PERMISSION_MAP_INVALID` | Permission row not found for a role handle (often a Hibernate composite-key miss — B29) |
| `INTERNAL_ERROR` | Catch-all server failure |
| `NOT_FOUND` | Resource does not exist |
| `UNAUTHENTICATED` | No session or expired token |

---

## 4. Endpoint reference

> **Five non-obvious request shapes — check these before debugging a 500:**
>
> 1. **`systemScope` must be `false` for project-scoped endpoints.** Sending `true`
>    with a project `contextHandle` causes the server to check the caller's system-scope
>    role — which typically fails with a 500 and no body. `EDiscoveryClient` auto-derives
>    this, but raw `curl` calls must set it explicitly.
>
> 2. **`initializeOrganization` is required before most org/project calls.** The server
>    checks session state, not just `contextHandle` in the body. Without the session-state
>    call you get HTTP 500 with no body. See `listCorpora` for the canonical example.
>
> 3. **`createCase` requires at least one user in `membersRequestMessage.users`.** An empty
>    array returns HTTP 500 "Could not set permissions". Always include the orchestration
>    user with a valid role handle.
>
> 4. **`orgManager/listRoles` requires `objectType` in the body.** Omitting it causes the
>    server to NPE on `SecureObjectTypes.equals(null)` and return `CAE_ERROR`. Pass
>    `{"objectType": "PROJECT"}`.
>
> 5. **`requestProjectDelete` is not idempotent.** Calling it twice while a request is
>    pending returns HTTP 500 "already requested". `helpers.admin_ops.delete_project`
>    catches this automatically — callers outside that helper must handle it.

---

### 4.1 Authentication

#### `realmManager/createSession`

**Purpose:** Log in and get a session token. This must be the first call in any session.

**Scope:** None — auth itself.

**Auth:** HTTP Basic (`Authorization: Basic ...`) plus the JSON body. The
Basic header is the password check; the body's `userDeviceID` is
correlated with the issued token.

*Minimal login request:*

```json
{
  "drWsClientContext": {
    "username":         "DRSysAdmin",
    "organizationName": "super_system_customer",
    "ldapDomainName":   ""
  },
  "contextPath":  "/ediscovery",
  "userDeviceID": "<uuid4>"
}
```

*Success response:*

```json
{
  "status": "SUCCESS",
  "sessionToken": "<long opaque base64-ish string ending in ||<uuid4>>",
  "lastAccessTime": 1779116205487,
  "userPolicy": { "...": "..." },
  "drWsClientContext": { "...": "..." },
  "numberResults": 0
}
```

**Quirks:**

- The trailing `||<uuid4>` of the token must match `userDeviceID` for
  subsequent calls to be accepted.
- Calling unauthenticated endpoints with no token NPEs server-side
  instead of returning 401 (BUG_LOG B24). Always log in first.
- LDAP-domain users append `@<domain>` to `username` if
  `ldapDomainName` is set.

---

### 4.2 Realm-level (system scope)

These endpoints operate at the realm level. Call them as DRSysAdmin in
`super_system_customer` with `systemScope: true`. No `initializeOrganization`
call is needed before these.

#### `realmManager/listOrganizations`

**Purpose:** Enumerate all organizations in the realm.

**Scope:** System.

*Request — system-scoped list:*

```json
{ "contextHandle": "super_system_customer", "systemScope": true }
```

*Response:*

```json
{
  "status": "SUCCESS",
  "totalCount": 5,
  "organizations": [
    {
      "handle":       "139",
      "name":         "training",
      "attributes":   { "defaultRole": "...", "...": "..." },
      "createdOn":    1779000000000,
      "deletePending": false,
      "processing":   { "...": "..." },
      "roles":        [ "..." ],
      "storageUsages": [ "..." ],
      "totalStorageUsage": 0
    }
  ]
}
```

**Quirks:**

- Org handles are numeric strings (e.g. `"139"`), not 40-character hex.
  See BUG_LOG B20.

---

#### `realmManager/createOrganization`

**Purpose:** Create a new organization. Used by `dr-load admin create-org`.

**Scope:** System.

*Request — create a new org:*

```json
{
  "contextHandle":    "super_system_customer",
  "systemScope":      true,
  "name":             "qa-bootstrap-001",
  "description":      "Phase-1 verification org",
  "organizationName": "qa-bootstrap-001"
}
```

*Response:*

```json
{
  "status": "SUCCESS",
  "organization": {
    "handle": "1576",
    "name":   "qa-bootstrap-001",
    "attributes": { "...": "..." }
  }
}
```

**Side effects:** The server creates four default roles in the new org
(Organization Administrator, Project Administrator, Project Member,
Claimant) plus LDAP entries (`ou=users,o=<name>`, `ou=groups,...`).
Role handles are minted at this point and are per-org-per-install.

**Quirks:**

- DRSysAdmin is NOT auto-added to the new org as Org Admin. The
  `createCustomerUser` REST surface is blocked for this case — the
  browser Express Provisioning flow must be used to add the first user
  to a fresh org. See §5 and BUG_LOG B36.
- No REST `deleteOrganization` endpoint exists on this build. Verified
  500 on `realmManager/deleteOrganization`, `removeOrganization`,
  `destroyOrganization`, and `adminOrgManager/deleteOrganization`.

---

#### `realmManager/initializeOrganization`

**Purpose:** Switch the session's active org or project context. Required
before most org- or project-scoped calls. The server checks session
state, not just `contextHandle` in the request body.

**Scope:** Implicit — operates on the session, not a named resource.

*Request — switch session to an org:*

```json
{
  "requestHandle":    null,
  "contextHandle":    "training",
  "organizationName": "training"
}
```

*Request — switch session to a specific project:*

```json
{
  "requestHandle":    null,
  "contextHandle":    "1580",
  "organizationName": "training",
  "systemScope":      false
}
```

**Response:** A `status=SUCCESS` envelope plus org or project metadata.
The server's session state is now scoped to the target.

---

#### `realmManager/getRealmStatus`

**Purpose:** Cheap health check used by `dr-load preflight`.

**Scope:** System.

*Request:*

```json
{ "contextHandle": "super_system_customer", "systemScope": true }
```

*Response:*

```json
{ "status": "SUCCESS", "realmStatus": "AVAILABLE" }
```

---

#### `realmManager/getStorageUsageDownloadUrl` / `getMigrationQuotaReportUrl`

**Purpose:** Generate a one-time download URL for a CSV storage or
migration report.

**Scope:** System.

*Response:*

```json
{
  "status": "SUCCESS",
  "url": "https://192.168.58.128:8443/ediscovery/rest/reports/storage_usage_<uuid>.csv"
}
```

The URL is signed and short-lived. GET it directly without re-auth.

---

#### `realmManager/getOCRUsageStatisticsUrl`

**Purpose:** Generate a download URL for the OCR usage report (used by
the Edge-recorded workflow in `tests/test_ocr_report.py`).

**Scope:** System.

*Request — specify a date window:*

```json
{
  "contextHandle": "super_system_customer",
  "systemScope":   true,
  "filters": [
    { "attribute": "FROM_DATE", "value": "2026-01-01" },
    { "attribute": "TO_DATE",   "value": "2026-01-31" }
  ]
}
```

*Response:* `{ "status": "SUCCESS", "url": "..." }`

---

### 4.3 Organization scope

These endpoints run after `initializeOrganization(<org_name>)`. Body
uses `contextHandle: "<org_name>", systemScope: false`.

#### `orgManager/listConnectors`

**Purpose:** Enumerate connectors visible to the current user in the
specified org. Used by `dr-load admin list-connectors`.

**Scope:** Org. Must call `initializeOrganization` first.

*Request:*

```json
{ "contextHandle": "training" }
```

*Response — connector record (key fields):*

```json
{
  "status": "SUCCESS",
  "totalCount": 2,
  "connectors": [
    {
      "handle":      "000084ba6f8e4a2488d74ef2af4e893b8ea2ac99",
      "name":        "training-import-nfs-local",
      "type":        "NFS",
      "mode":        "READ",
      "status":      "AVAILABLE",
      "readOnly":    true,
      "remotePath":  "/data/import",
      "offset":      "/data/import"
    }
  ]
}
```

**Critical — how `--path` resolves against `remotePath`:**

When you call `orgManager/createDataArea` with a `path` argument, the
server resolves it as `<remotePath>/<path>`:

| `remotePath` | `--path` you pass | Files the server scans |
|---|---|---|
| `/data/import` | `/testload` | `/data/import/testload` |
| `/data/import` | `/Dave White Hard Drive` | `/data/import/Dave White Hard Drive` |
| `/data/import` | `/data/testload` | `/data/import/data/testload` (wrong!) |

**`--path` is the subpath under `remotePath`, never an absolute host
filesystem path.** Passing an absolute path doubles the prefix and the
server finds no documents, causing `createRepresentation` to fail in
1–2 seconds with no obvious error message.

**Quirks:**

- Connector handles are 40-character hex strings, unlike org/project
  handles which are numeric.
- Before v0.06, DRSysAdmin saw 0 connectors here until added as Org
  Admin in the target org. (BUG_LOG B14.)
- Paths with spaces work end-to-end through the CLI, JSON body, and
  server resolver — verified on a 250-document dataset with
  `"/Dave White Collected Hard Drive 2023-07-24"`.

---

#### `orgManager/listConnectorTypes`

**Purpose:** List connector types this install supports.

**Scope:** Org or system.

*Response:*

```json
{
  "status": "SUCCESS",
  "connectorTypes": ["NFS", "CIFS", "SHAREPOINT", "EXCHANGE", "RELATIVITY"]
}
```

---

#### `orgManager/listProjects`

**Purpose:** Enumerate all projects in the org. Used by `dr-load admin
list` and by name-to-handle lookups throughout the CLI.

**Scope:** Org.

*Request:*

```json
{ "contextHandle": "training" }
```

*Response — project record (key fields):*

```json
{
  "status": "SUCCESS",
  "totalProjects": 4,
  "projects": [
    {
      "handle":                 "1580",
      "name":                   "qa-bootstrap-proj-001",
      "description":            "Phase-1 verification project",
      "orgName":                "training",
      "projectActivationState": "ACTIVE",
      "projectState":           "AVAILABLE",
      "projectGuid":            "000000009f512d5c0ce4a123",
      "userName":               "drsysadmin",
      "dateCreated":            "2026-05-16 12:25:16"
    }
  ]
}
```

**Critical fields:**

- `handle` — numeric string (e.g. `"1580"`), not 40-character hex.
- `projectActivationState` — `"ACTIVE"` / `"DELETE_REQUEST_PENDING"` /
  etc. This is the real "is the project alive?" signal.
  `projectState` is sometimes `"UNKNOWN"` even for active projects.

**Quirks:**

- A half-failed `createCase` can leave a project in `mgmtproject` that
  is invisible to this listing (the state filter excludes pre-AVAILABLE
  entries). Recover with `dr-load admin delete-project --handle HANDLE`
  (BUG_LOG B35).

---

#### `orgManager/listUsers`

**Purpose:** Enumerate users in the org with their role assignments.
This is the only working role-discovery surface on this build. Used by
`helpers.admin_ops.find_role_handle` to auto-resolve role handles during
`createCase`. See also: `ecaManager/createCase` in [§4.4](#ecamanager-createcase).

**Scope:** Org.

*Request:*

```json
{ "contextHandle": "training" }
```

*Response — user record (key fields):*

```json
{
  "status": "SUCCESS",
  "totalUsers": 2,
  "users": [
    {
      "handle":             "admin@training",
      "userName":           "admin",
      "displayName":        "Ad min",
      "email":              "admin@localhost.com",
      "organizationHandle": "139",
      "admin":              false,
      "enabled":            true,
      "roleHandles":        ["00003855b4e4ec3264634192b340373841503303"],
      "roles":              [ "...full role objects..." ]
    }
  ]
}
```

**Critical:** The `name` field is **always `null`** on this build. Use
`userName` instead. (Caught during v0.06 development.)

---

#### `orgManager/listGroups`

**Purpose:** Enumerate groups in the org.

**Response:** `{ "status": "SUCCESS", "totalCount": 0, "groups": [] }`

Most installs have no groups — users get roles directly.

---

#### `orgManager/listCorpora`

**Purpose:** Enumerate corpora (indexed document collections) in the
org. Must be called after `initializeOrganization(<org>)` — calling it
at system scope causes the server to NPE and return HTTP 500 with no
body (BUG_LOG B31).

**Scope:** Org. Must call `initializeOrganization` first.

*Request:*

```json
{ "contextHandle": "training" }
```

*Response — corpus record (key fields):*

```json
{
  "status": "SUCCESS",
  "totalCount": 7,
  "corpora": [
    {
      "handle":              "148:0000bbfbf4bc487ed506416ebce8df70ef4a3da2",
      "owner":               "414",
      "name":                "welcome",
      "description":         "",
      "documentCount":       2,
      "corpusVersion":       6,
      "corpusViewHandle":    "0000bbfbf4bc487ed506416ebce8df70ef4a3da2",
      "representationSet":   ["METADATA_INDEX", "TEXT_SET", "CONTENT_INDEX", "VECTOR_SET"],
      "sharedState":         "PRIVATE",
      "archived":            false,
      "busy":                false,
      "deletePending":       false,
      "lastUpdateTimestamp": "2026-05-15 19:33:53"
    }
  ]
}
```

**Critical — `owner` is the project handle, not the handle prefix:**

The `handle` field uses a composite format:
`<corpus-view-container>:<corpus-hex-handle>`. The prefix (`148`) is the
**default-org corpus-view container**, not the owning project. Code that
splits on `:` to get the project will get the wrong answer for every
corpus.

```python
# WRONG — prefix is the corpus-view container, not the project
project_handle = corpus["handle"].split(":")[0]

# RIGHT — owner is the owning project's handle
project_handle = corpus["owner"]
```

The dashboard doc-counter bug (where every project showed 0 docs) was
caused by this mistake — fixed in v0.11 by switching to `corpus.owner`.

---

#### `orgManager/listDataAreas` / `listExportDataAreas` / `listExportDatabaseConnections`

**Purpose:** Enumerate data-area or export resources in the org.

**Scope:** Org. (`listExportDatabaseConnections` requires an org
`initializeOrganization` call, not system scope — BUG_LOG B32.)

*Response:* `{ "status": "SUCCESS", "dataAreas": [ ... ] }` or
`{ "connections": [] }`.

---

#### `orgManager/listTemplates`

**Purpose:** Enumerate the org's project templates. Used by
`helpers.api_client.EDiscoveryClient.discover_template_attributes` to
build the 18-element attribute list that `createCase` requires.

**Scope:** Org.

*Request:*

```json
{ "contextHandle": "training" }
```

*Response — template record:*

```json
{
  "status": "SUCCESS",
  "totalCount": 17,
  "templates": [
    {
      "handle":          "176",
      "name":            "Default Index Settings",
      "templateType":    "INDEX_SETTINGS",
      "defaultTemplate": true,
      "orgId":           139,
      "createdBy":       "system"
    }
  ]
}
```

**Critical:** Template handles are **per-org-per-install**. The same
template name in two different orgs has different handles. Always
discover at runtime — never hardcode (BUG_LOG B11, B14d).

The 17 `templateType` values on this build:

```
ALIAS_LISTS  ANALYTICAL_SETTINGS  BILLING_REPORT_SETTINGS
CUSTOM_FIELDS  DOCUMENT_METADATA  DOMAIN_LISTS  DUPE_SURVIVORSHIP
EMAIL_SIGNATURE  EXPORT_FIELDS  EXPORT_SETTINGS  INDEX_SETTINGS
LOADFILE_SETTINGS  USER_EXP  REPORT_SETTINGS  SEARCH_FIELDS
SEARCH_SETTINGS  TAG
```

`discover_template_attributes` injects an 18th synthetic
`IS_IMPORTED='false'` after `INDEX_SETTINGS` to match the browser-flow
payload (BUG_LOG B26).

---

#### `orgManager/listRoles`

**Purpose:** Enumerate roles for a given object type in the org.

**Scope:** Org.

*Request — always include `objectType`:*

```json
{
  "contextHandle": "training",
  "objectType":    "PROJECT"
}
```

*Response:*

```json
{
  "status": "SUCCESS",
  "roles": [
    {
      "handle": "00003855b4e4ec3264634192b340373841503303",
      "name":   "Organization Administrator"
    }
  ]
}
```

**Critical:** Always pass `objectType`. Omitting it causes the server to
NPE on `SecureObjectTypes.equals(null)` and return `CAE_ERROR` (BUG_LOG
B33). In practice, use `orgManager/listUsers` and read each user's
`roleHandles` field — that is the only fully working role-discovery
surface.

---

### 4.4 Project scope

These endpoints run after `initializeOrganization(<project_handle>)`.
Body uses `contextHandle: "<project_handle>", systemScope: false`.

#### `ecaManager/createCase`

**Purpose:** Create a new project (case). Used by `dr-load admin
create-project`. Requires templates discovered via
[`orgManager/listTemplates`](#orgmanager-listtemplates) and a role handle
from [`orgManager/listUsers`](#orgmanager-listusers).

**Scope:** Org (parent org of the new project), with `systemScope: false`.

*Full request body — all fields are required:*

```json
{
  "requestHandle":  null,
  "contextHandle":  "training",
  "systemScope":    false,
  "addToCaseData":  false,
  "custodians":     [],
  "name":           "qa-bootstrap-proj-001",
  "description":    "Phase-1 verification project",
  "attributes": [
    { "name": "ALIAS_LISTS",              "value": "283" },
    { "name": "ANALYTICAL_SETTINGS",      "value": "204" },
    { "name": "BILLING_REPORT_SETTINGS",  "value": "291" },
    { "name": "CUSTOM_FIELDS",            "value": "288" },
    { "name": "DOCUMENT_METADATA",        "value": "233" },
    { "name": "DOMAIN_LISTS",             "value": "227" },
    { "name": "DUPE_SURVIVORSHIP",        "value": "235" },
    { "name": "EMAIL_SIGNATURE",          "value": "231" },
    { "name": "EXPORT_FIELDS",            "value": "199" },
    { "name": "EXPORT_SETTINGS",          "value": "220" },
    { "name": "INDEX_SETTINGS",           "value": "176" },
    { "name": "IS_IMPORTED",              "value": "false" },
    { "name": "LOADFILE_SETTINGS",        "value": "285" },
    { "name": "USER_EXP",                 "value": "229" },
    { "name": "REPORT_SETTINGS",          "value": "277" },
    { "name": "SEARCH_FIELDS",            "value": "255" },
    { "name": "SEARCH_SETTINGS",          "value": "237" },
    { "name": "TAG",                      "value": "225" }
  ],
  "membersRequestMessage": {
    "groups": [],
    "users": [
      {
        "name": "drsysadmin",
        "roleHandles": ["00003855b4e4ec3264634192b340373841503303"]
      }
    ]
  },
  "projectLogoBytes": null,
  "logoFileName":     "",
  "reviewSystem":     null,
  "reviewProjectId":  0
}
```

> Note on attribute values: the numeric values above (`"283"`, `"204"`,
> etc.) are template handles for the `training` org on this install.
> They change per-org and per-install. Use
> `client.discover_template_attributes("training")` to get the correct
> values at runtime — never hardcode them.

*Response — note that `status` is `null` on success:*

```json
{
  "status":         null,
  "caseHandle":     "1580",
  "requestHandle":  null,
  "warningDetails": null,
  "auditLogUrl":    null,
  "errorCode":      null,
  "extendedStatus": null,
  "numberResults":  0
}
```

**Quirks:**

- Response `status` is `null` on success, not `"SUCCESS"`. The helper
  only fails on `"FAILURE"`.
- An empty `users` array returns HTTP 500 "Could not set permissions".
  At least one user with a valid role handle is required.
- Even on success the server log shows `ERROR Could not find role row
  with:<handle>PROJECT` (BUG_LOG B29) and a `NullPointerException` from
  SendEmail (B30). Both are cosmetic — the project still activates.
- A half-failed `createCase` (e.g., when SendEmail's NPE bubbles up)
  leaves the project hidden from `listProjects`. See [BUG_LOG B35](BUG_LOG.md)
  and [§4.6](#46-project-deletion-two-phase) for recovery.

---

#### `projectManager/getIndexSettings`

**Purpose:** Read the project's index settings — typically called by the
browser immediately after switching to a project.

**Scope:** Project.

*Request:*

```json
{
  "requestHandle": null,
  "contextHandle": "1580",
  "handle":        "1580",
  "systemScope":   false
}
```

*Response:* `{ "status": "SUCCESS", "settings": { "...": "..." } }`

---

#### `projectManager/getUpdateStatus`

**Purpose:** Bulk update-status check (connector, component, and storage
states). The browser fires this after `initializeOrganization` for a
project.

**Scope:** Project.

*Request:*

```json
{
  "requestHandle":     null,
  "contextHandle":     "1580",
  "projectHandle":     0,
  "timestamp":         0,
  "updateStatusTypes": ["CONNECTOR", "COMPONENT", "STORAGE"]
}
```

---

#### `projectManager/listCorpusSets`

**Purpose:** Enumerate corpus sets in the project. Used by the import
pipeline to find the default corpus set to attach a new corpus to.
See also: `corpusSetManager/addCorpus` in [§4.5](#45-import-pipeline).

**Scope:** Project.

*Request:*

```json
{
  "requestHandle": null,
  "contextHandle": "1580",
  "projectHandle": "1580",
  "count":         1,
  "startIndex":    0
}
```

*Response:*

```json
{
  "status": "SUCCESS",
  "totalCount": 1,
  "corpusSets": [
    {
      "handle":  "000070920025cd6333384f90a67a61ebf51c3639",
      "name":    "Default",
      "deletePending": false
    }
  ]
}
```

---

#### `projectManager/listTasks`

**Purpose:** Enumerate indexing and processing tasks in the project.
Used by `helpers.admin_ops.wait_for_tasks` to poll for `SUCCESS`.

**Scope:** Project.

*Request:*

```json
{
  "requestHandle": null,
  "contextHandle": "1580",
  "projectHandle": "1580"
}
```

*Response — task record (key fields):*

```json
{
  "status": "SUCCESS",
  "totalTasks": 1,
  "tasks": [
    {
      "handle":          "0000958e2e4b16f15d704300bbdb3437030ca932",
      "description":     "Creating representation Analytic Index for testload",
      "task":            "DOCUMENT_ADD_FROM_FILE_LIST",
      "taskStatus":      "SUCCESS",
      "operationState":  "SUCCESS",
      "percentComplete": 100,
      "numberResults":   2,
      "secondsElapsed":  11,
      "dateCompleted":   "2026-05-16 12:26:21",
      "owner":           "drsysadmin"
    }
  ]
}
```

**Critical:** Active states are `RUNNING`, `QUEUED`, `PENDING`,
`PROCESSING`. Terminal states include `SUCCESS` and `FAILED`. The helper
polls until no active task remains, then inspects `operationState` and
`taskStatus` for success.

---

### 4.5 Import pipeline

Called after `initializeOrganization(<project_handle>)`. Run these four
endpoints in order:

```
createDataArea  →  createCorpus  →  corpusSetManager/addCorpus  →  createRepresentation
```

This chain is wrapped by `helpers.admin_ops.create_import_job`.

#### `orgManager/createDataArea`

**Purpose:** Create a data-area record that points at a path inside a
connector. Prerequisites: the project must exist (`createCase` was
called), and you must know the connector handle from
[`orgManager/listConnectors`](#orgmanager-listconnectors).

**Scope:** Project (`systemScope: false`, `contextHandle: <project_handle>`).

*Request — point at /testload inside the NFS connector:*

```json
{
  "requestHandle":      null,
  "contextHandle":      "1580",
  "systemScope":        false,
  "connectorHandle":    "000084ba6f8e4a2488d74ef2af4e893b8ea2ac99",
  "description":        "",
  "mode":               "IMPORT",
  "name":               "testload_testload",
  "path":               "/testload",
  "skippedDirectories": []
}
```

*Response:*

```json
{
  "status": "SUCCESS",
  "dataArea": {
    "handle": "0000a33071061120dfaf40cb8b24dca5ddd1bcfd"
  }
}
```

**Critical:**

- `path` is the **path inside the connector's `remotePath`**
  (e.g. `/testload`), not the absolute host filesystem path
  (`/data/import/testload`). See [§4.3 `listConnectors`](#orgmanager-listconnectors)
  for the full path-resolution table and why wrong paths cause silent
  indexing failures.
- `mode: "IMPORT"` for inbound NFS data. `"EXPORT"` exists for outbound.

---

#### `orgManager/createCorpus`

**Purpose:** Create a corpus that binds one or more data-area handles
into a logical indexable unit. Requires the `dataArea.handle` from
[`createDataArea`](#orgmanager-createdataarea).

**Scope:** Project.

*Request — bind one data area into a new corpus:*

```json
{
  "requestHandle":   null,
  "contextHandle":   "1580",
  "systemScope":     false,
  "attributes":      [{ "name": "projecthandle", "value": "1580" }],
  "brand":           true,
  "dataAreaHandles": ["0000a33071061120dfaf40cb8b24dca5ddd1bcfd"],
  "description":     "",
  "name":            "testload",
  "loadFileName":    "",
  "loadFileType":    "EDRM_XML",
  "loadFileProfileId": -1
}
```

*Response:*

```json
{
  "status": "SUCCESS",
  "corpus": {
    "handle": "1580:00004c79d6fdba6e399e4dbdb7882d94b45e15a8"
  }
}
```

**Critical:** The returned `corpus.handle` uses the composite
`<project_handle>:<corpus_handle>` format. Pass it as-is to downstream
calls (`addCorpus`, `createRepresentation`).

---

#### `corpusSetManager/addCorpus`

**Purpose:** Link a corpus to the project's corpus set (typically the
"Default" set). Prerequisites: corpus handle from
[`createCorpus`](#orgmanager-createcorpus) and corpus set handle from
[`listCorpusSets`](#projectmanager-listcorpussets).

**Scope:** Project.

*Request:*

```json
{
  "requestHandle":   null,
  "contextHandle":   "1580",
  "systemScope":     false,
  "corpusHandle":    "1580:00004c79d6fdba6e399e4dbdb7882d94b45e15a8",
  "corpusSetHandle": "000070920025cd6333384f90a67a61ebf51c3639"
}
```

*Response:* `{ "status": "SUCCESS" }`

---

#### `corpusManager/createRepresentation`

**Purpose:** Kick off the async indexing pipeline. Returns immediately;
poll [`projectManager/listTasks`](#projectmanager-listtasks) to track
completion. Prerequisites: corpus must be linked to a corpus set
(`addCorpus` called).

**Scope:** Project.

*Request — start indexing (CONTENT + VECTOR representations):*

```json
{
  "requestHandle":         null,
  "contextHandle":         "1580",
  "systemScope":           false,
  "corpusHandle":          "1580:00004c79d6fdba6e399e4dbdb7882d94b45e15a8",
  "attributes":            [{ "name": "projecthandle", "value": "1580" }],
  "scanAttributes":        [
    { "name": "batchNumber",   "value": "testload" },
    { "name": "projecthandle", "value": "1580" }
  ],
  "taskDescription":       "Creating representation Analytic Index for testload",
  "typeList":              ["CONTENT_INDEX", "VECTOR_SET"],
  "enablePatternDetection": true
}
```

*Response — note `status` is null:*

```json
{
  "status":       null,
  "errorCode":    null,
  "numberResults": 0
}
```

**Side effects:** The server creates four representation rows
automatically (METADATA, CONTENT, VECTOR, TEXT) even though only two
are requested in `typeList`. The DOCPREP service picks up the work
asynchronously.

---

### 4.6 Project deletion (two-phase)

Project deletion requires submitting a request and then approving it.
This two-step design allows for a human approval gate in production.
Wrapped by `helpers.admin_ops.delete_project`. The CLI is `dr-load
admin delete-project NAME`.

#### `adminOrgManager/requestProjectDelete`

**Purpose:** Submit a delete request for a project. The project enters
`DELETE_REQUEST_PENDING` state; the actual deletion happens after
approval.

**Scope:** Project + `systemScope: true` (this is one of the few
project-handle calls that uses system scope).

*Request:*

```json
{
  "requestHandle":   null,
  "contextHandle":   "1580",
  "projectHandle":   "1580",
  "systemScope":     true,
  "taskDescription": "Delete Project qa-bootstrap-proj-001"
}
```

*Response:* `{ "status": "SUCCESS" }`

**Quirks:**

- **Not idempotent.** A second call while a request is pending returns
  HTTP 500 with `extendedStatus: "Deletion of this project has already
  been requested."` `helpers.admin_ops.delete_project` catches and
  ignores this so cleanup is re-runnable. Raw callers must handle it.

---

#### `adminOrgManager/listDeletePendingProjects`

**Purpose:** List delete requests currently waiting for approval.
Used by `delete_project` to find the admin-request handle needed for
the approval call.

**Scope:** System.

*Request:*

```json
{
  "requestHandle": null,
  "systemScope":   true,
  "contextHandle": "super_system_customer"
}
```

*Response — request record (key fields):*

```json
{
  "status": "SUCCESS",
  "totalCount": 2,
  "requests": [
    {
      "handle":                 "4028ba009e319043019e3259d47000c5",
      "objectHandle":           "2210",
      "objectName":             "smoke-5a2a78c4",
      "adminRequestObjectType": "PROJECT",
      "requestStatus":          "PENDING",
      "requestedBy":            "drsysadmin",
      "orgName":                "training"
    }
  ]
}
```

**Critical:** The top-level key is **`requests`** (not `adminRequests`
or `projects` — an earlier helper used the wrong keys). Each item
identifies the project via **`objectHandle`** and **`objectName`** (not
`projectHandle` or `projectName`). The admin-request handle used for
approval is `handle` (not `objectHandle`). See BUG_LOG B14b.

---

#### `adminOrgManager/approveProjectDeleteRequest`

**Purpose:** Approve a pending delete request — this actually deletes
the project. Requires the admin-request handle from
[`listDeletePendingProjects`](#adminorgmanager-listdeletependingprojects).

**Scope:** System.

*Request — note: `handle` is the admin-request handle, not the project handle:*

```json
{
  "requestHandle":   null,
  "contextHandle":   "1580",
  "handle":          "4028ba009e319043019e3259d47000c5",
  "systemScope":     true,
  "taskDescription": "Approving delete for qa-bootstrap-proj-001"
}
```

*Response:* `{ "status": "SUCCESS" }`

**Critical:** `handle` here is the **admin-request handle** (from
`requests[].handle`), not the project handle. Passing the project handle
returns "not found".

---

### 4.7 Reports and billing

#### `projectManager/listBillingReportSettings`

**Purpose:** Read the project's billing report configuration.

**Scope:** Project.

*Request:* `{ "contextHandle": "<project_handle>" }`

*Response:* `{ "status": "SUCCESS", "reportSettings": [ "..." ] }`

---

#### `projectManager/getEmailReportDeliverySettings`

**Purpose:** Read email-delivery config for project reports.

**Scope:** Project.

---

#### `projectManager/listReportSettings` — BROKEN

**Status:** Confirmed server bug (BUG_LOG B34). Returns
`errorCode: CAE_ERROR` with `NumberFormatException: Cannot parse null
string` for every request body shape tried. No variant recovers.
Marked `@pytest.mark.xfail(strict=False)` in `tests/test_billing.py`.
Do not call this endpoint until the server fix lands.

---

## 5. Unwrapped and blocked endpoints

These endpoints exist server-side but cannot be reached via the REST
surface available to DRSysAdmin.

#### `orgManager/createCustomerUser` — BLOCKED

**Status:** The server's `SecureObjectInterceptor` requires the caller to
already be a user in the target org. DRSysAdmin is not a user in a
brand-new org, so this call fails with:

```
ERROR User drsysadmin does not have permission to perform createCustomerUser
ERROR User not found drsysadmin in org:<new_org>
WARN  Action [CREATE] NOT permitted on object [<new_org>] by user [drsysadmin]
```

No body shape recovers this — verified across `contextHandle` variants,
`systemScope` variants, and with and without a `users[]` payload.
(BUG_LOG B36.)

**Workaround:** The "create the org admin user" step is browser-only.
Open the web UI as DRSysAdmin → switch to the target org → use Express
Provisioning. This is a one-time step per fresh org.

---

#### `orgManager/listOrgRoles` / `realmManager/listRoles` / `ecaManager/listRoles` / `permissionManager/setPermissions` / ...

All return HTTP 500 with no body on this build. For role discovery, use
`orgManager/listUsers` and read each user's `roleHandles` field — that
is the only working surface.

---

## 6. Top 10 things to know before calling this API

| # | Symptom or pattern | Cause | Fix |
|---|---|---|---|
| 1 | HTTP 500, no body, on a project-scoped call | Body has `systemScope: true` with a project `contextHandle` | Set `systemScope: false`, or let `EDiscoveryClient` auto-derive it |
| 2 | HTTP 500, no body, on `listCorpora` | Session never called `initializeOrganization(<org>)` | Call `ops.switch_to_org(api, org)` first |
| 3 | `errorCode: CAE_ERROR` — NPE: SecureObjectTypes.equals(null) | `objectType` missing on `listRoles` | Pass `extra_body={"objectType": "PROJECT"}` |
| 4 | `errorCode: PERMISSION_MAP_INVALID` "Could not set permissions" | A role handle is invalid for the target org | Verify the handle via `listUsers`; never hardcode role handles |
| 5 | `errorCode: CAE_ERROR` — NPE: mail.Session.getProperty | SMTP is unconfigured; SendEmail subrequest NPEs on every `createCase` | Cosmetic — project still activates correctly (BUG_LOG B30) |
| 6 | `caseHandle: null` returned | Request body invalid — most often an empty `users` array | Include at least one user with a valid role handle |
| 7 | Project just created but `listProjects` does not show it | Half-failed `createCase` left the project in a pre-AVAILABLE state | Find the handle in `SERVER.log`; recover with `delete-project --handle` (BUG_LOG B35) |
| 8 | `requestProjectDelete` returns HTTP 500 "already requested" | Called twice while a request was pending | `helpers.admin_ops.delete_project` swallows this; raw callers must handle it |
| 9 | `createDataArea` succeeds but indexing finds 0 documents and fails in 1–2 seconds | `--path` does not exist under the connector's `remotePath` | Stage files under `<remotePath>/<path>` on the host; `--path` is always a subpath |
| 10 | Dashboard DOCS column reports 0 for all projects | Corpus-to-project mapping used `handle.split(":")[0]` instead of `corpus.owner` | Use `corpus["owner"]` — the handle prefix is the corpus-view container, not the project |

**Additional log noise that is safe to ignore** (server-side, all cosmetic — see [BUG_LOG §A](BUG_LOG.md#a--open-today-quick-scan)):

| Log pattern | Source | BUG_LOG entry |
|---|---|---|
| `Could not find role row with:<handle>PROJECT` | Every `createCase` | B29 |
| `NullPointerException: javax.mail.Session.getProperty` | Every `createCase` (no SMTP) | B30 |
| `Add object - could not find parent object ... type [WORK_BASKET]` | Every `createCase` | B37 |
| `Exception when canceling all requests for project NNNN ... Task Handle Not found` | Every project delete | B38 |
| `SecureObjectProcessing ... type [PROJECT_PREFERENCES] parent not found` | Every `createCase` | B39 |
| `DirectoryDeleteProcessingInstance: Invalid event JOB_STATUS_UPDATE` | Every large-project delete | B40 |
| `AurariaMgmtService: Could Not execute StorageQuotaCheck` | Daily at ~01:59 ET | B41 |
| `CaeJvmInstance: Invalid state — negative numJobsCurrent` | Large-job completion | B42 |
| `CaeNodeInstance: Invalid state — negative` | Large-job completion | B43 |
| `ChainOfCustodyFactory: cp command exit code is (1)` | Every large-project delete | B44 |
