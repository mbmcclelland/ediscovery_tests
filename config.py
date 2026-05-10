"""
Configuration management for eDiscovery API tests.
Loads settings from .env file or environment variables.

Supports two user profiles:
  - System admin (DR_ prefix): DRSysAdmin / super_system_customer
  - Org user (DR_ORG_ prefix): admin / training

All env vars use a DR_ prefix to avoid collisions with system
variables (e.g. Windows sets USERNAME automatically).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root; override=True ensures .env values
# take precedence over existing system environment variables.
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)


@dataclass(frozen=True)
class Config:
    """Immutable test configuration loaded from environment."""

    base_url: str = field(
        default_factory=lambda: os.getenv(
            "DR_BASE_URL", "https://192.168.58.128:8443/ediscovery/rest"
        )
    )
    username: str = field(default_factory=lambda: os.getenv("DR_USERNAME", "DRSysAdmin"))
    password: str = field(default_factory=lambda: os.getenv("DR_PASSWORD", ""))
    organization: str = field(
        default_factory=lambda: os.getenv("DR_ORGANIZATION", "super_system_customer")
    )
    ldap_domain: str = field(default_factory=lambda: os.getenv("DR_LDAP_DOMAIN", ""))
    request_timeout: int = field(
        default_factory=lambda: int(os.getenv("DR_REQUEST_TIMEOUT", "30"))
    )
    long_request_timeout: int = field(
        default_factory=lambda: int(os.getenv("DR_LONG_REQUEST_TIMEOUT", "120"))
    )
    verify_ssl: bool = field(
        default_factory=lambda: os.getenv("DR_VERIFY_SSL", "false").lower() == "true"
    )

    # Load test settings
    load_test_users: int = field(
        default_factory=lambda: int(os.getenv("DR_LOAD_TEST_USERS", "10"))
    )
    load_test_spawn_rate: int = field(
        default_factory=lambda: int(os.getenv("DR_LOAD_TEST_SPAWN_RATE", "2"))
    )
    load_test_duration: int = field(
        default_factory=lambda: int(os.getenv("DR_LOAD_TEST_DURATION", "60"))
    )

    # CLI settings
    log_dir: str = field(
        default_factory=lambda: os.getenv("DR_LOG_DIR", "/home/auraria/AHS/output")
    )
    poll_interval: int = field(
        default_factory=lambda: int(os.getenv("DR_POLL_INTERVAL", "10"))
    )
    report_output: str = field(
        default_factory=lambda: os.getenv("DR_REPORT_OUTPUT", "dr_report.csv")
    )

    # Postgres (used by preflight and job poller via subprocess — peer auth only)
    pg_host: str = field(default_factory=lambda: os.getenv("DR_PG_HOST", "localhost"))
    pg_db: str = field(default_factory=lambda: os.getenv("DR_PG_DB", "auraria_mgmt"))
    pg_user: str = field(default_factory=lambda: os.getenv("DR_PG_USER", "auraria"))
    pg_password: str = field(default_factory=lambda: os.getenv("DR_PG_PASSWORD", "auraria"))

    def endpoint(self, path: str) -> str:
        """Build full URL for an API endpoint path."""
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"


@dataclass(frozen=True)
class OrgUserConfig(Config):
    """
    Config for an org-scoped user (e.g. admin@training).
    Inherits base_url, timeouts, and SSL settings from Config,
    but uses separate credentials from DR_ORG_ env vars.
    """

    username: str = field(default_factory=lambda: os.getenv("DR_ORG_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("DR_ORG_PASSWORD", ""))
    organization: str = field(default_factory=lambda: os.getenv("DR_ORG_ORGANIZATION", ""))
    ldap_domain: str = field(default_factory=lambda: os.getenv("DR_ORG_LDAP_DOMAIN", ""))

    @property
    def is_configured(self) -> bool:
        """True if org user credentials have been provided."""
        return bool(self.username and self.password)


# Singleton instances
config = Config()
org_config = OrgUserConfig()
