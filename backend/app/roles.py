"""Single source of truth for VCMS role tiers."""

FULL_ROLES = ("admin", "general_manager", "operation_manager", "hr_assistant")
MANAGER_ROLES = ("main_sup", "wshc_lead")
SUPERVISOR_ROLES = ("site_sup", "safety_sup", "wshc", "logistics_sup")
ATTENDANCE_ROLES = FULL_ROLES + MANAGER_ROLES + SUPERVISOR_ROLES
COORDINATOR_ROLES = FULL_ROLES + MANAGER_ROLES
ALL_ROLES = FULL_ROLES + MANAGER_ROLES + SUPERVISOR_ROLES + ("payroll",)

