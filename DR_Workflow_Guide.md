# Digital Reef eDiscovery — Workflow & Database Guide

> **Audience:** Developers and analysts working on automation or load-testing of the Digital Reef
> platform. No prior knowledge of REST APIs or PostgreSQL is assumed.

---

## Table of Contents

1. Background: How the Pieces Fit Together
2. The auraria_mgmt Database — Table Reference
3. The Full Workflow — Step by Step
4. What Our Scripts Do vs. What the Browser Does
5. Fresh-Install / Reinstall Toolchain
6. Endpoint Capture Methodology (proxy + Playwright)
7. The dr-tui Landing Dashboard
8. Distribution / RPM Packaging

---

## 1. Background: How the Pieces Fit Together

### 1.1 What Is a REST API?

When you use the Digital Reef web interface, your browser is not directly reading from or writing
to the database. Instead, it sends **HTTP requests** to a Java application server running on
port 8443. That server does all the database work, then sends back a JSON response.

Think of it like a restaurant:

- **You** (the browser or our Python script) are the customer.
- **The REST API** is the waiter. You hand the waiter a written order — a JSON request body.
- **The Java application server** is the kitchen. It reads the order, does the work, and sends
  back a result.
- **PostgreSQL** is the pantry. The kitchen reads from and writes to it, but you never touch
  it directly.

Each "dish" on the menu is an **endpoint** — a named URL path like `orgManager/createCorpus`
or `ecaManager/createCase`. You call an endpoint by sending an HTTP POST to:

```
https://192.168.58.128:8443/ediscovery/rest/<endpoint>
```

with a JSON body containing the inputs.

### 1.2 What Is PostgreSQL?

PostgreSQL is a **relational database** — rows and columns, like a very powerful spreadsheet.
The Digital Reef database is named **`auraria_mgmt`**. It has 304 tables. Most of what you need
for the create-index-delete workflow lives in about 20 of them.

Every time the Java server does something meaningful (creates a project, starts an indexing job,
records a login), it writes one or more rows to specific tables. Those writes are what we captured
in the PostgreSQL log.

> **For Developers**
>
> Connect to the database read-only:
> ```bash
> sudo -u postgres psql auraria_mgmt
> ```
> Useful meta-commands: `\dt` lists tables, `\d tablename` describes columns.
> Never run `INSERT`, `UPDATE`, or `DELETE` — only the application server should write to the DB.

### 1.3 How Hibernate Talks to PostgreSQL (and Why the Log Looks the Way It Does)

The Java application uses a library called **Hibernate** to talk to PostgreSQL. Hibernate is an
ORM — *Object-Relational Mapper*. Instead of writing SQL by hand, developers define Java objects
(`class MgmtProject { String projectName; int projectId; ... }`), and Hibernate automatically
translates saving or loading those objects into SQL.

Because Hibernate uses PostgreSQL's extended query protocol, every database operation appears
in the log as three separate lines. The analogy holds from above: the kitchen sends the recipe to
the pantry in three steps rather than one:

| Log keyword | What happens |
|---|---|
| `parse` | PostgreSQL compiles the SQL template. Values are placeholders: `$1`, `$2`, ... |
| `bind` | Real values for `$1`, `$2`, etc. are loaded. The `DETAIL: parameters:` line shows the actual data. |
| `execute` | The query runs. The `DETAIL` line appears again, identical to `bind`. |

To read any log entry: use the `parse` line to understand **what SQL is running**, and the
`DETAIL` line to see **what the actual values are**.

The number in brackets — like `[789737]` — is the database **process ID (PID)**. All lines
sharing a PID belong to the same connection, usually the same HTTP request. When two PIDs
appear interleaved, two things are running in parallel (e.g. the main request and a background
polling thread checking job status).

---

## 2. The auraria_mgmt Database — Table Reference

The 304 tables in `auraria_mgmt` fall into six functional areas. This section covers the ones
that matter for the create-index-delete workflow.

---

### Group A — Project Registry

#### `mgmtproject`

The main project record. One row per project.

| Column | Type | Meaning |
|---|---|---|
| `projectid` | bigint | Integer primary key, e.g. `214278`. Auto-assigned. |
| `projectname` | varchar | Human-readable name, e.g. `ExampleTestProject-01`. |
| `projectstate` | varchar | `ACTIVE`, `PENDING_DELETE`, or `DELETED`. |
| `projecttype` | varchar | Always `ADVANCED_ANALYTICS` for our work. |
| `username` | varchar | Who created the project. |
| `customerid` | bigint | The organization (e.g. "training"). |
| `serviceid` | bigint | Which app-server instance owns this project. |
| `storageid` | bigint | Where files are stored. |

> **Note:** `projectid` is an integer (e.g. `214278`), but most other tables reference things
> by a **40-character hex handle** (e.g. `00003ad3092f6a81...`). Projects have both. Most API
> calls use the handle; the DB uses the integer as the primary key.

#### `mgmtproject_attributes`

Key-value settings attached to a project. One row per setting per project.

