# v0.08 Endpoint Reference — System Settings (advanced)

Endpoints captured 2026-05-12 via a manual mitmproxy session
(`/tmp/dr_proxy_capture_v08_syssettings.json`, 170 entries). The user
drove the full System Settings panel exercising every sub-tab —
Realm-level configuration that isn't covered by the v0.05–v0.07 docs.

Conventions follow v0.06: all calls are POST to
`/ediscovery/rest/<path>` against `super_system_customer` with the
rolling-session-token Auth header. Bodies always carry
`requestHandle: null` from a fresh client unless they explicitly reuse
it as a handle (e.g. `updateService`).

---

## ✅ Mail Server Configuration

| Op | Endpoint | Returns |
|---|---|---|
| Read current config | `realmManager/getMailServerConfig` | 200 + `mailServerConfig` (or empty) |
| Create / update config | `realmManager/createMailServerConfig` | 200 + `mailServerConfig` |
| Read notification recipients | `realmManager/listEmailIdsToNotify` | 200 + `emailIds: [str]` |
| Set notification recipients | `realmManager/setEmailNotificationCfg` | 200 (500 on empty list — see notes) |

**Create / update mail server:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "smtpHostId": "192.168.58.128",
  "smtpHostPort": "25",
  "systemScope": true
}
```

Response includes the persisted `mailServerConfig` block with `handle`,
`mailSmtpAuth`, host/port. The "create" endpoint is also the
upsert/update path — there's no separate `update` endpoint.

**Set notification recipients:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "emailIds": ["alerts@example.com"],
  "systemScope": true
}
```

⚠️ Submitting an empty list (`emailIds: []`) returned HTTP 500 in our
capture — the UI may be expected to filter the call when the list is
empty rather than submit it.

---

## ✅ Splash Message (login banner)

| Op | Endpoint | Returns |
|---|---|---|
| Read | `realmManager/getSplashMessage` | 200 + `enabled` + `splashMessage` |
| Set | `realmManager/setSplashMessage` | 200 |

**Set body:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "enabled": true,
  "splashMessage": "system message for all users goes here",
  "systemScope": true
}
```

Echoes the persisted state in the response. To clear, pass
`enabled: false` (the message text doesn't need to be wiped).

---

## ✅ Realm Nodes — Adding workers

`listNodes` is already documented in v0.07. The new write path:

| Op | Endpoint | Returns |
|---|---|---|
| Create node | `realmManager/createNode` | 200 + new node |

**Create body:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "name": "realmNode",
  "ipAddress": "192.168.58.128",
  "analyticNodeMode": "STANDARD",
  "tempStorageName": "realmNode_temp",
  "tempStorageExport": "/opt/digitalreef/tmp"
}
```

⚠️ In our capture the call returned HTTP 500 — the same IP already had
a node registered. Likely succeeds when adding a previously-unseen
worker; needs a second capture with a real new IP to verify.

`analyticNodeMode` accepts at least `"STANDARD"`. Other values
(`"OCR_ONLY"` etc.) probably exist — confirmable from
`realmManager/getDREnumNames`.

There's no captured `deleteNode` / `updateNode` yet — capture gap.

---

## ✅ Services (Reef Review / Auto-process / Custom)

DR's "Service" abstraction maps requests to one of several node groups.
Each org's projects are bound to a service.

| Op | Endpoint | Returns |
|---|---|---|
| List services | `realmManager/listServices` | 200 + `services` |
| Create service | `realmManager/createService` | 200 + `service` |
| Update service | `serviceManager/updateService` | 200 + `service` |
| Delete service | `realmManager/deleteService` | 204 No Content |
| List projects bound to a service | `serviceManager/listProjectsForService` | 200 + `projects` |
| Get Reef Review connector (per-service) | `connectorManager/getReefReviewConnector` | 200 |

**Create service:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "serviceName": "NewService",
  "serviceDescription": "NewService Description",
  "serviceExpressNodes": [],
  "serviceOcrNodes": [],
  "serviceRealmNodes": []
}
```

The three `serviceXxxNodes` arrays carry IP-addresses of the nodes
that handle each pipeline class (Express index, OCR, base realm).
Empty arrays mean "use the system default service" for that class.

**Update service** — note `requestHandle` here carries the service's
handle (same pattern as depot-update):

```json
{
  "requestHandle": "1340",
  "contextHandle": "super_system_customer",
  "serviceName": "NewService",
  "serviceDescription": "NewService Description s",
  "serviceExpressNodes": ["192.168.58.128"],
  "serviceOcrNodes": [],
  "serviceRealmNodes": ["192.168.58.128"]
}
```

**Delete service** (returns 204):

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "handle": "1340"
}
```

