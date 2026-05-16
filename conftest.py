"""
Shared pytest fixtures for eDiscovery API tests.

Fixtures:
    cfg         -- System admin Config (session scope)
    api         -- System admin EDiscoveryClient (session scope)
    api_fresh   -- Fresh system admin client (function scope)
    org_cfg     -- Org user Config (session scope)
    api_org     -- Org user EDiscoveryClient (session scope, skips if not configured)
"""

import functools
import pytest
import urllib3
import requests

from config import Config, OrgUserConfig, config, org_config
from helpers.api_client import EDiscoveryClient, APIError


# ---------------------------------------------------------------- warnings
if not config.verify_ssl:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# -------------------------------------------------------------- helpers
def skip_on_permission_or_error(func):
    """
    Decorator: skip a test only when the server explicitly tells us the
    caller lacks permission. Everything else — CAE_ERROR, HTTP 500,
    server NPEs — is propagated as a real failure.

    Before BUG_LOG B13 was fixed in v0.04, this decorator also swallowed
    `CAE_ERROR` and HTTP 500 as skips. The result was that a server-side
    meltdown produced a green CI run, because every test that hit the
    broken endpoint silently turned into a skip. That made the suite
    actively misleading. Now only the documented permission errorCodes
    skip; real errors carry their full payload into the failure message.
    """
    _PERMISSION_ERROR_CODES = {"PERMISSION_DENIED", "ACCESS_DENIED", "FORBIDDEN"}

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if e.error_code in _PERMISSION_ERROR_CODES:
                pytest.skip(f"{e.error_code}: {e.extended_status}")
            raise
    return wrapper


# ------------------------------------------------- system admin fixtures
@pytest.fixture(scope="session")
def cfg() -> Config:
    """Return the system admin Config."""
    return config


@pytest.fixture(scope="session")
def api(cfg) -> EDiscoveryClient:
    """
    System admin client. Shared across the entire test session.
    Logs in once as DRSysAdmin.
    """
    client = EDiscoveryClient(cfg)
    client.login()
    yield client
    client.logout()


@pytest.fixture
def api_fresh(cfg) -> EDiscoveryClient:
    """Fresh system admin client created per-test."""
    client = EDiscoveryClient(cfg)
    client.login()
    yield client
    client.logout()


@pytest.fixture
def api_unauthenticated(cfg) -> EDiscoveryClient:
    """Client with NO session token."""
    return EDiscoveryClient(cfg)


# ---------------------------------------------------- org user fixtures
@pytest.fixture(scope="session")
def org_cfg() -> OrgUserConfig:
    """Return the org user Config."""
    return org_config


@pytest.fixture(scope="session")
def api_org(org_cfg) -> EDiscoveryClient:
    """
    Org-scoped user client (e.g. admin@training).
    Shared across the entire test session.
    Skips if DR_ORG_USERNAME / DR_ORG_PASSWORD are not configured.
    """
    if not org_cfg.is_configured:
        pytest.skip(
            "Org user not configured. Set DR_ORG_USERNAME, DR_ORG_PASSWORD, "
            "and DR_ORG_ORGANIZATION in .env"
        )
    client = EDiscoveryClient(org_cfg)
    client.login()
    yield client
    client.logout()


# ------------------------------------------------------------ pytest config
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "smoke: Quick smoke tests")
    config.addinivalue_line("markers", "auth: Authentication tests")
    config.addinivalue_line("markers", "ocr: OCR usage report tests")
    config.addinivalue_line("markers", "status: System/realm status tests")
    config.addinivalue_line("markers", "projects: Project management tests")
    config.addinivalue_line("markers", "orgs: Organization management tests")
    config.addinivalue_line("markers", "connectors: Connector management tests")
    config.addinivalue_line("markers", "org_user: Tests requiring org-scoped user")
    config.addinivalue_line("markers", "slow: Long-running tests")
