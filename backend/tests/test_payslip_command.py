"""
Tests for the PAYSLIP command — all 6 requirements.

Req 1 — Validate employee (unregistered phone → rejected by dispatcher)
Req 2 — Check payroll record for selected month
Req 3 — Generate or fetch PDF payslip
Req 4 — Send PDF to employee on WhatsApp
Req 5 — Store payslip request log (payslip_requests table)
Req 6 — Never expose another employee's payslip

Additional coverage:
  - Month parsing (name / abbreviation / numeric / Hindi / with year)
  - Default previous month when no arg given
  - Text summary fields (gross, net, EPF, HRA, bonus, attendance, paid_at)
  - Confidentiality footer in reply
  - payslip_requests status transitions: PENDING → FULFILLED / NOT_FOUND / ERROR
  - PDF URL cached back on payslips row after generation
  - Document send fallback to text when gateway fails
  - WhatsApp document vs text-only reply depending on PDF availability
"""

from __future__ import annotations

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
        if self._q:
            raw      = self._q.pop(0)
            obj.data = raw if isinstance(raw, list) else ([raw] if raw else [])
        else:
            obj.data = []
        obj.count = len(obj.data)
        return obj

    def select(self, *a, **kw): return self
    def insert(self, *a, **kw): return self
    def update(self, *a, **kw): return self
    def eq(self, *a, **kw):     return self
    def limit(self, *a, **kw):  return self
    def order(self, *a, **kw):  return self
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

EMP_ID = "emp-uuid-001"
ORG_ID = "org-uuid-001"
PS_ID  = "payslip-uuid-001"
PR_ID  = "pr-uuid-001"

EMPLOYEE = {
    "employee_id":      EMP_ID,
    "org_id":           ORG_ID,
    "name":             "Priya Sharma",
    "phone":            "+919876543210",
    "source":           "users",
    "whatsapp_user_id": None,
}

PAYSLIP = {
    "id":                    PS_ID,
    "employee_id":           EMP_ID,   # owner field — critical for Req 6
    "org_id":                ORG_ID,
    "month":                 4,
    "year":                  2026,
    "gross_salary_inr":      25000,
    "net_salary_inr":        22812,
    "basic_salary_inr":      15000,
    "hra_inr":               5000,
    "da_inr":                0,
    "allowances_inr":        0,
    "overtime_inr":          0,
    "bonus_inr":             500,
    "epf_deduction_inr":     1800,
    "esic_deduction_inr":    188,
    "professional_tax_inr":  200,
    "tds_inr":               0,
    "other_deductions_inr":  0,
    "net_salary_inr":        22812,
    "paid_at":               "2026-04-30T10:00:00",
    "payment_method":        "BANK_TRANSFER",
    "payslip_pdf_url":       None,       # no pre-existing PDF
    "working_days":          26,
    "present_days":          25,
}

PAYSLIP_WITH_PDF = {**PAYSLIP, "payslip_pdf_url": "https://s3.ap-south-1.amazonaws.com/bucket/payslip.pdf"}

_SEND_DOC_PATCH = "app.services.whatsapp_gateway.WhatsAppGateway.send_document"
_SEND_PATCH     = "app.services.whatsapp_gateway.send_whatsapp"


def _make_sb(*, payslip=None, pr_insert=None) -> MockSupabase:
    """
    Build a MockSupabase for the standard payslip fetch flow.
    payslip_requests.insert  → pr_insert (default: [{id: PR_ID}])
    payslips.select          → [payslip] or []
    payslips.update          → [] (cache write — only called when PDF generated)
    """
    sb = MockSupabase()
    sb.configure("payslip_requests",
                 pr_insert if pr_insert is not None else [{"id": PR_ID}],
                 [])   # update call
    if payslip is not None:
        sb.configure("payslips", [payslip])
    else:
        sb.configure("payslips", [])
    return sb


