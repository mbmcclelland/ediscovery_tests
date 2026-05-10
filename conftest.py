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
    Decorator: skip a test if the API returns PERMISSION_DENIED or a 500.
    DRSysAdmin is a system-level account and lacks some org-level permissions.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if e.error_code == "PERMISSION_DENIED":
                pytest.skip(f"Permission denied: {e.extended_status}")
            if e.error_code == "CAE_ERROR":
                pytest.skip(f"Server error: {e.extended_status}")
            raise
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 500:
                pytest.skip(f"Server 500: {e}")
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
