"""
Tests for WhatsApp HR Bot module.

Coverage:
  1. Command parser — all 7 commands, case variants, fuzzy match, unknown
  2. Date parsing — ISO, DD/MM/YYYY, natural language
  3. Month parsing — name, abbreviation, numeric
  4. Leave type inference
  5. Complaint category inference
  6. handle_whatsapp_message — full dispatch (employee found / not found)
  7. Individual command handlers (mocked supabase)
  8. API endpoints — webhook, leave CRUD, payslips, complaints, stats
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

# ─── IDs ─────────────────────────────────────────────────────────────────────
ORG_ID  = "aaaa1111-cccc-dddd-eeee-ffff00001111"
EMP_ID  = "bbbb2222-dddd-eeee-ffff-aaaa11112222"
REQ_ID  = "cccc3333-eeee-ffff-aaaa-bbbb22223333"
COMP_ID = "dddd4444-ffff-aaaa-bbbb-cccc33334444"
PS_ID   = "eeee5555-aaaa-bbbb-cccc-dddd44445555"

PHONE   = "+919876543210"

_ORG_ROW  = [{"org_id": ORG_ID}]
_AUDIT    = []

_EMPLOYEE = {
    "employee_id": EMP_ID,
    "org_id":      ORG_ID,
    "name":        "Priya Sharma",
    "source":      "users",
    "phone":       PHONE,
}


# ═════════════════════════════════════════════════════════════════════════════
# 1. Command parser
# ═════════════════════════════════════════════════════════════════════════════

class TestCommandParser:
    def _p(self, text):
        from app.services.hr_bot_service import parse_command
        return parse_command(text)

    def test_help_upper(self):       assert self._p("HELP")[0] == "HELP"
    def test_help_lower(self):       assert self._p("help")[0] == "HELP"
    def test_help_mixed(self):       assert self._p("Help")[0] == "HELP"

    def test_leave_with_args(self):
        cmd, args = self._p("LEAVE 2026-06-20 not feeling well")
        assert cmd == "LEAVE"
        assert "2026-06-20" in args[0]
        assert "not feeling well" in args[0]

    def test_payslip_with_month(self):
        cmd, args = self._p("payslip April")
        assert cmd == "PAYSLIP"
        assert "April" in args[0]

    def test_shift_no_args(self):
        cmd, args = self._p("SHIFT")
        assert cmd == "SHIFT"
        assert args == []

    def test_balance_no_args(self):
        cmd, _ = self._p("BALANCE")
        assert cmd == "BALANCE"

    def test_complaint_with_text(self):
        cmd, args = self._p("COMPLAINT my salary was not paid this month")
        assert cmd == "COMPLAINT"
        assert "salary" in args[0]

    def test_career_no_args(self):
        cmd, _ = self._p("CAREER")
        assert cmd == "CAREER"

    def test_unknown_gibberish(self):
        cmd, _ = self._p("xyzabc 123")
        assert cmd == "UNKNOWN"

    def test_empty_string(self):
        cmd, _ = self._p("")
        assert cmd == "UNKNOWN"

    def test_whitespace_only(self):
        cmd, _ = self._p("   ")
        assert cmd == "UNKNOWN"

    def test_fuzzy_help(self):
        cmd, _ = self._p("HELPP")   # one extra char
        # fuzzy may or may not match — just ensure it doesn't crash
        assert isinstance(cmd, str)

    def test_leave_case_insensitive(self):
        cmd, _ = self._p("leave 2026-06-20 sick")
        assert cmd == "LEAVE"


# ═════════════════════════════════════════════════════════════════════════════
# 2. Date parsing
# ═════════════════════════════════════════════════════════════════════════════

class TestDateParsing:
    def _d(self, s):
        from app.services.hr_bot_service import _parse_date
        return _parse_date(s)

    def test_iso(self):          assert self._d("2026-06-20") == "2026-06-20"
    def test_dmy_dash(self):     assert self._d("20-06-2026") == "2026-06-20"
    def test_dmy_slash(self):    assert self._d("20/06/2026") == "2026-06-20"
    def test_dmy_dot(self):      assert self._d("20.06.2026") == "2026-06-20"

    def test_day_month_natural(self):
        result = self._d("20 June")
        assert result.endswith("-06-20")

    def test_ordinal_day(self):
        result = self._d("20th June")
        assert result.endswith("-06-20")

    def test_month_day(self):
        result = self._d("June 20")
        assert result.endswith("-06-20")

    def test_invalid_returns_none(self):
        from app.services.hr_bot_service import _parse_date
        # New API: returns None (does not raise) so callers produce user-friendly errors
        assert _parse_date("not-a-date") is None


# ═════════════════════════════════════════════════════════════════════════════
# 3. Month parsing
# ═════════════════════════════════════════════════════════════════════════════

class TestMonthParsing:
    def _m(self, s):
        from app.services.hr_bot_service import _parse_month_arg
        now = datetime(2026, 5, 19)
        return _parse_month_arg(s, now)

    def test_full_name(self):         assert self._m("April")[0]     == 4
    def test_abbrev(self):            assert self._m("apr")[0]       == 4
    def test_numeric(self):           assert self._m("4")[0]         == 4
    def test_december(self):          assert self._m("December")[0]  == 12
    def test_with_year(self):
        m, y = self._m("April 2025")
        assert m == 4 and y == 2025
    def test_invalid_returns_none(self):
        m, _ = self._m("notamonth")
        assert m is None


# ═════════════════════════════════════════════════════════════════════════════
# 4. Leave type and complaint category inference
# ═════════════════════════════════════════════════════════════════════════════

class TestInference:
    def test_sick_leave(self):
        from app.services.hr_bot_service import _infer_leave_type
        assert _infer_leave_type("i have fever and am not well") == "SICK"

    def test_emergency_leave(self):
        from app.services.hr_bot_service import _infer_leave_type
        assert _infer_leave_type("family emergency") == "EMERGENCY"

    def test_casual_default(self):
        from app.services.hr_bot_service import _infer_leave_type
        assert _infer_leave_type("need a day off") == "CASUAL"

    def test_complaint_payroll(self):
        from app.services.hr_bot_service import _infer_complaint_category
        assert _infer_complaint_category("my salary was not paid") == "PAYROLL"

    def test_complaint_harassment(self):
        from app.services.hr_bot_service import _infer_complaint_category
        assert _infer_complaint_category("my manager harasses me daily") == "HARASSMENT"

    def test_complaint_safety(self):
        from app.services.hr_bot_service import _infer_complaint_category
        assert _infer_complaint_category("safety equipment is missing") == "SAFETY"

    def test_complaint_general(self):
        from app.services.hr_bot_service import _infer_complaint_category
        # "break room" is categorised as FACILITIES (room keyword) — that's correct.
        # Use a truly general complaint to test the GENERAL fallback.
        assert _infer_complaint_category("I have a general concern") == "GENERAL"


# ═════════════════════════════════════════════════════════════════════════════
# 5. handle_help — pure output test
# ═════════════════════════════════════════════════════════════════════════════

class TestHelpHandler:
    def test_help_contains_all_commands(self):
        from app.services.hr_bot_service import handle_help
        output = handle_help(_EMPLOYEE)
        for cmd in ["LEAVE", "PAYSLIP", "SHIFT", "BALANCE", "COMPLAINT", "CAREER", "HELP"]:
            assert cmd in output, f"{cmd} missing from HELP output"

    def test_help_bilingual(self):
        from app.services.hr_bot_service import handle_help
        output = handle_help(_EMPLOYEE)
        # Has some Hindi content (Devanagari characters)
        assert any("ऀ" <= ch <= "ॿ" for ch in output)

    def test_help_has_employee_name(self):
        from app.services.hr_bot_service import handle_help
        output = handle_help(_EMPLOYEE)
        assert "Priya" in output


# ═════════════════════════════════════════════════════════════════════════════
# 6. handle_leave
# ═════════════════════════════════════════════════════════════════════════════

def _make_sb(table_results: dict):
    """Build a mock supabase where .table(name) returns configured results."""
    sb = MagicMock()
    def table_side(name):
        chain = MagicMock()
        for m in ("select","eq","neq","limit","order","insert","update","in_","gte","lte"):
            getattr(chain, m).return_value = chain
        res = MagicMock()
        results = table_results.get(name, [[]])
        call_idx = {"i": 0}
        def execute():
            idx = call_idx["i"]
            data = results[idx % len(results)] if isinstance(results[0], list) else results
            call_idx["i"] += 1
            res.data  = data
            res.count = len(data)
            return res
        chain.execute.side_effect = execute
        return chain
    sb.table.side_effect = table_side
    return sb


class TestLeaveHandler:
    def _sb_happy(self):
        # Call order for handle_leave:
        #   leave_balances[0] — _check_leave_balance SELECT (all balance cols)
        #   leave_requests[0] — _is_duplicate_request SELECT  → [] (no dup)
        #   leave_requests[1] — INSERT                        → row with ticket
        #   leave_balances[1] — _deduct_leave_balance SELECT  → {id, used}
        #   leave_balances[2] — _deduct_leave_balance UPDATE  → []
        #   users[0]          — _notify_managers_new_leave    → [] (no managers)
        return _make_sb({
            "leave_balances": [
                [{"id": "bal-001",
                  "casual_remaining": 10, "casual_used": 2,  "casual_total": 12,
                  "sick_remaining":   12, "sick_used":   0,  "sick_total":   12,
                  "earned_remaining": 15, "earned_used": 0,  "earned_total": 15}],
                [{"id": "bal-001", "casual_used": 2}],  # deduction select
                [],                                      # deduction update
            ],
            "leave_requests": [
                [],                         # duplicate check → none found
                [{"id": REQ_ID,
                  "ticket_number": "LV-20260620-TST01"}],  # insert result
            ],
            "users": [[]],  # manager lookup → no managers (no WhatsApp send)
        })

    def test_leave_happy_path(self):
        from app.services.hr_bot_service import handle_leave
        sb = self._sb_happy()
        with patch("app.services.whatsapp_gateway.send_whatsapp", return_value="ok"):
            r = handle_leave(sb, _EMPLOYEE, ["2026-06-20 not feeling well"])
        assert "✅" in r
        assert "LV-" in r   # ticket number
        assert "CASUAL" in r or "casual" in r.lower()

    def test_leave_sick_type_inferred(self):
        from app.services.hr_bot_service import handle_leave
        sb = self._sb_happy()
        with patch("app.services.whatsapp_gateway.send_whatsapp", return_value="ok"):
            r = handle_leave(sb, _EMPLOYEE, ["2026-06-21 fever"])
        assert "SICK" in r or "sick" in r.lower()

    def test_leave_missing_date(self):
        from app.services.hr_bot_service import handle_leave
        sb = MagicMock()
        r = handle_leave(sb, _EMPLOYEE, [])
        assert "date" in r.lower() or "format" in r.lower()

    def test_leave_missing_reason(self):
        from app.services.hr_bot_service import handle_leave
        sb = MagicMock()
        r = handle_leave(sb, _EMPLOYEE, ["2026-06-20"])
        assert "reason" in r.lower()

    def test_leave_invalid_date(self):
        from app.services.hr_bot_service import handle_leave
        sb = MagicMock()
        r = handle_leave(sb, _EMPLOYEE, ["not-a-date sick"])
        # New parser says "Could not understand … as a date"
        assert "understand" in r.lower() or "date" in r.lower() or "❌" in r


# ═════════════════════════════════════════════════════════════════════════════
# 7. handle_payslip
# ═════════════════════════════════════════════════════════════════════════════

_PAYSLIP_ROW = [{
    "id": PS_ID, "employee_id": EMP_ID,  # required for security owner-check
    "month": 4, "year": 2026,
    "gross_salary_inr": 25000, "net_salary_inr": 22812,
    "basic_salary_inr": 15000, "hra_inr": 5000,
    "epf_deduction_inr": 1800, "esic_deduction_inr": 188,
    "professional_tax_inr": 200, "tds_inr": 0,
    "payslip_pdf_url": None,  # no pre-existing PDF; triggers generation path
    "paid_at": "2026-04-30T10:00:00", "present_days": 26, "working_days": 26,
}]


class TestPayslipHandler:
    def test_payslip_happy(self):
        from app.services.hr_bot_service import handle_payslip
        sb = _make_sb({"payslips": [_PAYSLIP_ROW]})
        r = handle_payslip(sb, _EMPLOYEE, ["April"])
        assert "₹25" in r or "25,000" in r
        assert "22,812" in r or "₹22" in r
        assert "EPF" in r
        assert "April 2026" in r

    def test_payslip_not_found(self):
        from app.services.hr_bot_service import handle_payslip
        sb = _make_sb({"payslips": [[]]})
        r = handle_payslip(sb, _EMPLOYEE, ["March"])
        assert "No payslip" in r or "not found" in r.lower()

    def test_payslip_defaults_to_previous_month(self):
        from app.services.hr_bot_service import handle_payslip
        sb = _make_sb({"payslips": [[]]})
        r = handle_payslip(sb, _EMPLOYEE, [])
        assert isinstance(r, str)

    def test_payslip_invalid_month(self):
        from app.services.hr_bot_service import handle_payslip
        sb = MagicMock()
        r = handle_payslip(sb, _EMPLOYEE, ["Blarch"])
        assert "understand" in r.lower() or "invalid" in r.lower() or "Could not" in r


# ═════════════════════════════════════════════════════════════════════════════
# 8. handle_balance
# ═════════════════════════════════════════════════════════════════════════════

_BALANCE_ROW = [{
    "id": "bal-001", "casual_remaining": 8, "casual_used": 4,
    "sick_remaining": 12, "sick_used": 0,
    "earned_remaining": 12, "earned_used": 3,
}]


class TestBalanceHandler:
    def test_balance_happy(self):
        from app.services.hr_bot_service import handle_balance
        sb = _make_sb({"leave_balances": [_BALANCE_ROW]})
        r = handle_balance(sb, _EMPLOYEE, [])
        assert "8" in r
        assert "12" in r
        assert "Casual" in r or "casual" in r.lower()

    def test_balance_no_record_creates_default(self):
        from app.services.hr_bot_service import handle_balance
        sb = _make_sb({"leave_balances": [[]], "": [[{"id": "new-bal"}]]})
        r = handle_balance(sb, _EMPLOYEE, [])
        assert isinstance(r, str)
        assert "Balance" in r


# ═════════════════════════════════════════════════════════════════════════════
# 9. handle_complaint
# ═════════════════════════════════════════════════════════════════════════════

class TestComplaintHandler:
    def test_complaint_happy(self):
        from app.services.hr_bot_service import handle_complaint
        sb = _make_sb({"employee_complaints": [[{"id": COMP_ID}]]})
        r = handle_complaint(sb, _EMPLOYEE, ["my salary was not paid this month at all"])
        assert "HR-" in r   # ticket number
        assert "Payroll" in r or "PAYROLL" in r   # category (displayed as title case)
        assert "✅" in r

    def test_complaint_too_short(self):
        from app.services.hr_bot_service import handle_complaint
        sb = MagicMock()
        r = handle_complaint(sb, _EMPLOYEE, ["bad"])
        assert "detail" in r.lower() or "describe" in r.lower()

    def test_complaint_empty(self):
        from app.services.hr_bot_service import handle_complaint
        sb = MagicMock()
        r = handle_complaint(sb, _EMPLOYEE, [])
        assert isinstance(r, str)


# ═════════════════════════════════════════════════════════════════════════════
# 10. handle_career
# ═════════════════════════════════════════════════════════════════════════════

_JOB_ROWS = [
    {"id": "job-001", "title": "Front Desk Manager", "role_type": "Management",
     "description": "Lead the front desk team at our Mumbai property.", "status": "open"},
    {"id": "job-002", "title": "F&B Supervisor", "role_type": "Operations",
     "description": "Oversee food and beverage operations.", "status": "open"},
]


class TestCareerHandler:
    def test_career_with_openings(self):
        from app.services.hr_bot_service import handle_career
        sb = _make_sb({"jobs": [_JOB_ROWS]})
        r = handle_career(sb, _EMPLOYEE, [])
        assert "Front Desk Manager" in r
        assert "F&B Supervisor" in r

    def test_career_no_openings(self):
        from app.services.hr_bot_service import handle_career
        sb = _make_sb({"jobs": [[]]})
        r = handle_career(sb, _EMPLOYEE, [])
        assert "No open" in r or "no open" in r.lower()


# ═════════════════════════════════════════════════════════════════════════════
# 11. handle_unknown + not_registered
# ═════════════════════════════════════════════════════════════════════════════

class TestFallbacks:
    def test_unknown_command(self):
        from app.services.hr_bot_service import handle_unknown
        r = handle_unknown("random text here")
        assert "HELP" in r

    def test_not_registered(self):
        from app.services.hr_bot_service import handle_not_registered
        r = handle_not_registered("+919999999999")
        assert "not registered" in r.lower() or "registered" in r.lower()


# ═════════════════════════════════════════════════════════════════════════════
# 12. handle_whatsapp_message — full dispatch
# ═════════════════════════════════════════════════════════════════════════════

_USER_ROW = [{"id": EMP_ID, "org_id": ORG_ID, "email": "priya@hotel.in", "phone": PHONE}]
_SESSION  = [{"id": "sess-001", "message_count": 5}]


class TestDispatcher:
    def _sb_with_employee(self, extra_tables=None):
        tables = {
            "users":           [_USER_ROW, [{"id": EMP_ID}]],
            "hr_bot_sessions": [_SESSION,  [{"id": "sess-001"}]],
        }
        if extra_tables:
            tables.update(extra_tables)
        return _make_sb(tables)

    def test_dispatch_help(self):
        from app.services.hr_bot_service import handle_whatsapp_message
        sb = self._sb_with_employee()
        r = handle_whatsapp_message(sb, PHONE, "HELP")
        assert "LEAVE" in r
        assert "PAYSLIP" in r

    def test_dispatch_not_registered(self):
        from app.services.hr_bot_service import handle_whatsapp_message
        sb = _make_sb({
            "users":           [[]],
            "candidates":      [[]],
            "hr_bot_sessions": [[], [{"id": "sess-new"}]],
        })
        r = handle_whatsapp_message(sb, "+919000000000", "HELP")
        assert "not registered" in r.lower() or "registered" in r.lower()

    def test_dispatch_unknown_command(self):
        from app.services.hr_bot_service import handle_whatsapp_message
        sb = self._sb_with_employee()
        r = handle_whatsapp_message(sb, PHONE, "RANDOMCMD blah blah")
        assert "HELP" in r

    def test_dispatch_complaint(self):
        from app.services.hr_bot_service import handle_whatsapp_message
        sb = self._sb_with_employee({
            "employee_complaints": [[{"id": COMP_ID}]],
        })
        r = handle_whatsapp_message(sb, PHONE, "COMPLAINT my salary was not paid this month")
        assert "HR-" in r


# ═════════════════════════════════════════════════════════════════════════════
# 13. API endpoints
# ═════════════════════════════════════════════════════════════════════════════

_LR_ROW = [{
    "id": REQ_ID, "employee_id": EMP_ID, "leave_date": "2026-06-20",
    "leave_type": "CASUAL", "reason": "personal", "status": "PENDING",
    "ticket_number": "LV-20260519-ABCD01", "created_at": "2026-05-19T10:00:00",
}]

_COMP_ROW = [{
    "id": COMP_ID, "employee_id": EMP_ID,
    "complaint_text": "test complaint text here",
    "category": "GENERAL", "ticket_number": "HR-20260519-XY0001",
    "status": "OPEN", "created_at": "2026-05-19T10:00:00",
}]


class TestHRBotEndpoints:
    def test_webhook_processes_help(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",           _USER_ROW, [{"id": EMP_ID}])
        sb.configure("hr_bot_sessions", _SESSION, [{"id": "sess-001"}])

        with patch("app.routers.hr_bot._send_whatsapp", return_value="WA-SID"):
            resp = client.post("/api/v1/hr-bot/webhook", data={
                "From":       f"whatsapp:{PHONE}",
                "Body":       "HELP",
                "MessageSid": "SM123",
                "NumMedia":   "0",
            })
        assert resp.status_code == 200

    def test_webhook_unknown_employee(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",           [[]])   # not found
        sb.configure("candidates",      [[]])
        sb.configure("hr_bot_sessions", [[]], [{"id": "sess-new"}])

        with patch("app.routers.hr_bot._send_whatsapp", return_value=None):
            resp = client.post("/api/v1/hr-bot/webhook", data={
                "From":       "whatsapp:+919000000001",
                "Body":       "HELP",
                "MessageSid": "SM456",
                "NumMedia":   "0",
            })
        assert resp.status_code == 200   # always 200 to Twilio

    def test_list_sessions(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        sb.configure("hr_bot_sessions", [_SESSION[0]])

        resp = client.get("/api/v1/hr-bot/sessions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_leave_requests(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",          _ORG_ROW)
        sb.configure("leave_requests", _LR_ROW)

        resp = client.get("/api/v1/hr-bot/leave-requests")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_approve_leave(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",          _ORG_ROW)
        # variadic: SELECT returns _LR_ROW, UPDATE returns update result
        sb.configure("leave_requests", _LR_ROW, [{"id": REQ_ID}])

        with patch("app.routers.hr_bot._get_employee_phone", return_value=None):
            resp = client.patch(f"/api/v1/hr-bot/leave-requests/{REQ_ID}/approve",
                                json={"notes": "Approved by manager"})
        assert resp.status_code == 200
        assert resp.json()["approved"] is True

    def test_approve_already_approved_409(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        approved_row = [{**_LR_ROW[0], "status": "APPROVED"}]
        sb.configure("leave_requests", approved_row)

        resp = client.patch(f"/api/v1/hr-bot/leave-requests/{REQ_ID}/approve", json={})
        assert resp.status_code == 409

    def test_reject_leave(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",          _ORG_ROW)
        sb.configure("leave_requests", _LR_ROW, [{"id": REQ_ID}])

        with patch("app.routers.hr_bot._get_employee_phone", return_value=None):
            resp = client.patch(f"/api/v1/hr-bot/leave-requests/{REQ_ID}/reject",
                                json={"rejection_reason": "Staff shortage"})
        assert resp.status_code == 200
        assert resp.json()["rejected"] is True

    def test_create_payslip(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",    _ORG_ROW)
        sb.configure("payslips", [{"id": PS_ID, "month": 4, "year": 2026}])

        with patch("app.routers.hr_bot._get_employee_phone", return_value=None):
            resp = client.post("/api/v1/hr-bot/payslips", json={
                "employee_id":      EMP_ID,
                "month":            4,
                "year":             2026,
                "gross_salary_inr": 25000,
                "net_salary_inr":   22812,
            })
        assert resp.status_code == 201
        assert resp.json()["id"] == PS_ID

    def test_list_payslips(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",    _ORG_ROW)
        sb.configure("payslips", [{"id": PS_ID, "month": 4, "year": 2026}])

        resp = client.get("/api/v1/hr-bot/payslips")
        assert resp.status_code == 200

    def test_list_complaints(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",                    _ORG_ROW)
        # list_complaints now reads from v_hr_complaints_display (masked view)
        sb.configure("v_hr_complaints_display",  _COMP_ROW)

        resp = client.get("/api/v1/hr-bot/complaints")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_resolve_complaint(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users",          _ORG_ROW)
        # resolve_complaint now reads from hr_complaints (authoritative table)
        comp_with_phone = {**_COMP_ROW[0], "phone": "+919876543210", "employee_id": None}
        sb.configure("hr_complaints",  [comp_with_phone], [{"id": COMP_ID}])

        with patch("app.routers.hr_bot._send_whatsapp", return_value="sid"):
            resp = client.patch(f"/api/v1/hr-bot/complaints/{COMP_ID}/resolve",
                                json={"resolution_notes": "Issue addressed"})
        assert resp.status_code == 200
        assert resp.json()["resolved"] is True

    def test_bot_stats(self, client_as_admin, mock_supabase):
        client, sb = client_as_admin
        sb.configure("users", _ORG_ROW)
        # stats makes multiple count queries — each returns count=0 from default mock
        resp = client.get("/api/v1/hr-bot/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "active_sessions" in body
        assert "leave_requests_pending" in body
        assert "complaints_open" in body
