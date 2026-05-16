# Digital Reef eDiscovery — Workflow & Database Guide

> **Audience:** Developers and analysts working on automation or load-testing of the Digital Reef
> platform. No prior knowledge of REST APIs or PostgreSQL is assumed.

---

## Table of Contents

1. Background: How the Pieces Fit Together
2. The auraria_mgmt Database — Table Reference
3. The Full Workflow — Step by Step
4. What Our Scripts Do vs. What the Browser Does

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

What roles each member has. Two role handles matter for our work:

| Role handle | Name | Grants `createCorpus`? |
|---|---|---|
| `000052762b86e562...` | Organization Administrator | Yes ✅ |
| `00009d44952d7d8a...` | Project Administrator | No ❌ |

> The root cause of the `PERMISSION_DENIED` bug we debugged: our scripts were assigning
> `Project Administrator` role. Switched to `Organization Administrator` in `.env` to fix it.

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

INSERT mgmtproject_attributes    × 18 rows (one per setting)
  (214278, 'ALIAS_LISTS',             '316')
  (214278, 'ANALYTICAL_SETTINGS',     '208')
  (214278, 'BILLING_REPORT_SETTINGS', '324')
  (214278, 'CUSTOM_FIELDS',           '321')
  (214278, 'DOMAIN_LISTS',            '260')
  (214278, 'DUPE_SURVIVORSHIP',       '268')
  (214278, 'EMAIL_SIGNATURE',         '264')
  (214278, 'EXPORT_FIELDS',           '203')
  (214278, 'EXPORT_SETTINGS',         '253')
  (214278, 'INDEX_SETTINGS',          '180')
  (214278, 'IS_IMPORTED',             'false')
  (214278, 'LOADFILE_SETTINGS',       '318')
  (214278, 'REPORT_SETTINGS',         '310')
  (214278, 'SEARCH_FIELDS',           '288')
  (214278, 'SEARCH_SETTINGS',         '270')
  (214278, 'TAG',                     '258')
  (214278, 'USER_EXP',               '262')
  (214278, 'DOCUMENT_METADATA',       '266')

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

> **Note — IS_IMPORTED:** The browser always writes `IS_IMPORTED = 'false'` as the 11th
> attribute above. Our scripts currently skip it. This is the only confirmed difference between
> a browser-created project and an API-created project in `mgmtproject_attributes`.

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

**API call:** `adminOrgManager/requestProjectDelete`

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

**API calls:** `adminOrgManager/listDeletePendingProjects` (read-only) then
`adminOrgManager/approveProjectDeleteRequest`

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

The Angular source code and the Edge recorder confirm that our scripts call the **same API
endpoints in the same order** as the browser. There is no hidden compound endpoint.

The browser logs in as DRSysAdmin only. Our scripts use a dual-login (admin@training creates
the project, DRSysAdmin handles everything else). Both approaches work — they produce the same
database state — because what matters is that both users are listed in `membersRequestMessage`
with `Organization Administrator` role.

| Step | Browser | Our Scripts | Match? |
|---|---|---|---|
| Login | DRSysAdmin only | Dual: admin@training + DRSysAdmin | Different, but both work |
| createCase caller | DRSysAdmin | admin@training | Different, same result |
| Both users in membersRequestMessage with Org Admin role | ✅ | ✅ | ✅ |
| `IS_IMPORTED = 'false'` in project attributes | ✅ | ❌ missing | ⚠️ |
| createDataArea | ✅ | ✅ | ✅ |
| createCorpus | ✅ | ✅ | ✅ |
| listCorpusSets + addCorpus | ✅ | ✅ | ✅ |
| createRepresentation typeList | `['CONTENT_INDEX', 'VECTOR_SET']` | Same | ✅ |
| IMPORT_ACTIVITY_TABLE row created | ✅ | ✅ | ✅ |
| All 4 representation types created | ✅ | ✅ | ✅ |

### The One Fix Needed

Add `IS_IMPORTED` to `TEMPLATE_ATTRIBUTES` in both `locustfile_indexing.py` and
`debug_create_data_area.py`:

```python
TEMPLATE_ATTRIBUTES = [
    {"name": "ALIAS_LISTS",             "value": "316"},
    {"name": "ANALYTICAL_SETTINGS",     "value": "208"},
    {"name": "BILLING_REPORT_SETTINGS", "value": "324"},
    {"name": "CUSTOM_FIELDS",           "value": "321"},
    {"name": "DOMAIN_LISTS",            "value": "260"},
    {"name": "DUPE_SURVIVORSHIP",       "value": "268"},
    {"name": "EMAIL_SIGNATURE",         "value": "264"},
    {"name": "EXPORT_FIELDS",           "value": "203"},
    {"name": "EXPORT_SETTINGS",         "value": "253"},
    {"name": "INDEX_SETTINGS",          "value": "180"},
    {"name": "IS_IMPORTED",             "value": "false"},   # browser always sends this
    {"name": "LOADFILE_SETTINGS",       "value": "318"},
    {"name": "REPORT_SETTINGS",         "value": "310"},
    {"name": "SEARCH_FIELDS",           "value": "288"},
    {"name": "SEARCH_SETTINGS",         "value": "270"},
    {"name": "TAG",                     "value": "258"},
    {"name": "USER_EXP",               "value": "262"},
    {"name": "DOCUMENT_METADATA",       "value": "266"},
]
```

---

*Last updated: 2026-05-10*
