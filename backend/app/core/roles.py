"""Canonical VCMS role catalogue and permission tiers.

Keep this module synchronized with db/migrations and frontend/js/config.js.
"""

FULL_ROLES = ("admin", "general_manager", "operation_manager", "hr_assistant")
MANAGER_ROLES = ("main_sup", "wshc_lead")
SUPERVISOR_ROLES = ("site_sup", "safety_sup", "wshc", "logistics_sup")
PAYROLL_ROLES = ("payroll",)

ALL_ROLES = FULL_ROLES + MANAGER_ROLES + SUPERVISOR_ROLES + PAYROLL_ROLES
ATTENDANCE_ROLES = FULL_ROLES + MANAGER_ROLES + SUPERVISOR_ROLES
COORDINATOR_ROLES = FULL_ROLES + MANAGER_ROLES
PROJECT_ADMIN_ROLES = FULL_ROLES + MANAGER_ROLES
PROJECT_ALL_PROJECTS_ROLES = FULL_ROLES + MANAGER_ROLES + PAYROLL_ROLES


def is_known_role(role: str) -> bool:
    return role in ALL_ROLES


def can_administer_projects(role: str) -> bool:
    return role in PROJECT_ADMIN_ROLES


def can_view_all_projects(role: str) -> bool:
    return role in PROJECT_ALL_PROJECTS_ROLES
