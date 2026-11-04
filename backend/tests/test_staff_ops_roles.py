"""SUPERVISOR and TIME_OFFICE roles, and the Python/SQL matrix agreement.

The permission matrix is defined twice: in `PERMISSION_MATRIX` for API checks
and in `rbac_has_permission()` for row-level security. Nothing stops the two
drifting apart, and when they do the symptom is a confusing 404 rather than an
error. `TestMatrixMatchesSQL` parses the migration and compares, so a change
to one without the other fails here instead of in production.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.rbac_service import (
    ALL_PERMISSIONS,
    PERMISSION_MATRIX,
    ROLE_ALIASES,
    canonical_role,
    has_permission,
    permissions_for,
)

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
ROLES_SQL = MIGRATIONS / "066_staff_ops_roles.sql"


class TestRolesExist:
    def test_both_new_roles_are_defined(self):
        assert "SUPERVISOR" in PERMISSION_MATRIX
        assert "TIME_OFFICE" in PERMISSION_MATRIX

    def test_ten_canonical_roles(self):
        assert set(PERMISSION_MATRIX) == {
            "OWNER", "GROUP_ADMIN_HR", "GENERAL_MANAGER", "HR_MANAGER",
            "DEPARTMENT_HEAD", "SUPERVISOR", "TIME_OFFICE", "RECRUITER",
            "EMPLOYEE", "CANDIDATE",
        }

    def test_no_role_grants_an_unknown_permission(self):
        for role, perms in PERMISSION_MATRIX.items():
            unknown = perms - ALL_PERMISSIONS
            assert not unknown, f"{role} grants undefined permission(s): {unknown}"

    def test_every_alias_points_at_a_real_role(self):
        for alias, role in ROLE_ALIASES.items():
            assert role in PERMISSION_MATRIX, f"alias {alias} -> unknown role {role}"


class TestSupervisor:
    def test_runs_attendance(self):
        assert has_permission("SUPERVISOR", "attendance.read")
        assert has_permission("SUPERVISOR", "attendance.manage")

    def test_can_approve_leave(self):
        # PLAN decision 2: a supervisor may approve, or escalate.
        assert has_permission("SUPERVISOR", "leave.manage")

    def test_cannot_touch_pay(self):
        for permission in ("payroll.read", "payroll.manage",
                           "financial.read", "financial.manage"):
            assert not has_permission("SUPERVISOR", permission), permission

    def test_cannot_manage_employee_records(self):
        assert has_permission("SUPERVISOR", "employees.read")
        assert not has_permission("SUPERVISOR", "employees.manage")

    def test_cannot_touch_recruiting(self):
        for permission in ("candidates.manage", "jobs.manage", "applications.manage"):
            assert not has_permission("SUPERVISOR", permission), permission

    @pytest.mark.parametrize("alias", ["supervisor", "shift_incharge", "captain", "floor_supervisor"])
    def test_aliases_resolve(self, alias):
        assert canonical_role(alias) == "SUPERVISOR"


class TestTimeOffice:
    def test_can_record_attendance(self):
        # Manual punch, mark late, flag no-show (PLAN decision 3).
        assert has_permission("TIME_OFFICE", "attendance.read")
        assert has_permission("TIME_OFFICE", "attendance.manage")

    def test_can_identify_staff_at_the_gate(self):
        assert has_permission("TIME_OFFICE", "employees.read")

    def test_has_no_leave_payroll_or_reports(self):
        for permission in ("leave.read", "leave.manage", "payroll.read",
                           "payroll.manage", "reports.read", "reports.financial"):
            assert not has_permission("TIME_OFFICE", permission), permission

    def test_is_narrower_than_supervisor(self):
        assert permissions_for("TIME_OFFICE") < permissions_for("SUPERVISOR")

    @pytest.mark.parametrize("alias", ["time_office", "security", "gate", "security_desk"])
    def test_aliases_resolve(self, alias):
        assert canonical_role(alias) == "TIME_OFFICE"


class TestFailClosed:
    def test_unknown_role_is_candidate(self):
        assert canonical_role("chief_vibes_officer") == "CANDIDATE"

    def test_missing_role_is_candidate(self):
        assert canonical_role(None) == "CANDIDATE"

    def test_candidate_cannot_reach_attendance(self):
        assert not has_permission("CANDIDATE", "attendance.manage")


def _sql_permissions(role: str) -> set[str]:
    """Pull one role's permission array out of rbac_has_permission()."""
    sql = ROLES_SQL.read_text(encoding="utf-8")
    match = re.search(
        rf"IF r = '{role}' THEN RETURN permission = ANY\(ARRAY\[(.*?)\]\)", sql, re.S)
    if not match:
        return set()
    return set(re.findall(r"'([a-z_]+\.[a-z_]+)'", match.group(1)))