| Column | Meaning |
|---|---|
| `mgmtproject_projectid` | Links back to `mgmtproject.projectid`. |
| `mapkey` | Setting name, e.g. `INDEX_SETTINGS`, `IS_IMPORTED`. |
| `attributes` | Value — usually a template ID (e.g. `180`) or a flag (`false`). |

Template IDs are references into the `datamining_templates` table. They define what search
settings, export settings, and alias lists the project inherits.

---

### Group B — Data Sources

These tables describe *where documents come from*.

#### `con_connector_cfg`

The list of configured data connectors: NFS shares, Exchange servers, SharePoint sites, etc.
Connectors are set up once by an admin and reused across projects. The NFS connector handle
in `.env` (`DR_NFS_CONNECTOR_HANDLE`) is a row in this table.

#### `con_dataarea_cfg`

A **data area** is a pointer to a specific location within a connector — think of the connector
as a bookshelf and the data area as one shelf.

| Column | Meaning |
|---|---|
| `dataareaguid` | 40-char hex handle. Primary key. |
| `connectorid` | Which connector this area belongs to. |
| `connectormode` | `IMPORT` (pulling files in) or `EXPORT`. |
| `description` | Auto-created ones say `project_data_files for project:...`. |

Every project automatically gets one data area called `project_data_files`, pointing to local
optimized storage. This is created by the server during `createCase` without an explicit API call.
When you call `orgManager/createDataArea`, you create a second data area pointing to the NFS
source (e.g. `/testload`).

#### `con_fsdataarea_cfg`

Extends `con_dataarea_cfg` for filesystem-based connectors. Adds one column: `areapath` — the
actual path on disk (e.g. `/aurariamnt/optimized/local-indexstorage/.../project_data_files/214278`).
Other connector types have their own extension tables: `con_exchangedataarea_cfg`,
`con_sharepointdataarea_cfg`, etc.

---

### Group C — Corpora & Indexing Pipeline

#### `datamining_corpus`

A **corpus** is the collection of documents you want to analyze. One row per corpus.

| Column | Meaning |
|---|---|
| `handle` | 40-char hex. Primary key used in all API calls. |
| `corpus_id` | Sequential short ID, e.g. `0000000013`. |
| `master_project` | Always `0`. Do not use for joins — see developer note below. |
| `organization_handle` | Org name, e.g. `training`. |
| `delete_pending` | Set to `true` when deletion is requested. |

#### `datamining_corpussets`

A **corpus set** is the container that holds a project's corpora. Every project gets one created
automatically. The `project_handle` column stores the project's integer ID as a string, making
this the correct join point between projects and corpora.

#### `datamining_corpussets_datamining_corpus`

Junction table. Links each corpus set to the corpora it contains.

| Column | Meaning |
|---|---|
| `datamining_corpussets_handle` | The corpus set. |
| `corporaset_handle` | The corpus. |

#### `datamining_corpus_representation`

The **indexing pipeline tracker**. Each row is one indexing job for one corpus. The server
creates four rows automatically when you call `createRepresentation`, even if you only request
two types:

| `representation_type` | Handle suffix | What it builds |
|---|---|---|
| 1 | `_METADATA_INDEX` | File metadata index (author, date, size, etc.) |
| 2 | `_CONTENT_INDEX` | Full-text search index |
| 3 | `_VECTOR_SET` | Vector embeddings for similarity/concept search |
| 5 | `_TEXT_SET` | Raw extracted text from each document |

The `representation_state` column tracks progress:

| Value | Meaning |
|---|---|
| `1` | Queued — waiting to run |
| `2` | Active — currently processing |
| `1` (again) | Complete — returned to 1, but `last_update_timestamp` is updated |

> **For Developers**
>
> To check indexing status for a project:
> ```sql
> SELECT dc.corpus_id,
>        dcr.representation_type,
>        dcr.representation_state,   -- 1=queued/done, 2=running
>        dcr.handle
> FROM datamining_corpussets dcs
> JOIN datamining_corpussets_datamining_corpus jt
>        ON jt.datamining_corpussets_handle = dcs.handle
> JOIN datamining_corpus dc
>        ON dc.handle = jt.corporaset_handle
> JOIN datamining_corpus_representation dcr
>        ON dcr.corpus_handle = dc.handle
> WHERE dcs.project_handle = '214278'   -- use the integer project ID as a string
> ORDER BY dc.corpus_id, dcr.representation_type;
> ```

---

### Group D — Import Activity

#### `import_activity_table`

The record of import batches — what the **Imports section of the UI reads**.
One row per corpus, created at the same time as the corpus representations.

| Column | Meaning |
|---|---|
| `batch_handle` | 16-char hex identifier. Primary key. |
| `batch_name` | Human-readable name, e.g. `testload`. Comes from `batchNumber` in `createRepresentation`. |
| `corpus_handle` | Links to `datamining_corpus.handle`. |
| `user_id` | Who created the batch. |
| `number_of_files_scanned` | Starts at `0`; updated in real time as files are processed. |
| `size_of_files_scanned` | Total bytes scanned. Also live-updated. |
| `timestamp` | When the batch was created (Unix epoch in milliseconds). |

