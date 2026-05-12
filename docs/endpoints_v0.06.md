# v0.06 Endpoint Reference — Write Paths

Endpoints for the **v0.06 CRUD layer** and shared write paths used by the
v0.07 Organizations CRUD work. Captured 2026-05-11 via two routes:

1. `playwright_fresh_init.py` against a freshly-installed DR — covered the
   **create** path (depot, system depot, virus, expressProvision, org user,
   password change, EULA).
2. Hybrid manual capture — user-driven UI gestures via mitmproxy on `:8090`
   — covered **edit / delete / reset-password** plus bonus settings.

Captures preserved at:

- `/tmp/dr_api_capture_v06_writes.json` (init run 1 — creates)
- `/tmp/dr_api_capture_v06_user.json` (init run 2 — org user + password)
- `/tmp/dr_proxy_capture_v06_edits.json` (hybrid manual — edits/deletes/etc.)
- `/tmp/dr_proxy_capture_v06_sysusers.json` (D5 capture — system-user
  create / update / reset / addSystemUserToOrg)
- `/tmp/dr_proxy_capture_v06_sysgroups.json` (D6 capture — system-group
  create / update / delete + groupManager/setUsers)
- `/tmp/dr_proxy_capture_v07_connectors.json` (v0.07.1 capture —
  connector create / update / delete / deactivate + explore +
  validateNFS / validateExchange)

Conventions follow v0.05. Auth header is the rolling raw `sessionToken`.
All bodies include `requestHandle: null` from a fresh client **except**
where noted (depot-edit reuses `requestHandle` as the entity handle).

---

## ✅ Confirmed — Storage Depots

| Op | Endpoint | Returns |
|---|---|---|
| Create | `realmManager/createRemoteNFSStorageArea` | 200 + `remoteStorageArea` |
| Edit   | `storageAreaManager/updateRemoteNFSStorageArea` | 200 + `remoteStorageArea` |
| Delete | `realmManager/deleteStorageArea` | 204 No Content |

**Create body:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "name": "localDocStorage",
  "fqdn": "192.168.58.128",
  "export": "/data/archive",
  "facilityType": "NFS_NAS",
  "storageAreaType": "DOC_STORAGE",
  "storageUseType": "DOCUMENT_STORE",
  "allocationSize": 0,
  "inUse": true,
  "monitoringNode": null
}
```

For Index depots only `name`, `export`, and `storageUseType: "INDEX_STORE"`
change. Both variants share `storageAreaType: "DOC_STORAGE"` (facility class).

**Edit body** — note `requestHandle` carries the depot's handle:

```json
{
  "requestHandle": "291",
  "contextHandle": "super_system_customer",
  "fqdn": "192.168.58.128",
  "export": "/data/docstorage2",
  "facilityType": "NFS_NAS",
  "storageAreaType": "DOC_STORAGE",
  "storageUseType": "DOCUMENT_STORE",
  "allocationSize": 0
}
```

**Delete body** (returns 204 — `api_client.post()` D1 fix handles this):

```json
{"handle": "274", "contextHandle": "super_system_customer"}
```

**Pre-call validation chain** (UI fires these before create/edit):

1. `orgManager/getNfsMounts({remoteHost, timeoutSeconds: 10})` — populate share dropdown
2. `viewManager/validateName({name, objectType, systemScope})` — uniqueness
3. `connectorManager/validateNFSConnector({fqdn, export, ...})` — host reachability

---

## ✅ Confirmed — System Storage Depot

| Op | Endpoint | Returns |
|---|---|---|
| Assign | `realmManager/createSystemStorageDepot` | 200 + `{numberResults: 0}` |

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "ipAddress": "192.168.58.128",
  "storageFacilityId": "55",
  "mountPoint": "/data/archive",
  "systemScope": true
}
```

`storageFacilityId` is the handle of a `DOCUMENT_STORE` depot. Re-read with
`realmManager/getSystemStorageDepot` (already in v0.05 reads).

