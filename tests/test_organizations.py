"""
Tests for organization-level endpoints.
"""

import pytest

from conftest import skip_on_permission_or_error


@pytest.mark.orgs
@pytest.mark.smoke
class TestListOrganizations:
    """Organization listing and lookup."""

    def test_list_organizations(self, api):
        data = api.post("realmManager/listOrganizations")
        assert "organizations" in data
        assert isinstance(data["organizations"], list)

    def test_organizations_have_names(self, api):
        data = api.post("realmManager/listOrganizations")
        for org in data.get("organizations", []):
            assert "name" in org and org["name"], "Org missing name"
            assert "handle" in org, "Org missing handle"
            break

    def test_list_organization_names(self, api):
        data = api.post("realmManager/listOrganizationNames")
        assert data.get("status") != "FAILURE"

    def test_find_organization(self, api):
        """Verify at least one organization exists in the system."""
        data = api.post("realmManager/listOrganizations")
        orgs = data.get("organizations", [])
        assert len(orgs) > 0, "Expected at least one organization"
        for org in orgs:
            assert "name" in org and org["name"], "Org missing name"


@pytest.mark.orgs
class TestOrgResources:
    """Resources within an organization: connectors, corpora, data areas."""

    @skip_on_permission_or_error
    def test_list_connectors(self, api):
        data = api.post("orgManager/listConnectors")
        assert data.get("status") != "FAILURE"

    def test_list_connector_types(self, api):
        data = api.post("orgManager/listConnectorTypes")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_list_corpora(self, api):
        data = api.post("orgManager/listCorpora")
        assert data.get("status") != "FAILURE"

    def test_list_data_areas(self, api):
        data = api.post("orgManager/listDataAreas")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_list_export_data_areas(self, api):
        data = api.post("orgManager/listExportDataAreas")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_list_export_database_connections(self, api):
        data = api.post("orgManager/listExportDatabaseConnections")
        assert data.get("status") != "FAILURE"

    def test_list_templates(self, api):
        data = api.post("orgManager/listTemplates")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_list_models(self, api):
        data = api.post("orgManager/listModels")
        assert data.get("status") != "FAILURE"