> **For Developers**
>
> `datamining_corpus.master_project` is always `0` — it cannot be used to join corpora back to
> projects. The correct path goes through the corpus set:
> ```sql
> SELECT ia.batch_name,
>        ia.number_of_files_scanned,
>        ia.user_id
> FROM datamining_corpussets dcs
> JOIN datamining_corpussets_datamining_corpus jt
>        ON jt.datamining_corpussets_handle = dcs.handle
> JOIN import_activity_table ia
>        ON ia.corpus_handle = jt.corporaset_handle
> WHERE dcs.project_handle = '214278';  -- integer project ID as string
> ```

---

### Group E — Access Control

Three tables work together to answer: *"can this user do this thing?"*

#### `authorization_objects`

A registry of every entity that can be access-controlled: projects, corpora, data areas.

| Column | Meaning |
|---|---|
| `handle` | Same handle as the secured entity. |
| `type` | `CORPUS`, `CORPUS_DATA_AREA`, `PROJECT`, etc. |
| `org_handle` | Which organization owns it. |
| `inherit` | Whether it inherits parent permissions. |

#### `authorization_permissions`

Who is a member of each secured object.

| Column | Meaning |
|---|---|
| `name` | Username (e.g. `drsysadmin`). |
| `obj_handle` | Links to `authorization_objects.handle`. |

#### `authorization_permissions_rolehandles`

What roles each member has. Two role names matter for our work:

| Role name | Grants `createCorpus`? |
|---|---|
| Organization Administrator | Yes ✅ |
| Project Administrator | No ❌ |

> Role *handles* are 40-char hex strings, regenerated whenever the org is recreated
> (e.g. by `playwright_fresh_install.py`). Look them up via `orgManager/listRoles` and
> match by `name`. `locustfile_indexing.py` v0.03 does this in `on_start`.
>
> The root cause of the `PERMISSION_DENIED` bug we debugged: our scripts were assigning
> `Project Administrator` role. Switched to `Organization Administrator` to fix it.

> **For Developers**
>
> To check what roles a user has on a project:
> ```sql
> SELECT ap.name,
>        rh.rolehandles
> FROM authorization_permissions ap
> JOIN authorization_permissions_rolehandles rh
>        ON rh.authorization_permissions_handle = ap.handle
> WHERE ap.obj_handle = '<project_handle>';
> ```

---

### Group F — Background Jobs

#### `ediscovery_workbasket`

Every long-running operation (indexing, export, deletion) creates a row here. The UI polls this
table to show progress bars and status.

| Column | Meaning |
|---|---|
| `workbasket_type` | `IMPORT`, `EXPORT`, `DELETE_PROJECT`, etc. |
| `operation_state` | `RUNNING`, `COMPLETE`, `FAILED`. |
| `percent_complete` | `0` to `100`. |
| `warnings` | `true` if the job finished with non-fatal issues (e.g. unreadable files). |
| `user_id` | Who triggered it. |
| `project_name` | Project name for display purposes. |

---

## 3. The Full Workflow — Step by Step

> **How to read the log**
>
> Every database write appears three times in the PostgreSQL log: `parse` (SQL template compiled),
> `bind` (values loaded — read the `DETAIL: parameters:` line here), `execute` (query runs).
> The `DETAIL` line in `bind` and `execute` are identical; you only need to read one.
>
> Example — creating a project:
> ```
> LOG:  parse: insert into MGMTPROJECT (projectName, projectState, ...) values ($1, $2, ...)
> LOG:  bind
> DETAIL: parameters: $1='ExampleTestProject-01', $2='ACTIVE', ...
> LOG:  execute
> DETAIL: parameters: $1='ExampleTestProject-01', $2='ACTIVE', ...   ← same as bind
> LOG:  duration: 3.131 ms
> ```

---

### Phase 1 — Login

**UI:** Navigate to `https://192.168.58.128:8443/ediscovery/`, enter `DRSysAdmin` / `password`,
click **Log in**.

**API call:** `realmManager/createSession`

**Database write:**

```
INSERT INTO mgmtcustomeruser_session_tokens
  username        = 'drsysadmin'
  organizationname = 'super_system_customer'
  token           = '<pipe-delimited session token>'
```

The server returns a session token that must be included in the `Authorization` header of every
subsequent request. The token is pipe-delimited across six segments — username, organization,
timestamp, and device ID among them. One segment (`seg[4]`) is reserved for a project context
handle, but the REST API never populates it; the browser manages project context client-side.

---

### Phase 2 — Create New Project

**UI (steps 10–28):**

1. Click the options icon on any row in the project list, select **"New Project …"**
2. In the modal, click **"✏ Add / Remove Members …"**, select `admin@training`, click **→**
   then **OK**.
3. Type `ExampleTestProject-01` in the Name field, click **Create Project**.

**API call:** `ecaManager/createCase`

All writes below happen in a single **transaction** — meaning they either all succeed together
or all fail together, so the database is never left in a half-written state.

**Database writes:**