**List projects for a service** — used by the "is this service in use?"
check before delete:

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "handle": "15",
  "startIndex": 0,
  "count": 0,
  "systemScope": true
}
```

Response carries `projects[]` with `name`, `orgName`, `dateCreated`,
`projectState`, `projectServiceName`, `projectGuid` etc. The default
realm service starts at `handle="15"`.

---

## ✅ Templates (Meta-Template Profiles + bulk operations)

| Op | Endpoint | Returns | Notes |
|---|---|---|---|
| List | `orgManager/listTemplates` | 200 + `templates` | filter by `scope` + `tempType` |
| Create | `orgManager/createTemplate` | 200 + `template` |
| Update | `orgManager/updateTemplate` | 200 + `template` | name immutable in practice; description + defaultFlag mutable |
| Delete | `orgManager/deleteTemplate` | 200 + `templates: []` |
| Get entries | `templateManager/getMetaTemplateProfileEntries` | 200 + `metaTemplateProfileEntries` |
| Copy from another | `templateManager/copyFromTemplate` | 200 |
| Copy to another | `templateManager/copyToTemplate` | 204 |
| Push to orgs | `templateManager/copyMetaTemplateProfileEntriesToOrganizations` | 200 + `taskHandle` |
| Export to file | `templateManager/exportTemplates` | 200 + `fileUrl` |
| Import from file | `templateManager/importTemplates` | 200 (or 500 on bad payload) |

**List filter shape:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "scope": "SYSTEM_LEVEL",
  "tempType": "META_TEMPLATE_PROFILE",
  "systemScope": true
}
```

Other `tempType` values exist (`EXPORT_FIELDS`, `EMAIL_SIGNATURE`, …),
seen in `exportTemplates` calls below.

**Create:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "name": "templateProfile",
  "type": "META_TEMPLATE_PROFILE",
  "description": "templateProfile Description",
  "defaultTemplate": false,
  "scope": "SYSTEM_LEVEL",
  "ownerHandle": "super_system_customer",
  "systemScope": true
}
```

**Update** — adds `handle`, drops `scope` + `ownerHandle`:

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "handle": "1366",
  "name": "templateProfile",
  "type": "META_TEMPLATE_PROFILE",
  "description": "templateProfile Description s",
  "defaultTemplate": false,
  "systemScope": true
}
```

**Delete:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "handle": "1366",
  "taskDescription": "Delete Template templateProfile",
  "systemScope": true
}
```

**Copy from a template into the current one:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "fromHandle": "137",
  "toHandle": "1385",
  "systemScope": true
}
```

`copyToTemplate` has the same shape but returns 204.

**Push template profile entries to orgs** — long-running async op,
returns a task handle:

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "conflictResolutionType": "COPY",
  "metaTemplateProfileEntries": null,
  "organizations": ["training"],
  "ownerHandle": "1366",
  "systemScope": true
}
```

Response: `{"taskHandle": "<hex>"}`. Poll with `taskManager/getTasks`.

`conflictResolutionType` likely accepts `COPY` / `SKIP` / `OVERWRITE` —
needs confirmation.

**Export:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "handles": [],
  "templateType": "EXPORT_FIELDS",
  "allTemplates": true,
  "projectHandle": null
}
```

Response: `{"fileUrl": "/getfile?templatesDownload=...&token=<...>"}` —
fetch with a plain GET to that URL to download the export blob.

**Import** — base64-encoded zip in `templateData`:

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "templateData": [
    {"uploadedTemplateData": "<base64 zip>", "compressed": true}
  ],
  "templateType": "EXPORT_FIELDS",
  "projectHandle": null
}
```

⚠️ Our capture returned HTTP 500 (`IllegalStateException` from the
XML parser) — the export/import round-trip needs a matching template
type and well-formed payload. Test with a real DR export first.

---

## ✅ Email Signatures / Content Blocks

| Op | Endpoint | Returns |
|---|---|---|
| List | `projectManager/listEmailSignatures` | 200 + `emailSignatures` |
| Create | `projectManager/createEmailSignature` | 200 + `emailSignature` |

**List:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "ownerHandle": "1479",
  "systemScope": true,
  "startIndex": 0,
  "count": 100
}
```

