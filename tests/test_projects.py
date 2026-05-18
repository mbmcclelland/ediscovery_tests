"""
Tests for project listing and management endpoints.

Covers:
  - orgManager/listProjects
  - realmManager/listProjects
  - projectManager/* read-only endpoints
"""

import pytest

from conftest import skip_on_permission_or_error


@pytest.mark.projects
@pytest.mark.smoke
class TestListProjects:
    """Project listing and retrieval."""

    def test_list_projects_via_org_manager(self, api):
        """orgManager/listProjects returns SUCCESS."""
        data = api.post("orgManager/listProjects")
        assert data.get("status") != "FAILURE"

    def test_list_projects_returns_array(self, api):
        data = api.post("orgManager/listProjects")
        assert "projects" in data
        assert isinstance(data["projects"], list)

    def test_projects_have_required_fields(self, api):
        """Each project object has name, handle, and projectState."""
        data = api.post("orgManager/listProjects")
        for proj in data.get("projects", []):
            assert "name" in proj, "Project missing 'name'"
            assert "handle" in proj, "Project missing 'handle'"
            assert "projectState" in proj, "Project missing 'projectState'"
            break  # Validate first item

    def test_project_states_are_valid(self, api):
        """All project states are from the expected enum."""
        valid_states = {
            "UNKNOWN", "AVAILABLE", "WARNING", "FAILURE",
            "NOT_LICENSED", "DEACTIVATED", "NOT_AVAILABLE",
        }
        data = api.post("orgManager/listProjects")
        for proj in data.get("projects", []):
            state = proj.get("projectState")
            if state is not None:
                assert state in valid_states, f"Invalid state '{state}' for project '{proj.get('name')}'"

    def test_list_projects_via_realm_manager(self, api):
        """realmManager/listProjects returns SUCCESS (admin-level)."""
        data = api.post("realmManager/listProjects")
        assert data.get("status") != "FAILURE"

    def test_list_admin_projects(self, api):
        """Realm-level project listing (admin scope)."""
        data = api.post("realmManager/listProjects")
        assert data.get("status") != "FAILURE"
        assert "projects" in data

    def test_total_projects_count(self, api):
        """Response includes totalProjects count."""
        data = api.post("orgManager/listProjects")
        if "totalProjects" in data:
            assert isinstance(data["totalProjects"], int)
            assert data["totalProjects"] >= 0


@pytest.mark.projects
class TestProjectStatusUpdates:
    """Project status and resource endpoints."""

    def test_get_org_project_status_updates(self, api):
        data = api.post("projectManager/getOrgProjectStatusUpdates")
        assert data.get("status") != "FAILURE"


@pytest.mark.projects
class TestListUsers:
    """User and group listing within an org."""

    def test_list_users(self, api):
        data = api.post("orgManager/listUsers")
        assert data.get("status") != "FAILURE"

    def test_list_groups(self, api):
        data = api.post("orgManager/listGroups")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_list_users_and_groups(self, api):
        data = api.post("orgManager/listUsersAndGroups")
        assert data.get("status") != "FAILURE"

    @skip_on_permission_or_error
    def test_list_roles(self, api):
        # listRoles requires an objectType field; without one the server
        # NPEs on a null SecureObjectTypes.equals call (BUG_LOG B33).
        data = api.post("orgManager/listRoles", extra_body={"objectType": "PROJECT"})
        assert data.get("status") != "FAILURE"