```
INSERT mgmtproject
  projectid = 214278  (auto-assigned by the database)
  projectname = 'ExampleTestProject-01'
  projectstate = 'ACTIVE'
  username = 'drsysadmin'

INSERT con_dataarea_cfg          ← auto-created by the server; no separate API call
  description = 'project_data_files for project:ExampleTestProject-01'
  connectormode = 'IMPORT'

INSERT con_fsdataarea_cfg
  areapath = '/aurariamnt/optimized/local-indexstorage/.../project_data_files/214278'

INSERT authorization_objects     ← registers the data area for access control
  type = 'CORPUS_DATA_AREA'

INSERT mgmtproject_attributes    × 17 rows (one per template attribute)
  (214278, 'ALIAS_LISTS',             '<template_id>')
  (214278, 'ANALYTICAL_SETTINGS',     '<template_id>')
  (214278, 'BILLING_REPORT_SETTINGS', '<template_id>')
  (214278, 'CUSTOM_FIELDS',           '<template_id>')
  (214278, 'DOMAIN_LISTS',            '<template_id>')
  (214278, 'DUPE_SURVIVORSHIP',       '<template_id>')
  (214278, 'EMAIL_SIGNATURE',         '<template_id>')
  (214278, 'EXPORT_FIELDS',           '<template_id>')
  (214278, 'EXPORT_SETTINGS',         '<template_id>')
  (214278, 'INDEX_SETTINGS',          '<template_id>')
  (214278, 'LOADFILE_SETTINGS',       '<template_id>')
  (214278, 'REPORT_SETTINGS',         '<template_id>')
  (214278, 'SEARCH_FIELDS',           '<template_id>')
  (214278, 'SEARCH_SETTINGS',         '<template_id>')
  (214278, 'TAG',                     '<template_id>')
  (214278, 'USER_EXP',                '<template_id>')
  (214278, 'DOCUMENT_METADATA',       '<template_id>')

INSERT authorization_objects     ← registers the project itself for access control
  type = 'CORPUS'
  handle = <project_handle>

INSERT authorization_permissions × 2    ← one row per project member
  (name='drsysadmin', obj_handle=<project_handle>)
  (name='admin',      obj_handle=<project_handle>)

INSERT authorization_permissions_rolehandles × 2
  both assigned role 000052762b86e562... (Organization Administrator)

INSERT datamining_workingsets    ← scratch space for document operations
INSERT datamining_corpussets     ← the container that will hold this project's corpora
  project_handle = '214278'
```

> **Note — template IDs are environment-specific.** Each row's value is a handle into
> `datamining_templates`. Get the current values via `orgManager/listTemplates` (scope
> `ORG_LEVEL`, `defaultTemplate=true`). `locustfile_indexing.py` v0.03+ does this lookup
> in `on_start`; `tests/test_indexing_workflow.py` still reads them from `.env` via
> `DR_TEMPLATE_*`.
>
> **Note — `IS_IMPORTED`.** Older versions of this guide listed an 18th attribute
> `IS_IMPORTED='false'`. The May 11 capture of the real browser flow shows only 17
> template attributes — no `IS_IMPORTED`. If `mgmtproject_attributes` does end up with
> an `IS_IMPORTED` row, the server is writing it server-side, not the client.

---

### Phase 3 — Navigate to Imports

**UI (steps 29–30):** In the left sidebar tree, click the **"⟶ Imports"** node. Then click the
context menu icon that appears and select the first option ("Add from Connector" or equivalent).

**API calls:** Read-only list queries. **No database writes.**

The UI loads the list of existing import batches for this project and displays the connector
browser so the user can select a data source.

---

### Phase 4 — Create Data Set

**UI (steps 31–36):**

1. Click the NFS connector row in the connector grid.
2. Expand the folder tree, click the `/testload` directory.
3. Enter `testload-20260510-001` in the Name field.
4. Click **Create Data Set**.

The Angular component's `ok()` method fires four API calls in sequence.

---

#### 4a — `orgManager/createDataArea` + `orgManager/createCorpus`

Creates the data pointer to `/testload`, then creates the corpus that will hold the documents.
Also links the corpus to the project's corpus set.

```
INSERT con_dataarea_cfg
  connectorid    = <NFS connector handle>
  connectormode  = 'IMPORT'

INSERT con_fsdataarea_cfg
  areapath = '/testload'

INSERT authorization_objects
  type = 'CORPUS_DATA_AREA'

INSERT datamining_corpus
  corpus_id          = '0000000013'
  organization_handle = 'training'
  handle             = '00003ad3...'
  master_project     = 0           ← always 0; not the project integer

INSERT datamining_corpus_data_area    ← links corpus → data area
  corpus_handle    = '00003ad3...'
  data_area_handle = <data area from createDataArea>

INSERT datamining_corpus_attributes
  (corpus_handle, 'projecthandle', '<project_handle>')

INSERT authorization_objects
  type = 'CORPUS'
  handle = '00003ad3...'

INSERT datamining_corpussets_datamining_corpus    ← hooks corpus into project
  datamining_corpussets_handle = '<set_handle>'
  corporaset_handle            = '00003ad3...'
```

---

#### 4b — `corpusManager/createRepresentation`

