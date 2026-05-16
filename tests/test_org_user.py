"""
Tests that require an org-scoped user (e.g. admin@training).

These use the `api_org` fixture which logs in with
DR_ORG_USERNAME / DR_ORG_PASSWORD / DR_ORG_ORGANIZATION.

Run just these:  pytest -m org_user -v
"""

import pytest

from conftest import skip_on_permission_or_error


@pytest.mark.org_user
class TestOrgUserConnectors:
    """Connector operations that require org-level permissions."""

    def test_list_connectors(self, api_org):
        data = api_org.post("orgManager/listConnectors")
        assert data.get("status") != "FAILURE"

    def test_list_connector_types(self, api_org):
        data = api_org.post("orgManager/listConnectorTypes")
        assert data.get("status") != "FAILURE"


@pytest.mark.org_user
class TestOrgUserProjects:
    """Project and user operations that require org-level permissions."""

    def test_list_projects(self, api_org):
        data = api_org.post("orgManager/listProjects")
        assert data.get("status") != "FAILURE"
        assert "projects" in data

    @skip_on_permission_or_error
    def test_list_users_and_groups(self, api_org):
        data = api_org.post("orgManager/listUsersAndGroups")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_list_roles(self, api_org):
        data = api_org.post("orgManager/listRoles")
        assert data.get("status") != "FAILURE"


@pytest.mark.org_user
class TestOrgUserResources:
    """Org resources that require org-level permissions."""

    def test_list_corpora(self, api_org):
        data = api_org.post("orgManager/listCorpora")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_list_export_data_areas(self, api_org):
        data = api_org.post("orgManager/listExportDataAreas")
        assert data.get("status") != "FAILURE"

    def test_list_export_database_connections(self, api_org):
        data = api_org.post("orgManager/listExportDatabaseConnections")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_list_models(self, api_org):
        data = api_org.post("orgManager/listModels")
        assert data.get("status") != "FAILURE"


@pytest.mark.org_user
class TestOrgUserBilling:
    """Billing operations that require org-level permissions."""

    @skip_on_permission_or_error
    def test_list_billing_report_settings(self, api_org):
        data = api_org.post("projectManager/listBillingReportSettings")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_get_email_report_delivery_settings(self, api_org):
        data = api_org.post("projectManager/getEmailReportDeliverySettings")
        assert data.get("status") != "FAILURE"
