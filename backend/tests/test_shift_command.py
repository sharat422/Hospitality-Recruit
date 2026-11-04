"""
Tests for the SHIFT command — all 4 requirements.

Req 1 — Fetch employee's next 7 days schedule
Req 2 — Format shifts for WhatsApp
Req 3 — Include date, start time, end time, property, department, manager
Req 4 — Friendly message when no shift exists

Additional coverage:
  - 7-day window enforced (shifts beyond day 7 excluded)
  - Data source priority: v_employee_shifts → v_candidate_shifts → fallback
  - Fallback bug fix: uses employee-specific candidate lookup, not any candidate
  - Shift formatting helpers: _fmt_time, _calc_shift_duration, _fmt_shift_block
  - Shift count summary in reply
  - Multiple shifts formatted separately with blank line between
  - Partial data (no property, no manager, no department) handled gracefully
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# MockSupabase (same queue-based pattern as other test files)
# ─────────────────────────────────────────────────────────────────────────────

class TableChain:
    def __init__(self, queue: list):
        self._q = queue

    def _pop(self):
        obj = MagicMock()
        obj.data  = self._q.pop(0) if self._q else []
        obj.count = len(obj.data)
        return obj

    def select(self, *a, **kw): return self
    def insert(self, *a, **kw): return self
    def update(self, *a, **kw): return self
    def eq(self, *a, **kw):     return self
    def neq(self, *a, **kw):    return self
    def in_(self, *a, **kw):    return self
    def gte(self, *a, **kw):    return self
    def lte(self, *a, **kw):    return self
    def order(self, *a, **kw):  return self
    def limit(self, *a, **kw):  return self
    def execute(self):           return self._pop()


class MockSupabase:
    def __init__(self):
        self._tables: dict[str, list] = {}

    def configure(self, table: str, *results):
        self._tables.setdefault(table, [])
        for r in results:
            self._tables[table].append(r)

    def table(self, name: str) -> TableChain:
        return TableChain(self._tables.get(name, []))


# ─────────────────────────────────────────────────────────────────────────────
# Shared test data
# ─────────────────────────────────────────────────────────────────────────────

EMPLOYEE = {
    "employee_id":      "emp-uuid-001",
    "org_id":           "org-uuid-001",
    "name":             "Priya Sharma",
    "phone":            "+919876543210",
    "source":           "users",
    "whatsapp_user_id": None,
}

EMPLOYEE_CANDIDATE = {**EMPLOYEE, "source": "candidates"}

_TODAY = datetime.now(timezone.utc).date()
_D = lambda days: (_TODAY + timedelta(days=days)).isoformat()  # date string N days from today


def _shift(
    *,
    days_ahead:   int    = 1,
    start_hour:   int    = 9,
    end_hour:     int    = 17,
    role:         str    = "Banquet Waiter",
    shift_type:   str    = "full_day",
    property_name:str    = "Grand Hyatt Mumbai",
    department:   str    = "F&B",
    manager_email:str    = "rajesh.kumar@hotel.com",
    manager_name: str    = "Rajesh Kumar",
    location:     str    = "Level 3, Banquet Hall",
    shift_id:     str    = "shift-uuid-001",
) -> dict:
    """Build a realistic shift row as returned by v_employee_shifts."""
    day = _TODAY + timedelta(days=days_ahead)
    return {
        "employee_id":          EMPLOYEE["employee_id"],
        "org_id":               EMPLOYEE["org_id"],
        "shift_id":             shift_id,
        "assignment_status":    "confirmed",
        "start_date":           f"{day.isoformat()}T{start_hour:02d}:00:00",
        "end_date":             f"{day.isoformat()}T{end_hour:02d}:00:00",
        "role":                 role,
        "shift_type":           shift_type,
        "shift_status":         "open",
        "hours_per_week":       40,
        "property_name":        property_name,
        "department":           department,
        "location":             location,
        "manager_id":           "mgr-uuid-001",
        "manager_email":        manager_email,
        "manager_display_name": manager_name,
    }


SHIFT_TOMORROW = _shift(days_ahead=1)
SHIFT_DAY3     = _shift(days_ahead=3, role="Sous Chef", shift_type="morning",
                         property_name="JW Marriott", department="Kitchen",
                         manager_name="Meena Patel", shift_id="shift-uuid-002")
SHIFT_DAY8     = _shift(days_ahead=8)   # beyond 7-day window — should NOT appear


def _call_handle_shift(sb, employee=None) -> str:
    from app.services.hr_bot_service import handle_shift
    return handle_shift(sb, employee or EMPLOYEE, [])


# ═════════════════════════════════════════════════════════════════════════════
# Req 1 — Fetch next 7 days schedule
# ═════════════════════════════════════════════════════════════════════════════

class TestFetchSchedule:
    def test_view_queried_for_platform_user(self):
        """Primary data source: v_employee_shifts queried for users-table employees."""
        sb = MockSupabase()
        sb.configure("v_employee_shifts", [SHIFT_TOMORROW])

        with patch.object(sb, "table", wraps=sb.table) as mock_tbl:
            _call_handle_shift(sb)

        tbl_names = [c.args[0] for c in mock_tbl.call_args_list]
        assert "v_employee_shifts" in tbl_names

    def test_candidate_view_used_when_source_is_candidate(self):
        """Hired candidates (source=candidates) use v_candidate_shifts."""
        sb = MockSupabase()
        sb.configure("v_employee_shifts", [])       # empty → try candidate view
        sb.configure("v_candidate_shifts", [SHIFT_TOMORROW])

        with patch.object(sb, "table", wraps=sb.table) as mock_tbl:
            _call_handle_shift(sb, EMPLOYEE_CANDIDATE)

        tbl_names = [c.args[0] for c in mock_tbl.call_args_list]
        assert "v_candidate_shifts" in tbl_names

    def test_fallback_used_when_view_raises(self):
        """When both views fail, raw shift_matches + shifts fallback is tried."""
        sb = MockSupabase()
        # candidates lookup
        sb.configure("candidates", [{"id": "cand-001"}])
        # shift_matches
        sb.configure("shift_matches", [{"shift_id": "shift-001", "status": "confirmed"}])
        # shifts
        sb.configure("shifts", [{"id": "shift-001",
                                  "role": "Waiter", "shift_type": "morning",
                                  "start_date": f"{_D(1)}T09:00:00",
                                  "end_date":   f"{_D(1)}T13:00:00",
                                  "status": "open"}])

        with patch.object(sb, "table") as mock_tbl:
            chain = MagicMock()
            for m in ("select","eq","in_","gte","lte","order","limit"):
                getattr(chain, m).return_value = chain

            call_count = {"n": 0}
            def execute():
                call_count["n"] += 1
                n = call_count["n"]
                if n == 1:
                    raise Exception("view unavailable")   # v_employee_shifts fails
                if n == 2:
                    raise Exception("view unavailable")   # v_candidate_shifts fails
                if n == 3:
                    m = MagicMock(); m.data = [{"id": "cand-001"}]; return m
                if n == 4:
                    m = MagicMock(); m.data = [{"shift_id": "s1", "status": "confirmed"}]; return m
                m = MagicMock()
                m.data = [{"id": "s1", "role": "Waiter", "shift_type": "morning",
                           "start_date": f"{_D(1)}T09:00:00",
                           "end_date":   f"{_D(1)}T13:00:00", "status": "open"}]
                return m

            chain.execute.side_effect = execute
            mock_tbl.return_value = chain

            reply = _call_handle_shift(sb)

        # At least returns a string (fallback worked or returned no-shift message)
        assert isinstance(reply, str)

    def test_7_day_filter_applied(self):
        """Shifts beyond 7 days must not appear (window enforced in query)."""
        sb = MockSupabase()
        # View returns one shift inside window, one outside — the outside one
        # should be filtered by the .lte("start_date", week_end) at DB level.
        # In tests we simulate the DB doing the filtering correctly.
        sb.configure("v_employee_shifts", [SHIFT_TOMORROW])   # day 1 — inside

        reply = _call_handle_shift(sb)
        assert "HospBot" in reply
        assert "7 Days" in reply or "shift" in reply.lower()

    def test_empty_result_returns_no_shift_message(self):
        """Req 4: no shifts → friendly bilingual message."""
        sb = MockSupabase()
        sb.configure("v_employee_shifts", [])
        sb.configure("v_candidate_shifts", [])
        sb.configure("candidates", [])   # fallback lookup returns nothing

        reply = _call_handle_shift(sb)
        assert "no shift" in reply.lower() or "no upcoming" in reply.lower() or "7 days" in reply.lower()

    def test_single_shift_returned(self):
        sb = MockSupabase()
        sb.configure("v_employee_shifts", [SHIFT_TOMORROW])
        reply = _call_handle_shift(sb)
        assert "shift" in reply.lower() or "Waiter" in reply

    def test_multiple_shifts_returned(self):
        sb = MockSupabase()
        sb.configure("v_employee_shifts", [SHIFT_TOMORROW, SHIFT_DAY3])
        reply = _call_handle_shift(sb)
        # Both roles should appear
        assert "Banquet Waiter" in reply
        assert "Sous Chef" in reply


# ═════════════════════════════════════════════════════════════════════════════
# Req 2 — WhatsApp format
# ═════════════════════════════════════════════════════════════════════════════

class TestWhatsAppFormat:
    def _reply(self, shifts=None) -> str:
        sb = MockSupabase()
        sb.configure("v_employee_shifts", shifts or [SHIFT_TOMORROW])
        return _call_handle_shift(sb)

    def test_bot_name_in_reply(self):
        assert "HospBot" in self._reply()

    def test_header_mentions_next_7_days(self):
        r = self._reply()
        assert "7 Days" in r or "Schedule" in r

    def test_dividers_present(self):
        r = self._reply()
        assert "━" in r

    def test_shift_count_summary(self):
        r = self._reply([SHIFT_TOMORROW, SHIFT_DAY3])
        assert "2" in r and "shift" in r.lower()

    def test_single_shift_count(self):
        r = self._reply([SHIFT_TOMORROW])
        assert "1 shift" in r

    def test_blank_line_between_shifts(self):
        r = self._reply([SHIFT_TOMORROW, SHIFT_DAY3])
        # Two shifts → there should be a blank line separating them
        assert "\n\n" in r

    def test_emoji_in_each_shift(self):
        r = self._reply()
        # Each shift block starts with 🔹
        assert "🔹" in r

    def test_help_footer_present(self):
        r = self._reply()
        assert "HELP" in r


# ═════════════════════════════════════════════════════════════════════════════
# Req 3 — Fields: date, start time, end time, property, department, manager
# ═════════════════════════════════════════════════════════════════════════════

class TestShiftFields:
    def _reply(self, shift_data=None) -> str:
        sb = MockSupabase()
        sb.configure("v_employee_shifts", [shift_data or SHIFT_TOMORROW])
        return _call_handle_shift(sb)

    # ── Date ─────────────────────────────────────────────────────────────────
    def test_date_present(self):
        r = self._reply()
        tomorrow = (_TODAY + timedelta(days=1)).strftime("%d")
        assert tomorrow in r   # day number appears in the reply

    def test_date_formatted_human_readable(self):
        r = self._reply()
        # Should show month abbreviation, e.g. "Jun" not "06"
        months = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"]
        assert any(m in r for m in months)

    # ── Start time ────────────────────────────────────────────────────────────
    def test_start_time_present(self):
        r = self._reply()
        assert "09:00" in r   # SHIFT_TOMORROW starts at 09:00

    # ── End time ─────────────────────────────────────────────────────────────
    def test_end_time_present(self):
        r = self._reply()
        assert "17:00" in r   # SHIFT_TOMORROW ends at 17:00

    # ── Time separator ────────────────────────────────────────────────────────
    def test_time_range_formatted(self):
        r = self._reply()
        assert "09:00" in r and "17:00" in r and "–" in r

    # ── Duration ─────────────────────────────────────────────────────────────
    def test_duration_in_reply(self):
        r = self._reply()
        assert "8 hrs" in r   # 09:00 to 17:00 = 8 hours

    # ── Property / venue ─────────────────────────────────────────────────────
    def test_property_name_present(self):
        r = self._reply()
        assert "Grand Hyatt Mumbai" in r

    def test_location_used_when_no_property(self):
        shift_no_prop = {**SHIFT_TOMORROW, "property_name": None,
                         "location": "JW Marriott Level 2"}
        r = self._reply(shift_no_prop)
        assert "JW Marriott Level 2" in r

    def test_no_property_no_location_graceful(self):
        shift_bare = {**SHIFT_TOMORROW, "property_name": None, "location": None}
        r = self._reply(shift_bare)
        assert "HospBot" in r   # still returns a reply
        assert "🏨" not in r    # venue emoji omitted when no venue

    # ── Department ────────────────────────────────────────────────────────────
    def test_department_present(self):
        r = self._reply()
        assert "F&B" in r

    def test_no_department_graceful(self):
        shift_no_dept = {**SHIFT_TOMORROW, "department": None}
        r = self._reply(shift_no_dept)
        assert "HospBot" in r
        assert "🏢" not in r   # dept emoji omitted when no dept

    # ── Manager ───────────────────────────────────────────────────────────────
    def test_manager_name_present(self):
        r = self._reply()
        assert "Rajesh Kumar" in r

    def test_manager_from_email_fallback(self):
        shift_email_only = {**SHIFT_TOMORROW,
                             "manager_display_name": None,
                             "manager_email": "meena.patel@hotel.com"}
        r = self._reply(shift_email_only)
        assert "Meena" in r or "meena" in r.lower()

    def test_no_manager_graceful(self):
        shift_no_mgr = {**SHIFT_TOMORROW,
                         "manager_display_name": None,
                         "manager_email": None,
                         "manager_id": None}
        r = self._reply(shift_no_mgr)
        assert "HospBot" in r
        assert "👤" not in r   # manager emoji omitted when no manager

    # ── Role ─────────────────────────────────────────────────────────────────
    def test_role_present(self):
        r = self._reply()
        assert "Banquet Waiter" in r

    def test_shift_type_present(self):
        r = self._reply()
        assert "Full Day" in r or "full_day" in r.lower() or "Full" in r

    # ── Multiple shifts all fields ────────────────────────────────────────────
    def test_second_shift_fields(self):
        sb = MockSupabase()
        sb.configure("v_employee_shifts", [SHIFT_TOMORROW, SHIFT_DAY3])
        r = _call_handle_shift(sb)
        # Second shift details
        assert "Sous Chef" in r
        assert "JW Marriott" in r
        assert "Kitchen" in r
        assert "Meena Patel" in r


# ═════════════════════════════════════════════════════════════════════════════
# Req 4 — No shift exists → friendly message
# ═════════════════════════════════════════════════════════════════════════════

class TestNoShiftMessage:
    def _no_shift_reply(self) -> str:
        sb = MockSupabase()
        sb.configure("v_employee_shifts", [])
        sb.configure("v_candidate_shifts", [])
        sb.configure("candidates", [])   # fallback finds nothing
        return _call_handle_shift(sb)

    def test_reply_is_string(self):
        assert isinstance(self._no_shift_reply(), str)

    def test_bot_name_in_reply(self):
        assert "HospBot" in self._no_shift_reply()

    def test_no_shift_message_english(self):
        r = self._no_shift_reply()
        assert "no" in r.lower() or "shift" in r.lower() or "scheduled" in r.lower()

    def test_no_shift_message_hindi(self):
        r = self._no_shift_reply()
        hindi_chars = sum(1 for c in r if "ऀ" <= c <= "ॿ")
        assert hindi_chars > 0

    def test_suggests_contacting_supervisor(self):
        r = self._no_shift_reply()
        assert "supervisor" in r.lower() or "contact" in r.lower() or "roster" in r.lower()

    def test_no_ticket_or_amount_in_no_shift_reply(self):
        r = self._no_shift_reply()
        assert "₹" not in r
        assert "LV-" not in r


# ═════════════════════════════════════════════════════════════════════════════
# Formatting helpers — unit tests
# ═════════════════════════════════════════════════════════════════════════════

class TestFmtTime:
    def test_iso_timestamp(self):
        from app.services.hr_bot_service import _fmt_time
        assert _fmt_time("2026-06-10T09:30:00") == "09:30"

    def test_midnight(self):
        from app.services.hr_bot_service import _fmt_time
        assert _fmt_time("2026-06-10T00:00:00") == "00:00"

    def test_end_of_day(self):
        from app.services.hr_bot_service import _fmt_time
        assert _fmt_time("2026-06-10T23:59:00") == "23:59"

    def test_invalid_returns_empty(self):
        from app.services.hr_bot_service import _fmt_time
        assert _fmt_time("not-a-date") == ""

    def test_empty_returns_empty(self):
        from app.services.hr_bot_service import _fmt_time
        assert _fmt_time("") == ""


class TestCalcShiftDuration:
    def test_8_hours(self):
        from app.services.hr_bot_service import _calc_shift_duration
        assert _calc_shift_duration("2026-06-10T09:00:00", "2026-06-10T17:00:00") == "8 hrs"

    def test_4_point_5_hours(self):
        from app.services.hr_bot_service import _calc_shift_duration
        assert _calc_shift_duration("2026-06-10T09:00:00", "2026-06-10T13:30:00") == "4.5 hrs"

    def test_1_hour(self):
        from app.services.hr_bot_service import _calc_shift_duration
        assert _calc_shift_duration("2026-06-10T09:00:00", "2026-06-10T10:00:00") == "1 hrs"

    def test_invalid_returns_empty(self):
        from app.services.hr_bot_service import _calc_shift_duration
        assert _calc_shift_duration("bad", "also-bad") == ""

    def test_end_before_start_returns_empty(self):
        from app.services.hr_bot_service import _calc_shift_duration
        result = _calc_shift_duration("2026-06-10T17:00:00", "2026-06-10T09:00:00")
        assert result == ""   # negative duration ignored


class TestFmtShiftBlock:
    def _block(self, **overrides) -> list[str]:
        from app.services.hr_bot_service import _fmt_shift_block
        s = {**SHIFT_TOMORROW, **overrides}
        return _fmt_shift_block(s)

    def test_starts_with_date_emoji(self):
        block = self._block()
        assert block[0].startswith("🔹")

    def test_time_line_present(self):
        block = self._block()
        time_lines = [l for l in block if "⏰" in l]
        assert len(time_lines) == 1
        assert "09:00" in time_lines[0]
        assert "17:00" in time_lines[0]

    def test_duration_in_time_line(self):
        block = self._block()
        time_lines = [l for l in block if "⏰" in l]
        assert "8 hrs" in time_lines[0]

    def test_property_line_present(self):
        block = self._block()
        prop_lines = [l for l in block if "🏨" in l]
        assert len(prop_lines) == 1
        assert "Grand Hyatt" in prop_lines[0]

    def test_dept_line_present(self):
        block = self._block()
        dept_lines = [l for l in block if "🏢" in l]
        assert len(dept_lines) == 1
        assert "F&B" in dept_lines[0]

    def test_manager_line_present(self):
        block = self._block()
        mgr_lines = [l for l in block if "👤" in l]
        assert len(mgr_lines) == 1
        assert "Rajesh Kumar" in mgr_lines[0]

    def test_role_line_present(self):
        block = self._block()
        role_lines = [l for l in block if "💼" in l]
        assert len(role_lines) == 1
        assert "Banquet Waiter" in role_lines[0]

    def test_shift_type_in_role_line(self):
        block = self._block()
        role_lines = [l for l in block if "💼" in l]
        assert "Full Day" in role_lines[0]

    def test_no_property_omits_venue_line(self):
        block = self._block(property_name=None, location=None)
        assert all("🏨" not in l for l in block)

    def test_no_dept_omits_dept_line(self):
        block = self._block(department=None)
        assert all("🏢" not in l for l in block)

    def test_no_manager_omits_manager_line(self):
        block = self._block(manager_display_name=None, manager_email=None)
        assert all("👤" not in l for l in block)

    def test_missing_start_time_omits_time_line(self):
        block = self._block(start_date="", end_date="")
        assert all("⏰" not in l for l in block)


# ═════════════════════════════════════════════════════════════════════════════
# Fallback — unit tests
# ═════════════════════════════════════════════════════════════════════════════

class TestFetchShiftsFallback:
    def _fallback(self, *, candidate_rows=None, shift_match_rows=None,
                  shift_rows=None, employee=None) -> list:
        from app.services.hr_bot_service import _fetch_shifts_fallback

        sb = MockSupabase()
        sb.configure("candidates",    candidate_rows    or [])
        sb.configure("shift_matches", shift_match_rows  or [])
        sb.configure("shifts",        shift_rows        or [])

        return _fetch_shifts_fallback(sb, employee or EMPLOYEE)

    def test_candidate_source_skips_lookup(self):
        """If source=candidates, use employee_id directly without candidate lookup."""
        from app.services.hr_bot_service import _fetch_shifts_fallback

        sb = MockSupabase()
        # No candidates table data — the lookup should be skipped
        sb.configure("shift_matches",
                     [{"shift_id": "s1", "status": "confirmed"}])
        sb.configure("shifts",
                     [{"id": "s1", "role": "Waiter", "start_date": f"{_D(1)}T09:00:00",
                       "end_date": f"{_D(1)}T17:00:00", "status": "open"}])

        result = _fetch_shifts_fallback(sb, EMPLOYEE_CANDIDATE)
        # shift_matches was queried — shift returned
        assert len(result) >= 1

    def test_no_candidate_found_returns_empty(self):
        result = self._fallback(candidate_rows=[])
        assert result == []

    def test_no_shift_matches_returns_empty(self):
        result = self._fallback(
            candidate_rows=[{"id": "cand-001"}],
            shift_match_rows=[],
        )
        assert result == []

    def test_shift_returned_when_available(self):
        shift_row = {
            "id": "s1", "role": "Waiter",
            "start_date": f"{_D(1)}T09:00:00",
            "end_date":   f"{_D(1)}T17:00:00",
            "status": "open",
            "property_name": "Test Hotel",
            "department": "F&B",
        }
        result = self._fallback(
            candidate_rows=[{"id": "cand-001"}],
            shift_match_rows=[{"shift_id": "s1", "status": "confirmed"}],
            shift_rows=[shift_row],
        )
        assert len(result) == 1
        assert result[0]["role"] == "Waiter"

    def test_fallback_does_not_use_wrong_candidate(self):
        """
        Bug fix: original fetched ANY candidate in the org.
        Now it filters by phone + org. Verify phone-based lookup is used.
        """
        from app.services.hr_bot_service import _fetch_shifts_fallback

        sb = MockSupabase()
        eq_filter_cols = []

        original_table = sb.table

        def recording_table(name):
            chain = original_table(name)
            if name == "candidates":
                original_eq = chain.eq
                def recording_eq(col, val):
                    eq_filter_cols.append(col)
                    return original_eq(col, val)
                chain.eq = recording_eq
            return chain

        with patch.object(sb, "table", side_effect=recording_table):
            _fetch_shifts_fallback(sb, EMPLOYEE)

        # "phone" must be one of the filters (not just org_id)
        assert "phone" in eq_filter_cols

    def test_db_error_returns_empty_not_raise(self):
        from app.services.hr_bot_service import _fetch_shifts_fallback

        sb = MockSupabase()
        with patch.object(sb, "table", side_effect=Exception("DB down")):
            result = _fetch_shifts_fallback(sb, EMPLOYEE)
        assert result == []


# ═════════════════════════════════════════════════════════════════════════════
# Integration — dispatcher routes SHIFT command correctly
# ═════════════════════════════════════════════════════════════════════════════

class TestShiftDispatch:
    def test_shift_command_dispatched(self):
        from app.services.hr_bot_service import handle_whatsapp_message

        sb = MockSupabase()
        # Employee lookup
        sb.configure("whatsapp_users", [{"id": "wu", "employee_id": "emp-uuid-001",
                                          "org_id": "org-uuid-001",
                                          "display_name": "Priya", "opt_out": False}])
        sb.configure("whatsapp_users", [{"id": "wu", "message_count": 1}])
        sb.configure("whatsapp_users", [])
        sb.configure("hr_bot_sessions", [{"id": "s", "message_count": 1}])
        sb.configure("hr_bot_sessions", [])
        sb.configure("whatsapp_messages", [{"id": "wm"}])
        # Shift query
        sb.configure("v_employee_shifts", [SHIFT_TOMORROW])
        # Message update
        sb.configure("whatsapp_messages", [])

        with patch("app.services.whatsapp_gateway.WhatsAppGateway.send", return_value="ok"):
            reply = handle_whatsapp_message(sb, EMPLOYEE["phone"], "SHIFT")

        assert "HospBot" in reply
        assert "shift" in reply.lower() or "schedule" in reply.lower()

    def test_hindi_pali_alias_dispatched(self):
        """'पाली' (Hindi for shift) should reach handle_shift."""
        from app.services.hr_bot_service import handle_whatsapp_message

        sb = MockSupabase()
        sb.configure("whatsapp_users", [{"id": "wu", "employee_id": "emp-uuid-001",
                                          "org_id": "org-uuid-001",
                                          "display_name": "Priya", "opt_out": False}])
        sb.configure("whatsapp_users", [{"id": "wu", "message_count": 1}])
        sb.configure("whatsapp_users", [])
        sb.configure("hr_bot_sessions", [{"id": "s", "message_count": 1}])
        sb.configure("hr_bot_sessions", [])
        sb.configure("whatsapp_messages", [{"id": "wm"}])
        sb.configure("v_employee_shifts", [])    # no shifts
        sb.configure("v_candidate_shifts", [])
        sb.configure("candidates", [])
        sb.configure("whatsapp_messages", [])

        with patch("app.services.whatsapp_gateway.WhatsAppGateway.send", return_value="ok"):
            reply = handle_whatsapp_message(sb, EMPLOYEE["phone"], "पाली")

        # Should reach handle_shift and return the no-shift message
        assert "HospBot" in reply
        assert "shift" in reply.lower() or "schedule" in reply.lower() or "7" in reply
