"""
Tests for system status and monitoring endpoints.

Many realm-level endpoints don't return a "status" field on success;
they return domain data directly (e.g. realmStatus, sessionToken).
We test for the presence of expected data fields instead.
"""

import pytest


@pytest.mark.status
@pytest.mark.smoke
class TestRealmStatus:
    """Realm-level health and status checks."""

    def test_get_realm_status_returns_data(self, api):
        data = api.post("realmManager/getRealmStatus")
        assert "realmStatus" in data

    def test_realm_status_value(self, api):
        data = api.post("realmManager/getRealmStatus")
        valid_states = {
            "UNKNOWN", "AVAILABLE", "WARNING", "FAILURE",
            "PARTIAL_FAILURE", "NOT_LICENSED", "DEACTIVATED", "NOT_AVAILABLE",
        }
        assert data.get("realmStatus") in valid_states, (
            f"Unexpected realmStatus: {data.get('realmStatus')}"
        )

    def test_realm_is_not_failed(self, api):
        """In a working environment the realm should not be in FAILURE."""
        data = api.post("realmManager/getRealmStatus")
        assert data.get("realmStatus") not in ("FAILURE", "NOT_AVAILABLE"), (
            f"Realm is in bad state: {data.get('realmStatus')}"
        )


@pytest.mark.status
class TestSystemStatus:
    """statusLogManager system status endpoints."""

    def test_list_system_status(self, api):
        data = api.post("statusLogManager/listSystemStatus")
        assert data.get("status") != "FAILURE"

    def test_list_realm_summary_state(self, api):
        data = api.post("statusLogManager/listRealmSummaryState")
        assert data.get("status") != "FAILURE"

    def test_list_storage_utilization(self, api):
        data = api.post("statusLogManager/listStorageUtilizationStatus")
        assert data.get("status") != "FAILURE"

    def test_list_storage_mount_status(self, api):
        data = api.post("statusLogManager/listStorageMountStatus")
        assert data.get("status") != "FAILURE"

    def test_list_org_storage_status(self, api):
        data = api.post("statusLogManager/listOrganizationStorageStatus")
        assert data.get("status") != "FAILURE"


@pytest.mark.status
class TestNodeMonitoring:
    """Node and service monitoring."""

    def test_list_nodes(self, api):
        data = api.post("realmManager/listNodes")
        assert data.get("status") != "FAILURE"

    def test_list_services(self, api):
        data = api.post("realmManager/listServices")
        assert data.get("status") != "FAILURE"

    def test_list_jobs(self, api):
        data = api.post("realmManager/listJobs")
        assert data.get("status") != "FAILURE"

    def test_list_logged_in_users(self, api):
        data = api.post("realmManager/listLoggedInUsers")
        assert data.get("status") != "FAILURE"


@pytest.mark.status
class TestLicenseInfo:
    """License and version checks."""

    def test_get_license_info(self, api):
        data = api.post("realmManager/getLicenseInfo")
        assert data.get("status") != "FAILURE"

    def test_get_licensed_features(self, api):
        data = api.post("realmManager/getLicensedFeatures")
        assert data.get("status") != "FAILURE"

    def test_get_version(self, api):
        data = api.post("realmManager/getVersion")
        assert "sessionToken" in data