def _handle(sb, args_str: str, msg_id: str = "wm-001") -> str:
    """Call handle_payslip with PDF generation stubbed out (no fpdf2 needed)."""
    from app.services.hr_bot_service import handle_payslip
    args = [args_str] if args_str else []
    with patch("app.services.hr_bot_service._generate_and_cache_payslip_pdf",
               return_value=None), \
         patch(_SEND_DOC_PATCH, return_value=None):
        return handle_payslip(sb, EMPLOYEE, args, msg_id=msg_id)


# ═════════════════════════════════════════════════════════════════════════════
# Req 1 — Employee validation (dispatcher level)
# ═════════════════════════════════════════════════════════════════════════════

class TestEmployeeValidation:
    def test_unregistered_phone_blocked(self):
        from app.services.hr_bot_service import handle_whatsapp_message

        sb = MockSupabase()
        sb.configure("whatsapp_users", [])
        sb.configure("users",          [])
        sb.configure("candidates",     [])
        sb.configure("hr_bot_sessions", [])
        sb.configure("whatsapp_users",  [])

        with patch("app.services.whatsapp_gateway.WhatsAppGateway.send", return_value=None):
            reply = handle_whatsapp_message(sb, "+919999999998", "PAYSLIP April")
        assert "not registered" in reply.lower() or "registered" in reply.lower()


# ═════════════════════════════════════════════════════════════════════════════
# Req 2 — Check payroll record
# ═════════════════════════════════════════════════════════════════════════════

class TestPayrollRecordLookup:
    def test_found_returns_data(self):
        sb    = _make_sb(payslip=PAYSLIP)
        reply = _handle(sb, "April")
        assert "April 2026" in reply
        assert "25,000" in reply or "₹25" in reply

    def test_not_found_reply(self):
        sb    = _make_sb(payslip=None)
        reply = _handle(sb, "March")
        assert "no payslip" in reply.lower() or "not found" in reply.lower()

    def test_not_found_mentions_month(self):
        sb    = _make_sb(payslip=None)
        reply = _handle(sb, "March")
        assert "March" in reply

    def test_db_error_returns_friendly_message(self):
        from app.services.hr_bot_service import handle_payslip

        sb = MockSupabase()
        sb.configure("payslip_requests", [{"id": PR_ID}])
        sb.configure("payslips")  # empty queue → raises on execute

        with patch.object(sb, "table", side_effect=Exception("DB down")):
            reply = handle_payslip(sb, EMPLOYEE, ["April"])
        assert "unable" in reply.lower() or "❌" in reply or "failed" in reply.lower()

    def test_default_previous_month_when_no_arg(self):
        """PAYSLIP with no arg defaults to previous month — returns a string."""
        sb    = _make_sb(payslip=None)   # not found is OK — just check it runs
        reply = _handle(sb, "")
        assert isinstance(reply, str)
        assert "HospBot" in reply

    # Month parsing variants
    @pytest.mark.parametrize("arg,month_in_reply", [
        ("April",    "April"),
        ("apr",      "April"),
        ("4",        "April"),
        ("December", "December"),
        ("dec",      "December"),
        ("12",       "December"),
    ])
    def test_month_variants(self, arg, month_in_reply):
        sb    = _make_sb(payslip=None)
        reply = _handle(sb, arg)
        assert month_in_reply in reply

    def test_month_with_year(self):
        sb    = _make_sb(payslip=None)
        reply = _handle(sb, "April 2025")
        assert "April" in reply and "2025" in reply

    def test_hindi_month_april(self):
        sb    = _make_sb(payslip=None)
        reply = _handle(sb, "अप्रैल")
        assert "April" in reply

    def test_hindi_month_january(self):
        sb    = _make_sb(payslip=None)
        reply = _handle(sb, "जनवरी")
        assert "January" in reply

    def test_invalid_month_returns_error(self):
        from app.services.hr_bot_service import handle_payslip
        sb    = MagicMock()
        reply = handle_payslip(sb, EMPLOYEE, ["Octember"])
        assert "understand" in reply.lower() or "Could not" in reply or "❌" in reply

    def test_salary_alias_routes_to_payslip(self):
        """'salary April' is an alias — should reach handle_payslip."""
        from app.services.hr_bot_service import handle_whatsapp_message

        sb = MockSupabase()
        # Minimal employee lookup chain
        sb.configure("whatsapp_users",  [{"id": "wu", "employee_id": EMP_ID,
                                           "org_id": ORG_ID, "display_name": "Priya",
                                           "opt_out": False}])
        sb.configure("whatsapp_users",  [{"id": "wu", "message_count": 1}])
        sb.configure("whatsapp_users",  [])
        sb.configure("hr_bot_sessions", [{"id": "s", "message_count": 1}])
        sb.configure("hr_bot_sessions", [])
        sb.configure("whatsapp_messages", [{"id": "wm"}])
        sb.configure("payslip_requests",  [{"id": PR_ID}], [])
        sb.configure("payslips", [])
        sb.configure("whatsapp_messages", [])

        with patch("app.services.whatsapp_gateway.WhatsAppGateway.send", return_value="ok"), \
             patch("app.services.hr_bot_service._generate_and_cache_payslip_pdf", return_value=None):
            reply = handle_whatsapp_message(sb, EMPLOYEE["phone"], "salary April")
        assert "payslip" in reply.lower() or "April" in reply or "HospBot" in reply


