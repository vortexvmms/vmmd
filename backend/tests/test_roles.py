from app.core.roles import (
    ALL_ROLES,
    FULL_ROLES,
    MANAGER_ROLES,
    PROJECT_ADMIN_ROLES,
    PROJECT_ALL_PROJECTS_ROLES,
    SUPERVISOR_ROLES,
    can_administer_projects,
    can_view_all_projects,
)


def test_role_catalogue_has_no_duplicates():
    assert len(ALL_ROLES) == len(set(ALL_ROLES))


def test_project_administrators_are_management_tiers():
    assert PROJECT_ADMIN_ROLES == FULL_ROLES + MANAGER_ROLES
    assert all(can_administer_projects(role) for role in PROJECT_ADMIN_ROLES)
    assert not any(can_administer_projects(role) for role in SUPERVISOR_ROLES + ("payroll",))


def test_all_project_visibility_is_explicit():
    assert all(can_view_all_projects(role) for role in FULL_ROLES + MANAGER_ROLES + ("payroll",))
    assert not any(can_view_all_projects(role) for role in SUPERVISOR_ROLES)
