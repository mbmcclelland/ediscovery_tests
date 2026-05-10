"""
End-to-end workflow tests.

Each test replicates a full user workflow as a chain of API calls,
mirroring the kind of click-sequences captured by the Edge recorder.

Workflow 1 -- "OCR Usage Report" (from ocrreport1.json):
  1. Create session (login)
  2. Get realm status (verify system is up)
  3. Get OCR usage statistics for Jan 2026
  4. Get OCR usage statistics download URL
  5. Verify URL is accessible
"""

import datetime
import pytest
import requests

from helpers.api_client import EDiscoveryClient


def _epoch_ms(year: int, month: int, day: int) -> int:
    dt = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


@pytest.mark.smoke
class TestWorkflowOCRReport:
    """
    Full end-to-end: login -> check status -> pull OCR report -> get download URL.
    """

    def test_ocr_report_workflow(self, cfg):
        client = EDiscoveryClient(cfg)

        # Step 1 -- Login
        client.login()
        assert client.session_token, "Login should return a session token"

        # Step 2 -- Verify realm is reachable
        realm = client.post("realmManager/getRealmStatus")
        assert "realmStatus" in realm
        assert realm["realmStatus"] not in ("FAILURE", "NOT_AVAILABLE")

        # Step 3 -- Get OCR statistics (Jan 1-31 2026)
        filters = [
            {"attribute": "FROM_DATE", "operator": "EQUALS", "value": _epoch_ms(2026, 1, 1)},
            {"attribute": "TO_DATE", "value": _epoch_ms(2026, 1, 31)},
        ]
        stats = client.post(
            "realmManager/getOCRUsageStatistics",
            extra_body={"filters": filters, "startIndex": 0, "count": 0},
        )
        assert "numOCRDocuments" in stats
        assert "numOCRPages" in stats

        # Step 4 -- Get download URL
        url_resp = client.post(
            "realmManager/getOCRUsageStatisticsUrl",
            extra_body={"filters": filters, "startIndex": 0, "count": 0},
        )
        assert url_resp.get("url"), "Download URL should not be empty"

        # Step 5 -- Verify the download URL is reachable (HEAD request)
        download_url = url_resp["url"]
        if download_url.startswith("http"):
            head = requests.head(
                download_url,
                verify=cfg.verify_ssl,
                timeout=cfg.request_timeout,
                allow_redirects=True,
            )
            assert head.status_code in (200, 302), (
                f"Download URL returned {head.status_code}"
            )

        client.logout()


@pytest.mark.smoke
class TestWorkflowProjectOverview:
    """
    Workflow: login -> list projects -> pick first project.
    """

    def test_project_overview_workflow(self, cfg):
        client = EDiscoveryClient(cfg)
        client.login()

        # List projects
        proj_resp = client.post("orgManager/listProjects")
        projects = proj_resp.get("projects", [])
        assert isinstance(projects, list)

        if projects:
            first = projects[0]
            assert "name" in first
            assert "handle" in first

        client.logout()


@pytest.mark.smoke
class TestWorkflowSystemHealth:
    """
    Workflow: login -> realm status -> node list -> services.
    """

    def test_system_health_workflow(self, cfg):
        client = EDiscoveryClient(cfg)
        client.login()

        # Realm status
        realm = client.post("realmManager/getRealmStatus")
        assert "realmStatus" in realm

        # Nodes
        nodes = client.post("realmManager/listNodes")
        assert nodes.get("status") != "FAILURE"

        # Services
        services = client.post("realmManager/listServices")
        assert services.get("status") != "FAILURE"

        # System status
        sys_status = client.post("statusLogManager/listSystemStatus")
        assert sys_status.get("status") != "FAILURE"

        client.logout()
