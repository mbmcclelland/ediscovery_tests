# v0.05 Endpoint Reference — Read Paths

Endpoints needed for the **read-only v0.05 restructure** (System Settings tab,
Organizations tab, org drill-down). Captured from
`/tmp/dr_api_capture.json` (2026-05-11) unless noted.

Write paths (create / edit / delete / reset-password) are **deferred to v0.06**
— see "Deferred" at the bottom.

---

## Conventions

- **Base URL:** `https://192.168.58.128:8443/ediscovery/rest/<endpoint>`
- **Method:** all are `POST`, even reads. Bodies are JSON.
- **Auth header:** raw `sessionToken` (not `Bearer`, not `Basic`). Rolling
  tokens — every response returns a fresh `sessionToken` to use next.
- **`contextHandle`** — `"super_system_customer"` for DRSysAdmin realm-wide
  calls, `<orgName>` for org-scoped calls.
- **`systemScope`** — `true` for realm-wide calls, `false` (or omitted) for
  org-scoped calls.
- **`requestHandle`** — `null` from a fresh client.

---

## System Settings tab — DRSysAdmin only

### F1, F2 — Document & Index Storage Depots

One endpoint covers both. Filter by `storageUseType`.

| Op | Endpoint | Body | Notes |
|---|---|---|---|
| List | `realmManager/listRemoteNFSStorageAreas` | `{contextHandle: "super_system_customer"}` | Returns all NFS storage areas |

**Response → `storageAreas: [...]`**, each entry has:

```
handle, name,
storageAreaType: "DOC_STORAGE",
storageUseType:  "DOCUMENT_STORE" | "INDEX_STORE",
facilityType:    "NFS_NAS",
fqdn, export, readOnly,
inService, inUse, usePriorityOrder,
deactivationThreshold, reactivationThreshold,
kbAvailable, kbUsed, allocationSize
```

**TUI filter:**

- Doc Storage panel: `storageUseType == "DOCUMENT_STORE"`
- Index Storage panel: `storageUseType == "INDEX_STORE"`

### F3 — System Storage Depot

| Op | Endpoint | Body | Notes |
|---|---|---|---|
| Get current | `realmManager/getSystemStorageDepot` | `{contextHandle: "super_system_customer", systemScope: true}` | Realm has exactly one system depot |

**Response → `systemStorageDepotDto`:**

```
depotId, depotName, description, directoryPath, attributes: [...]
```

### F4 — Virus Definitions

| Op | Endpoint | Body | Notes |
|---|---|---|---|
| Status | `realmManager/getVirusDefinitions` | `{contextHandle: "super_system_customer", systemScope: true}` | Read current config + last update |
| Trigger update | `realmManager/updateVirusDefinitions` | `{contextHandle, enabled, frequency: "DAILY", updateDefinitionFiles: true, systemScope: true}` | **v0.06 only** — returns `workbasketHandle` to poll |

**Response → flat top-level fields:**

```
enabled: bool, frequency: "DAILY"|"WEEKLY"|...,
runHour: int, running: bool,
updateStatus: str, updatedOn: epoch_ms, version: str
```

### F5 — System Users

| Op | Endpoint | Body | Notes |
|---|---|---|---|
| List | `adminOrgManager/listUsersAndGroups` | `{contextHandle: "super_system_customer", organizationName: "super_system_customer", onlyUsers: false, onlyGroups: false, systemScope: true}` | Returns both users & groups; filter `users[]` for this panel |

**Response → `users: [...]`**, each entry:

```
handle: "<username>@super_system_customer",
displayName, firstName, lastName,
email, distinguishedName,
enabled, locked, mfa, local,
authenticationMethod, customerName, organizationHandle,
domainHandle, lastAccess, daysUntilPasswordExpires,
roleHandles: [...], roles: [{handle, name, ...}],
allowedIPAddressRange: [...]
```

### F6 — System Groups

Same endpoint as F5; read the `groups: [...]` array instead of `users: [...]`.

**Response → `groups: [...]`** (empty on the 2026-05-11 capture — confirm shape
when groups exist).

---

## Organizations tab — both roles

### Org-1 — Organizations list

| Op | Endpoint | Body | Required role |
|---|---|---|---|
| List (realm-wide) | `realmManager/listOrganizations` | `{contextHandle: "super_system_customer", count: 0, startIndex: 0, filters: [], systemScope: true}` | DRSysAdmin |

**Response → `organizations: [...]`**, each entry:

```
handle, name, description,
deletePending, processing,
attributes: [{name, value}, ...]   # incl. defaultRole, enhancedParticipantProcessing
roles: [...],
storageUsages: [...],
totalStorageUsage: int
```

For **admin@training** (org users), `realmManager/listOrganizations` is not
authorised. Use the implied "your org" from `OrgUserConfig.organization`.

### Org-2 — Org Users / Admins / Groups (drill-down)

| Op | Endpoint | Body | Required role |
|---|---|---|---|
| List users | `orgManager/listUsers` | `{contextHandle: "<org>", organizationName: "<org>", startIndex: 0, count: 100}` | Org admin (or DRSysAdmin via init) |
| List users + groups | `orgManager/listUsersAndGroups` | `{contextHandle: "<org>", organizationName: "<org>"}` | Org admin |
| List roles | `orgManager/listRoles` | `{contextHandle: "<org>", objectType: "ALL", systemScope: false}` | Org admin |

