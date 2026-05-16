"""
Debug: full indexing workflow matching the MS Edge Recorder JSON.

JSON flow (FullWorkflow-ProjectCreate-ProjectDelete):
  1. Login as DRSysAdmin (only login — no dual-login)
  2. initializeOrganization → training
  3. ecaManager/createCase  (DRSysAdmin creates project; admin added via membersRequestMessage)
  4. initializeOrganization → project context
  5. orgManager/createDataArea
  6. orgManager/createCorpus
  7. projectManager/listCorpusSets + corpusSetManager/addCorpus
  8. corpusManager/createRepresentation  (kicks off async indexing)
  9. Poll projectManager/listTasks until Active = 0
  10. adminOrgManager/requestProjectDelete
  11. adminOrgManager/listDeletePendingProjects + approveProjectDeleteRequest

Run: python debug_create_data_area.py [--deleteproject] [--datasetname testload-20260510-001]
"""

import os
import argparse
import uuid
import requests
import urllib3
import getpass
import time

from dotenv import load_dotenv


def parse_duration(value):
    """Parse a duration string like '60s', '5m', '2h' into seconds."""
    value = value.strip().lower()
    if value.endswith("h"):
        return int(value[:-1]) * 3600
    elif value.endswith("m"):
        return int(value[:-1]) * 60
    elif value.endswith("s"):
        return int(value[:-1])
    else:
        return int(value)


parser = argparse.ArgumentParser(description="Debug: full indexing workflow matching exact browser flow.")
parser.add_argument("--deleteproject", action="store_true", help="Delete the project after the workflow completes")
parser.add_argument("--retryinterval", type=str, default="60s",
                    help="Duration between retries, e.g. 60s, 5m, 2h (default: 60s)")
parser.add_argument("--retrycount", type=int, default=10,
                    help="Number of retries when waiting for indexing (default: 10)")
parser.add_argument("--nfsimportpath", type=str, default=None,
                    help="NFS import path, e.g. '/testload' (overrides DR_NFS_IMPORT_PATH)")
parser.add_argument("--datasetname", type=str, default=None,
                    help="Dataset / batch name, e.g. 'testload-20260510-001' (overrides DR_NFS_DATASET_NAME)")
args = parser.parse_args()

retry_interval_secs = parse_duration(args.retryinterval)

load_dotenv(override=True)
urllib3.disable_warnings()

BASE     = os.getenv("DR_BASE_URL")
SYS_USER = os.getenv("DR_USERNAME", "DRSysAdmin")
SYS_ORG  = os.getenv("DR_ORGANIZATION", "super_system_customer")
SYS_PASS = os.getenv("DR_PASSWORD") or getpass.getpass(f"Password for {SYS_USER}: ")

# Org where the project lives
TARGET_ORG = os.getenv("DR_ORG_ORGANIZATION", "training")
# User to add as a project member (so they can access the project in the UI)
ORG_USER   = os.getenv("DR_ORG_USERNAME", "admin")

NFS_CONNECTOR   = os.getenv("DR_NFS_CONNECTOR_HANDLE", "")
NFS_PATH        = args.nfsimportpath or os.getenv("DR_NFS_IMPORT_PATH", "/testload")
NFS_DATASET_NAME = args.datasetname or os.getenv("DR_NFS_DATASET_NAME") or os.path.basename(NFS_PATH.rstrip("/"))

# Organization Administrator role — required for createCorpus permission
ADMIN_ROLE = os.getenv(
    "DR_ADMIN_ROLE_HANDLE",
    "000052762b86e562c058435e83221133832cb1d0",  # Org Admin for 192.168.58.128
)