This is the trigger that starts the indexing pipeline. The API request asks for
`["CONTENT_INDEX", "VECTOR_SET"]`, but the server creates all four representation types.
The `import_activity_table` row is written in the same transaction — this is what makes the
batch appear in the UI's Imports section.

```
INSERT datamining_corpus_representation × 4
  '..._METADATA_INDEX'  type=1  state=1   ← queued
  '..._CONTENT_INDEX'   type=2  state=1   ← queued
  '..._VECTOR_SET'      type=3  state=1   ← queued
  '..._TEXT_SET'        type=5  state=1   ← queued

INSERT import_activity_table              ← Imports section reads this
  batch_name             = 'testload'     ← derived from batchNumber in scanAttributes
  corpus_handle          = '00003ad3...'
  number_of_files_scanned = 0            ← starts at zero; updated as files are processed
  size_of_files_scanned   = 0
  user_id                = 'drsysadmin'
  batch_handle           = 'ee1efca3...' ← short 16-char identifier
```

**After this point the background indexing engine takes over.** It polls
`datamining_corpus_representation` for queued rows (`state=1`) and processes them. As it works:

```
UPDATE datamining_corpus_representation
  SET representation_state = 2   ← now running

UPDATE import_activity_table
  SET number_of_files_scanned = 25
      size_of_files_scanned   = <bytes>
      last_modified           = <timestamp>

UPDATE datamining_corpus_representation
  SET representation_state = 1   ← complete (back to 1; check last_update_timestamp)
```

---

### Phase 5 — Search

**UI (steps 37–47):** Expand a panel, type `quiet period` in the search box, press Enter.

**API call:** Read-only queries against the full-text index files on disk.

**Database writes:** None during the search. A `datamining_saved_searches` row is written only
if the user explicitly saves the query.

---

### Phase 6 — Delete Project

Deletion requires two steps: a **request** and an **approval**. In this recorded workflow both
steps are performed by the same DRSysAdmin account, but in production they are typically done
by two different people.

---

#### 6a — Request Deletion (steps 48–52)

**UI:** Return to project list, right-click the project, select **"Request Project Deletion"**.

**API call:** `orgManager/requestProjectDelete` *(as the org user, with `contextHandle=<org>`)*

```
UPDATE mgmtproject
  SET projectstate = 'PENDING_DELETE'

INSERT ediscovery_workbasket
  workbasket_type  = 'DELETE_PROJECT'
  operation_state  = 'PENDING'
  project_name     = 'ExampleTestProject-01'

INSERT admin_request_table
  ← tracks the pending approval record
```

---

#### 6b — Approve Deletion (steps 53–59)

**UI:** Navigate to System Administration → Pending Deletions, select the project, click
**"Approve Deletion"**.

**API calls:** `realmManager/listDeletePendingProjects` (read-only) then
`adminOrgManager/approveProjectDeleteRequest` — both as **DRSysAdmin** with
`contextHandle=super_system_customer` and `systemScope=true`.

```
DELETE import_activity_table        WHERE corpus_handle = '00003ad3...'
DELETE datamining_corpus_data_area  WHERE corpus_handle = '00003ad3...'

UPDATE datamining_corpus            SET delete_pending = true
UPDATE datamining_corpussets        SET delete_pending = true

DELETE authorization_permissions    WHERE obj_handle = <project_handle>
DELETE authorization_objects        WHERE handle = <project_handle>

UPDATE mgmtproject                  SET projectstate = 'DELETED'
UPDATE ediscovery_workbasket        SET operation_state = 'COMPLETE'
```

Actual file deletion from disk (`/aurariamnt/optimized/...`) happens asynchronously after the
database marks the project deleted.

---

## 4. What Our Scripts Do vs. What the Browser Does

The Angular source code, the Edge recorder, and the May 11 playwright capture
(`/tmp/dr_api_capture.json`, 211 calls) all confirm that `locustfile_indexing.py` v0.03
calls the **same API endpoints in the same order** as the browser. There is no hidden
compound endpoint.

Both the captured browser flow and `locustfile_indexing.py` v0.03 log in as the org user
(`admin@training`) for the project lifecycle and only swap to DRSysAdmin for the final
**approve-delete** step. What matters for permissions is that the org user is added to
`membersRequestMessage` with the `Organization Administrator` role at `createCase` time.