`ownerHandle` is the system or org owner (the project handle on
per-project signatures).

**Create:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "name": "newContentBlock",
  "description": "newContentBlock Description",
  "emailSignatureText": "Content Block to be Excluded Goes Here",
  "systemScope": true,
  "ownerHandle": "1479"
}
```

Response carries the full `emailSignature` object: `handle`,
`createdBy`, `createdOn`, name, description, body text. The UI uses
this for both true email signatures and exclusion content blocks — the
`emailSignatureText` field carries either depending on context.

Update / delete weren't exercised in this capture — likely
`updateEmailSignature` and `deleteEmailSignature` by symmetry.

---

## ✅ Project Analytical Settings

| Op | Endpoint | Returns |
|---|---|---|
| Read settings for a project | `projectManager/getAnalyticalSettings` | 200 + `analyticalSettings` |

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "handle": "1385",
  "systemScope": true
}
```

The response is large — every analytical knob (de-dup strategy,
threading mode, attachment inclusion, custodian fields, calendar
handling, near-dup tuning, search query templates) lives here. Key
sub-objects:

- `caseDiscardCandidatesNamedQueries` — pre-populated discard queries
  (Archives / NIST / Directories / Disk Images).
- `emailThreadingModes` — list of mode IDs (`RFC_2822_METADATA`,
  `MS_OTLOOK_METADATA`, `CONTENT_BASED`, …).
- `deDupScope` / `deDupStrategy` — `HORIZONTAL` + `MSG_CONTENT`.
- Boolean toggles for attachment / recipient / sender inclusion.

There's a matching `setAnalyticalSettings` endpoint that wasn't
exercised — probably mirrors the read shape with the same nested
object. v0.08.1 capture gap.

---

## ✅ Inactivity Timeout & Password Policy (additional context)

Already in v0.06 doc; captured request bodies confirmed here.

**Set inactivity timeout** (returns 204):

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "inactivityTimeoutInSeconds": 5940,
  "systemScope": true
}
```

**Set password policy:**

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "enforceStrongPasswords": true,
  "minimumPasswordLength": 6,
  "minimumUppercaseLetters": 0,
  "minimumLowercaseLetters": 0,
  "minimumNumbers": 0,
  "minimumSymbols": 0,
  "passwordExpirationInDays": 90,
  "systemScope": true
}
```

⚠️ Note: in our capture, the **response** echoed `enforceStrongPasswords:
false` even when we requested `true`. The UI may double-call
`getPasswordPolicy` after set to confirm. Or the server lazily applies.

---

## ✅ Permissions Catalogue (UI-side helper)

| Op | Endpoint | Returns |
|---|---|---|
| List secured object types | `permissionManager/getSecureObjectGroups` | 200 + `groupedSecureObjectTypes` |

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "systemScope": true
}
```

Response groups system-level + org-level permission types with
display labels, icons, and the create/view/delete state of each. Used
by the role-editor UI to render the permission tree. Example entries:

```json
{
  "secureObjectType": "PASSWORD_AND_USER_LOGOUT_POLICY",
  "displayValue": "Password & User Logout Policy",
  "iconClass": "fa fa-key",
  "iconColor": "color-purple-03",
  "permissionLevel": "SYSTEM",
  "sequence": 1,
  "systemCreateState": "true",
  "systemViewState": "true",
  "systemDeleteState": "undefined"
},
{
  "secureObjectType": "EMAIL_SERVER_AND_NOTIFICATIONS",
  "displayValue": "Email Server & Notifications",
  "iconClass": "fa fa-envelope", …
}
```

Use this to populate the permissions matrix in any future role-editor
modal.

---

## ✅ Tasks — async job tracker

| Op | Endpoint | Returns |
|---|---|---|
| Poll task status | `taskManager/getTasks` | 200 + `tasks` |

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "taskHandles": ["00008df50bebefec3a0845c286de50e75d760db0"]
}
```