**Response → `users: [...]` and `groups: [...]`** with the same per-user shape
as F5 above, plus per-user `admin: bool` flag (`true` ⇒ "Organization Administrator"
role assigned via `roleHandles`).

**TUI split:**

- "Users" tab: `users[]` where `admin == false`
- "Admins" tab: `users[]` where `admin == true` *or* role name = "Organization Administrator"
- "Groups" tab: `groups[]`

**DRSysAdmin caveat:** Must call `realmManager/initializeOrganization`
(`{organizationName: "<org>"}`, `check=False`) before any `orgManager/*` call
when impersonating org context. Already handled by `dr_tui/data.py:ensure_org_context`.

### Org-3 — Projects (drill-down)

Already covered in v0.04 — re-stated here for completeness.

| Op | Endpoint | Body | Role |
|---|---|---|---|
| All orgs (sys) | `realmManager/listSystemUserProjectsByUserName` | `{contextHandle: "super_system_customer", userName: "drsysadmin", systemScope: true}` | DRSysAdmin (note **lowercase** username) |
| All orgs (org) | `orgManager/listUserProjectsForAllOrgs` | `{contextHandle: "<org>"}` | Org admin |

**Response → `userOrgProjects: [{organizationName, projects: [...], role}, ...]`**

Per-org projects array has `{name, handle, ...}`. Filter by
`organizationName == <selected-org>` for the drill-down panel.

### Org-4 — Running & Completed Jobs (drill-down)

| Op | Endpoint | Body | Role |
|---|---|---|---|
| Tasks per project | `projectManager/listTasks` | `{contextHandle: "<projectHandle>", projectHandle: "<ph>", selectedAttributes: ["includesavedsearches"]}` | both |

**Split:**

- Running: tasks with no `dateCompleted` field
- Completed: tasks with `dateCompleted` set

Status info is nested under `currentStatus[].data[]` arrays keyed by section
name (`"Execution Summary"`, `"General Information"`).

### Org-5 — Connectors (relocated)

| Op | Endpoint | Body | Role |
|---|---|---|---|
| List | `adminOrgManager/listConnectors` | `{contextHandle: "<org>", organizationName: "<org>"}` | Org admin (or DRSysAdmin via init) |

**Response → `connectors: [...]`** with:

```
handle, name, type, mode,
networkId, remoteHost, remotePath, offset,
readOnly, status, mountedConnectorMode
```

### Org-6 — Org-scoped Storage Depot details (drill-down)

Two complementary sources:

1. **From the org row in `realmManager/listOrganizations`:**

   ```
   storageUsages: [{...per-depot usage entries...}],
   totalStorageUsage: int
   ```

2. **From `realmManager/listRemoteNFSStorageAreas`** (re-used from F1/F2),
   cross-reference by handle / facility.

If we need richer per-org allocation (e.g. the auto-provisioned VSD created
by `realmManager/expressProvision`), `getOrganization` may be required —
**not yet captured**, capture during v0.06 discovery if needed.

---

## Endpoints already used by v0.04 (verify still needed)

These remain in use by `dr_tui/data.py` v0.04 and need no changes for v0.05:

- `realmManager/createSession`         — login (HTTP Basic + `userDeviceID`)
- `realmManager/initializeOrganization`— DRSysAdmin → switch org context
- `userManager/getCurrentUser`         — sanity check post-login
- `realmManager/getRealm`              — banner / version

---

## Deferred to v0.06 (write paths)

These endpoints **must be captured before v0.06 implementation starts**.
Tracked in tasks #9 (`A2b`) and #10 (`A2c`).

| Feature | Endpoint (suspected) | Confirmed? |
|---|---|---|
| Storage depot create  | unknown (storage UI flow → endpoint TBD) | ❌ |
| Storage depot edit    | unknown                                  | ❌ |
| Storage depot delete  | unknown                                  | ❌ |
| System user create    | likely `adminOrgManager/createSystemUser` or `realmManager/createSystemUser` | ❌ |
| System user edit      | unknown                                  | ❌ |
| System user delete    | unknown                                  | ❌ |
| System user reset-pw  | unknown (likely `userManager/resetPassword` admin variant) | ❌ |
| System group create / edit / delete | unknown                    | ❌ |
| Org user edit / delete | likely `orgManager/updateUser` / `orgManager/deleteUser` | ❌ |
| Org group create / edit / delete | likely `orgManager/createGroup` / … | ❌ |
| Connector edit / delete | likely `orgManager/deleteConnector` etc. | ❌ |
| Add system user to org | unknown                                  | ❌ |
| Add system group to org | unknown                                 | ❌ |
| Org modify | unknown — `realmManager/updateOrganization`?    | ❌ |
| Org create (already known) | `realmManager/expressProvision`     | ✅ |
| Org delete (already known) | `realmManager/deleteOrganization`   | ✅ |
| Virus def update (already known) | `realmManager/updateVirusDefinitions` | ✅ |
