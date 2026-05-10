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
    ) -> dict:
        """
        POST to an endpoint.

        Args:
            path: Endpoint path, e.g. "orgManager/listProjects"
            extra_body: Additional fields for the request body.
            timeout: Override default timeout.
            check: If True (default), raise APIError on FAILURE status.

        Returns:
            Parsed JSON response dict.
        """
        body: dict[str, Any] = {
            "contextHandle": self.cfg.organization,
            "systemScope": True,
        }
        if extra_body:
            body.update(extra_body)

        url = self.cfg.endpoint(path)
        t = timeout or self.cfg.request_timeout
        logger.debug("POST %s", url)

        resp = self.session.post(url, json=body, timeout=t)
        resp.raise_for_status()
        data = resp.json()

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