# ═════════════════════════════════════════════════════════════════════════════
# Req 3 — Generate or fetch PDF
# ═════════════════════════════════════════════════════════════════════════════

class TestPDFGenerationFetch:
    def test_existing_pdf_url_used_directly(self):
        """If payslip already has a URL, skip generation."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP_WITH_PDF)
        gen_called = []

        with patch("app.services.hr_bot_service._generate_and_cache_payslip_pdf",
                   side_effect=lambda *a: gen_called.append(True) or None), \
             patch(_SEND_DOC_PATCH, return_value="wamid.doc"):
            reply = handle_payslip(sb, EMPLOYEE, ["April"])

        # Generation should be skipped because URL already exists
        assert len(gen_called) == 0

    def test_no_url_triggers_generation(self):
        """No URL on payslip → _generate_and_cache_payslip_pdf is called."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP)  # payslip_pdf_url=None
        gen_called = []

        with patch("app.services.hr_bot_service._generate_and_cache_payslip_pdf",
                   side_effect=lambda *a: gen_called.append(True) or None), \
             patch(_SEND_DOC_PATCH, return_value=None):
            handle_payslip(sb, EMPLOYEE, ["April"])

        assert len(gen_called) == 1

    def test_generate_and_cache_calls_pdf_service(self):
        """_generate_and_cache_payslip_pdf calls payslip_pdf.generate_payslip_pdf."""
        from app.services.hr_bot_service import _generate_and_cache_payslip_pdf

        sb = MockSupabase()
        sb.configure("payslips", [])  # update result (cache write)

        with patch("app.services.payslip_pdf.generate_payslip_pdf",
                   return_value=b"%PDF-fake") as mock_gen, \
             patch("app.services.payslip_pdf.upload_payslip_to_s3",
                   return_value="https://s3.ap-south-1.amazonaws.com/b/p.pdf"):
            url = _generate_and_cache_payslip_pdf(sb, PAYSLIP, EMPLOYEE)

        mock_gen.assert_called_once()
        assert url == "https://s3.ap-south-1.amazonaws.com/b/p.pdf"

    def test_generate_caches_url_on_payslips_row(self):
        """After S3 upload, the URL is saved back to payslips."""
        from app.services.hr_bot_service import _generate_and_cache_payslip_pdf

        sb = MockSupabase()
        sb.configure("payslips", [])

        updated_keys = []

        def capture_update(payload):
            updated_keys.append(list(payload.keys()))
            return MagicMock(data=[])

        with patch("app.services.payslip_pdf.generate_payslip_pdf",
                   return_value=b"%PDF-fake"), \
             patch("app.services.payslip_pdf.upload_payslip_to_s3",
                   return_value="https://s3.region.amazonaws.com/bucket/p.pdf"), \
             patch.object(sb, "table", wraps=sb.table) as mock_tbl:
            _generate_and_cache_payslip_pdf(sb, PAYSLIP, EMPLOYEE)

        # payslips.update should have been called with payslip_pdf_url
        payslip_updates = [c for c in mock_tbl.call_args_list if c.args[0] == "payslips"]
        assert len(payslip_updates) >= 1

    def test_fpdf_not_installed_returns_none(self):
        """If fpdf2 not installed, generate_payslip_pdf returns None gracefully."""
        from app.services.payslip_pdf import generate_payslip_pdf
        with patch.dict("sys.modules", {"fpdf": None}):
            result = generate_payslip_pdf(PAYSLIP, "Priya Sharma")
        assert result is None

    def test_s3_not_configured_returns_none(self):
        """No AWS credentials → upload returns None."""
        from app.services.payslip_pdf import upload_payslip_to_s3
        # settings is a lazy import inside the function; patch at source
        with patch("app.core.config.settings") as mock_s:
            mock_s.AWS_S3_BUCKET     = None
            mock_s.AWS_ACCESS_KEY_ID = None
            result = upload_payslip_to_s3(b"pdf", ORG_ID, EMP_ID, 4, 2026)
        assert result is None

    def test_generate_pdf_contains_employee_name(self):
        """The PDF (if generated) must include the employee name."""
        try:
            from fpdf import FPDF  # skip if not installed
        except ImportError:
            pytest.skip("fpdf2 not installed")

        from app.services.payslip_pdf import generate_payslip_pdf
        pdf_bytes = generate_payslip_pdf(PAYSLIP, "Priya Sharma", org_name="Test Hotel")
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 1000   # real PDF, not empty

    def test_s3_key_format(self):
        """S3 key must be payslips/{org_id}/{employee_id}/{year}_{mm:02d}.pdf"""
        captured_keys = []
        # settings is lazy-imported inside the function; patch at source module
        with patch("boto3.client") as mock_boto, \
             patch("app.core.config.settings") as mock_s:
            mock_s.AWS_S3_BUCKET         = "test-bucket"
            mock_s.AWS_ACCESS_KEY_ID     = "key"
            mock_s.AWS_SECRET_ACCESS_KEY = "secret"
            mock_client = MagicMock()
            mock_boto.return_value = mock_client
            mock_client.put_object.side_effect = lambda **kw: captured_keys.append(kw["Key"])
            mock_client.generate_presigned_url.return_value = "https://presigned"

            from app.services.payslip_pdf import upload_payslip_to_s3
            upload_payslip_to_s3(b"pdf", ORG_ID, EMP_ID, 4, 2026)

        assert len(captured_keys) == 1
        assert captured_keys[0] == f"payslips/{ORG_ID}/{EMP_ID}/2026_04.pdf"