| Step | Browser (May 11 capture) | locustfile_indexing.py v0.03 | Match? |
|---|---|---|---|
| Workflow user | `admin@training` | `admin@training` | ✅ |
| Approve-delete user | `DRSysAdmin` | `DRSysAdmin` | ✅ |
| `realmManager/initializeOrganization` before project ops | ✅ | ✅ | ✅ |
| `ecaManager/createCase` with **17** template attributes | ✅ | ✅ (resolved via `orgManager/listTemplates`) | ✅ |
| Org Admin role in `membersRequestMessage` | ✅ | ✅ (resolved via `orgManager/listRoles`) | ✅ |
| `orgManager/createDataArea` (mode=`IMPORT`) | ✅ | ✅ | ✅ |
| `corpusSetManager/getCorpusSetByName("AllCorpora")` | ✅ | ✅ | ✅ |
| `orgManager/createCorpus` | ✅ | ✅ | ✅ |
| `corpusSetManager/addCorpus` | ✅ | ✅ | ✅ |
| `corpusManager/createRepresentation` with `typeList=["CONTENT_INDEX","VECTOR_SET"]` | ✅ | ✅ | ✅ |
| Poll `taskManager/getTasks([taskHandle])` until `dateCompleted` | ✅ | ✅ | ✅ |
| `orgManager/requestProjectDelete` as org user | ✅ | ✅ | ✅ |
| `realmManager/listDeletePendingProjects` (sys, `systemScope=true`) | ✅ | ✅ | ✅ |
| `adminOrgManager/approveProjectDeleteRequest` (sys) | ✅ | ✅ | ✅ |
| `IMPORT_ACTIVITY_TABLE` row created server-side | ✅ | ✅ | ✅ |
| All 4 representation types written server-side | ✅ | ✅ | ✅ |

### How handles are resolved

`locustfile_indexing.py` looks up environment-specific handles dynamically on each user's
`on_start`, so the test stays drift-proof when `playwright_fresh_install.py` rebuilds the
org:

| Handle | Lookup | Filter |
|---|---|---|
| NFS import connector | `adminOrgManager/listConnectors` | `type=NFS`, `mode=READ` |
| Admin role | `orgManager/listRoles` | `name="Organization Administrator"` |
| Template attribute IDs | `orgManager/listTemplates` | `defaultTemplate=true` |

`tests/test_indexing_workflow.py` (pytest) still reads these from `.env`
(`DR_NFS_CONNECTOR_HANDLE`, `DR_ADMIN_ROLE_HANDLE`, `DR_TEMPLATE_*`); resync them after
each playwright rebuild.

### Smoke test (2026-05-11)

`dr-load indexing -u 1 -d 90s` against 192.168.58.128 — 50 requests, 0 failures, 3
complete project lifecycles, 4 indexing jobs reached `COMPLETE`. See CHANGELOG v0.03.

---

## 5. Fresh-Install / Reinstall Toolchain

Added in v0.06. A three-step chain that tears DR down to bare metal and
brings it back up to a tested baseline — DRSysAdmin/`password`,
`admin@training`/`password`, `localDocStorage` + `localIndexStorage`
created, System Storage Depot assigned, `training` org provisioned.

> ⚠️ **Destructive and unrecoverable.** Step 1 deletes `/home/auraria/AHS*`
> and the contents of `/data/docstorage/` and `/data/indexstorage/`. Only
> run when you intend to start over.

### 5.1 — `cleandr.sh`

```bash
bash cleandr.sh
```

**What it does:**

1. `systemctl stop drd` — graceful stop of the Java application server.
2. Copies the live `/home/auraria/AHS/conf/license.lic` → `/root/license.lic`
   (falls back to a CWD-local `license.lic`, then to an existing
   `/root/license.lic` if both sources are missing).
3. `rm -rfv` on `/home/auraria/AHS*`, `/var/.com.zerog.registry.xml`
   (InstallAnywhere registry), `/tmp/cbe*`, `/tmp/cpuinfo.txt`,
   `/tmp/artemis*`, `/tmp/install.dir.*`, `/data/docstorage/*`,
   `/data/indexstorage/*`.

**Why the license dance:** the InstallAnywhere uninstall doesn't preserve
licensing; without the `/root` copy you'd have to re-request the license
file every reinstall.

### 5.2 — `DR_freshinstall.exp`

```bash
cd /tmp
expect -f /home/auraria/scripts/ediscovery_tests/DR_freshinstall.exp
```

**What it does:**

- `spawn ./5.5.3.2.bin -i console` — runs the InstallAnywhere installer
  in console mode (the binary expects `/tmp` as CWD).
- Accepts the EULA via six `<Enter>` then `y`.
- Picks Full node type (option 1), eDiscovery product (option 1),
  generate-new-SSL=Yes (option 1), hostname-CA=No (option 2), IP
  192.168.58.128 (option 1).
- Waits through the actual install (~3–5 minutes — most of it is the
  bundled JRE extraction).
- After the installer exits, opens a new bash and runs:
  - `cp /root/license.lic /home/auraria/AHS/conf/license.lic`
  - `systemctl restart drd` (so drd picks up the freshly-placed license)

**Why expect is brittle:** the script uses `expect -exact` against
deterministic installer text, which is robust. Earlier autoexpect
captures included bash-prompt expectations with embedded escape
sequences (xterm title + bracketed-paste) that don't replay across
shells. The current hand-cleaned version avoids prompt matching
entirely.

### 5.3 — `playwright_fresh_init.py`

```bash
source .venv/bin/activate
python playwright_fresh_init.py            # headless
python playwright_fresh_init.py --no-headless --slow-mo 200  # watch it run
```

**What it does:**

1. Login as DRSysAdmin (tries `DRSysAdmin` then `password` — handles both
   first-install and re-run scenarios).
2. Forced password change `DRSysAdmin` → `password` (skips silently if
   already `password`).
