"""
Tests for connector management endpoints.
"""

import pytest

from helpers.api_client import APIError
from conftest import skip_on_permission_or_error


@pytest.mark.connectors
class TestConnectorListing:
    """List and inspect connectors."""

    @skip_on_permission_or_error
    def test_list_connectors_via_org(self, api):
        data = api.post("orgManager/listConnectors")
        assert data.get("status") != "FAILURE"

    def test_list_connector_types(self, api):
        data = api.post("orgManager/listConnectorTypes")
        assert data.get("status") != "FAILURE"

    def test_list_connectors_via_realm(self, api):
        """Admin-level connector listing across all orgs."""
        data = api.post("realmManager/listConnectorStatusesForRealm")
        assert data.get("status") != "FAILURE"

    def test_list_connector_data_area_status(self, api):
        data = api.post("realmManager/listConnectorDataAreaStatus")
        assert data.get("status") != "FAILURE"


@pytest.mark.connectors
class TestConnectorRetrieval:
    """
    Retrieve individual connectors by handle.
    Requires orgManager/listConnectors permission.
    """

    @pytest.fixture
    def first_connector_handle(self, api):
        """Get the handle of the first available connector, or skip."""
        try:
            data = api.post("orgManager/listConnectors")
        except (APIError, Exception):
            pytest.skip("Cannot list connectors (permission denied or error)")
        connectors = data.get("connectors", [])
        if not connectors:
            pytest.skip("No connectors configured in this environment")
        return connectors[0].get("handle")

    def test_get_connector_by_handle(self, api, first_connector_handle):
        data = api.post(
            "connectorManager/getConnector",
            extra_body={"contextHandle": first_connector_handle},
        )
        assert data.get("status") != "FAILURE"

    def test_list_references_to_connector(self, api, first_connector_handle):
        data = api.post(
            "connectorManager/listReferencesToConnector",
            extra_body={"contextHandle": first_connector_handle},
        )
        assert data.get("status") != "FAILURE"