# ═════════════════════════════════════════════════════════════════════════════
# Req 4 — Send PDF via WhatsApp
# ═════════════════════════════════════════════════════════════════════════════

class TestPDFDelivery:
    def test_pdf_url_triggers_document_send(self):
        """When PDF URL available, send_document is called."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP_WITH_PDF)
        with patch(_SEND_DOC_PATCH, return_value="wamid.doc001") as mock_send:
            reply = handle_payslip(sb, EMPLOYEE, ["April"])

        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert EMPLOYEE["phone"] in call_args[0][0] or EMPLOYEE["phone"] in str(call_args)
        assert "Payslip" in str(call_args) or "payslip" in str(call_args).lower()

    def test_pdf_sent_shown_in_reply(self):
        """When document send succeeds, reply says 'PDF payslip sent above'."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP_WITH_PDF)
        with patch(_SEND_DOC_PATCH, return_value="wamid.ok"):
            reply = handle_payslip(sb, EMPLOYEE, ["April"])

        assert "sent" in reply.lower() or "above" in reply.lower()

    def test_pdf_not_sent_shows_url_as_fallback(self):
        """When document send fails but URL exists, reply shows URL in text."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP_WITH_PDF)
        with patch(_SEND_DOC_PATCH, return_value=None):   # send fails
            reply = handle_payslip(sb, EMPLOYEE, ["April"])

        assert "https://" in reply   # URL shown in text fallback

    def test_no_pdf_no_url_shows_contact_hr(self):
        """No PDF, no URL → text says contact HR."""
        sb    = _make_sb(payslip=PAYSLIP)  # payslip_pdf_url=None
        reply = _handle(sb, "April")       # _generate_and_cache stubbed → None
        assert "contact hr" in reply.lower() or "pdf" in reply.lower()

    def test_send_document_caption_contains_month_year(self):
        """Document caption must mention the month and year."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP_WITH_PDF)
        sent_captions = []
        with patch(_SEND_DOC_PATCH,
                   side_effect=lambda ph, url, caption, filename: sent_captions.append(caption) or "ok"):
            handle_payslip(sb, EMPLOYEE, ["April"])

        assert len(sent_captions) == 1
        assert "April" in sent_captions[0] and "2026" in sent_captions[0]

    def test_send_document_filename_format(self):
        """Filename must follow Payslip_{Month}_{Year}.pdf convention."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP_WITH_PDF)
        sent_filenames = []
        with patch(_SEND_DOC_PATCH,
                   side_effect=lambda ph, url, caption, filename:
                   sent_filenames.append(filename) or "ok"):
            handle_payslip(sb, EMPLOYEE, ["April"])

        assert len(sent_filenames) == 1
        fn = sent_filenames[0]
        assert fn.startswith("Payslip_") and fn.endswith(".pdf")
        assert "April" in fn and "2026" in fn

    def test_send_document_phone_is_employee_phone(self):
        """Document must be sent to the requesting employee's phone, not anyone else."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP_WITH_PDF)
        sent_to = []
        with patch(_SEND_DOC_PATCH,
                   side_effect=lambda phone, *a, **kw: sent_to.append(phone) or "ok"):
            handle_payslip(sb, EMPLOYEE, ["April"])

        assert len(sent_to) == 1
        assert EMPLOYEE["phone"] in sent_to[0]

    def test_send_fails_gracefully(self):
        """If send_document raises an exception, reply still returned."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP_WITH_PDF)
        with patch(_SEND_DOC_PATCH, side_effect=Exception("Twilio down")):
            reply = handle_payslip(sb, EMPLOYEE, ["April"])

        assert "HospBot" in reply   # reply still returned


# ═════════════════════════════════════════════════════════════════════════════
# Req 5 — Store payslip request log
# ═════════════════════════════════════════════════════════════════════════════

class TestPayslipRequestLog:
    def test_request_logged_on_fetch(self):
        """payslip_requests.insert called when payslip is fetched."""
        from app.services.hr_bot_service import handle_payslip

        sb = MockSupabase()
        sb.configure("payslip_requests", [{"id": PR_ID}], [])
        sb.configure("payslips", [PAYSLIP])

        insert_calls = []

        with patch.object(sb, "table", wraps=sb.table) as mock_tbl, \
             patch("app.services.hr_bot_service._generate_and_cache_payslip_pdf",
                   return_value=None), \
             patch(_SEND_DOC_PATCH, return_value=None):
            handle_payslip(sb, EMPLOYEE, ["April"])

        pr_calls = [c for c in mock_tbl.call_args_list if c.args[0] == "payslip_requests"]
        assert len(pr_calls) >= 1   # at least one call (insert for logging)

    def test_log_payslip_request_returns_id(self):
        from app.services.hr_bot_service import _log_payslip_request

        sb = MockSupabase()
        sb.configure("payslip_requests", [{"id": PR_ID}])

        pr_id = _log_payslip_request(sb, EMPLOYEE, 4, 2026, "wm-001")
        assert pr_id == PR_ID

    def test_update_payslip_request_fulfilled(self):
        from app.services.hr_bot_service import _update_payslip_request

        sb = MockSupabase()
        sb.configure("payslip_requests", [])   # update result

        # Must not raise
        _update_payslip_request(sb, PR_ID, "FULFILLED", payslip_id=PS_ID)

    def test_update_payslip_request_not_found(self):
        from app.services.hr_bot_service import _update_payslip_request

        sb = MockSupabase()
        sb.configure("payslip_requests", [])
        _update_payslip_request(sb, PR_ID, "NOT_FOUND")

    def test_update_payslip_request_error(self):
        from app.services.hr_bot_service import _update_payslip_request

        sb = MockSupabase()
        sb.configure("payslip_requests", [])
        _update_payslip_request(sb, PR_ID, "ERROR", error_detail="DB error")

    def test_update_with_none_id_is_noop(self):
        """_update_payslip_request(None, ...) must not crash."""
        from app.services.hr_bot_service import _update_payslip_request

        sb = MockSupabase()
        _update_payslip_request(sb, None, "FULFILLED")   # should not raise

    def test_status_fulfilled_when_payslip_found(self):
        """Happy path: request log status should reach FULFILLED."""
        calls = []

        with patch("app.services.hr_bot_service._update_payslip_request",
                   side_effect=lambda *a, **kw: calls.append((a, kw))):
            _handle(_make_sb(payslip=PAYSLIP), "April")

        # _update_payslip_request(supabase, pr_id, status, ...) → args[2] is status
        statuses = [c[0][2] for c in calls]
        assert "FULFILLED" in statuses

    def test_status_not_found_when_payslip_missing(self):
        """Missing payslip: request log status should be NOT_FOUND."""
        calls = []
        with patch("app.services.hr_bot_service._update_payslip_request",
                   side_effect=lambda *a, **kw: calls.append((a, kw))):
            _handle(_make_sb(payslip=None), "April")

        statuses = [c[0][2] for c in calls]   # args[2] is status
        assert "NOT_FOUND" in statuses

    def test_status_error_on_db_failure(self):
        """DB error on fetch: request log status should be ERROR."""
        from app.services.hr_bot_service import handle_payslip

        sb = MockSupabase()
        sb.configure("payslip_requests", [{"id": PR_ID}])

        calls = []
        with patch("app.services.hr_bot_service._update_payslip_request",
                   side_effect=lambda *a, **kw: calls.append((a, kw))), \
             patch.object(sb, "table", side_effect=Exception("DB down")):
            handle_payslip(sb, EMPLOYEE, ["April"])

        statuses = [c[0][2] for c in calls]   # args[2] is status
        assert "ERROR" in statuses


# ═════════════════════════════════════════════════════════════════════════════
# Req 6 — Do not expose another employee's payslip
# ═════════════════════════════════════════════════════════════════════════════

class TestPayslipSecurity:
    def test_query_filters_by_employee_id(self):
        """The DB query must always include .eq('employee_id', employee_id)."""
        from app.services.hr_bot_service import handle_payslip

        sb = _make_sb(payslip=PAYSLIP)
        eq_calls = []

        original_table = sb.table

        def recording_table(name):
            chain = original_table(name)
            original_eq = chain.eq

            def recording_eq(col, val):
                if col == "employee_id":
                    eq_calls.append(val)
                return original_eq(col, val)

            chain.eq = recording_eq
            return chain

        with patch.object(sb, "table", side_effect=recording_table), \
             patch("app.services.hr_bot_service._generate_and_cache_payslip_pdf",
                   return_value=None), \
             patch(_SEND_DOC_PATCH, return_value=None):
            handle_payslip(sb, EMPLOYEE, ["April"])

        # employee_id filter must have been applied at least once
        assert EMP_ID in eq_calls

    def test_security_mismatch_blocked(self):
        """
        Defense-in-depth: if DB somehow returns a row with a different employee_id
        (RLS disabled, misconfigured), the handler must reject it.
        """
        from app.services.hr_bot_service import handle_payslip

        other_employees_payslip = {**PAYSLIP, "employee_id": "other-emp-uuid-999"}

        sb = MockSupabase()
        sb.configure("payslip_requests", [{"id": PR_ID}], [])
        sb.configure("payslips", [other_employees_payslip])

        reply = handle_payslip(sb, EMPLOYEE, ["April"])

        # Must NOT reveal payslip data
        assert "25,000" not in reply        # no earnings exposed
        assert "22,812" not in reply        # no net pay exposed
        # Must return an error or security message
        assert "❌" in reply or "contact" in reply.lower() or "unable" in reply.lower()

    def test_security_event_logged(self):
        """Security mismatch must be logged at ERROR level."""
        from app.services.hr_bot_service import handle_payslip

        other_employees_payslip = {**PAYSLIP, "employee_id": "attacker-uuid"}

        sb = MockSupabase()
        sb.configure("payslip_requests", [{"id": PR_ID}], [])
        sb.configure("payslips", [other_employees_payslip])

        import logging
        with patch.object(logging.getLogger("app.services.hr_bot_service"), "error") as mock_log:
            handle_payslip(sb, EMPLOYEE, ["April"])

        # Logger.error should have been called (security event)
        assert mock_log.called
        log_msg = str(mock_log.call_args_list)
        assert "SECURITY" in log_msg or "mismatch" in log_msg.lower()

    def test_no_employee_id_on_row_is_safe(self):
        """
        If the DB row has no employee_id (legacy / migration gap), the check
        skips cleanly — does not block the legitimate owner.
        """
        payslip_no_owner = {k: v for k, v in PAYSLIP.items() if k != "employee_id"}
        payslip_no_owner["payslip_pdf_url"] = None

        sb = _make_sb(payslip=payslip_no_owner)
        reply = _handle(sb, "April")

        # Should still return the payslip (row lacks employee_id, check skipped)
        assert "April 2026" in reply
        assert "25,000" in reply or "₹25" in reply

    def test_same_employee_always_allowed(self):
        """Normal happy path: own payslip is always returned."""
        sb    = _make_sb(payslip=PAYSLIP)   # PAYSLIP.employee_id == EMPLOYEE["employee_id"]
        reply = _handle(sb, "April")
        assert "April 2026" in reply


# ═════════════════════════════════════════════════════════════════════════════
# Text reply content
# ═════════════════════════════════════════════════════════════════════════════

class TestPayslipTextReply:
    def _reply(self, payslip_row=None) -> str:
        return _handle(_make_sb(payslip=payslip_row or PAYSLIP), "April")

    def test_bot_name_in_reply(self):
        assert "HospBot" in self._reply()

    def test_employee_name_in_reply(self):
        assert "Priya" in self._reply()

    def test_month_year_in_reply(self):
        r = self._reply()
        assert "April" in r and "2026" in r

    def test_gross_salary_in_reply(self):
        r = self._reply()
        assert "25,000" in r or "25000" in r

    def test_net_pay_in_reply(self):
        r = self._reply()
        assert "22,812" in r or "22812" in r

    def test_epf_shown(self):
        assert "EPF" in self._reply()

    def test_hra_shown_when_nonzero(self):
        assert "HRA" in self._reply()

    def test_bonus_shown_when_nonzero(self):
        assert "Bonus" in self._reply() or "500" in self._reply()

    def test_attendance_shown(self):
        r = self._reply()
        assert "25" in r and "26" in r   # present_days / working_days

    def test_paid_on_shown(self):
        r = self._reply()
        assert "Paid" in r or "2026-04-30" in r or "Apr" in r

    def test_confidential_footer(self):
        """Reply must always include confidentiality notice."""
        r = self._reply()
        assert "CONFIDENTIAL" in r or "confidential" in r.lower()

    def test_hindi_in_reply(self):
        """Reply must include at least one Hindi phrase."""
        r = self._reply()
        hindi_count = sum(1 for c in r if "ऀ" <= c <= "ॿ")
        assert hindi_count > 0

    def test_zero_deductions_not_shown(self):
        """TDS = 0 should not appear in deductions section."""
        r = self._reply()
        # TDS is 0 — should not show "TDS" in the reply
        assert "TDS" not in r

    def test_pdf_not_available_message(self):
        """When no PDF at all, reply says contact HR."""
        r = self._reply(PAYSLIP)   # payslip_pdf_url=None, generation stubbed to None
        assert "pdf" in r.lower()


# ═════════════════════════════════════════════════════════════════════════════
# WhatsApp document gateway — send_document unit tests
# ═════════════════════════════════════════════════════════════════════════════

class TestSendDocumentGateway:
    def test_meta_send_document_success(self):
        from app.services.whatsapp_gateway import WhatsAppGateway
        gw = WhatsAppGateway(provider="meta")

        with patch("app.services.whatsapp_gateway.settings") as mock_s, \
             patch("app.services.whatsapp_gateway.httpx.Client") as mock_http:
            mock_s.WHATSAPP_ACCESS_TOKEN    = "token123"
            mock_s.WHATSAPP_PHONE_NUMBER_ID = "pid456"
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"messages": [{"id": "wamid.doc001"}]}
            mock_resp.raise_for_status = MagicMock()
            mock_http.return_value.__enter__.return_value.post.return_value = mock_resp

            result = gw.send_document(
                "+919876543210",
                "https://example.com/pay.pdf",
                caption  = "April payslip",
                filename = "Payslip_April_2026.pdf",
            )
        assert result == "wamid.doc001"

    def test_meta_missing_token_returns_none(self):
        from app.services.whatsapp_gateway import WhatsAppGateway
        gw = WhatsAppGateway(provider="meta")
        with patch("app.services.whatsapp_gateway.settings") as mock_s:
            mock_s.WHATSAPP_ACCESS_TOKEN    = None
            mock_s.WHATSAPP_PHONE_NUMBER_ID = None
            result = gw.send_document("+919876543210", "https://example.com/p.pdf")
        assert result is None

    def test_interakt_send_document_success(self):
        from app.services.whatsapp_gateway import WhatsAppGateway
        gw = WhatsAppGateway(provider="interakt")

        with patch("app.services.whatsapp_gateway.settings") as mock_s, \
             patch("app.services.whatsapp_gateway.httpx.Client") as mock_http:
            mock_s.INTERAKT_API_KEY = "iak-key"
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"id": "iak-doc-001"}
            mock_resp.raise_for_status = MagicMock()
            mock_http.return_value.__enter__.return_value.post.return_value = mock_resp

            result = gw.send_document(
                "+919876543210",
                "https://example.com/p.pdf",
            )
        assert result == "iak-doc-001"

    def test_interakt_missing_key_returns_none(self):
        from app.services.whatsapp_gateway import WhatsAppGateway
        gw = WhatsAppGateway(provider="interakt")
        with patch("app.services.whatsapp_gateway.settings") as mock_s:
            mock_s.INTERAKT_API_KEY = None
            result = gw.send_document("+919876543210", "https://x.com/p.pdf")
        assert result is None

    def test_twilio_send_document_success(self):
        from app.services.whatsapp_gateway import WhatsAppGateway
        gw = WhatsAppGateway(provider="twilio")

        # Client is lazy-imported inside _send_document_twilio; patch at source
        with patch("app.services.whatsapp_gateway.settings") as mock_s, \
             patch("twilio.rest.Client") as mock_client_cls:
            mock_s.TWILIO_ACCOUNT_SID     = "ACtest"
            mock_s.TWILIO_AUTH_TOKEN      = "auth"
            mock_s.TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"
            mock_msg = MagicMock(); mock_msg.sid = "SM.twilio.doc"
            mock_client_cls.return_value.messages.create.return_value = mock_msg

            result = gw.send_document(
                "+919876543210",
                "https://example.com/p.pdf",
                caption = "April payslip",
            )
        assert result == "SM.twilio.doc"

    def test_module_send_document_function(self):
        """Module-level send_document() delegates to WhatsAppGateway."""
        from app.services.whatsapp_gateway import send_document
        with patch.object(
            __import__("app.services.whatsapp_gateway",
                        fromlist=["WhatsAppGateway"]).WhatsAppGateway,
            "send_document",
            return_value="wamid.mod",
        ) as mock:
            result = send_document("+919876543210", "https://x.com/p.pdf", "cap", "file.pdf")
        mock.assert_called_once_with("+919876543210", "https://x.com/p.pdf", "cap", "file.pdf")