class TestMatrixMatchesSQL:
    """The Python matrix and the RLS function must not drift apart."""

    # Pre-existing drift, found by this test on the day it was written:
    # performance.*, training.* and career.* were added to PERMISSION_MATRIX
    # when those features shipped, but never added to rbac_has_permission().
    # The API therefore allows what RLS denies, and the symptom is an empty
    # result rather than a 403. Correcting it WIDENS database permissions, so
    # it is recorded here rather than fixed silently. When someone does fix
    # the SQL, these flip to XPASS and the marks should be removed.
    _KNOWN_DRIFT = pytest.mark.xfail(
        reason="pre-existing: performance/training/career missing from rbac_has_permission()",
        strict=True,
    )

    @pytest.mark.parametrize("role", [
        pytest.param("GENERAL_MANAGER", marks=_KNOWN_DRIFT),
        pytest.param("HR_MANAGER", marks=_KNOWN_DRIFT),
        pytest.param("DEPARTMENT_HEAD", marks=_KNOWN_DRIFT),
        pytest.param("EMPLOYEE", marks=_KNOWN_DRIFT),
        "SUPERVISOR", "TIME_OFFICE", "RECRUITER",
    ])
    def test_sql_matches_python(self, role):
        sql_perms = _sql_permissions(role)
        py_perms = PERMISSION_MATRIX[role]
        assert sql_perms, f"{role} missing from rbac_has_permission()"
        assert sql_perms == py_perms, (
            f"{role} drifted.\n"
            f"  only in SQL   : {sorted(sql_perms - py_perms)}\n"
            f"  only in Python: {sorted(py_perms - sql_perms)}"
        )

    def test_sql_canonicaliser_knows_both_new_roles(self):
        sql = ROLES_SQL.read_text(encoding="utf-8")
        canonical = re.search(r"FUNCTION canonical_user_role.*?\$\$;", sql, re.S).group(0)
        for alias in ("supervisor", "shift_incharge", "captain", "floor_supervisor",
                      "time_office", "security", "gate", "security_desk"):
            assert f"'{alias}'" in canonical, f"SQL canonicaliser missing alias {alias}"
        assert "'SUPERVISOR','TIME_OFFICE'" in canonical.replace(" ", "")

    def test_sql_aliases_match_python_aliases(self):
        sql = ROLES_SQL.read_text(encoding="utf-8")
        canonical = re.search(r"FUNCTION canonical_user_role.*?\$\$;", sql, re.S).group(0)
        pairs = dict(re.findall(r"WHEN '([a-z_]+)' THEN '([A-Z_]+)'", canonical))
        assert pairs == {k: v for k, v in ROLE_ALIASES.items() if k != "candidate"}

    def test_supervisor_is_department_scoped_in_sql(self):
        sql = ROLES_SQL.read_text(encoding="utf-8")
        scoping = re.search(r"FUNCTION rbac_department_access.*?\$\$;", sql, re.S).group(0)
        assert "SUPERVISOR" in scoping, "supervisors would see every department"
        assert "DEPARTMENT_HEAD" in scoping