# Template attribute IDs — confirmed from browser capture on 192.168.58.128
TEMPLATE_ATTRIBUTES = [
    {"name": "ALIAS_LISTS",             "value": "18621"},
    {"name": "ANALYTICAL_SETTINGS",     "value": "18542"},
    {"name": "BILLING_REPORT_SETTINGS", "value": "18629"},
    {"name": "CUSTOM_FIELDS",           "value": "18626"},
    {"name": "DOMAIN_LISTS",            "value": "18565"},
    {"name": "EMAIL_SIGNATURE",         "value": "18569"},
    {"name": "EXPORT_FIELDS",           "value": "18537"},
    {"name": "EXPORT_SETTINGS",         "value": "18558"},
    {"name": "INDEX_SETTINGS",          "value": "18514"},
    {"name": "IS_IMPORTED",             "value": "false"},
    {"name": "LOADFILE_SETTINGS",       "value": "18623"},
    {"name": "SEARCH_FIELDS",           "value": "18593"},
    {"name": "DOCUMENT_METADATA",       "value": "18571"},
    {"name": "USER_EXP",                "value": "18567"},
    {"name": "REPORT_SETTINGS",         "value": "18615"},
    {"name": "SEARCH_SETTINGS",         "value": "18575"},
    {"name": "DUPE_SURVIVORSHIP",       "value": "18573"},
    {"name": "TAG",                     "value": "18563"},
]

print(f"Server:      {BASE}")
print(f"Login user:  {SYS_USER}@{SYS_ORG}  (single login — matches browser JSON)")
print(f"Target org:  {TARGET_ORG}")
print(f"Member:      {ORG_USER}  (added to project via membersRequestMessage)")
print(f"Connector:   {NFS_CONNECTOR}")
print(f"NFS path:    {NFS_PATH}")
print(f"Dataset:     {NFS_DATASET_NAME}")

token = None
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def api_post(path, body, label=""):
    global token, headers
    if token:
        headers["Authorization"] = token
    resp = requests.post(
        f"{BASE}/{path}", json=body, headers=headers,
        verify=False, timeout=60,
    )
    print(f"\n--- {label} ---")
    print(f"  POST {path} -> HTTP {resp.status_code}")
    try:
        data = resp.json()
        new_token = data.get("sessionToken")
        if new_token:
            token = new_token
            headers["Authorization"] = token
        status = data.get("status", "(none)")
        error  = data.get("errorCode", "")
        if error:
            print(f"  status={status} error={error}")
            print(f"  ext: {data.get('extendedStatus', '')[:200]}")
        else:
            print(f"  status={status}")
        return data
    except Exception:
        print(f"  Not JSON: {resp.text[:500]}")
        return None


# ===== Step 1: Login as DRSysAdmin =====
print("\n" + "=" * 60)
print(f"STEP 1: Login as {SYS_USER}@{SYS_ORG}")
print("=" * 60)
device_id = str(uuid.uuid4())
resp = requests.post(
    f"{BASE}/realmManager/createSession",
    json={
        "drWsClientContext": {
            "username": SYS_USER,
            "organizationName": SYS_ORG,
        },
        "contextPath": "/ediscovery",
        "userDeviceID": device_id,
    },
    auth=(SYS_USER, SYS_PASS),
    verify=False, timeout=30,
)
login_data = resp.json()
token = login_data.get("sessionToken", "")
if token:
    headers["Authorization"] = token
print(f"  HTTP {resp.status_code}")
if '|' in token:
    parts = token.split("|")
    print(f"  Token: seg[1]={parts[1] if len(parts) > 1 else '?'}, seg[2]={parts[2] if len(parts) > 2 else '?'}")
else:
    print(f"  ERROR: unexpected token format — login may have failed")
    print(f"  Response: {login_data.get('status', '?')} / {login_data.get('errorCode', '')}")
    exit(1)


# ===== Step 2: Initialize Organization → training =====
print("\n" + "=" * 60)
print(f"STEP 2: initializeOrganization → {TARGET_ORG}")
print("=" * 60)
api_post("realmManager/initializeOrganization", {
    "requestHandle": None,
    "contextHandle": TARGET_ORG,
    "organizationName": TARGET_ORG,
}, f"initOrg → {TARGET_ORG}")


# ===== Step 3: Create Project =====
print("\n" + "=" * 60)
print("STEP 3: Create Project")
print("=" * 60)
project_name = f"debug-{uuid.uuid4().hex[:8]}"
case_data = api_post("ecaManager/createCase", {
    "requestHandle": None,
    "contextHandle": TARGET_ORG,
    "addToCaseData": False,
    "custodians": [],
    "name": project_name,
    "description": f"Debug {project_name}",
    "attributes": TEMPLATE_ATTRIBUTES,
    "membersRequestMessage": {
        "groups": [],
        "users": [
            # Browser adds admin via the membership modal; creator (DRSysAdmin) is also explicit
            {"name": ORG_USER.lower(),  "roleHandles": [ADMIN_ROLE]},
            {"name": SYS_USER.lower(), "roleHandles": [ADMIN_ROLE]},
        ],
    },
    "projectLogoBytes": None,
    "logoFileName": "",
    "systemScope": False,
    "reviewSystem": None,
    "reviewProjectId": 0,
}, "createCase")

