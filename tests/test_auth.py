"""
Tests for session creation and authentication.

Maps to the login step in the Edge workflow:
  UI: Enter username -> click "Log in"
  API: POST /realmManager/createSession (Basic Auth)
       -> sessionToken used as Authorization header thereafter
"""

import pytest

from helpers.api_client import EDiscoveryClient, APIError


@pytest.mark.auth
@pytest.mark.smoke
class TestCreateSession:
    """Happy-path authentication tests."""

    def test_login_returns_success(self, api):
        """Session fixture already logged in; verify we have a token."""
        assert api.session_token is not None, "Session token should be set after login"

    def test_login_returns_session_token(self, cfg):
        """Fresh login returns a non-empty sessionToken."""
        client = EDiscoveryClient(cfg)
        resp = client.login()
        assert resp.get("sessionToken"), "Expected a sessionToken in the response"
        assert client.session_token is not None
        client.logout()

    def test_session_token_is_reusable(self, api):
        """Subsequent API calls with the same session succeed."""
        data = api.post("realmManager/getVersion")
        # getVersion doesn't return "status" — just verify we got data back
        assert "sessionToken" in data

    def test_login_returns_bearer_token(self, cfg):
        """If the server issues a bearerToken, it should be a non-empty string."""
        client = EDiscoveryClient(cfg)
        resp = client.login()
        bearer = resp.get("bearerToken")
        if bearer is not None:
            assert isinstance(bearer, str) and len(bearer) > 0
        client.logout()


@pytest.mark.auth
class TestGetVersion:
    """Verify the /realmManager/getVersion smoke endpoint."""

    def test_get_version_success(self, api):
        data = api.post("realmManager/getVersion")
        assert "sessionToken" in data

    def test_get_version_has_session_token(self, api):
        data = api.post("realmManager/getVersion")
        assert "sessionToken" in data
