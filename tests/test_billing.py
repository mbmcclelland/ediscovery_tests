"""
Tests for billing and reporting endpoints.
"""

import pytest

from helpers.api_client import APIError
from conftest import skip_on_permission_or_error


@pytest.mark.smoke
class TestBillingReportSettings:
    """Billing report configuration."""

    def test_get_billing_report_settings(self, api):
        """List billing report settings (may require specific permissions)."""
        try:
            data = api.post("projectManager/listBillingReportSettings")
            assert data.get("status") != "FAILURE"
        except APIError as e:
            if e.error_code == "PERMISSION_DENIED":
                pytest.skip(f"User lacks billing permissions: {e.extended_status}")
            raise


class TestProjectReports:
    """Project-level report settings and retrieval."""

    @skip_on_permission_or_error
    def test_list_billing_report_settings(self, api):
        data = api.post("projectManager/listBillingReportSettings")
        assert data.get("status") != "FAILURE"

    @pytest.mark.xfail(
        reason="Server NumberFormatException on null string — see BUG_LOG B34. "
               "No request-body shape recovers; tracked as a server-side defect.",
        strict=False,
    )
    @skip_on_permission_or_error
    def test_list_report_settings(self, api):
        data = api.post("projectManager/listReportSettings")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_get_email_report_delivery_settings(self, api):
        data = api.post("projectManager/getEmailReportDeliverySettings")
        assert data.get("status") != "FAILURE"


class TestStorageReports:
    """Realm-level storage and migration reports."""

    def test_get_storage_usage_download_url(self, api):
        data = api.post("realmManager/getStorageUsageDownloadUrl")
        assert data.get("status") != "FAILURE"

    def test_get_migration_quota_report(self, api):
        data = api.post("realmManager/getMigrationQuotaReport")
        assert data.get("status") != "FAILURE"

    def test_get_migration_quota_report_url(self, api):
        data = api.post("realmManager/getMigrationQuotaReportUrl")
        assert data.get("status") != "FAILURE"

    def test_get_migration_quota_notification(self, api):
        data = api.post("realmManager/getMigrationQuotaNotification")
        assert data.get("status") != "FAILURE"