project_handle = case_data.get("caseHandle") if case_data else None
if project_handle is not None:
    project_handle = str(project_handle)
print(f"  Project: {project_name}, Handle: {project_handle}")
if not project_handle:
    print("  FAILED — exiting")
    exit(1)


# ===== Step 4: Initialize Organization → project context =====
print("\n" + "=" * 60)
print("STEP 4: initializeOrganization → project context")
print("=" * 60)
time.sleep(3)

api_post("realmManager/initializeOrganization", {
    "requestHandle": None,
    "contextHandle": project_handle,
    "organizationName": TARGET_ORG,
    "caseHandle": project_handle,
}, "initOrg → project")

api_post("projectManager/getIndexSettings", {
    "requestHandle": None,
    "contextHandle": project_handle,
    "handle": project_handle,
    "systemScope": False,
}, "getIndexSettings")

api_post("projectManager/getUpdateStatus", {
    "requestHandle": None,
    "contextHandle": project_handle,
    "projectHandle": 0,
    "timestamp": 0,
    "updateStatusTypes": ["CONNECTOR", "COMPONENT", "STORAGE"],
}, "getUpdateStatus")


# ===== Step 5: Create Data Area =====
print("\n" + "=" * 60)
print("STEP 5: Create Data Area")
print("=" * 60)
da_data = api_post("orgManager/createDataArea", {
    "requestHandle": None,
    "contextHandle": project_handle,
    "connectorHandle": NFS_CONNECTOR,
    "description": "",
    "mode": "IMPORT",
    "name": NFS_DATASET_NAME,
    "path": NFS_PATH,
    "skippedDirectories": [],
}, "createDataArea")

da_handle = None
if da_data:
    print(f"  Keys: {list(da_data.keys())}")
    da = da_data.get("dataArea", {})
    da_handle = da.get("handle") if isinstance(da, dict) else da_data.get("handle")
    print(f"  Data area handle: {da_handle}")
if not da_handle:
    print("  FAILED — exiting")
    exit(1)


# ===== Step 6: Create Corpus =====
print("\n" + "=" * 60)
print("STEP 6: Create Corpus")
print("=" * 60)
corpus_data = api_post("orgManager/createCorpus", {
    "requestHandle": None,
    "contextHandle": project_handle,
    "attributes": [{"name": "projecthandle", "value": project_handle}],
    "brand": True,
    "dataAreaHandles": [da_handle],
    "description": "",
    "name": NFS_DATASET_NAME,
    "loadFileName": "",
    "loadFileType": "EDRM_XML",
    "loadFileProfileId": -1,
}, "createCorpus")

corpus_handle = None
if corpus_data:
    print(f"  Keys: {list(corpus_data.keys())}")
    corpus = corpus_data.get("corpus", {})
    corpus_handle = corpus.get("handle") if isinstance(corpus, dict) else None
    if not corpus_handle:
        for k in ("corpusHandle", "handle"):
            v = corpus_data.get(k)
            if v and ":" in str(v):
                corpus_handle = v
                break
    print(f"  Corpus handle: {corpus_handle}")
if not corpus_handle:
    print("  FAILED — exiting")
    exit(1)


# ===== Step 7: List CorpusSets + Add Corpus =====
print("\n" + "=" * 60)
print("STEP 7: Add Corpus to CorpusSet")
print("=" * 60)
cs_data = api_post("projectManager/listCorpusSets", {
    "requestHandle": None,
    "contextHandle": project_handle,
    "projectHandle": project_handle,
    "count": 1,
    "startIndex": 0,
}, "listCorpusSets")

cs_handle = None
if cs_data:
    sets = cs_data.get("corpusSets", [])
    if sets:
        cs_handle = sets[0].get("handle")
        print(f"  CorpusSet handle: {cs_handle}")