---

## ✅ Confirmed — Virus Definitions

| Op | Endpoint | Returns |
|---|---|---|
| Update / re-config | `realmManager/updateVirusDefinitions` | 200 + `{status: "SUCCESS"}` |

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "enabled": true,
  "frequency": "DAILY",
  "updateDefinitionFiles": false,
  "systemScope": true
}
```

`updateDefinitionFiles: true` triggers an immediate sync; `false` only
persists the schedule.

---

## ✅ Confirmed — Organizations

| Op | Endpoint | Returns |
|---|---|---|
| Create | `realmManager/expressProvision` | 200 + org object |
| Edit   | `adminOrgManager/updateOrganization` | 200 |
| Delete | `realmManager/deleteOrganization` | 204 No Content |

**Create:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "organizationName": "training",
  "description": "",
  "userRoleName": {"drsysadmin": "Organization Administrator"},
  "groupRoleName": {},
  "systemScope": true
}
```

`userRoleName` maps `{username: role-name}` of users to auto-add to the
new org with the named role.

**Edit:**

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "name": "training",
  "description": "description goes here",
  "organizationHandle": "72",
  "systemScope": true
}
```

**Delete** (returns 204):

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "handle": "320",
  "taskDescription": "Delete Organization scratchorg",
  "systemScope": true
}
```

Note `taskDescription` — the UI generates a human-readable string for the
async deletion job that surfaces in `realmManager/listDeletePendingProjects`.

---

## ✅ Confirmed — Users (system + org)

| Op | Endpoint | Returns | Notes |
|---|---|---|---|
| Create system user | `adminOrgManager/createUser` | 200 + `user` object | `orgName: "super_system_customer"`, `systemScope: true` |
| Update user (any scope) | `userManager/updateUser` | 200 | uses `userHandle`; firstName/lastName/email/roleHandles mutable |
| Create org user | `orgManager/createUser` | 200 + `user` object | `contextHandle: <org>`, `systemScope: false` |
| Add system user to org | `adminOrgManager/addSystemUserToOrg` | 200 + `users` array | parallel of `addSystemGroupToOrg` |
| Delete user (admin) | `adminOrgManager/deleteUser` | 200 | works for both system + org users by varying `organizationName` |
| Reset password (admin) | `userManager/resetPassword` | 200 | `orgName: "super_system_customer"` for system users |
| Change password (self) | `userManager/changeUserPassword` | 200 |
| Accept EULA | `userManager/acceptEula` | 200 |

**Create system user** (captured 2026-05-12):

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "domainHandle": "local",
  "local": true,
  "roleHandles": ["000027538e76b59c27cf4a51a8316b96aaf52274"],
  "password": "Password123",
  "userName": "newsystemuser",
  "email": "fake@email.com",
  "firstName": "New",
  "lastName": "SystemUser",
  "mfa": false,
  "conditionalOnIPAddress": false,
  "allowedIPAddressRange": null,
  "systemScope": true,
  "orgName": "super_system_customer"
}
```

`contextHandle` in the captured trace was whatever org the admin was
sitting in (`"training"`) — `super_system_customer` works equivalently
and self-contains the call. Response includes the full user object with
`handle: "<userName>@super_system_customer"`.

**Update user** — applies to both system and org users; only the
mutable fields are required:

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "userHandle": "newsystemuser@super_system_customer",
  "email": "fake@email.com",
  "firstName": "Newt",
  "lastName": "SystemUser",
  "roleHandles": ["000027538e76b59c27cf4a51a8316b96aaf52274"],
  "mfa": false,
  "conditionalOnIPAddress": false,
  "allowedIPAddressRange": null,
  "systemScope": true
}
```