3. Create `localDocStorage` (Doc, NFS share index 1).
4. Create `localIndexStorage` (Index, NFS share index 4).
5. Assign the doc depot as the System Storage Depot.
6. Create the `training` organization.
7. Open `training` settings, navigate to Organization Users, create
   `admin/training` (display name "Admin User", email
   `admin@localhost.com`, role `Organization Administrator`, password
   `Password123`).
8. Logout, login as `admin@training/Password123`.
9. Forced password change `Password123` → `password`.
10. Logout.

Every phase has a skip-if-exists check, so re-running is idempotent.

**Module reuse:** `playwright_fresh_init.py` imports phases from
`playwright_fresh_install.py`. The latter was refactored in v0.06 so
`argparse.parse_args()` only runs when invoked as `__main__` — phases
are importable.

**Endpoint side-effects:** running this script captures every used
endpoint to `/tmp/dr_api_capture.json` and (via mitmproxy on `:8090`)
`/tmp/dr_proxy_capture.json`. The captures from a recent fresh-install
run are the source material for `docs/endpoints_v0.06.md`.

### 5.4 — Verification

After step 3 the system should be ready for `dr-load`, `dr-tui`, and the
pytest suite without further configuration:

```bash
dr-load preflight                      # 6 checks, all green
dr-tui                                 # log in either role
pytest -m smoke                        # quick health
.venv/bin/python -c "
import requests, uuid
requests.packages.urllib3.disable_warnings()
B = 'https://192.168.58.128:8443/ediscovery/rest'
r = requests.post(f'{B}/realmManager/createSession',
    json={'drWsClientContext':{'username':'admin','organizationName':'training'},
          'contextPath':'/ediscovery','userDeviceID':str(uuid.uuid4())},
    auth=('admin','password'), verify=False)
print('admin@training login:', r.status_code, '✓' if r.json().get('sessionToken') else '✗')
"
```

---

## 6. Endpoint Capture Methodology

Two complementary techniques produce the `docs/endpoints_v0.05.md` and
`docs/endpoints_v0.06.md` references. Both feed the same JSON file format
(see `proxy_logger.py`) so the same parsers work on either.

### 6.1 — Automated capture (Playwright)

`playwright_fresh_init.py` (and the older `playwright_fresh_install.py`)
drive the UI through deterministic sequences while mitmproxy records.
This is best for **create** flows because:

- The UI's pre-validation calls (`viewManager/validateName`,
  `connectorManager/validateNFSConnector`, `orgManager/getNfsMounts`,
  etc.) all fire during the modal interaction — captured for free.
- The actual create endpoint fires once when the user clicks OK —
  unambiguous to identify.
- Same gestures run repeatably, so you can re-run on a fresh env after
  changes.

