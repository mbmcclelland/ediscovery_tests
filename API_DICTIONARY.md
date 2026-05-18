# Digital Reef eDiscovery — API Dictionary

**Version 0.09 · 2026-05-18**

Reference for every REST endpoint the test suite + `dr-load admin` CLI
exercises. Each entry has been validated live against the build at
`192.168.58.128:8443`. Request and response shapes are captured from
real responses, not derived from a swagger file (none is served by
this build — verified 404/500 on every conventional swagger path).

For workflow narrative see `DR_Workflow_Guide.md`. For operator
quickstart see `QA_README.md`.

---

## Table of contents

1. [Connection + auth model](#1-connection--auth-model)
2. [Request envelope](#2-request-envelope)
3. [Error format](#3-error-format)
4. [Endpoint reference](#4-endpoint-reference)
   - [4.1 Authentication](#41-authentication)
   - [4.2 Realm-level (system scope)](#42-realm-level-system-scope)
   - [4.3 Organization scope](#43-organization-scope)
   - [4.4 Project scope](#44-project-scope)
   - [4.5 Import pipeline](#45-import-pipeline)
   - [4.6 Project deletion (two-phase)](#46-project-deletion-two-phase)
   - [4.7 Reports / billing](#47-reports--billing)
5. [Unwrapped / blocked endpoints](#5-unwrapped--blocked-endpoints)
6. [Known server quirks (cheat sheet)](#6-known-server-quirks-cheat-sheet)

---

## 1. Connection + auth model

```
Base URL:        https://<host>:8443/ediscovery/rest
TLS:             self-signed by default; client must accept (or pin a cert)
Content-Type:    application/json
Accept:          application/json
Auth header:     Authorization: <raw sessionToken from createSession>
                 (NOT "Bearer …" — the token is the entire header value)
```

**Session lifecycle:**

1. `POST /realmManager/createSession` with HTTP Basic Auth + a UUID
   `userDeviceID` in the JSON body → server returns a `sessionToken`.
2. Every subsequent request sends `Authorization: <sessionToken>`.
3. The server **rolls** the token: every response may contain a fresh
   `sessionToken` field. The client must capture and use the latest one.
4. No explicit logout endpoint is used; sessions time out server-side.

The `EDiscoveryClient` in `helpers/api_client.py` does all of this
transparently.

---

## 2. Request envelope

Every endpoint takes JSON, and the suite's `EDiscoveryClient.post()`
auto-fills two fields if the caller doesn't override them:

| Field | Default | Meaning |
|---|---|---|
| `contextHandle` | `self.cfg.organization` (system org) | The org or project the operation targets. **Many endpoints fail if this is wrong.** |
| `systemScope` | Auto-derived | `True` iff `contextHandle == self.cfg.organization`; else `False`. |

**Scope rules (most important and most surprising):**

- **System scope** (`systemScope=true, contextHandle=super_system_customer`) — used by realm-level endpoints (`listOrganizations`, `createOrganization`, `getRealmStatus`).
- **Org scope** (`systemScope=false, contextHandle=<org_name>`) — used by `orgManager/*` endpoints once you've called `initializeOrganization` to put the session into that org's context.
- **Project scope** (`systemScope=false, contextHandle=<project_handle>`) — used by `projectManager/*`, `orgManager/createDataArea`, `orgManager/createCorpus`, etc. once `initializeOrganization` has set the project context.

**Critical:** Setting `contextHandle` in the body alone is not always sufficient. **Many endpoints also require the session to have been initialized into that scope via `realmManager/initializeOrganization` first.** Without the session-state side, you get HTTP 500 with no body. See `listCorpora` for the canonical example.

---

## 3. Error format

The server uses two error vocabularies:

**(a) Structured `status=FAILURE` JSON** (preferred):

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

**(b) HTTP 5xx with non-JSON HTML body** (anti-pattern, but common):

When the server hits an internal error before its response handler can
build a JSON envelope (NPE inside a service request, unauthenticated
endpoint call per BUG_LOG B24), it returns an HTML error page. The
client surfaces this as a `requests.exceptions.HTTPError(500, ...)`.
Always check `/home/auraria/AHS/output/192.168.58.128_SERVER.log` for
the stack trace.

**Common `errorCode` values seen on this build:**

| errorCode | Meaning |
|---|---|
| `PERMISSION_DENIED` | The caller lacks permission for this action |
| `CAE_ERROR` | Generic "something inside the server crashed" — see `extendedStatus` for the actual exception |
| `PERMISSION_MAP_INVALID` | Permission row not found for a role handle (often Hibernate composite-key miss — B29) |
| `INTERNAL_ERROR` | Catch-all server failure |
| `NOT_FOUND` | Resource doesn't exist |
| `UNAUTHENTICATED` | No session or expired token |

---

## 4. Endpoint reference

### 4.1 Authentication

#### `realmManager/createSession`

**Purpose:** Log in and get a session token.

**Scope:** None — auth itself.

**Auth:** HTTP Basic (`Authorization: Basic …`) + the JSON body. The
Basic header is the password check; the body's `userDeviceID` is
correlated with the issued token.

**Request:**

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

**Response (success):**

```json
{
  "status": "SUCCESS",
  "sessionToken": "<long opaque base64-ish string ending in ||<uuid4>>",
  "lastAccessTime": 1779116205487,
  "userPolicy": { ... },
  "drWsClientContext": { ... },
  "numberResults": 0
}
```

The trailing `||<uuid4>` of the token must match `userDeviceID` for
subsequent calls to be accepted.

**Quirks:**

- Calling unauthenticated endpoints with no token NPEs server-side instead of returning 401 (BUG_LOG B24). Always log in first.
- LDAP-domain users append `@<domain>` to `username` if `ldapDomainName` is set.

---

### 4.2 Realm-level (system scope)

These endpoints operate on the realm — they're called as DRSysAdmin in
the `super_system_customer` org with `systemScope: true`.

#### `realmManager/listOrganizations`

**Purpose:** Enumerate all orgs in the realm.

**Scope:** System.

**Request:**

```json
{ "contextHandle": "super_system_customer", "systemScope": true }
```

**Response:**

```json
{
  "status": "SUCCESS",
  "totalCount": 5,
  "organizations": [
    {
      "handle": "139",
      "name": "training",
      "attributes": { "defaultRole": "...", ... },
      "createdOn": 1779000000000,
      "deletePending": false,
      "processing": { ... },
      "roles": [ ... ],
      "storageUsages": [ ... ],
      "totalStorageUsage": 0
    },
    ...
  ]
}
```

**Quirks:**

- Org handles are numeric strings (e.g. `"139"`), not 40-char hex — BUG_LOG B20.

---

#### `realmManager/createOrganization`

**Purpose:** Create a new organization. Used by `dr-load admin create-org`.

**Scope:** System.

**Request:**

```json
{
  "contextHandle":   "super_system_customer",
  "systemScope":     true,
  "name":            "qa-bootstrap-001",
  "description":     "Phase-1 verification org",
  "organizationName": "qa-bootstrap-001"
}
```

**Response:**

```json
{
  "status": "SUCCESS",
  "organization": {
    "handle": "1576",
    "name":   "qa-bootstrap-001",
    "attributes": { ... },
    ...
  }
}
```

**Side effects:** Server creates 4 default roles in the new org
(Organization Administrator, Project Administrator, Project Member,
Claimant) plus LDAP entries (`ou=users,o=<name>`, `ou=groups,…`). Role
handles are minted at this point and are **per-org-per-install**.

**Quirks:**

- DRSysAdmin is NOT auto-added to the new org as Org Admin. To use the new org's `createCustomerUser` / etc., DRSysAdmin must first be added through a non-REST path (browser Express Provisioning or DB direct). BUG_LOG B36.
- No corresponding REST `deleteOrganization` endpoint exists on this build — verified 500 on `realmManager/deleteOrganization`, `removeOrganization`, `destroyOrganization`, `adminOrgManager/deleteOrganization`.

---

#### `realmManager/initializeOrganization`

**Purpose:** Switch the **session's** active org/project context. Required before most org- or project-scoped calls; the server checks session state, not just `contextHandle` in the request body.

**Scope:** Implicit (operates on the session).

**Request (switching to an org):**

```json
{
  "requestHandle":    null,
  "contextHandle":    "training",
  "organizationName": "training"
}
```

**Request (switching to a project):**

```json
{
  "requestHandle":    null,
  "contextHandle":    "1580",
  "organizationName": "training",
  "systemScope":      false
}
```

**Response:** A `status=SUCCESS` envelope plus organization/project metadata. The server's session state is now scoped to the target.

---

#### `realmManager/getRealmStatus`

**Purpose:** Cheap "is the realm up" health check used by `dr-load preflight`.

**Scope:** System.

**Request:** `{ "contextHandle": "super_system_customer", "systemScope": true }`

**Response:**

```json
{ "status": "SUCCESS", "realmStatus": "AVAILABLE" }
```

---

#### `realmManager/getStorageUsageDownloadUrl` / `getMigrationQuotaReportUrl`

**Purpose:** Generate a one-time download URL for a CSV storage/migration report.

**Scope:** System.

**Response:**

```json
{
  "status": "SUCCESS",
  "url":    "https://192.168.58.128:8443/ediscovery/rest/reports/storage_usage_<uuid>.csv"
}
```

The URL is signed and short-lived; GET it directly without re-auth.

---

#### `realmManager/getOCRUsageStatisticsUrl`

**Purpose:** Generate a download URL for the OCR usage report (used by
the Edge-recorded workflow in `tests/test_ocr_report.py`).

**Request:**

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

**Response:** `{ "status": "SUCCESS", "url": "..." }`

---

### 4.3 Organization scope

Called after `initializeOrganization(<org_name>)`. Body usually has
`contextHandle: "<org_name>", systemScope: false`.

#### `orgManager/listConnectors`

**Purpose:** Enumerate connectors visible in `org`. Used by `dr-load admin list-connectors`.

**Scope:** Org. **Must `initializeOrganization` first.**

**Request:** `{ "contextHandle": "training" }`

**Response:**

```json
{
  "status": "SUCCESS",
  "totalCount": 2,
  "connectors": [
    {
      "handle":      "000084ba6f8e4a2488d74ef2af4e893b8ea2ac99",
      "name":        "training-import-nfs-local",
      "type":        "NFS",
      "mode":        "READ_WRITE",
      "status":      "ACTIVE",
      "readOnly":    false,
      "networkId":   "...",
      "offset":      0,
      "attributes":  { ... }
    },
    ...
  ]
}
```

**Quirks:**

- Connector handles are 40-character hex strings (unlike org/project handles which are numeric).
- Before v0.06 DRSysAdmin saw 0 connectors here; after adding DRSysAdmin as Org Admin to the target org, it sees them. (BUG_LOG B14.)

---

#### `orgManager/listConnectorTypes`

**Purpose:** List the connector types the install supports (NFS, CIFS, etc.).

**Scope:** Org or system.

**Response:** `{ "status": "SUCCESS", "connectorTypes": ["NFS", "CIFS", "SHAREPOINT", "EXCHANGE", "RELATIVITY"] }`

---

#### `orgManager/listProjects`

**Purpose:** Enumerate projects in `org`. Used by `dr-load admin list` and project-name lookups throughout.

**Scope:** Org.

**Request:** `{ "contextHandle": "training" }`

**Response:**

```json
{
  "status": "SUCCESS",
  "totalProjects": 4,
  "services": [],
  "projects": [
    {
      "handle":                  "1580",
      "name":                    "qa-bootstrap-proj-001",
      "description":             "Phase-1 verification project",
      "orgName":                 "training",
      "projectActivationState":  "ACTIVE",
      "projectState":            "AVAILABLE",
      "projectGuid":             "000000009f512d5c0ce4a123",
      "projectServiceName":      "Digital Reef Default",
      "type":                    "dr_eca",
      "userName":                "drsysadmin",
      "dateCreated":             "2026-05-16 12:25:16",
      "lastAccessed":            "",
      "autoCreatedReviewProject": false,
      "reviewSystem":            "None",
      "reviewProjectId":         0,
      "attributes":              { ... }
    },
    ...
  ]
}
```

**Critical fields:**

- `handle` — numeric string (e.g. `"1580"`), not 40-char hex.
- `projectActivationState` — `"ACTIVE"` / `"DELETE_REQUEST_PENDING"` / etc. **This is the real "is the project alive" signal.** `projectState` is sometimes `"UNKNOWN"` even for active projects.

**Quirks:**

- Half-failed `createCase` can leave a project in `mgmtproject` that is **invisible to this listing** (state filter excludes pre-AVAILABLE entries). Recover via `dr-load admin delete-project --handle HANDLE` (BUG_LOG B35).

---

#### `orgManager/listUsers`

**Purpose:** Enumerate users in `org` with their role assignments. The **only role-discovery surface** that works on this build; used by `helpers.admin_ops.find_role_handle` to auto-resolve role handles during `createCase`.

**Scope:** Org.

**Request:** `{ "contextHandle": "training" }`

**Response:**

```json
{
  "status": "SUCCESS",
  "totalUsers": 2,
  "totalGroups": 0,
  "users": [
    {
      "handle":               "admin@training",
      "userName":             "admin",
      "firstName":            "Ad",
      "lastName":             "min",
      "displayName":          "Ad min",
      "distinguishedName":    "Ad min",
      "email":                "admin@localhost.com",
      "authenticationMethod": "PASSWORD",
      "customerName":         "training",
      "organizationHandle":   "139",
      "domainHandle":         "local",
      "admin":                false,
      "enabled":              true,
      "locked":               false,
      "local":                true,
      "mfa":                  false,
      "ediscoveryEula":       true,
      "tlsExpressEula":       false,
      "roleHandles":          ["00003855b4e4ec3264634192b340373841503303"],
      "roles":                [ ... full role objects ... ],
      "systemRoles":          [ ... ],
      ...
    },
    ...
  ],
  "groups": []
}
```

**Critical:** `name` field is **always `None`** on this build. Use `userName` instead. (Caught the hard way during v0.06 development.)

---

#### `orgManager/listGroups`

**Purpose:** Enumerate groups in `org`.

**Response:** `{ "status": "SUCCESS", "totalCount": 0, "groups": [] }`

(Most installs have no groups; users get roles directly.)

---

#### `orgManager/listCorpora`

**Purpose:** Enumerate corpora (data sets that have been indexed) in `org`.

**Scope:** Org. **Must `initializeOrganization` first** — otherwise the server NPEs and returns HTTP 500 with no body (BUG_LOG B31).

**Request:** `{ "contextHandle": "training" }`

**Response:**

```json
{
  "status": "SUCCESS",
  "totalCount": 7,
  "corpora": [
    {
      "handle":              "1580:00004c79d6fdba6e399e4dbdb7882d94b45e15a8",
      "description":         "",
      "documentCount":       2,
      "corpusVersion":       1,
      "corpusViewHandle":    "...",
      "dataAreaSet":         { ... },
      "archived":            false,
      "busy":                false,
      "deletePending":       false,
      "attributes":          { ... }
    },
    ...
  ]
}
```

**Critical:** Corpus handles use composite format `<project_handle>:<corpus_handle>`. Don't parse them — treat as opaque strings.

---

#### `orgManager/listDataAreas` / `listExportDataAreas` / `listExportDatabaseConnections`

**Purpose:** Enumerate data-area resources in `org`.

**Scope:** Org (`listExportDatabaseConnections` requires org init, not system — BUG_LOG B32).

**Response:** `{ "status": "SUCCESS", "dataAreas": [ ... ] }` (or `connections: []`).

---

#### `orgManager/listTemplates`

**Purpose:** Enumerate the org's project templates. Used by `helpers.api_client.EDiscoveryClient.discover_template_attributes` to build the 18-element attribute list for `createCase`.

**Scope:** Org.

**Request:** `{ "contextHandle": "training" }`

**Response:**

```json
{
  "status": "SUCCESS",
  "totalCount": 17,
  "templates": [
    {
      "handle":          "176",
      "name":            "Default Index Settings",
      "templateType":    "INDEX_SETTINGS",
      "description":     "",
      "defaultTemplate": true,
      "orgId":           139,
      "createdBy":       "system",
      "attributes":      { ... }
    },
    ...
  ]
}
```

**Critical:** Template handles are **per-org-per-install** (the same template name in two different orgs has different handles). Always discover at runtime — never hardcode (BUG_LOG B11, B14d).

The 17 templateType values seen on this build:

```
ALIAS_LISTS  ANALYTICAL_SETTINGS  BILLING_REPORT_SETTINGS
CUSTOM_FIELDS  DOCUMENT_METADATA  DOMAIN_LISTS  DUPE_SURVIVORSHIP
EMAIL_SIGNATURE  EXPORT_FIELDS  EXPORT_SETTINGS  INDEX_SETTINGS
LOADFILE_SETTINGS  USER_EXP  REPORT_SETTINGS  SEARCH_FIELDS
SEARCH_SETTINGS  TAG
```

`discover_template_attributes` injects an 18th synthetic `IS_IMPORTED='false'` after `INDEX_SETTINGS` to match the browser-flow payload (BUG_LOG B26).

---

#### `orgManager/listRoles`

**Purpose:** Enumerate roles for a given object type.

**Scope:** Org.

**Request:**

```json
{
  "contextHandle": "training",
  "objectType":    "PROJECT"
}
```

**Response:**

```json
{
  "status": "SUCCESS",
  "roles": [
    {
      "handle":           "00003855b4e4ec3264634192b340373841503303",
      "name":             "Organization Administrator",
      "objectActionList": [ ... ],
      "attributes":       { ... }
    },
    ...
  ]
}
```

**Critical:** **Always pass `objectType`** (one of `PROJECT`, `ORG`, etc.). Omitting it causes the server to NPE on `SecureObjectTypes.equals(null)` and return `errorCode: CAE_ERROR` (BUG_LOG B33).

---

### 4.4 Project scope

Called after `initializeOrganization(<project_handle>)`. Body has
`contextHandle: "<project_handle>", systemScope: false`.

#### `ecaManager/createCase`

**Purpose:** Create a project (case). Used by `dr-load admin create-project`.

**Scope:** Org (the new project's parent org), with `systemScope: false`.

**Request:**

```json
{
  "requestHandle":    null,
  "contextHandle":    "training",
  "systemScope":      false,
  "addToCaseData":    false,
  "custodians":       [],
  "name":             "qa-bootstrap-proj-001",
  "description":      "Phase-1 verification project",
  "attributes":       [
    { "name": "ALIAS_LISTS",          "value": "283" },
    { "name": "ANALYTICAL_SETTINGS",  "value": "204" },
    { "name": "BILLING_REPORT_SETTINGS", "value": "291" },
    { "name": "CUSTOM_FIELDS",        "value": "288" },
    { "name": "DOCUMENT_METADATA",    "value": "233" },
    { "name": "DOMAIN_LISTS",         "value": "227" },
    { "name": "DUPE_SURVIVORSHIP",    "value": "235" },
    { "name": "EMAIL_SIGNATURE",      "value": "231" },
    { "name": "EXPORT_FIELDS",        "value": "199" },
    { "name": "EXPORT_SETTINGS",      "value": "220" },
    { "name": "INDEX_SETTINGS",       "value": "176" },
    { "name": "IS_IMPORTED",          "value": "false" },
    { "name": "LOADFILE_SETTINGS",    "value": "285" },
    { "name": "USER_EXP",             "value": "229" },
    { "name": "REPORT_SETTINGS",      "value": "277" },
    { "name": "SEARCH_FIELDS",        "value": "255" },
    { "name": "SEARCH_SETTINGS",      "value": "237" },
    { "name": "TAG",                  "value": "225" }
  ],
  "membersRequestMessage": {
    "groups": [],
    "users":  [
      { "name": "drsysadmin",
        "roleHandles": ["00003855b4e4ec3264634192b340373841503303"] }
    ]
  },
  "projectLogoBytes": null,
  "logoFileName":     "",
  "reviewSystem":     null,
  "reviewProjectId":  0
}
```

**Response:**

```json
{
  "status":         null,           // not "SUCCESS" — this is by design
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

- Response `status` is `null` on success, not `"SUCCESS"`. `_check_status` only fails on `"FAILURE"`.
- Empty `users` array → HTTP 500 ("Could not set permissions"). At least one user with a role handle is required.
- Even on success, the server log shows `ERROR Could not find role row with:<handle>PROJECT` (BUG_LOG B29) and `NullPointerException: javax.mail.Session.getProperty` from SendEmail (B30). Both are cosmetic — the project still activates.
- Half-failed createCase (e.g., when SendEmail's NPE bubbles) leaves the project hidden from `listProjects` — see B35 for recovery.

---

#### `projectManager/getIndexSettings`

**Purpose:** Read the project's index settings (browser sanity call after switching to a project).

**Request:**

```json
{
  "requestHandle": null,
  "contextHandle": "1580",
  "handle":        "1580",
  "systemScope":   false
}
```

**Response:** `{ "status": "SUCCESS", "settings": { ... } }`

---

#### `projectManager/getUpdateStatus`

**Purpose:** Bulk update-status check (connector / component / storage states). Browser fires this after `initializeOrganization` for a project.

**Request:**

```json
{
  "requestHandle":      null,
  "contextHandle":      "1580",
  "projectHandle":      0,
  "timestamp":          0,
  "updateStatusTypes":  ["CONNECTOR", "COMPONENT", "STORAGE"]
}
```

---

#### `projectManager/listCorpusSets`

**Purpose:** Enumerate corpus sets in the project. Used by the import pipeline to find the default corpusSet to attach a new corpus to.

**Request:**

```json
{
  "requestHandle": null,
  "contextHandle": "1580",
  "projectHandle": "1580",
  "count":         1,
  "startIndex":    0
}
```

**Response:**

```json
{
  "status": "SUCCESS",
  "totalCount": 1,
  "corpusSets": [
    {
      "handle":              "000070920025cd6333384f90a67a61ebf51c3639",
      "name":                "Default",
      "description":         "",
      "deletePending":       false,
      "corpusSetViewHandle": "...",
      "representationSet":   { ... }
    }
  ]
}
```

---

#### `projectManager/listTasks`

**Purpose:** Enumerate indexing / processing tasks in the project. Used by `helpers.admin_ops.wait_for_tasks` to poll for SUCCESS.

**Request:**

```json
{
  "requestHandle": null,
  "contextHandle": "1580",
  "projectHandle": "1580"
}
```

**Response:**

```json
{
  "status": "SUCCESS",
  "totalTasks": 1,
  "tasks": [
    {
      "handle":           "0000958e2e4b16f15d704300bbdb3437030ca932",
      "description":      "Creating representation Analytic Index for testload",
      "task":             "DOCUMENT_ADD_FROM_FILE_LIST",
      "taskType":         "OTHER",
      "taskStatus":       "SUCCESS",
      "operationState":   "SUCCESS",
      "percentComplete":  100,
      "numberResults":    2,
      "secondsElapsed":   11,
      "dateStarted":      "2026-05-16 12:26:10",
      "dateCompleted":    "2026-05-16 12:26:21",
      "owner":            "drsysadmin",
      "warnings":         false,
      "drWsStatus":       { "status": "SUCCESS" },
      "compareExportList": [],
      "attributes":       [ ... ]
    }
  ]
}
```

**Critical:** Active states are `RUNNING`, `QUEUED`, `PENDING`, `PROCESSING`. Terminal states include `SUCCESS`, `FAILED`. The helper polls until no active task remains, then inspects `operationState` / `taskStatus` for success.

---

### 4.5 Import pipeline

Called after `initializeOrganization(<project_handle>)`. The full chain
in order: `createDataArea` → `createCorpus` → `corpusSetManager/addCorpus`
→ `createRepresentation`. Wrapped by `helpers.admin_ops.create_import_job`.

#### `orgManager/createDataArea`

**Purpose:** Create a data-area record that points at a path inside a connector.

**Request:**

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

**Response:**

```json
{
  "status": "SUCCESS",
  "dataArea": {
    "handle": "0000a33071061120dfaf40cb8b24dca5ddd1bcfd",
    ...
  }
}
```

**Critical:**

- `path` is **the path inside the connector's `areapath`** (e.g. `/testload`), not the host filesystem path (`/data/import/testload`). The same dataset has three different path representations in different parts of the codebase — see BUG_LOG B15b.
- `mode: "IMPORT"` for inbound NFS data. `"EXPORT"` exists for outbound.

---

#### `orgManager/createCorpus`

**Purpose:** Create a corpus binding one or more data-area handles into a logical "indexable unit."

**Request:**

```json
{
  "requestHandle":      null,
  "contextHandle":      "1580",
  "systemScope":        false,
  "attributes":         [
    { "name": "projecthandle", "value": "1580" }
  ],
  "brand":              true,
  "dataAreaHandles":    ["0000a33071061120dfaf40cb8b24dca5ddd1bcfd"],
  "description":        "",
  "name":               "testload",
  "loadFileName":       "",
  "loadFileType":       "EDRM_XML",
  "loadFileProfileId":  -1
}
```

**Response:**

```json
{
  "status": "SUCCESS",
  "corpus": {
    "handle": "1580:00004c79d6fdba6e399e4dbdb7882d94b45e15a8",
    ...
  }
}
```

**Critical:** Returned `corpus.handle` uses composite `<project_handle>:<corpus_handle>` format. Pass it as-is downstream.

---

#### `corpusSetManager/addCorpus`

**Purpose:** Link a corpus to a corpus set (typically the project's "Default" set).

**Request:**

```json
{
  "requestHandle":    null,
  "contextHandle":    "1580",
  "systemScope":      false,
  "corpusHandle":     "1580:00004c79d6fdba6e399e4dbdb7882d94b45e15a8",
  "corpusSetHandle":  "000070920025cd6333384f90a67a61ebf51c3639"
}
```

**Response:** `{ "status": "SUCCESS" }`

---

#### `corpusManager/createRepresentation`

**Purpose:** Kick off the async indexing pipeline (CONTENT_INDEX + VECTOR_SET). Returns immediately; poll `projectManager/listTasks` for completion.

**Request:**

```json
{
  "requestHandle":          null,
  "contextHandle":          "1580",
  "systemScope":            false,
  "corpusHandle":           "1580:00004c79d6fdba6e399e4dbdb7882d94b45e15a8",
  "attributes":             [
    { "name": "projecthandle", "value": "1580" }
  ],
  "scanAttributes":         [
    { "name": "batchNumber",   "value": "testload" },
    { "name": "projecthandle", "value": "1580" }
  ],
  "taskDescription":         "Creating representation Analytic Index for testload",
  "typeList":                ["CONTENT_INDEX", "VECTOR_SET"],
  "enablePatternDetection":  true
}
```

**Response:**

```json
{
  "status": null,
  "errorCode": null,
  "numberResults": 0
}
```

**Side effects:** Server creates 4 representation rows automatically (METADATA, CONTENT, VECTOR, TEXT) even though only 2 are requested in `typeList`. DOCPREP service picks up the work asynchronously.

---

### 4.6 Project deletion (two-phase)

Project deletion requires submitting a request and then approving it.
Wrapped by `helpers.admin_ops.delete_project`. The CLI is
`dr-load admin delete-project NAME`.

#### `adminOrgManager/requestProjectDelete`

**Purpose:** Submit a delete request for a project.

**Scope:** Project (the request itself is project-scoped) + `systemScope: true`.

**Request:**

```json
{
  "requestHandle":   null,
  "contextHandle":   "1580",
  "projectHandle":   "1580",
  "systemScope":     true,
  "taskDescription": "Delete Project qa-bootstrap-proj-001"
}
```

**Response:** `{ "status": "SUCCESS" }`

**Quirks:**

- **Non-idempotent.** A second call while one is pending returns HTTP 500 with `extendedStatus: "Deletion of this project has already been requested."` `helpers.admin_ops.delete_project` catches this and continues to the approve phase.

---

#### `adminOrgManager/listDeletePendingProjects`

**Purpose:** List delete requests currently waiting for approval.

**Scope:** System.

**Request:** `{ "requestHandle": null, "systemScope": true, "contextHandle": "super_system_customer" }`

**Response:**

```json
{
  "status": "SUCCESS",
  "totalCount": 2,
  "requests": [
    {
      "handle":                  "4028ba009e319043019e3259d47000c5",
      "objectHandle":            "2210",
      "objectName":              "smoke-5a2a78c4",
      "adminRequestObjectType":  "PROJECT",
      "requestStatus":           "PENDING",
      "requestedBy":             "drsysadmin",
      "description":             "e2e bootstrap smoke test",
      "orgName":                 "training",
      "actionTakenOn":           "1969-12-31 19:00:00"
    },
    ...
  ]
}
```

**Critical:** Top-level key is **`requests`** (not `adminRequests` / `projects` — earlier helper used the wrong keys, BUG_LOG B14b). Each item identifies the project via **`objectHandle`** + **`objectName`** (not `projectHandle` / `projectName`). The request's own handle (used for approval) is `handle`.

---

#### `adminOrgManager/approveProjectDeleteRequest`

**Purpose:** Approve a pending delete request — actually deletes the project.

**Request:**

```json
{
  "requestHandle":   null,
  "contextHandle":   "1580",
  "handle":          "4028ba009e319043019e3259d47000c5",
  "systemScope":     true,
  "taskDescription": "Approving delete for qa-bootstrap-proj-001"
}
```

**Response:** `{ "status": "SUCCESS" }`

**Important:** `handle` here is the **admin-request handle** (from `requests[].handle`), NOT the project handle.

---

### 4.7 Reports / billing

#### `projectManager/listBillingReportSettings`

**Purpose:** Read the project's billing report config.

**Request:** `{ "contextHandle": "<project_handle>" }`

**Response:** `{ "status": "SUCCESS", "reportSettings": [ ... ] }`

#### `projectManager/getEmailReportDeliverySettings`

**Purpose:** Read email-delivery config for project reports.

#### `projectManager/listReportSettings` — **BROKEN**

**Status:** Server bug B34. Returns `errorCode: CAE_ERROR` with `NumberFormatException: Cannot parse null string` regardless of body shape. No request variant recovers. Marked `@pytest.mark.xfail(strict=False)` in `tests/test_billing.py`.

---

## 5. Unwrapped / blocked endpoints

These exist server-side but cannot be reached via the REST surface available to DRSysAdmin.

#### `orgManager/createCustomerUser` — **BLOCKED**

**Status:** Server's `SecureObjectInterceptor` requires the caller to already be a user in the target org. DRSysAdmin isn't a user in a brand-new org, so the call fails with:

```
ERROR User drsysadmin does not have permission to perform createCustomerUser operation
ERROR User not found drsysadmin in org:<new_org>
WARN  Action [CREATE] NOT permitted on object [<new_org>] by user [drsysadmin]
```

The browser's Express Provisioning flow must use a non-REST path (JSP servlet or DB-direct) to get past this. **No body shape recovers** — verified across `contextHandle` variants, `systemScope` variants, with and without `users[]` payload. (BUG_LOG B36.)

**Workaround:** The "create the org admin user" step remains browser-only. Open the web UI as DRSysAdmin → switch to the target org → Express Provisioning.

#### `orgManager/listOrgRoles` / `realmManager/listRoles` / `ecaManager/listRoles` / `permissionManager/setPermissions` / ...

All return HTTP 500 with no body on this build. Most are likely auth-gated similarly. For role discovery, use `orgManager/listUsers` and read each user's `roleHandles` field — that's the only working surface.

---

## 6. Known server quirks (cheat sheet)

| Symptom | Cause | Fix |
|---|---|---|
| HTTP 500, no body, on a project-scoped call | Body has `systemScope: true` from a project-handle `contextHandle` | Set `systemScope: false` (or let `EDiscoveryClient` auto-derive) |
| HTTP 500, no body, on `listCorpora` | Session never called `initializeOrganization(<org>)` | Call `ops.switch_to_org` first |
| `errorCode: CAE_ERROR` `NPE: SecureObjectTypes.equals(null)` | `objectType` missing on `listRoles` | Pass `extra_body={"objectType": "PROJECT"}` |
| `errorCode: PERMISSION_MAP_INVALID` "Could not set permissions" | Hibernate composite-key miss on a role handle | Check the role_handle is valid for the target org via `listUsers` |
| `errorCode: CAE_ERROR` `NPE: mail.Session.getProperty` | SMTP unconfigured; SendEmail subrequest NPEs | Cosmetic — project still activates |
| `caseHandle: null` returned | Request body invalid (e.g., empty `users` array) | Always include at least one user with a role handle |
| `listProjects` doesn't show a project I just created | Half-failed createCase orphaned it pre-AVAILABLE | Find handle in SERVER.log, recover via `delete-project --handle` |
| `requestProjectDelete` HTTP 500 "already requested" | Idempotency violation | `helpers.admin_ops.delete_project` swallows this |
| `Could not find role row with:<handle>PROJECT` in SERVER.log | Hibernate composite-key noise on createCase | Cosmetic; the project still activates |
| Stale `DR_ADMIN_ROLE_HANDLE` in `.env` defeats auto-discovery | `load_dotenv(override=False)` honors shell env, but if shell doesn't set it the stale .env value backfills | CLI no longer reads this env var; only `--role-handle` flag overrides |
| `dr-load admin list-connectors` returns 0 as DRSysAdmin | DRSysAdmin not yet added as Org Admin to that org | One-time browser Express Provisioning step |
| `pip install` fails building gevent | `python3-devel` / `gcc` missing | `sudo dnf install -y python3-devel gcc` (now in prep script) |
| Silent install rolled back, no error message | InstallAnywhere rollback path swallowed the log | Use `scripts/install/dr_install.sh` — exits 2 on rollback |