**Add system user to org** — parallel of `addSystemGroupToOrg`:

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "systemObjectName": "newsystemuser",
  "orgNameRoleHandles": {
    "training": "00009577d38b5e38e53e47ebbbc73e704536024b"
  },
  "orgName": "super_system_customer"
}
```

Response returns the cross-linked user object with the org's
`organizationHandle` and the role from `orgNameRoleHandles`.

**Create org user** (D2 capture, retained for reference):

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "userName": "admin",
  "email": "admin@localhost.com",
  "firstName": "Admin",
  "lastName": "User",
  "password": "Password123",
  "domainHandle": "local",
  "local": true,
  "mfa": false,
  "conditionalOnIPAddress": false,
  "allowedIPAddressRange": null,
  "roleHandles": ["00009577d38b5e38e53e47ebbbc73e704536024b"],
  "systemScope": false
}
```

`roleHandles` carries the handle of the role (from `orgManager/listRoles`).
"Organization Administrator" role handle is realm-dependent — look up at
runtime.

**Delete** — note `contextHandle` and `organizationName` differ:

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "organizationName": "super_system_customer",
  "userName": "scratchuser",
  "systemScope": true
}
```

The captured pattern: `contextHandle` is the user's org but
`organizationName` is `super_system_customer` (realm scope) with
`systemScope: true`. This is the admin-side delete called from System
Settings; an org-scoped delete from inside the org's User panel may use a
different shape.

**Reset password (admin)** — first two attempts (`orgName: "training"`)
returned HTTP 500; the working call uses `orgName: "super_system_customer"`
+ `systemScope: true`:

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "userName": "scratchuser",
  "newPassword": "Password456",
  "orgName": "super_system_customer",
  "systemScope": true
}
```

