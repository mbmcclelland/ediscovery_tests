"""
Locust load tests for the eDiscovery REST API.

Usage:
    locust -f locustfile.py --host https://192.168.58.128:8443
    locust -f locustfile.py --host https://192.168.58.128:8443 \
        --headless -u 10 -r 2 --run-time 60s

Scenarios:
    ReadOnlyUser    -- status/health dashboards (weight: 3)
    OCRReportUser   -- OCR report generation (weight: 1)
    ProjectBrowser  -- browsing projects/connectors (weight: 2)
"""

import os
import datetime
import logging

from locust import HttpUser, task, between, tag
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

REST_PREFIX = "/ediscovery/rest"

USERNAME = os.getenv("DR_USERNAME", "DRSysAdmin")
PASSWORD = os.getenv("DR_PASSWORD", "")
ORGANIZATION = os.getenv("DR_ORGANIZATION", "super_system_customer")
VERIFY_SSL = os.getenv("DR_VERIFY_SSL", "false").lower() == "true"


def _epoch_ms(year, month, day):
    dt = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


class EDiscoveryMixin:
    """Shared auth and request helpers for all Locust user classes."""

    session_token = None

    def api_post(self, path, extra_body=None, name=None):
        """POST with raw session token as Authorization header."""
        body = {
            "contextHandle": ORGANIZATION,
            "systemScope": True,
        }
        if extra_body:
            body.update(extra_body)
        url = f"{REST_PREFIX}/{path}"
        headers = {"Authorization": self.session_token} if self.session_token else {}
        with self.client.post(
            url,
            json=body,
            name=name or path,
            verify=VERIFY_SSL,
            headers=headers,
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return None
            data = resp.json()
            # Capture rolling token
            new_token = data.get("sessionToken")
            if new_token:
                self.session_token = new_token
            if data.get("status") == "FAILURE":
                resp.failure(
                    f"API error: {data.get('errorCode')} - {data.get('extendedStatus')}"
                )
                return None
            return data

    def do_login(self):
        device_id = str(__import__('uuid').uuid4())
        body = {
            "drWsClientContext": {
                "username": USERNAME,
                "organizationName": ORGANIZATION,
            },
            "contextPath": "/ediscovery",
            "userDeviceID": device_id,
        }
        url = f"{REST_PREFIX}/realmManager/createSession"
        with self.client.post(
            url,
            json=body,
            name="realmManager/createSession",
            verify=VERIFY_SSL,
            auth=(USERNAME, PASSWORD),
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"Login HTTP {resp.status_code}")
                return False
            data = resp.json()
            if data.get("status") == "FAILURE":
                resp.failure(f"Login failed: {data.get('errorCode')}")
                return False
            self.session_token = data.get("sessionToken")
            if not self.session_token:
                resp.failure("No sessionToken returned")
                return False
            return True


class ReadOnlyUser(HttpUser, EDiscoveryMixin):
    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        self.do_login()

    @tag("status")
    @task(3)
    def check_realm_status(self):
        self.api_post("realmManager/getRealmStatus")

    @tag("status")
    @task(2)
    def list_system_status(self):
        self.api_post("statusLogManager/listSystemStatus")

    @tag("status")
    @task(2)
    def list_realm_summary(self):
        self.api_post("statusLogManager/listRealmSummaryState")

    @tag("status")
    @task(1)
    def get_version(self):
        self.api_post("realmManager/getVersion")

    @tag("status")
    @task(1)
    def list_logged_in_users(self):
        self.api_post("realmManager/listLoggedInUsers")

    @tag("status")
    @task(1)
    def list_storage_utilization(self):
        self.api_post("statusLogManager/listStorageUtilizationStatus")


class OCRReportUser(HttpUser, EDiscoveryMixin):
    weight = 1
    wait_time = between(2, 5)

    def on_start(self):
        self.do_login()

    @tag("ocr")
    @task(3)
    def get_ocr_statistics_jan2026(self):
        self.api_post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": [
                    {"attribute": "FROM_DATE", "operator": "EQUALS", "value": _epoch_ms(2026, 1, 1)},
                    {"attribute": "TO_DATE", "value": _epoch_ms(2026, 1, 31)},
                ],
                "startIndex": 0,
                "count": 0,
            },
            name="realmManager/getOCRUsageStatistics [Jan 2026]",
        )

    @tag("ocr")
    @task(2)
    def get_ocr_download_url_jan2026(self):
        self.api_post(
            "realmManager/getOCRUsageStatisticsUrl",
            extra_body={
                "filters": [
                    {"attribute": "FROM_DATE", "operator": "EQUALS", "value": _epoch_ms(2026, 1, 1)},
                    {"attribute": "TO_DATE", "value": _epoch_ms(2026, 1, 31)},
                ],
                "startIndex": 0,
                "count": 0,
            },
            name="realmManager/getOCRUsageStatisticsUrl [Jan 2026]",
        )

    @tag("ocr")
    @task(1)
    def get_ocr_statistics_full_year(self):
        self.api_post(
            "realmManager/getOCRUsageStatistics",
            extra_body={
                "filters": [
                    {"attribute": "FROM_DATE", "operator": "EQUALS", "value": _epoch_ms(2025, 1, 1)},
                    {"attribute": "TO_DATE", "value": _epoch_ms(2025, 12, 31)},
                ],
                "startIndex": 0,
                "count": 0,
            },
            name="realmManager/getOCRUsageStatistics [Full 2025]",
        )


class ProjectBrowser(HttpUser, EDiscoveryMixin):
    weight = 2
    wait_time = between(1, 4)

    def on_start(self):
        self.do_login()

    @tag("projects")
    @task(3)
    def list_projects(self):
        self.api_post("orgManager/listProjects")

    @tag("projects")
    @task(2)
    def list_users(self):
        self.api_post("orgManager/listUsers")

    @tag("orgs")
    @task(2)
    def list_organizations(self):
        self.api_post("realmManager/listOrganizations")

    @tag("connectors")
    @task(1)
    def list_connectors(self):
        self.api_post("orgManager/listConnectors")

    @tag("projects")
    @task(1)
    def list_corpora(self):
        self.api_post("orgManager/listCorpora")

    @tag("projects")
    @task(1)
    def list_roles(self):
        self.api_post("orgManager/listRoles")

    @tag("billing")
    @task(1)
    def get_billing_settings(self):
        self.api_post("billingReportManager/getBillingReportSettings")
