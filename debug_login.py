"""
Diagnostic script: tries several common auth patterns against createSession
and prints the full response body so we can see what the server expects.

Usage:
    python debug_login.py
"""

import json
import requests
import urllib3
import getpass

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---- EDIT THESE ----
BASE_URL = "https://192.168.58.128:8443/ediscovery/rest"
USERNAME = "DRSysAdmin"
ORGANIZATION = ""  # fill in if you know it
LDAP_DOMAIN = ""   # fill in if applicable
# --------------------

PASSWORD = getpass.getpass(f"Password for {USERNAME}: ")

ENDPOINT = f"{BASE_URL}/realmManager/createSession"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


def try_request(label: str, **kwargs):
    """Fire a request and print the full result."""
    print(f"\n{'='*60}")
    print(f"ATTEMPT: {label}")
    print(f"{'='*60}")
    try:
        resp = requests.post(ENDPOINT, verify=False, timeout=30, **kwargs)
        print(f"  Status:  {resp.status_code}")
        print(f"  Headers: {dict(resp.headers)}")
        try:
            body = resp.json()
            print(f"  Body (JSON):\n{json.dumps(body, indent=2)}")
        except Exception:
            print(f"  Body (text): {resp.text[:2000]}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")


# --- Attempt 1: Password in drWsClientContext (some DR versions do this) ---
try_request(
    "Password inside drWsClientContext",
    headers=HEADERS,
    json={
        "drWsClientContext": {
            "username": USERNAME,
            "organizationName": ORGANIZATION,
            "ldapDomainName": LDAP_DOMAIN or None,
        },
        "contextPath": "/ediscovery",
        "objectName": PASSWORD,  # some APIs use objectName for password
    },
)

# --- Attempt 2: Basic Auth header ---
try_request(
    "HTTP Basic Auth header",
    headers=HEADERS,
    auth=(USERNAME, PASSWORD),
    json={
        "drWsClientContext": {
            "username": USERNAME,
            "organizationName": ORGANIZATION,
        },
        "contextPath": "/ediscovery",
    },
)

# --- Attempt 3: Custom X-Password header ---
try_request(
    "Custom X-Password header",
    headers={**HEADERS, "X-Password": PASSWORD},
    json={
        "drWsClientContext": {
            "username": USERNAME,
            "organizationName": ORGANIZATION,
        },
        "contextPath": "/ediscovery",
    },
)

# --- Attempt 4: Password as Authorization Bearer ---
try_request(
    "Authorization: Bearer <password>",
    headers={**HEADERS, "Authorization": f"Bearer {PASSWORD}"},
    json={
        "drWsClientContext": {
            "username": USERNAME,
            "organizationName": ORGANIZATION,
        },
        "contextPath": "/ediscovery",
    },
)

# --- Attempt 5: Form-encoded (the endpoint accepts x-www-form-urlencoded) ---
try_request(
    "Form-encoded body",
    headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    data={
        "username": USERNAME,
        "password": PASSWORD,
        "organizationName": ORGANIZATION,
        "contextPath": "/ediscovery",
    },
)

# --- Attempt 6: JSON with password as top-level field ---
try_request(
    "Password as top-level JSON field",
    headers=HEADERS,
    json={
        "drWsClientContext": {
            "username": USERNAME,
            "organizationName": ORGANIZATION,
        },
        "password": PASSWORD,
        "contextPath": "/ediscovery",
    },
)

# --- Attempt 7: Minimal body (just context, no extras) ---
try_request(
    "Minimal body - just drWsClientContext",
    headers=HEADERS,
    json={
        "drWsClientContext": {
            "username": USERNAME,
            "organizationName": ORGANIZATION,
        },
    },
)

print("\n" + "="*60)
print("DONE — check which attempt returned status=SUCCESS or a 200")
print("and share the output so we can fix the api_client.py login method.")
print("="*60)