**Self-service password change** (existing user knows old pw):

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "oldPassword": "DRSysAdmin",
  "newPassword": "password"
}
```

**EULA:** `{"requestHandle": null, "contextHandle": "...", "ediscoveryEula": true}`

✅ **User edit closed (D5):** `userManager/updateUser` is now captured
(see "Update user" body above). Works for both system and org users —
the `userHandle` field carries the realm-qualified handle.

---

## ✅ Confirmed — Groups

| Op | Endpoint | Returns | Notes |
|---|---|---|---|
| Org group create | `orgManager/createGroup` | 200 | `systemScope: false` |
| System group create | `adminOrgManager/createGroup` | 200 | `systemScope: true`, `organizationName: super_system_customer` |
| Group update (any scope) | `orgManager/updateGroup` | 200 + `group` | toggle `systemScope` to address system vs org group; nested `group` body |
| Group delete (any scope) | `orgManager/deleteGroup` | 200 | toggle `systemScope` to address system vs org group |
| Set group members | `groupManager/setUsers` | 200 | bulk replace; `userHandles: [...]` |
| Add system group to org | `adminOrgManager/addSystemGroupToOrg` | 200 |

**Key finding (D6, 2026-05-12):** there is **no separate
`adminOrgManager/updateGroup` or `adminOrgManager/deleteGroup`** — the
org-scope `orgManager/*` endpoints work for system groups via
`systemScope: true` + `contextHandle: super_system_customer`. The UI
follows this pattern. Confirmed live with a probe `d6final` group
created via `adminOrgManager/createGroup`, edited via
`orgManager/updateGroup`, and deleted via `orgManager/deleteGroup` — all
returning SUCCESS.

**System group update** (captured 2026-05-12):

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "group": {
    "name": "d6probe",
    "description": "d6probe description changed",
    "handle": "0000dc12700b3bb85f9d4aec97ae779fdeeb1ba7",
    "roleHandles": ["000027538e76b59c27cf4a51a8316b96aaf52274"],
    "roles": [{"name": "System Administrator",
               "handle": "000027538e76b59c27cf4a51a8316b96aaf52274"}]
  },
  "systemScope": true
}
```

Body wraps the mutable fields inside a nested `group` object. Both
`roleHandles` and `roles` are sent (the latter is for display; the
server matches on `handle`). Response echoes the resulting group.

**System group delete** (captured 2026-05-12):

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "handle": "0000dc12700b3bb85f9d4aec97ae779fdeeb1ba7",
  "taskDescription": "Deleting Group 0000dc12700b3bb85f9d4aec97ae779fdeeb1ba7",
  "systemScope": true
}
```

`taskDescription` is just a free-form human-readable string for the
realm's pending-jobs queue.

**Set group members** (captured during D6 edit gesture — replaces all
members in one shot):

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "groupHandle": "0000dc12700b3bb85f9d4aec97ae779fdeeb1ba7",
  "userHandles": ["drsysadmin"],
  "systemScope": true
}
```

Returns plain `{status: SUCCESS}`. For org groups, `systemScope: false`
and the user handles should be fully qualified (`username@org`).

**Org group create:**

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "name": "orglevelgroup",
  "description": "description this is an Organization group",
  "roleHandles": ["00009577d38b5e38e53e47ebbbc73e704536024b"],
  "systemScope": false
}
```

**Org group delete:**

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "handle": "0000331148985b343d154d498bd69b22e6279c56",
  "taskDescription": "Deleting Group …",
  "systemScope": false
}
```

**System group create** — same shape as org-group plus `organizationName` +
`systemScope: true`:

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "name": "syslevelgroup",
  "description": "Description This is a system group",
  "roleHandles": ["0000b27328406dfb1a204d648ea5dcba62f8d835"],
  "organizationName": "super_system_customer",
  "systemScope": true
}
```

**Add system group to org** — uses `systemObjectName` + a map of
`{orgName: roleHandle}`:

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "systemObjectName": "syslevelgroup",
  "orgNameRoleHandles": {
    "training": "00009577d38b5e38e53e47ebbbc73e704536024b"
  }
}
```

✅ **Group edit + system-group delete closed (D6):** see the System-group
update + delete blocks above. The org-scope endpoints handle both scopes
via the `systemScope` flag — `adminOrgManager/updateGroup` /
`adminOrgManager/deleteGroup` don't appear to exist as distinct
endpoints.

---

## ✅ Confirmed — Connectors (v0.07.1)

The last v0.07 capture gap, closed 2026-05-12. The full lifecycle for a
connector spans **two** managers — `orgManager` for create + delete and
`connectorManager` for validate / update / browse. There's also a
distinct `deactivate` operation that's softer than delete (marks status
`DEACTIVATED` instead of removing the row).

| Op | Endpoint | Returns | Notes |
|---|---|---|---|
| Create NFS | `orgManager/createNFSConnector` | 200 + `connector` | needs `mountedConnectorMode: "CLASSIC"` |
| Create Exchange | `orgManager/createExchangeConnector` | 200 + `connector` | Azure AD or domain-controller auth |
| Update Exchange | `connectorManager/updateExchangeConnector` | 200 | uses `handle` |
| Validate NFS (pre-save) | `connectorManager/validateNFSConnector` | 200 + `valid: bool` | call before create / edit |
| Validate Exchange (pre-save) | `connectorManager/validateExchangeConnector` | 200 + `valid: bool` | likely returns FAILURE if auth bad |
| Browse NFS path | `connectorManager/exploreConnector` | 200 + `paths[]` | used by data-area picker |
| Get Exchange detail | `connectorManager/getExchangeConnector` | 200 + `connector` | pre-fill for edit modal |
| Delete (true removal) | `orgManager/deleteConnector` | 204 No Content | by `handle` + `taskDescription` |
| Deactivate (soft) | `adminOrgManager/deactivateConnectors` | 204 No Content | by **name** in a `handles` list (bulk-capable) |

**Create NFS:**

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "description": "d9probe description",
  "mountedConnectorMode": "CLASSIC",
  "name": "d9probe",
  "readOnly": true,
  "remoteHost": "192.168.58.128",
  "remotePath": "/data/import"
}
```

`exploreConnector` is what the UI fires when a user expands a path in
the create modal:

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "connectorType": "NFS",
  "connectorName": "d9probe",
  "remoteHost": "192.168.58.128",
  "remotePath": "/data/import",
  "organizationName": "training",
  "parentPath": {"name": "/data/import", "handle": "", "leaf": false, "type": null}
}
```

Response carries `paths: [{handle, name, leaf}, …]`.

**Create Exchange:**

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "description": "d9probe.",
  "name": "MSExchange",
  "username": null,
  "password": "password",
  "contentUrl": null,
  "domainController": null,
  "azureADEnabled": true,
  "tenantDomain": "tennant.domain",
  "applicationId": "appid…",
  "applicationSecret": "appsecret…",
  "refreshToken": null,
  "readOnly": true
}
```

Set `azureADEnabled: false` + populate `domainController` for on-prem
Exchange; or `azureADEnabled: true` + tenant/app/secret for cloud.

**Update Exchange** — mirrors create plus `handle`:

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "handle": "0000d92e…",
  "name": "MSExchange",
  "description": "d9probe.",
  "password": "password",
  "azureADEnabled": true,
  "tenantDomain": "tennant.domain22",
  "applicationId": "appid…",
  "applicationSecret": "appsecret…"
}
```

**Delete** (true removal — returns 204):

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "handle": "00004a0d…",
  "taskDescription": "d9probe"
}
```

**Deactivate** (soft — leaves the row but flips status to
`DEACTIVATED`). Body sends the connector's **name** (not handle) inside
a list — supports bulk deactivation:

```json
{
  "requestHandle": null,
  "contextHandle": "training",
  "handles": ["MSExchange"]
}
```

After deactivate, the same row stays visible in `listConnectors` with
`status: "DEACTIVATED"`. The UI's "Delete" button calls
`deleteConnector` — the deactivate path is only reachable via the
admin-bulk-action menu.

**Pre-call validation pattern** — UI fires before create:

1. `viewManager/validateName({name, objectType: "CONNECTOR", organizationName})`
2. `connectorManager/validate(NFS|Exchange)Connector({…fields, edit: false/true})`
3. `orgManager/create(NFS|Exchange)Connector(…)`

The doc says `updateNFSConnector` exists by symmetry but wasn't
exercised in this capture pass — likely
`connectorManager/updateNFSConnector` with a body mirroring create +
`handle`. Future v0.07.2 capture if needed.

---

## ✅ Confirmed — Realm Settings (bonus)

These weren't on the original ask but were captured in the same session.
Useful for a future "Realm Settings" tab.

| Op | Endpoint | Body keys |
|---|---|---|
| Read inactivity timeout | `realmManager/getInactivityTimeout` | `contextHandle`, `systemScope` |
| Set inactivity timeout | `realmManager/setInactivityTimeout` | `inactivityTimeoutInSeconds`, `contextHandle`, `systemScope` (returns 204) |
| Set password policy | `realmManager/setPasswordPolicy` | `enforceStrongPasswords`, `minimumPasswordLength`, `minimumUppercaseLetters`, `minimumLowercaseLetters`, `minimumNumbers`, `minimumSymbols`, `passwordExpirationInDays`, plus context/scope |
| List system-level roles | `realmManager/listSystemRoles` | `objectType`, `contextHandle`, `systemScope` |
| List admin-org roles | `adminOrgManager/listRoles` | `objectType`, `organizationName`, `contextHandle` |
| List groups in org | `orgManager/listGroups` | `contextHandle` |
| List users in a group | `groupManager/listUsers` | `groupHandle`, `contextHandle`, `systemScope` |
| Search imported (LDAP) groups | `realmManager/listImportedGroupsByGroupName` | `groupName`, `count`, `startIndex`, `filters`, `contextHandle`, `systemScope` |

---

## ❓ Still missing (capture gaps)

(All v0.06/v0.07 gaps closed. NFS update + Exchange domain-controller
auth aren't exercised yet but are documented by symmetry.)

**Closed in D5 (2026-05-12):**

- ✅ `userManager/updateUser` — captured live during the System Users
  Edit gesture (changed `lastName` field; status SUCCESS).
- ✅ `adminOrgManager/addSystemUserToOrg` — the system-user→org cross-link
  endpoint, parallel of `addSystemGroupToOrg`.
- ✅ System-user create — confirmed `adminOrgManager/createUser`
  (distinct from `orgManager/createUser`) with `orgName:
  "super_system_customer"` + `systemScope: true`.
- ✅ System-user delete — `adminOrgManager/deleteUser` works with
  `organizationName: "super_system_customer"` + `systemScope: true`.

**Closed in D6 (2026-05-12):**

- ✅ `orgManager/updateGroup` (with `systemScope: true`) — handles system
  group edit; no separate admin variant exists.
- ✅ `orgManager/deleteGroup` (with `systemScope: true`) — same story
  for delete.
- ✅ `groupManager/setUsers` — bulk-replace group membership; captured
  bonus from the D6 edit gesture.

**Closed in v0.07.1 (2026-05-12):**

- ✅ `orgManager/createNFSConnector` / `createExchangeConnector` —
  connector create paths for the two main flavours.
- ✅ `connectorManager/updateExchangeConnector` — edit path. NFS
  update is presumed to mirror it (`connectorManager/updateNFSConnector`)
  but wasn't exercised in this capture.
- ✅ `orgManager/deleteConnector` (returns 204) — true row removal by
  `handle` + `taskDescription`.
- ✅ `adminOrgManager/deactivateConnectors` (returns 204) — soft delete
  that flips `status` to `DEACTIVATED` instead of removing the row.
  Body takes the connector **name** in a `handles` list (bulk-capable).
- ✅ `connectorManager/validateNFSConnector` /
  `validateExchangeConnector` — pre-create validation hits.
- ✅ `connectorManager/exploreConnector` — path-picker for the create
  modal.
- ✅ `connectorManager/getExchangeConnector` — pre-fill source for the
  edit modal.

Decision for v0.06 ship scope: build CRUD with the confirmed endpoints
above; surface "edit user / group" as v0.06.1 capture-gap stubs. Reset-pw
and delete cover most operational admin needs.

---

## Pre-call helper endpoints (already covered)

The CRUD modals need these read-only helpers. All confirmed in earlier
captures and v0.05 docs:

| Endpoint | Used by |
|---|---|
| `orgManager/getNfsMounts` | depot create — share dropdown |
| `connectorManager/validateNFSConnector` | depot create — pre-validate |
| `viewManager/validateName` | depot/user/group/org create — uniqueness |
| `orgManager/listLdapDomains` | user create — domain selector |
| `realmManager/getMailServerConfig` | user create — email checkbox toggle |
| `realmManager/getPasswordPolicy` | password forms — strength meter |
| `storageAreaManager/countCustomersForFacility` | system-depot pre-assign |
| `realmManager/listCustomersForStorageFacility` | system-depot usage |
| `realmManager/listNodes` | depot create — `monitoringNode` source |
| `realmManager/getDREnumNames` | enum value tables |
| `orgManager/listRoles` | org-scoped role dropdown for user/group create |
| `realmManager/listSystemRoles` | realm-scoped role dropdown |
| `adminOrgManager/listRoles` | admin-side role dropdown |
| `orgManager/listGroups` | group list within an org |
| `realmManager/getInactivityTimeout` | settings panel |

---

## Status conventions

Most writes return `{status: "SUCCESS", numberResults: 0, ...}`. Two
exceptions:

- `createSystemStorageDepot` returns just `{numberResults: 0}` — no `status`
  field. The v0.05 `_check_status` already permits absent `status`.
- `deleteStorageArea` and `deleteOrganization` and `setInactivityTimeout`
  return **204 No Content**. Already handled by the D1 fix in
  `api_client.post()` (returns empty dict instead of trying to parse JSON).