Limits: **edit / delete** UI gestures vary across the DR codebase
(some panels have a dedicated Edit button, others use right-click → menu,
others use a chevron at the row's right edge). The original MS Edge
recording (`misc/DR_FreshInstall.json`) only covers create, so we don't
have proven selectors for edit/delete gestures. Attempting them with
Playwright tends to open a context menu that blocks subsequent clicks.

### 6.2 — Hybrid manual capture

For edit/delete/reset-password, the proxy stays on `:8090` and a human
drives the UI through the gestures by hand. The capture is just as
useful — same JSON format, full request bodies, response codes — but
takes ~10 minutes of attended browser time per round.

The `userManager/resetPassword` admin variant was discovered this way:
the first two attempts in the capture failed with HTTP 500 (the user
tried different argument shapes) before settling on the working
`orgName: "super_system_customer"` + `systemScope: true` form. The
failed attempts are themselves useful — they tell us which arguments
the server explicitly rejects.

### 6.3 — Parsing captures

A capture file is a list of dicts: `endpoint`, `method`, `request_body`,
`status`, `response_body`. Quick group-by-endpoint:

```python
import json
from collections import defaultdict
calls = json.load(open("/tmp/dr_proxy_capture.json"))
by_ep = defaultdict(list)
for c in calls:
    by_ep[c["endpoint"]].append(c)
for ep in sorted(by_ep):
    print(f"({len(by_ep[ep]):3d}) {ep}")
```

For documentation, pull the first non-empty `request_body` per endpoint
and the response status. That's enough to write the table in
`docs/endpoints_v0.06.md`.

---

## 7. The dr-tui Landing Dashboard (v0.07)

### 7.1 — What it shows

The first tab a DRSysAdmin sees on login. Five panels, each refreshing
independently:

| Panel | Data | Refresh | Source |
|---|---|---|---|
| License | every label / value from `realmManager/getLicenseInfo` | 30 s | REST |
| Realm Node — Status Details | `listNodes` + per-node `getNodeStatus` (components, connectors, storage mounts) — matches Monitoring → Node Status | 30 s | REST |
| System Metrics | CPU %, Memory %, Network rx/tx, Disk read+write IOPS with sparklines + peak + average over a rolling 60-sample window | 2 s | `psutil` (local) |
| Logs | `tail -f /home/auraria/AHS/output/*.log` with INFO / WARN / ERROR filter toggles, rotation-safe | 1 s | local file poll |
| Top processes | top 5 by CPU%, ps-aux style | 3 s | `psutil` (local) |

The local panels (Metrics, Logs, Processes) assume `dr-tui` runs on the
DR host itself — which is the lab setup. Running `dr-tui` from a
separate machine still shows the License + Node panels (REST) but the
local panels then reflect that machine, not DR.

### 7.2 — How the refresh loops are wired

`DashboardScreen.on_mount` registers four independent `set_interval`
timers (gated on `ROLE_SYS`):

```python
self.set_interval(2.0,  self._dash_tick_metrics)
self.set_interval(1.0,  self._dash_tick_logs)
self.set_interval(3.0,  self._dash_tick_procs)
self.set_interval(30.0, self._dash_tick_realm)
```

The realm tick spawns a worker thread (`run_worker(thread=True)`) for
the REST call; the local ticks run on the UI thread because `psutil`
calls + file-stat polls are sub-millisecond. A slow REST round-trip
cannot stall metrics or the log stream because they're on independent
timers.

The realm response gets applied via `call_from_thread(_dash_apply_realm, …)`
so all DOM updates happen on the UI thread.

### 7.3 — Log filter implementation

`LogTailer.poll()` returns a `list[LogLine]` where each line carries a
parsed `level` ("INFO" / "WARN" / "ERROR" / ""). The dashboard's
`_dash_tick_logs` filters by membership in `self._log_filter`, which
the three filter buttons toggle:

```python
def _toggle_log_filter(self, level):
    if level in self._log_filter:
        self._log_filter.discard(level)
    else:
        self._log_filter.add(level)
```

The buttons swap their `variant` (primary / warning / error vs.
"default") so the visual state of each filter stays in sync.

Unparsed lines (no INFO/WARN/ERROR substring — often stack-trace
continuations) are always rendered. This avoids hiding the middle
lines of a multi-line traceback when filters exclude its first line.

---

## 8. Distribution / RPM Packaging (v0.07)

### 8.1 — The `dr-tools` RPM

Build with `cd packaging && make rpm` on a Rocky / RHEL / Fedora host.
Output:

```
packaging/rpmbuild/SRPMS/dr-tools-VERSION-1.el9.src.rpm    (~24 MB)
packaging/rpmbuild/RPMS/x86_64/dr-tools-VERSION-1.el9.x86_64.rpm  (~20 MB)
```

The source RPM bundles a wheelhouse (`dist/wheelhouse/*.whl`) so the
binary RPM is **offline-installable** — no internet needed at install
time. Install with `sudo dnf install ./dr-tools-*.rpm`. The RPM lays
down:

| Path | Owner |
|---|---|
| `/opt/dr-tools/venv` | Self-contained Python 3 venv with every runtime dep |
| `/opt/dr-tools/share/env.example` | Sample `.env` for `cp` + edit |
| `/usr/bin/dr-tui` `/usr/bin/dr-load` | Launcher scripts (`exec /opt/dr-tools/venv/bin/<tool>`) |
| `/usr/share/doc/dr-tools/` | README + CHANGELOG + endpoint docs |
| `/usr/share/licenses/dr-tools/__version__.py` | Version stamp |

The venv is independent of system Python — `dr-tools` co-exists with any
other Python apps on the box. `dnf remove dr-tools` cleanly removes
everything under `/opt/dr-tools` + the two launchers.

### 8.2 — Wheelhouse strategy

`make wheels` runs `pip wheel` against the local checkout, which:

1. Builds the `dr-tools` project itself as a wheel.
2. Fetches + builds every transitive runtime dep (from `install_requires`
   in `setup.cfg`) as a wheel.
3. Dumps everything into `dist/wheelhouse/`.

Dev-only deps (`pytest`, `playwright`, `mitmproxy`) live in
`extras_require[dev]` and are deliberately **not** in the wheelhouse —
they bloat the RPM without serving the runtime, and `mitmproxy >= 10.0`
isn't even installable on Python 3.9 (RHEL 9's default).

To install dev deps locally:

```bash
pip install -e .[dev]
```

### 8.3 — Two spec-file gotchas

When writing the `.spec`:

1. **Don't name a macro `install_root`** — RPM's spec parser pre-scans
   for section directives (`%install`, `%build`, …) and a `%install_root`
   macro reference looks like a duplicate `%install` to the parser. Use
   `%global drroot` or similar instead.
2. **Don't put `%install` (or any `%section` keyword) inside a comment
   in `%build` / `%post` / etc.** — the parser doesn't honor `#`
   comment markers when scanning for section headers. Strip the leading
   `%` from any literal mentions of section names in comments.

### 8.4 — Reproducible builds

The Makefile is idempotent: `make clean && make rpm` from a fresh
checkout always produces an equivalent wheelhouse + RPM. The `_topdir`
is anchored to `packaging/rpmbuild/` so the build doesn't touch
`~/rpmbuild` and multiple builds can coexist on one machine.

For aarch64, generate the wheelhouse on an arm64 host and flip
`BuildArch: aarch64` in the spec — psutil + psycopg2 are the only C
extensions and both have manylinux aarch64 wheels on PyPI.

---

*Last updated: 2026-05-12*