Response: `tasks: [{handle, currentStatus, dateCompleted, ...}]`.
Each task carries `currentStatus[]` with named sections — "General
Information", "Execution Summary" — each containing `data: [{name,
value}]` rows. The same structure as `projectManager/listTasks` used
by dr_tui's Running/Completed Jobs panels.

Used by long-running ops like
`copyMetaTemplateProfileEntriesToOrganizations` to poll completion.

---

## ✅ Realm Users by Org

| Op | Endpoint | Returns |
|---|---|---|
| List orgs a system user belongs to | `realmManager/listSystemUserOrgs` | 200 + `organizationNames` |

```json
{
  "requestHandle": null,
  "contextHandle": "super_system_customer",
  "userName": "drsysadmin",
  "startIndex": 0,
  "count": 0,
  "filters": [],
  "systemScope": true
}
```

Useful for the user-edit modal: shows which orgs a realm-scoped user
currently cross-links into. Pairs with `adminOrgManager/addSystemUserToOrg`
(v0.06 doc) for granting org access.

---

## ❓ Capture gaps remaining

| Feature | Notes |
|---|---|
| `realmManager/updateNode` / `deleteNode` | Not yet exercised. Likely mirrors `createNode` + `deleteService` patterns. |
| `setAnalyticalSettings` | Read endpoint captured; write side wasn't. |
| `updateEmailSignature` / `deleteEmailSignature` | Create captured; edit / delete not exercised. |
| `connectorManager/updateNFSConnector` | Symmetry with `updateExchangeConnector` suggests it exists; not in any capture. |
| `realmManager/createNode` with a fresh IP | Captured call returned 500 because the only IP was already in use. |

---

## Capture inventory

For grep / pivot work, the full endpoint count in
`/tmp/dr_proxy_capture_v08_syssettings.json` (170 entries) was:

```
serviceManager/listProjectsForService               11    polled while watching service
projectManager/getUpdateStatus                       8    background heartbeat
realmManager/listNodes                               5
orgManager/getRole                                   5
orgManager/listTemplates                             4
realmManager/getPasswordPolicy                       4
realmManager/getInactivityTimeout                    4
realmManager/listServices                            4
realmManager/getMailServerConfig                     3
orgManager/getNfsMounts                              3
viewManager/validateName                             3
permissionManager/getCombinedUserRole                2
realmManager/setInactivityTimeout                    2
realmManager/setPasswordPolicy                       2
realmManager/listEmailIdsToNotify                    2
realmManager/getSystemStorageDepot                   2
realmManager/getSplashMessage                        2
realmManager/listSystemRoles                         2
adminOrgManager/listUsersAndGroups                   2
realmManager/initializeOrganization                  2
realmManager/createMailServerConfig                  1
realmManager/setEmailNotificationCfg                 1
realmManager/setSplashMessage                        1
realmManager/createNode                              1
realmManager/createService                           1
serviceManager/updateService                         1
realmManager/deleteService                           1
orgManager/createTemplate                            1
orgManager/updateTemplate                            1
orgManager/deleteTemplate                            1
templateManager/copyFromTemplate                     1
templateManager/copyToTemplate                       1
templateManager/exportTemplates                      1
templateManager/importTemplates                      1
templateManager/getMetaTemplateProfileEntries        1
templateManager/copyMetaTemplateProfileEntriesToOrganizations  1
projectManager/listEmailSignatures                   1
projectManager/createEmailSignature                  1
projectManager/getAnalyticalSettings                 1
permissionManager/getSecureObjectGroups              1
realmManager/listSystemUserOrgs                      1
taskManager/getTasks                                 1
connectorManager/getReefReviewConnector              1
connectorManager/validateNFSConnector                1
realmManager/listRemoteNFSStorageAreas               1
storageAreaManager/countCustomersForFacility         1
realmManager/listCustomersForStorageFacility         1
realmManager/getVirusDefinitions                     1
realmManager/getLicenseInfo                          1
realmManager/listOrganizations                       1
realmManager/listDeletedProjects                     1
realmManager/getRealm                                1
realmManager/getLicensedFeatures                     1
realmManager/listSystemUserProjectsByUserName        1
userManager/getCurrentUser                           1
realmManager/createSession                           1
```
