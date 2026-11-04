"""Leaving the hotel revokes access immediately.

The check lives in build_access_context, which re-reads the users row on every
request, so revocation takes effect on the next API call rather than when a
token happens to expire.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.rbac_service import (
    EXITED_EMPLOYMENT_STATUSES,
    EXITED_PERMISSIONS,
    AccessContext,
    authorize,
    build_access_context,
    serialize_context,
)

MIGRATION = (Path(__file__).resolve().parents[2]
             / "supabase" / "migrations" / "068_staff_ops_exit_revokes_access.sql")


class FakeResult:
    def __init__(self, data): self.data = data


class FakeTable:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self): return FakeResult(self._rows)


class FakeSupabase:
    """Minimal stand-in: one users row and one memberships row."""

    def __init__(self, user_row, memberships=None):
        self._user = user_row
        self._memberships = memberships if memberships is not None else [
            {"property_id": "prop-1", "department_id": "dept-1", "is_active": True},
        ]

    def table(self, name):
        return FakeTable([self._user] if name == "users" else self._memberships)


def context_for(role="DEPARTMENT_HEAD", status=None) -> AccessContext:
    return build_access_context(
        FakeSupabase({
            "id": "user-1", "org_id": "org-1", "role": role,
            "department_id": "dept-1", "active_property_id": "prop-1",
            "employment_status": status,
        }),
        {"sub": "user-1"},
    )


class TestActiveEmployeeUnaffected:
    def test_active_keeps_full_permissions(self):
        ctx = context_for("DEPARTMENT_HEAD", "ACTIVE")
        assert ctx.is_exited is False
        assert "attendance.manage" in ctx.permissions
        assert "leave.manage" in ctx.permissions

    def test_null_status_is_treated_as_active(self):
        # Every existing row predates the column being populated.
        ctx = context_for("HR_MANAGER", None)
        assert ctx.is_exited is False
        assert "employees.manage" in ctx.permissions

    def test_empty_string_is_treated_as_active(self):
        assert context_for("HR_MANAGER", "").is_exited is False

    def test_on_notice_keeps_working(self):
        # Serving notice is still working: they need their roster.
        ctx = context_for("SUPERVISOR", "ON_NOTICE")
        assert ctx.is_exited is False
        assert "attendance.manage" in ctx.permissions


class TestExitRevokes:
    @pytest.mark.parametrize("status", sorted(EXITED_EMPLOYMENT_STATUSES))
    def test_every_exit_status_revokes(self, status):
        ctx = context_for("DEPARTMENT_HEAD", status)
        assert ctx.is_exited is True
        assert ctx.permissions == EXITED_PERMISSIONS

    def test_alumni_is_revoked(self):
        # What the existing exit flow actually writes.
        assert context_for("GENERAL_MANAGER", "ALUMNI").is_exited is True

    def test_left_and_absconding_are_revoked(self):
        # What Staff Ops profiles write.
        assert context_for("SUPERVISOR", "LEFT").is_exited is True
        assert context_for("SUPERVISOR", "ABSCONDING").is_exited is True

    def test_status_match_is_case_insensitive(self):
        assert context_for("EMPLOYEE", "left").is_exited is True
        assert context_for("EMPLOYEE", "  Alumni  ").is_exited is True

    def test_departed_manager_loses_operational_access(self):
        ctx = context_for("DEPARTMENT_HEAD", "LEFT")
        for permission in ("attendance.manage", "attendance.read", "leave.manage",
                           "employees.read", "reports.read", "properties.read"):
            assert permission not in ctx.permissions, permission

    def test_departed_owner_loses_everything_too(self):
        ctx = context_for("OWNER", "ALUMNI")
        assert ctx.permissions == EXITED_PERMISSIONS
        assert "employees.manage" not in ctx.permissions

    def test_role_is_kept_for_audit(self):
        # The role is retained for display and history; permissions are what
        # was emptied, so logs still show who the person had been.
        assert context_for("GENERAL_MANAGER", "LEFT").role == "GENERAL_MANAGER"


class TestStatutorySelfService:
    """An Indian employer still owes payslips and Form 16 after someone leaves."""

    def test_own_payslips_still_reachable(self):
        ctx = context_for("EMPLOYEE", "ALUMNI")
        authorize(ctx, "payroll.read", owner_user_id="user-1")

    def test_own_documents_still_reachable(self):
        ctx = context_for("EMPLOYEE", "ALUMNI")
        authorize(ctx, "documents.read", owner_user_id="user-1")

    def test_cannot_read_somebody_elses_payslip(self):
        ctx = context_for("DEPARTMENT_HEAD", "LEFT")
        with pytest.raises(HTTPException) as exc:
            authorize(ctx, "payroll.read", owner_user_id="someone-else")
        assert exc.value.status_code == 403

    def test_departed_owner_gets_no_org_wide_bypass(self):
        # A former OWNER must not keep the blanket exemption in authorize().
        ctx = context_for("OWNER", "ALUMNI")
        with pytest.raises(HTTPException):
            authorize(ctx, "documents.read", owner_user_id="someone-else")

    def test_revoked_permission_is_refused(self):
        ctx = context_for("HR_MANAGER", "LEFT")
        with pytest.raises(HTTPException) as exc:
            authorize(ctx, "attendance.manage")
        assert exc.value.status_code == 403


class TestSerialisation:
    def test_exit_state_is_exposed_to_the_frontend(self):
        payload = serialize_context(context_for("SUPERVISOR", "LEFT"))
        assert payload["isExited"] is True
        assert payload["employmentStatus"] == "LEFT"
        assert payload["permissions"] == sorted(EXITED_PERMISSIONS)

    def test_active_user_serialises_as_not_exited(self):
        payload = serialize_context(context_for("SUPERVISOR", "ACTIVE"))
        assert payload["isExited"] is False


class TestSqlMirrorsPython:
    """Migration 068 must revoke the same statuses and grant the same crumbs."""

    def test_sql_exit_statuses_match_python(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        fn = re.search(r"FUNCTION current_user_has_exited.*?\$\$;", sql, re.S).group(0)
        # Only the IN (...) list; COALESCE(..., 'ACTIVE') is the default, not
        # an exit status, and must not be swept up.
        in_list = re.search(r"\bIN \((.*?)\)", fn, re.S).group(1)
        sql_statuses = set(re.findall(r"'([A-Z_]+)'", in_list))
        assert sql_statuses == set(EXITED_EMPLOYMENT_STATUSES), (
            f"only in SQL: {sorted(sql_statuses - EXITED_EMPLOYMENT_STATUSES)}, "
            f"only in Python: {sorted(EXITED_EMPLOYMENT_STATUSES - sql_statuses)}")

    def test_sql_grants_the_same_statutory_permissions(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        branch = re.search(
            r"IF current_user_has_exited\(\) THEN\s*RETURN permission = ANY\(ARRAY\[(.*?)\]\)",
            sql, re.S).group(1)
        assert set(re.findall(r"'([a-z_.]+)'", branch)) == set(EXITED_PERMISSIONS)

    def test_on_notice_does_not_revoke_in_sql(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        fn = re.search(r"FUNCTION current_user_has_exited.*?\$\$;", sql, re.S).group(0)
        assert "ON_NOTICE" not in fn

    def test_trigger_reinstates_on_rehire(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        assert "'ACTIVE', 'ON_NOTICE'" in sql and "employment_status = 'ACTIVE'" in sql