if cs_handle:
    api_post("corpusSetManager/addCorpus", {
        "requestHandle": None,
        "contextHandle": project_handle,
        "corpusHandle": corpus_handle,
        "corpusSetHandle": cs_handle,
    }, "addCorpus")


# ===== Step 8: Create Representation (start indexing) =====
print("\n" + "=" * 60)
print("STEP 8: Create Representation (start indexing)")
print("=" * 60)
api_post("corpusManager/createRepresentation", {
    "requestHandle": None,
    "contextHandle": project_handle,
    "attributes": [{"name": "projecthandle", "value": project_handle}],
    "corpusHandle": corpus_handle,
    "scanAttributes": [
        {"name": "batchNumber",   "value": NFS_DATASET_NAME},
        {"name": "projecthandle", "value": project_handle},
    ],
    "taskDescription": f"Creating representation Analytic Index for {NFS_DATASET_NAME}",
    "typeList": ["CONTENT_INDEX", "VECTOR_SET"],
    "enablePatternDetection": True,
}, "createRepresentation")


# ===== Step 9: Wait for indexing to complete =====
print("\n" + "=" * 60)
print("STEP 9: Wait for indexing to complete")
print("=" * 60)
print(f"  Retry interval: {retry_interval_secs}s, Retry count: {args.retrycount}")

for retry in range(args.retrycount):
    task_data = api_post("projectManager/listTasks", {
        "requestHandle": None,
        "contextHandle": project_handle,
        "projectHandle": project_handle,
    }, f"listTasks (retry {retry + 1}/{args.retrycount})")

    if task_data:
        tasks  = task_data.get("tasks", [])
        active = [t for t in tasks if t.get("state") in
                  ("RUNNING", "QUEUED", "PENDING", "PROCESSING")]
        print(f"  Total tasks: {len(tasks)}, Active: {len(active)}")
        if not active:
            print("  Indexing complete!")
            break
        for t in active:
            print(f"    {t.get('name', '?')} -> {t.get('state', '?')} ({t.get('percentComplete', '?')}%)")
    time.sleep(retry_interval_secs)
else:
    print(f"  Exhausted {args.retrycount} retries — proceeding anyway")


# ===== Step 10+11: Request + Approve Delete =====
if not args.deleteproject:
    print("\n  --deleteproject not passed, skipping project deletion.")
else:
    # Re-init to system org context before admin operations
    print("\n" + "=" * 60)
    print("STEP 9b: Re-init to system org context for delete")
    print("=" * 60)
    api_post("realmManager/initializeOrganization", {
        "requestHandle": None,
        "contextHandle": SYS_ORG,
        "organizationName": SYS_ORG,
    }, f"initOrg → {SYS_ORG}")

    print("\n" + "=" * 60)
    print("STEP 10: Request Project Deletion")
    print("=" * 60)
    api_post("adminOrgManager/requestProjectDelete", {
        "requestHandle": None,
        "contextHandle": project_handle,
        "projectHandle": project_handle,
        "taskDescription": f"Delete Project {project_name}",
        "systemScope": True,
    }, "requestProjectDelete")

    print("\n" + "=" * 60)
    print("STEP 11: Find + Approve Deletion")
    print("=" * 60)
    delete_handle = None
    for attempt in range(5):
        time.sleep(3)
        pending_data = api_post("adminOrgManager/listDeletePendingProjects", {
            "systemScope": True,
        }, f"listDeletePendingProjects (attempt {attempt + 1})")

        if pending_data:
            pending = pending_data.get("requests", pending_data.get("adminRequests", pending_data.get("projects", [])))
            print(f"  Pending: {len(pending)} items")
            for req in pending:
                if project_name in str(req) or str(project_handle) in str(req):
                    delete_handle = req.get("handle")
                    print(f"  Found delete request: {delete_handle}")
                    break
        if delete_handle:
            break
        print("  Not found yet, retrying...")

    if delete_handle:
        api_post("adminOrgManager/approveProjectDeleteRequest", {
            "requestHandle": None,
            "contextHandle": project_handle,
            "handle": delete_handle,
            "systemScope": True,
            "taskDescription": f"Approving delete for {project_name}",
        }, "approveProjectDeleteRequest")
    else:
        print("  Could not find delete request handle after retries")

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
