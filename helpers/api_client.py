"""
eDiscovery REST API client.

Authentication protocol (reverse-engineered from browser traffic):
  1. Login:  POST /realmManager/createSession with HTTP Basic Auth
             + userDeviceID (UUID) in the JSON body
             -> receive sessionToken (includes the UUID)
  2. Calls:  POST /endpoint with:
             - Authorization header = raw sessionToken
             - JSON body with business fields (contextHandle, systemScope, etc.)
  3. Rolling tokens: every response may return a fresh sessionToken;
             the client uses the latest one.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import requests

from config import Config, config as default_config

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Raised when the API returns a non-SUCCESS status."""

    def __init__(self, status: str, error_code: str | None, extended: str | None, raw: dict):
        self.status = status
        self.error_code = error_code
        self.extended_status = extended
        self.raw = raw
        super().__init__(
            f"API error: status={status}, errorCode={error_code}, "
            f"extendedStatus={extended}"
        )


class EDiscoveryClient:
    """
    Thin wrapper around the eDiscovery REST API.

    Usage:
        client = EDiscoveryClient()
        client.login()
        data = client.post("orgManager/listProjects")
        client.logout()
    """

    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or default_config
        self.session = requests.Session()
        self.session.verify = self.cfg.verify_ssl
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self.session_token: str | None = None
        self.device_id: str = str(uuid.uuid4())

    # ------------------------------------------------------------------ auth
    def login(
        self,
        username: str | None = None,
        password: str | None = None,
        organization: str | None = None,
    ) -> dict:
        """
        Create a session via POST /realmManager/createSession.

        Login uses HTTP Basic Auth. A userDeviceID (UUID) is sent in the
        body to obtain a full session token. Subsequent calls use the
        raw sessionToken as the Authorization header.
        """
        username = username or self.cfg.username
        password = password or self.cfg.password
        organization = organization or self.cfg.organization

        payload = {
            "drWsClientContext": {
                "username": username,
                "organizationName": organization,
            },
            "contextPath": "/ediscovery",
            "userDeviceID": self.device_id,
        }
        if self.cfg.ldap_domain:
            payload["drWsClientContext"]["ldapDomainName"] = self.cfg.ldap_domain

        url = self.cfg.endpoint("realmManager/createSession")
        resp = self.session.post(
            url, json=payload, auth=(username, password),
            timeout=self.cfg.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "FAILURE":
            raise APIError(
                status=data["status"],
                error_code=data.get("errorCode"),
                extended=data.get("extendedStatus"),
                raw=data,
            )

        self.session_token = data.get("sessionToken")
        if not self.session_token:
            raise APIError(
                status="UNKNOWN", error_code=None,
                extended="No sessionToken returned from createSession",
                raw=data,
            )

        self.session.headers["Authorization"] = self.session_token
        logger.info("Logged in as %s (token=...%s)", username, self.session_token[-40:])
        return data

    def logout(self):
        """Clear session state."""
        self.session_token = None
        self.session.headers.pop("Authorization", None)

    # -------------------------------------------------------------- requests
    def post(
        self,
        path: str,
        extra_body: dict | None = None,
        *,
        timeout: int | None = None,
        check: bool = True,
        system_scope: bool | None = None,
    ) -> dict:
        """
        POST to an endpoint.

        Args:
            path: Endpoint path, e.g. "orgManager/listProjects"
            extra_body: Additional fields for the request body.
            timeout: Override default timeout.
            check: If True (default), raise APIError on FAILURE status.
            system_scope: Explicitly set systemScope in the request body.
                When None (the default), systemScope is auto-derived: True
                if contextHandle is still the configured org (i.e. caller
                did not override it), False if the caller overrode
                contextHandle to a project/case handle. Project-scoped
                endpoints (createDataArea, createCorpus, createRepresentation,
                etc.) MUST run with systemScope=False or the server will
                check super-system roles instead of project roles and 500.

        Returns:
            Parsed JSON response dict.
        """
        body: dict[str, Any] = {
            "contextHandle": self.cfg.organization,
        }
        if extra_body:
            body.update(extra_body)

        if system_scope is not None:
            body["systemScope"] = system_scope
        elif "systemScope" not in body:
            body["systemScope"] = (body["contextHandle"] == self.cfg.organization)

        url = self.cfg.endpoint(path)
        t = timeout or self.cfg.request_timeout
        logger.debug("POST %s (systemScope=%s)", url, body["systemScope"])

        resp = self.session.post(url, json=body, timeout=t)
        # Try to parse JSON before failing on HTTP status — error bodies
        # often carry useful errorCode/extendedStatus that raise_for_status
        # would otherwise discard.
        try:
            data = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise  # 2xx but non-JSON — surface the parse error
        if resp.status_code >= 400 and data.get("status") != "SUCCESS":
            # Prefer structured failure when the server provided one.
            if data.get("errorCode") or data.get("extendedStatus"):
                if check:
                    raise APIError(
                        status=data.get("status", f"HTTP {resp.status_code}"),
                        error_code=data.get("errorCode"),
                        extended=data.get("extendedStatus"),
                        raw=data,
                    )
            else:
                resp.raise_for_status()

        # Rolling tokens: capture the fresh token from every response
        new_token = data.get("sessionToken")
        if new_token:
            self.session_token = new_token
            self.session.headers["Authorization"] = new_token

        if check:
            self._check_status(data, path)

        return data

    def post_raw(
        self,
        path: str,
        body: dict,
        *,
        timeout: int | None = None,
    ) -> requests.Response:
        """POST with a fully custom body. Returns the raw Response object."""
        url = self.cfg.endpoint(path)
        t = timeout or self.cfg.request_timeout
        resp = self.session.post(url, json=body, timeout=t)
        resp.raise_for_status()
        try:
            data = resp.json()
            new_token = data.get("sessionToken")
            if new_token:
                self.session_token = new_token
                self.session.headers["Authorization"] = new_token
        except Exception:
            pass
        return resp

    # --------------------------------------------------------------- helpers
    def discover_template_attributes(
        self,
        org_name: str,
        *,
        include_is_imported: bool = True,
    ) -> list[dict]:
        """
        Discover this org's template handles via orgManager/listTemplates
        and return the list of {"name": <templateType>, "value": <handle>}
        dicts ready to pass as `attributes` to ecaManager/createCase.

        Template handles are per-org and change every install, so this is
        the only reliable source. Optionally appends the IS_IMPORTED='false'
        attribute that the browser flow always sends but isn't a real
        template (B26).

        Caller must be authenticated and in the target org context
        (initializeOrganization(org_name) before calling).

        NOTE: the caller's session needs listTemplates permission. On
        default-shipped builds, DRSysAdmin works but a plain org admin
        (admin@training) does NOT — call this with the system-admin
        client even if you'll create the project as the org user.
        """
        data = self.post("orgManager/listTemplates")
        attrs: list[dict] = []
        for t in data.get("templates", []):
            ttype = t.get("templateType")
            handle = t.get("handle")
            if ttype and handle:
                attrs.append({"name": ttype, "value": str(handle)})
        if include_is_imported:
            # Insert immediately after INDEX_SETTINGS to match the browser
            # ordering described in DR_Workflow_Guide.md §2.
            insert_at = next(
                (i + 1 for i, a in enumerate(attrs) if a["name"] == "INDEX_SETTINGS"),
                len(attrs),
            )
            attrs.insert(insert_at, {"name": "IS_IMPORTED", "value": "false"})
        return attrs

    @staticmethod
    def _check_status(data: dict, context: str = ""):
        status = data.get("status")
        if status is not None and status == "FAILURE":
            raise APIError(
                status=status,
                error_code=data.get("errorCode"),
                extended=data.get("extendedStatus"),
                raw=data,
            )
