"""
Debug: full indexing workflow matching exact browser flow.

Browser flow:
  1.  Login as DRSysAdmin -> super_system_customer
  2.  initializeOrganization -> training  (switches org context)
  3.  createCase with hardcoded template IDs
  3b. initializeOrganization -> project context
  4.  createDataArea
  5.  createCorpus
  6.  listCorpusSets + addCorpus
  7.  createRepresentation
  8.  requestDeleteCorpus + approveDeleteCorpus  (cleanup)

Env vars (all DR_ prefixed, matching config.py conventions):
  DR_BASE_URL            default: https://192.168.58.128:8443/ediscovery/rest
  DR_USERNAME            default: DRSysAdmin
  DR_PASSWORD            (prompted if absent)
  DR_ORGANIZATION        default: super_system_customer
  DR_ORG_USERNAME        default: admin
  DR_ORG_PASSWORD        (not used for auth here, but logged)
  DR_ORG_ORGANIZATION    default: training
  DR_NFS_CONNECTOR_HANDLE
  DR_NFS_IMPORT_PATH     default: /test_datasets/Small Sample
  DR_NFS_DATASET_NAME    default: Small Sample
  DR_ADMIN_ROLE_HANDLE
  DR_REQUEST_TIMEOUT     default: 30
  DR_LONG_REQUEST_TIMEOUT default: 120
  DR_VERIFY_SSL          default: false  (must be literally "true" to enable)

Run:
  python fullWorkflow.py
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import textwrap
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests
import urllib3
from dotenv import load_dotenv

# ── Environment ────────────────────────────────────────────────────────────────
load_dotenv(override=True)

# ── SSL ────────────────────────────────────────────────────────────────────────
VERIFY_SSL: bool = os.getenv("DR_VERIFY_SSL", "false").lower() == "true"
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Timeouts ───────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT:      int = int(os.getenv("DR_REQUEST_TIMEOUT",      "30"))
LONG_REQUEST_TIMEOUT: int = int(os.getenv("DR_LONG_REQUEST_TIMEOUT", "120"))

# ── Credentials / targeting ────────────────────────────────────────────────────
BASE     = os.getenv("DR_BASE_URL",      "https://192.168.58.128:8443/ediscovery/rest").rstrip("/")
SYS_USER = os.getenv("DR_USERNAME",      "DRSysAdmin")
SYS_ORG  = os.getenv("DR_ORGANIZATION",  "super_system_customer")
print(f"SYS_USER={SYS_USER!r}")
print(f"SYS_ORG={SYS_ORG!r}")
SYS_PASS = os.getenv("DR_PASSWORD") or getpass.getpass(f"Password for {SYS_USER}: ")

ORG_USERNAME = os.getenv("DR_ORG_USERNAME",     "admin")
ORG_ORG      = os.getenv("DR_ORG_ORGANIZATION", "training")
TARGET_ORG   = ORG_ORG

# ── NFS / connector settings ───────────────────────────────────────────────────
NFS_CONNECTOR    = os.getenv("DR_NFS_CONNECTOR_HANDLE", "")
NFS_PATH         = os.getenv("DR_NFS_IMPORT_PATH",      "/test_datasets/Small Sample")
NFS_DATASET_NAME = os.getenv("DR_NFS_DATASET_NAME",     "Small Sample")
ADMIN_ROLE       = os.getenv("DR_ADMIN_ROLE_HANDLE",    "")

_safe_name     = NFS_DATASET_NAME.replace(" ", "_")
DATA_AREA_NAME = f"{_safe_name}_{_safe_name}"

# ── Hardcoded template IDs ─────────────────────────────────────────────────────
TEMPLATE_ATTRIBUTES: list[dict] = [
    {"name": "ALIAS_LISTS",             "value": "18621"},
    {"name": "ANALYTICAL_SETTINGS",     "value": "18542"},
    {"name": "BILLING_REPORT_SETTINGS", "value": "18629"},
    {"name": "CUSTOM_FIELDS",           "value": "18626"},
    {"name": "DOMAIN_LISTS",            "value": "18565"},
    {"name": "EMAIL_SIGNATURE",         "value": "18569"},
    {"name": "EXPORT_FIELDS",           "value": "18537"},
    {"name": "EXPORT_SETTINGS",         "value": "18558"},
    {"name": "INDEX_SETTINGS",          "value": "18514"},
    {"name": "LOADFILE_SETTINGS",       "value": "18623"},
    {"name": "SEARCH_FIELDS",           "value": "18593"},
    {"name": "DOCUMENT_METADATA",       "value": "18571"},
    {"name": "USER_EXP",                "value": "18567"},
    {"name": "REPORT_SETTINGS",         "value": "18615"},
    {"name": "SEARCH_SETTINGS",         "value": "18575"},
    {"name": "DUPE_SURVIVORSHIP",       "value": "18573"},
    {"name": "TAG",                     "value": "18563"},
]

# ── ANSI colour helpers ────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
RED    = "\033[31m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
DIM    = "\033[2m"


def _colour(text: Any, *codes: str) -> str:
    if not sys.stdout.isatty():
        return str(text)
    return "".join(codes) + str(text) + RESET


def banner(title: str, step: int | str | None = None) -> None:
    label = f"STEP {step}: {title}" if step is not None else title
    line  = "═" * 66
    print(f"\n{_colour(line, BOLD, CYAN)}")
    print(_colour(f"  {label}", BOLD, CYAN))
    print(_colour(line, BOLD, CYAN))


def ok(msg: str)   -> None: print(_colour(f"  ✓  {msg}", GREEN))
def warn(msg: str) -> None: print(_colour(f"  ⚠  {msg}", YELLOW))
def err(msg: str)  -> None: print(_colour(f"  ✗  {msg}", RED))
def info(msg: str) -> None: print(f"     {msg}")


# ── Audit state ────────────────────────────────────────────────────────────────
_timings:     list[tuple[str, float, bool]] = []
_request_log: list[dict]                    = []


# ── Utility helpers ────────────────────────────────────────────────────────────

def _endpoint(path: str) -> str:
    return f"{BASE}/{path.lstrip('/')}"


def _truncate(value: Any, max_len: int = 120) -> str:
    s = str(value)
    return s if len(s) <= max_len else s[:max_len] + f"…[+{len(s) - max_len}]"


def _dump_dict(d: dict, indent: int = 5, max_depth: int = 3) -> None:
    prefix = " " * indent

    def _render(obj: Any, depth: int) -> str:
        if depth <= 0:
            return _truncate(obj, 60)
        if isinstance(obj, dict):
            if not obj:
                return "{}"
            inner = ", ".join(
                f"{k!r}: {_render(v, depth - 1)}"
                for k, v in list(obj.items())[:8]
            )
            if len(obj) > 8:
                inner += f", …+{len(obj) - 8} more"
            return "{" + inner + "}"
        if isinstance(obj, list):
            if not obj:
                return "[]"
            if depth == 1:
                return f"[…{len(obj)} items]"
            items = [_render(i, depth - 1) for i in obj[:4]]
            if len(obj) > 4:
                items.append(f"…+{len(obj) - 4} more")
            return "[" + ", ".join(items) + "]"
        return _truncate(obj, 80)

    for key, val in d.items():
        print(f"{prefix}{_colour(str(key), BOLD)}: {_render(val, max_depth - 1)}")


def _dump_token(tok: str) -> None:
    if not tok:
        warn("Token is empty")
        return
    parts  = tok.split("|")
    labels = ["session-id", "org", "username", "role", "expiry"]
    info(f"Token segments ({len(parts)} total):")
    for i, part in enumerate(parts):
        label = labels[i] if i < len(labels) else f"segment[{i}]"
        print(f"       {_colour(label, DIM)}: {_truncate(part, 60)}")


def _annotate_error_code(code: str) -> str:
    hints = {
        "PERMISSION_DENIED": (
            "DRSysAdmin is a system-level account and may lack org-level "
            "permissions for this call.  Consider using DR_ORG_USERNAME."
        ),
        "CAE_ERROR": (
            "Generic server error (often maps to HTTP 500).  "
            "Check server logs for the root cause."
        ),
    }
    hint = hints.get(code)
    return f"{code}  ← {hint}" if hint else code


# ── Global session state ───────────────────────────────────────────────────────
_token   = ""
_headers: dict[str, str] = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
}


def _set_token(new_token: str) -> None:
    global _token, _headers
    _token = new_token
    if new_token:
        _headers["Authorization"] = new_token
    elif "Authorization" in _headers:
        del _headers["Authorization"]


# ── Success detection ──────────────────────────────────────────────────────────

def _is_success(data: dict) -> bool:
    """
    Determine whether a response represents success.

    Different endpoints use different conventions:
      • Most endpoints:  data["status"] == "SUCCESS"
      • realm endpoints: no "status" field; presence of a non-empty
                         "sessionToken" is the success signal.
    """
    explicit_status = data.get("status")
    if explicit_status is not None and explicit_status != "SUCCESS":
        return False
    if explicit_status == "SUCCESS":
        return True
    # No status field: success iff a sessionToken was returned
    return bool(data.get("sessionToken"))


# ── Core HTTP helper ───────────────────────────────────────────────────────────

def api_post(
    path: str,
    body: dict,
    label: str = "",
    *,
    expected_keys: list[str] | None = None,
    critical: bool = False,
    long: bool = False,
) -> dict | None:
    url     = _endpoint(path)
    timeout = LONG_REQUEST_TIMEOUT if long else REQUEST_TIMEOUT
    t0      = time.perf_counter()

    print(f"\n  {_colour('→ POST', BOLD)} {_colour(path, CYAN)}")
    if label:
        info(f"Label   : {label}")
    info(f"URL     : {url}")
    info(f"Timeout : {timeout}s  ({'long' if long else 'standard'})")

    safe_body = json.loads(json.dumps(body))
    if "password" in safe_body:
        safe_body["password"] = "***"
    body_str = json.dumps(safe_body, indent=2)
    if len(body_str) > 1_200:
        body_str = body_str[:1_200] + "\n  …(truncated)"
    print(f"  {_colour('Request body:', DIM)}")
    print(textwrap.indent(body_str, "     "))

    try:
        resp = requests.post(
            url,
            json=body,
            headers=_headers,
            verify=VERIFY_SSL,
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        elapsed = time.perf_counter() - t0
        err(f"Request TIMED OUT after {elapsed:.1f}s  (limit={timeout}s)")
        _record(label or path, path, 0, "TIMEOUT", elapsed)
        if critical:
            _print_summary()
            sys.exit(1)
        return None
    except requests.exceptions.ConnectionError as exc:
        elapsed = time.perf_counter() - t0
        err(f"Connection error after {elapsed:.1f}s: {exc}")
        _record(label or path, path, 0, "CONNECTION_ERROR", elapsed)
        if critical:
            _print_summary()
            sys.exit(1)
        return None

    elapsed = time.perf_counter() - t0

    print(f"  {_colour('Response:', DIM)}")
    http_col = GREEN if resp.status_code < 400 else RED
    info(f"HTTP    : {_colour(str(resp.status_code), http_col)}")
    info(f"Time    : {elapsed:.2f}s")
    info(f"Size    : {len(resp.content):,} bytes")

    if resp.status_code >= 400:
        warn("Non-2xx HTTP – raw body preview (up to 800 chars):")
        print(textwrap.indent(_truncate(resp.text, 800), "     "))

    try:
        data: dict = resp.json()
    except ValueError:
        err("Response is NOT valid JSON")
        print(textwrap.indent(_truncate(resp.text, 400), "     "))
        _record(label or path, path, resp.status_code, "NOT_JSON", elapsed)
        if critical:
            _print_summary()
            sys.exit(1)
        return None

    # ── Token refresh ──────────────────────────────────────────────────────
    new_tok = data.get("sessionToken")
    if new_tok and new_tok != _token:
        _set_token(new_tok)
        info("Token   : refreshed ↓")
        _dump_token(_token)
    else:
        info("Token   : unchanged")

    # ── Success detection ──────────────────────────────────────────────────
    call_success    = _is_success(data)
    explicit_status = data.get("status")

    if explicit_status is not None:
        display_status = explicit_status
    elif call_success:
        display_status = "SUCCESS (token)"
    else:
        display_status = "FAILURE (no token)"

    error_code = data.get("errorCode",      "")
    error_msg  = data.get("errorMessage",   "")
    extended   = data.get("extendedStatus", "")

    if call_success:
        ok(f"App status : {display_status}")
    else:
        err(f"App status : {display_status}")
        if error_code:
            err(f"Error code : {_annotate_error_code(error_code)}")
        if error_msg:
            err(f"Error msg  : {error_msg}")
        if extended:
            err(f"Extended   : {_truncate(extended, 400)}")
        err("Full failure response:")
        print(textwrap.indent(json.dumps(data, indent=2), "     "))

    info("Response keys: " + ", ".join(_colour(k, BOLD) for k in data.keys()))
    _dump_dict(data)

    # ── Expected-key validation ────────────────────────────────────────────
    if expected_keys:
        effective_expected = [
            k for k in expected_keys
            if not (k == "status" and explicit_status is None)
        ]
        missing = [k for k in effective_expected if k not in data]
        if missing:
            warn(f"Expected key(s) missing from response: {missing}")
        else:
            ok(f"All expected keys present: {effective_expected}")

    _record(label or path, path, resp.status_code, display_status, elapsed)

    if not call_success and critical:
        err("Critical step failed – aborting run.")
        _print_summary()
        sys.exit(1)

    return data


def _record(
    label: str, path: str, http: int, app: str, elapsed: float
) -> None:
    _request_log.append(
        dict(
            label   = label,
            path    = path,
            http    = http,
            app     = app,
            elapsed = round(elapsed, 3),
        )
    )
    _timings.append((label, elapsed, app in ("SUCCESS", "SUCCESS (token)")))


# ── Summary table ──────────────────────────────────────────────────────────────

def _print_summary() -> None:
    banner("RUN SUMMARY")
    col = [36, 46, 6, 22, 9]
    header = (
        f"{'Label':<{col[0]}}  "
        f"{'Path':<{col[1]}}  "
        f"{'HTTP':>{col[2]}}  "
        f"{'App Status':<{col[3]}}  "
        f"{'Time (s)':>{col[4]}}"
    )
    divider = "─" * (sum(col) + 10)
    print(f"\n  {_colour(header, BOLD)}")
    print(f"  {divider}")
    for r in _request_log:
        is_ok      = r["app"] in ("SUCCESS", "SUCCESS (token)")
        status_col = _colour(r["app"], GREEN) if is_ok else _colour(r["app"], RED)
        print(
            f"  {r['label']:<{col[0]}}  "
            f"  {_truncate(r['path'], col[1]):<{col[1]}}  "
            f"  {r['http']:>{col[2]}}  "
            f"  {status_col:<{col[3]}}  "
            f"  {r['elapsed']:>{col[4] - 1}.2f}s"
        )
    total  = sum(t for _, t, _ in _timings)
    passed = sum(1 for _, _, s in _timings if s)
    failed = len(_timings) - passed
    print(
        f"\n  {_colour('Steps passed:', GREEN)} {passed}   "
        f"{_colour('Steps failed:', RED)} {failed}   "
        f"Total elapsed: {total:.2f}s"
    )
    print(
        f"\n  Finished: "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Pre-flight checks
# ══════════════════════════════════════════════════════════════════════════════

print(_colour("\n╔══════════════════════════════════════════╗", BOLD, CYAN))
print(_colour("║   Digital Reef Debug – Indexing Workflow ║", BOLD, CYAN))
print(_colour("╚══════════════════════════════════════════╝", BOLD, CYAN))
print(f"\n  Server         : {_colour(BASE,            CYAN)}")
print(f"  System user    : {_colour(SYS_USER,        BOLD)} @ {_colour(SYS_ORG, BOLD)}")
print(f"  Target org     : {_colour(TARGET_ORG,      BOLD)}")
print(f"  Org user       : {_colour(ORG_USERNAME,    BOLD)}  "
      f"{_colour('(DR_ORG_USERNAME → membersRequestMessage)', DIM)}")
print(f"  NFS connector  : {NFS_CONNECTOR  or _colour('NOT SET', RED)}")
print(f"  NFS path       : {NFS_PATH}")
print(f"  Dataset name   : {NFS_DATASET_NAME}")
print(f"  Data area name : {DATA_AREA_NAME}")
print(f"  Admin role     : {ADMIN_ROLE     or _colour('NOT SET', RED)}")
print(f"  Verify SSL     : {VERIFY_SSL}")
print(f"  Timeout (std)  : {REQUEST_TIMEOUT}s")
print(f"  Timeout (long) : {LONG_REQUEST_TIMEOUT}s")
print(f"  Run started    : "
      f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

_missing: list[str] = []
if not BASE:          _missing.append("DR_BASE_URL")
if not SYS_PASS:      _missing.append("DR_PASSWORD")
if not NFS_CONNECTOR: _missing.append("DR_NFS_CONNECTOR_HANDLE")
if not ADMIN_ROLE:    _missing.append("DR_ADMIN_ROLE_HANDLE")
if _missing:
    for m in _missing:
        err(f"Required env var not set: {m}")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 – Login (createSession)
# ══════════════════════════════════════════════════════════════════════════════
banner("Login", step=1)

device_id = str(uuid.uuid4())
info(f"Device ID  : {device_id}")
info(f"Endpoint   : {_endpoint('realmManager/createSession')}")

login_body = {
    "drWsClientContext": {
        "username":         SYS_USER,
        "organizationName": SYS_ORG,
    },
    "contextPath": "/ediscovery",
    "userDeviceID": device_id,
}

t0 = time.perf_counter()
try:
    login_resp = requests.post(
        _endpoint("realmManager/createSession"),
        json=login_body,
        auth=(SYS_USER, SYS_PASS),
        verify=VERIFY_SSL,
        timeout=REQUEST_TIMEOUT,
    )
except requests.exceptions.ConnectionError as exc:
    err(f"Cannot reach server: {exc}")
    sys.exit(1)
except requests.exceptions.Timeout:
    err(f"Login timed out after {REQUEST_TIMEOUT}s")
    sys.exit(1)

login_elapsed = time.perf_counter() - t0
http_col = GREEN if login_resp.status_code < 400 else RED
info(f"HTTP {_colour(str(login_resp.status_code), http_col)}  ({login_elapsed:.2f}s)  "
     f"{len(login_resp.content):,} bytes")

if login_resp.status_code >= 400:
    err(f"HTTP error on login: {login_resp.status_code}")
    print(textwrap.indent(_truncate(login_resp.text, 600), "     "))
    sys.exit(1)

try:
    login_data = login_resp.json()
except ValueError:
    err("Login response is not valid JSON:")
    print(textwrap.indent(login_resp.text[:400], "     "))
    sys.exit(1)

info("Login response keys: " + ", ".join(_colour(k, BOLD) for k in login_data.keys()))
_dump_dict(login_data)

_token_from_login = login_data.get("sessionToken", "")
if not _token_from_login:
    err("Login failed – no sessionToken in response")
    err(f"  numberResults    : {login_data.get('numberResults', '(absent)')}")
    err(f"  needSecurityCode : {login_data.get('needSecurityCode', '(absent)')}")
    err("Full response:")
    print(textwrap.indent(json.dumps(login_data, indent=2), "     "))
    sys.exit(1)

_set_token(_token_from_login)
_sys_token = _token  # saved — restored before deletion steps
ok("Login successful")
info(f"  numberResults    : {login_data.get('numberResults', '(absent)')}")
info(f"  needSecurityCode : {login_data.get('needSecurityCode', False)}")
info("Parsed token:")
_dump_token(_token)

_record(
    "createSession (sys login)",
    "realmManager/createSession",
    login_resp.status_code,
    "SUCCESS (token)",
    login_elapsed,
)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 – Login as org user (admin@training) — project creator
# ══════════════════════════════════════════════════════════════════════════════
banner("Login as org user (project creator)", step=2)

ORG_PASS = os.getenv("DR_ORG_PASSWORD") or getpass.getpass(
    f"Password for {ORG_USERNAME}@{TARGET_ORG}: "
)

org_device_id = str(uuid.uuid4())
info(f"Org user   : {ORG_USERNAME}@{TARGET_ORG}")
info(f"Device ID  : {org_device_id}")

t0 = time.perf_counter()
try:
    org_login_resp = requests.post(
        _endpoint("realmManager/createSession"),
        json={
            "drWsClientContext": {
                "username":         ORG_USERNAME,
                "organizationName": TARGET_ORG,
            },
            "contextPath": "/ediscovery",
            "userDeviceID": org_device_id,
        },
        auth=(ORG_USERNAME, ORG_PASS),
        verify=VERIFY_SSL,
        timeout=REQUEST_TIMEOUT,
    )
except requests.exceptions.ConnectionError as exc:
    err(f"Cannot reach server: {exc}")
    _print_summary()
    sys.exit(1)

org_login_elapsed = time.perf_counter() - t0
http_col = GREEN if org_login_resp.status_code < 400 else RED
info(f"HTTP {_colour(str(org_login_resp.status_code), http_col)}  "
     f"({org_login_elapsed:.2f}s)  {len(org_login_resp.content):,} bytes")

try:
    org_login_data = org_login_resp.json()
except ValueError:
    err("Org login response is not valid JSON")
    print(textwrap.indent(org_login_resp.text[:400], "     "))
    _print_summary()
    sys.exit(1)

_dump_dict(org_login_data)

org_token = org_login_data.get("sessionToken", "")
if not org_token:
    err("Org login failed – no sessionToken")
    err("Full response:")
    print(textwrap.indent(json.dumps(org_login_data, indent=2), "     "))
    _print_summary()
    sys.exit(1)

_set_token(org_token)
ok("Org login successful")
info("Parsed token:")
_dump_token(_token)

_record(
    "createSession (org login)",
    "realmManager/createSession",
    org_login_resp.status_code,
    "SUCCESS (token)",
    org_login_elapsed,
)

# ── initializeOrganization → org context (as org user) ───────────────────────
api_post(
    "realmManager/initializeOrganization",
    {
        "requestHandle":    None,
        "contextHandle":    TARGET_ORG,
        "organizationName": TARGET_ORG,
    },
    label="initializeOrganization (org context)",
    expected_keys=["sessionToken"],
    critical=True,
)

parts = _token.split("|")
info(
    f"Token org after switch: "
    f"{parts[1] if len(parts) > 1 else '?'} / "
    f"{parts[2] if len(parts) > 2 else '?'}"
)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 – createCase
# ══════════════════════════════════════════════════════════════════════════════
banner("Create Project (createCase)", step=3)

project_name = f"debug-{uuid.uuid4().hex[:8]}"
info(f"Project name  : {_colour(project_name, BOLD)}")
info(f"Template attrs: {len(TEMPLATE_ATTRIBUTES)}")
info(f"Creator       : {_colour(ORG_USERNAME.lower(), BOLD)} (auto-member as project creator)")
info(f"Extra member  : {_colour(SYS_USER.lower(), BOLD)} (system admin, added for deletion)")

# admin@training creates the project (auto-member); drsysadmin added for deletion approval
_members: list[dict] = [
    {"name": SYS_USER.lower(), "roleHandles": [ADMIN_ROLE]},
]

create_case_data = api_post(
    "ecaManager/createCase",
    {
        "requestHandle":  None,
        "contextHandle":  TARGET_ORG,
        "addToCaseData":  False,
        "custodians":     [],
        "name":           project_name,
        "description":    f"Debug run – {project_name}",
        "attributes":     TEMPLATE_ATTRIBUTES,
        "membersRequestMessage": {"groups": [], "users": _members},
        "projectLogoBytes": None,
        "logoFileName":     "",
        "systemScope":      False,
        "reviewSystem":     None,
        "reviewProjectId":  0,
    },
    label="createCase",
    expected_keys=["status", "caseHandle"],
    critical=True,
)

# ── Extract project handle ─────────────────────────────────────────────────────
project_handle: str = ""
for _key in ("caseHandle", "projectHandle", "handle", "id"):
    _v = (create_case_data or {}).get(_key)
    if _v:
        if _key != "caseHandle":
            warn(f"'caseHandle' absent; fell back to '{_key}' = {_v}")
        project_handle = str(_v)
        break

if not project_handle:
    err("Could not determine project handle from createCase response")
    err("Full createCase response:")
    print(json.dumps(create_case_data, indent=4))
    _print_summary()
    sys.exit(1)

ok(f"Project handle : {_colour(project_handle, BOLD)}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 – createDataArea  (orgManager path, matching browser flow)
# ══════════════════════════════════════════════════════════════════════════════
banner("Create Data Area", step=4)

info(f"Data area name : {_colour(DATA_AREA_NAME, BOLD)}")
info(f"NFS connector  : {NFS_CONNECTOR}")
info(f"NFS path       : {NFS_PATH}")
info(f"Project handle : {project_handle}")

data_area_data = api_post(
    "orgManager/createDataArea",
    {
        "contextHandle":    project_handle,
        "connectorHandle":  NFS_CONNECTOR,
        "description":      "",
        "mode":             "IMPORT",
        "name":             DATA_AREA_NAME,
        "path":             NFS_PATH,
        "skippedDirectories": [],
    },
    label="createDataArea",
    expected_keys=["status"],
    critical=True,
    long=True,
)

# ── Extract data area handle ───────────────────────────────────────────────────
data_area_handle: str = ""
for _key in ("dataArea", "dataAreaHandle", "handle", "id"):
    _v = (data_area_data or {}).get(_key)
    if _v:
        if isinstance(_v, dict):
            data_area_handle = str(_v.get("handle", ""))
        else:
            data_area_handle = str(_v)
        if data_area_handle:
            if _key not in ("dataArea", "dataAreaHandle"):
                warn(f"fell back to key '{_key}' = {_v}")
            break

if not data_area_handle:
    err("Could not determine data area handle from createDataArea response")
    err("Full createDataArea response:")
    print(json.dumps(data_area_data, indent=4))
    _print_summary()
    sys.exit(1)

ok(f"Data area handle : {_colour(data_area_handle, BOLD)}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 – createCorpus  (orgManager path)
# ══════════════════════════════════════════════════════════════════════════════
banner("Create Corpus", step=5)

info(f"Corpus name      : {_colour(NFS_DATASET_NAME, BOLD)}")
info(f"Data area handle : {data_area_handle}")
info(f"Project handle   : {project_handle}")

corpus_data = api_post(
    "orgManager/createCorpus",
    {
        "contextHandle":    project_handle,
        "attributes":       [{"name": "projecthandle", "value": project_handle}],
        "brand":            True,
        "dataAreaHandles":  [data_area_handle],
        "description":      "",
        "name":             NFS_DATASET_NAME,
        "loadFileName":     "",
        "loadFileType":     "EDRM_XML",
        "loadFileProfileId": -1,
    },
    label="createCorpus",
    expected_keys=["status"],
    critical=True,
    long=True,
)

# ── Extract corpus handle ──────────────────────────────────────────────────────
corpus_handle: str = ""
for _key in ("corpus", "corpusHandle", "handle", "id"):
    _v = (corpus_data or {}).get(_key)
    if _v:
        if isinstance(_v, dict):
            corpus_handle = str(_v.get("handle", ""))
        else:
            corpus_handle = str(_v)
        if corpus_handle:
            if _key not in ("corpus", "corpusHandle"):
                warn(f"fell back to key '{_key}' = {_v}")
            break

if not corpus_handle:
    err("Could not determine corpus handle from createCorpus response")
    err("Full createCorpus response:")
    print(json.dumps(corpus_data, indent=4))
    _print_summary()
    sys.exit(1)

ok(f"Corpus handle : {_colour(corpus_handle, BOLD)}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 – createRepresentation  (corpusManager path — kicks off indexing)
# ══════════════════════════════════════════════════════════════════════════════
banner("Create Representation (start indexing)", step=6)

info(f"Corpus handle  : {corpus_handle}")
info(f"Project handle : {project_handle}")

representation_data = api_post(
    "corpusManager/createRepresentation",
    {
        "contextHandle":  project_handle,
        "attributes":     [{"name": "projecthandle", "value": project_handle}],
        "corpusHandle":   corpus_handle,
        "scanAttributes": [
            {"name": "batchNumber",    "value": NFS_DATASET_NAME},
            {"name": "projecthandle",  "value": project_handle},
        ],
        "taskDescription":       f"Indexing {NFS_DATASET_NAME} for project {project_name}",
        "typeList":               ["CONTENT_INDEX", "VECTOR_SET"],
        "enablePatternDetection": True,
    },
    label="createRepresentation",
    expected_keys=["status"],
    critical=True,
    long=True,
)

# ── Extract representation handle (informational only) ────────────────────────
representation_handle: str = ""
for _key in ("representationHandle", "handle", "id"):
    _v = (representation_data or {}).get(_key)
    if _v:
        if _key != "representationHandle":
            warn(f"'representationHandle' absent; fell back to '{_key}' = {_v}")
        representation_handle = str(_v)
        break

if representation_handle:
    ok(f"Representation handle : {_colour(representation_handle, BOLD)}")
else:
    warn("No representation handle in createRepresentation response.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 8 – Indexing launched — no cleanup (let it run)
# ══════════════════════════════════════════════════════════════════════════════
banner("Indexing launched", step=7)

ok("Indexing job submitted — running asynchronously on the server.")
info(f"  Project  : {_colour(project_name, BOLD)}  (handle: {project_handle})")
info(f"  Corpus   : {corpus_handle}")
info(f"  NFS path : {NFS_PATH}")
info("Monitor progress via the Monitoring dashboard in the Digital Reef UI.")
info("To delete this project later, use DRSysAdmin → adminOrgManager/requestProjectDelete.")


# ══════════════════════════════════════════════════════════════════════════════
# Final summary
# ══════════════════════════════════════════════════════════════════════════════
_print_summary()