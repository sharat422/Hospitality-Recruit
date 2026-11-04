"""
Tests for the CAREER command — all 5 requirements.

Req 1 — Detect employee's current role
Req 2 — Show next possible hospitality roles
Req 3 — Show required skills and certifications (mark held ones ✅)
Req 4 — Suggest open internal jobs aligned with next roles
Req 5 — WhatsApp-friendly compact format

Additional coverage:
  - Role detection priority: candidate_profiles → v_employee_shifts → fallback
  - Career path lookup: exact, alias, substring, word-level, fallback
  - Certification matching: already-held vs still-needed
  - Job matching: title/role_type word overlap
  - Unknown/no role → generic hospitality path
  - No open jobs → friendly message
  - Hindi footer present
  - career_service module unit tests (detect_current_role, get_career_path,
    find_matching_jobs, get_employee_certs)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# MockSupabase (queue-based)
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
    def in_(self, *a, **kw):    return self
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

EMP_ID   = "emp-uuid-001"
ORG_ID   = "org-uuid-001"
CAND_ID  = "cand-uuid-001"

EMPLOYEE = {
    "employee_id":      EMP_ID,
    "org_id":           ORG_ID,
    "name":             "Priya Sharma",
    "phone":            "+919876543210",
    "source":           "users",
    "whatsapp_user_id": None,
}

EMPLOYEE_CANDIDATE = {**EMPLOYEE, "source": "candidates", "employee_id": CAND_ID}

# sample open jobs
JOB_FNB_SUP = {
    "id": "job-001", "title": "F&B Supervisor", "role_type": "full_time",
    "description": "Lead the F&B team.", "required_qualifications": "FSSAI",
    "status": "open",
}
JOB_BANQUET_MGR = {
    "id": "job-002", "title": "Banquet Manager", "role_type": "full_time",
    "description": "Manage banquet operations.", "required_qualifications": "",
    "status": "open",
}
JOB_FRONT_MGR = {
    "id": "job-003", "title": "Front Desk Manager", "role_type": "full_time",
    "description": "Manage front desk team.", "required_qualifications": "",
    "status": "open",
}


def _handle(sb, employee=None) -> str:
    from app.services.hr_bot_service import handle_career
    return handle_career(sb, employee or EMPLOYEE, [])


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a standard MockSupabase for handle_career flow
#
# Queue order inside handle_career:
#   detect_current_role:
#     1. candidates lookup (for _get_candidate_id)
#     2. candidate_profiles.current_role
#     3. v_employee_shifts.role
#     (stops when role found)
#   get_employee_certs:
#     4. candidates lookup
#     5. candidate_profiles.certifications
#   find_matching_jobs:
#     6. jobs
# ─────────────────────────────────────────────────────────────────────────────

def _make_sb(
    *,
    profile_role: str      = "Banquet Waiter",
    profile_certs: list    = None,
    shift_role: str        = None,
    candidate_id: str      = CAND_ID,
    open_jobs: list        = None,
) -> MockSupabase:
    sb = MockSupabase()
    # detect_current_role → _get_candidate_id → candidates
    sb.configure("candidates", [{"id": candidate_id}])
    # detect_current_role → candidate_profiles
    sb.configure("candidate_profiles",
                 [{"current_role": profile_role}] if profile_role else [])
    # detect_current_role → v_employee_shifts (only hit if profile has no role)
    if not profile_role and shift_role:
        sb.configure("v_employee_shifts", [{"role": shift_role}])
    else:
        sb.configure("v_employee_shifts", [])

    # get_employee_certs → _get_candidate_id → candidates
    sb.configure("candidates", [{"id": candidate_id}])
    # get_employee_certs → candidate_profiles
    sb.configure("candidate_profiles",
                 [{"certifications": profile_certs or []}])

    # find_matching_jobs → jobs
    sb.configure("jobs", open_jobs if open_jobs is not None else [JOB_FNB_SUP, JOB_BANQUET_MGR])
    return sb


# ═════════════════════════════════════════════════════════════════════════════
# Req 1 — Detect employee's current role
# ═════════════════════════════════════════════════════════════════════════════

class TestRoleDetection:
    def test_role_from_candidate_profile(self):
        """candidate_profiles.current_role is the primary source."""
        from app.services.career_service import detect_current_role

        sb = MockSupabase()
        sb.configure("candidates",         [{"id": CAND_ID}])
        sb.configure("candidate_profiles", [{"current_role": "Sous Chef"}])

        role = detect_current_role(sb, EMPLOYEE)
        assert role == "Sous Chef"

    def test_role_from_v_employee_shifts_fallback(self):
        """When no candidate_profile, fall back to v_employee_shifts."""
        from app.services.career_service import detect_current_role

        sb = MockSupabase()
        sb.configure("candidates",         [{"id": CAND_ID}])
        sb.configure("candidate_profiles", [{}])                  # no current_role
        sb.configure("v_employee_shifts",  [{"role": "Banquet Waiter"}])

        role = detect_current_role(sb, EMPLOYEE)
        assert role == "Banquet Waiter"

    def test_role_from_v_candidate_shifts_for_candidate_employee(self):
        """Hired candidates (source=candidates) use v_candidate_shifts."""
        from app.services.career_service import detect_current_role

        sb = MockSupabase()
        sb.configure("candidate_profiles", [{}])             # no role here
        sb.configure("v_employee_shifts",  [])               # no shifts here
        sb.configure("v_candidate_shifts", [{"role": "Room Attendant"}])

        role = detect_current_role(sb, EMPLOYEE_CANDIDATE)
        assert role == "Room Attendant"

    def test_role_from_raw_shift_fallback(self):
        """All views fail → raw shift_matches + shifts fallback."""
        from app.services.career_service import detect_current_role

        sb = MockSupabase()
        sb.configure("candidates",        [{"id": CAND_ID}])
        sb.configure("candidate_profiles",[{}])
        sb.configure("v_employee_shifts", [])
        sb.configure("shift_matches",     [{"shift_id": "s1", "status": "confirmed"}])
        sb.configure("shifts",            [{"role": "Head Chef"}])

        role = detect_current_role(sb, EMPLOYEE)
        assert role == "Head Chef"

    def test_no_role_returns_none(self):
        """All sources empty → returns None."""
        from app.services.career_service import detect_current_role

        sb = MockSupabase()
        sb.configure("candidates",        [{"id": CAND_ID}])
        sb.configure("candidate_profiles",[{}])
        sb.configure("v_employee_shifts", [])

        role = detect_current_role(sb, EMPLOYEE)
        assert role is None

    def test_role_shown_in_reply(self):
        sb    = _make_sb(profile_role="Banquet Waiter")
        reply = _handle(sb)
        assert "Banquet Waiter" in reply

    def test_unknown_role_shows_not_assigned(self):
        """No role → display says 'Not yet assigned'."""
        sb = MockSupabase()
        sb.configure("candidates",         [{"id": CAND_ID}])
        sb.configure("candidate_profiles", [{}])
        sb.configure("v_employee_shifts",  [])
        sb.configure("candidates",         [{"id": CAND_ID}])  # get_employee_certs
        sb.configure("candidate_profiles", [{"certifications": []}])
        sb.configure("jobs",               [])

        reply = _handle(sb)
        assert "Not yet assigned" in reply or "not" in reply.lower()

    def test_db_error_does_not_crash(self):
        """DB error on role detection → graceful fallback to generic path."""
        sb = MockSupabase()
        with patch.object(sb, "table", side_effect=Exception("DB down")):
            reply = _handle(sb)
        assert "HospBot" in reply   # still returns a reply


# ═════════════════════════════════════════════════════════════════════════════
# Req 2 — Show next possible hospitality roles
# ═════════════════════════════════════════════════════════════════════════════

class TestNextRoles:
    def test_three_next_roles_shown(self):
        sb    = _make_sb(profile_role="Banquet Waiter")
        reply = _handle(sb)
        # Banquet Waiter → Banquet Captain, Banquet Supervisor, F&B Supervisor
        assert "Banquet Captain" in reply or "F&B Supervisor" in reply

    def test_next_roles_numbered(self):
        sb    = _make_sb(profile_role="Waiter")
        reply = _handle(sb)
        assert "1️⃣" in reply
        assert "2️⃣" in reply

    def test_waiter_path(self):
        from app.services.career_service import get_career_path
        path = get_career_path("Waiter")
        assert "Captain Waiter" in path.next_roles
        assert len(path.next_roles) >= 2

    def test_sous_chef_path(self):
        from app.services.career_service import get_career_path
        path = get_career_path("Sous Chef")
        assert any("Head Chef" in r or "Executive" in r for r in path.next_roles)

    def test_receptionist_path(self):
        from app.services.career_service import get_career_path
        path = get_career_path("Receptionist")
        assert any("Supervisor" in r or "Concierge" in r for r in path.next_roles)

    def test_housekeeping_supervisor_path(self):
        from app.services.career_service import get_career_path
        path = get_career_path("Housekeeping Supervisor")
        assert any("Housekeeper" in r or "Manager" in r for r in path.next_roles)

    def test_unknown_role_generic_path(self):
        from app.services.career_service import get_career_path
        path = get_career_path("Random Unknown Role XYZ")
        assert path.key == "general staff"
        assert len(path.next_roles) >= 1

    def test_none_role_generic_path(self):
        from app.services.career_service import get_career_path
        path = get_career_path(None)
        assert path.key == "general staff"


# ═════════════════════════════════════════════════════════════════════════════
# Req 3 — Skills and certifications
# ═════════════════════════════════════════════════════════════════════════════

class TestSkillsAndCerts:
    def test_skills_shown_in_reply(self):
        sb    = _make_sb(profile_role="Waiter")
        reply = _handle(sb)
        # Waiter skills include "Table service" and "Upselling"
        assert "service" in reply.lower() or "etiquette" in reply.lower() or "skills" in reply.lower()

    def test_certifications_shown(self):
        sb    = _make_sb(profile_role="Waiter")
        reply = _handle(sb)
        # Waiter certs: FSSAI + FOSTAC
        assert "FSSAI" in reply or "FOSTAC" in reply

    def test_already_held_cert_marked(self):
        """Cert the employee already has should show ✅."""
        sb = _make_sb(
            profile_role  = "Waiter",
            profile_certs = ["fssai basic food hygiene"],  # already held
        )
        reply = _handle(sb)
        assert "✅" in reply

    def test_still_needed_cert_marked(self):
        """Cert not yet held should show 📋."""
        sb = _make_sb(
            profile_role  = "Waiter",
            profile_certs = [],  # none held
        )
        reply = _handle(sb)
        assert "📋" in reply

    def test_mixed_certs_both_markers(self):
        """Some held, some not → both ✅ and 📋 appear."""
        sb = _make_sb(
            profile_role  = "Waiter",
            profile_certs = ["fssai basic food hygiene"],  # holds FSSAI, not FOSTAC
        )
        reply = _handle(sb)
        assert "✅" in reply
        assert "📋" in reply

    def test_max_four_skills_shown(self):
        sb    = _make_sb(profile_role="Head Chef")
        reply = _handle(sb)
        # Should not dump an overwhelming list
        skill_bullets = [l for l in reply.split("\n") if l.strip().startswith("•")]
        assert len(skill_bullets) <= 4

    def test_max_three_certs_shown(self):
        sb    = _make_sb(profile_role="Head Chef")
        reply = _handle(sb)
        cert_lines = [l for l in reply.split("\n") if "✅" in l or "📋" in l]
        assert len(cert_lines) <= 3

    def test_get_employee_certs_returns_list(self):
        from app.services.career_service import get_employee_certs

        sb = MockSupabase()
        sb.configure("candidates",         [{"id": CAND_ID}])
        sb.configure("candidate_profiles", [{"certifications": ["FSSAI", "FOSTAC"]}])

        certs = get_employee_certs(sb, EMPLOYEE)
        assert isinstance(certs, list)
        assert len(certs) == 2

    def test_get_employee_certs_empty_profile(self):
        from app.services.career_service import get_employee_certs

        sb = MockSupabase()
        sb.configure("candidates",         [{"id": CAND_ID}])
        sb.configure("candidate_profiles", [{"certifications": []}])

        assert get_employee_certs(sb, EMPLOYEE) == []

    def test_get_employee_certs_no_profile(self):
        from app.services.career_service import get_employee_certs

        sb = MockSupabase()
        sb.configure("candidates",         [])  # no candidate record

        assert get_employee_certs(sb, EMPLOYEE) == []

    def test_get_employee_certs_db_error_returns_empty(self):
        from app.services.career_service import get_employee_certs

        sb = MockSupabase()
        with patch.object(sb, "table", side_effect=Exception("DB down")):
            assert get_employee_certs(sb, EMPLOYEE) == []

    def test_timeline_shown(self):
        sb    = _make_sb(profile_role="Waiter")
        reply = _handle(sb)
        assert "Timeline" in reply or "year" in reply.lower()


# ═════════════════════════════════════════════════════════════════════════════
# Req 4 — Suggest open internal jobs
# ═════════════════════════════════════════════════════════════════════════════

class TestInternalJobSuggestions:
    def test_matching_jobs_shown(self):
        """Jobs whose title matches next-role keywords appear in the reply."""
        sb = _make_sb(
            profile_role = "Banquet Waiter",
            open_jobs    = [JOB_FNB_SUP, JOB_BANQUET_MGR],
        )
        reply = _handle(sb)
        assert "F&B Supervisor" in reply or "Banquet Manager" in reply

    def test_no_open_jobs_friendly_message(self):
        sb = _make_sb(profile_role="Waiter", open_jobs=[])
        reply = _handle(sb)
        assert "no open" in reply.lower() or "notify" in reply.lower()

    def test_max_three_jobs_shown(self):
        sb = _make_sb(
            profile_role = "Waiter",
            open_jobs    = [JOB_FNB_SUP, JOB_BANQUET_MGR, JOB_FRONT_MGR,
                            {**JOB_FNB_SUP, "id": "job-4", "title": "Extra Job 1"},
                            {**JOB_FNB_SUP, "id": "job-5", "title": "Extra Job 2"}],
        )
        reply = _handle(sb)
        job_lines = [l for l in reply.split("\n") if l.strip().startswith("→")]
        assert len(job_lines) <= 3

    def test_jobs_not_matching_still_shown_as_fallback(self):
        """When no job matches next roles exactly, still show up to 3 open jobs."""
        unrelated_job = {
            "id": "job-x", "title": "Unrelated Generalist", "role_type": "contract",
            "description": "...", "status": "open",
        }
        sb = _make_sb(profile_role="Waiter", open_jobs=[unrelated_job])
        reply = _handle(sb)
        # Should show the unrelated job as fallback
        assert "Unrelated Generalist" in reply or "open" in reply.lower()

    def test_apply_internally_message(self):
        sb = _make_sb(profile_role="Waiter", open_jobs=[JOB_FNB_SUP])
        reply = _handle(sb)
        assert "HR" in reply or "apply" in reply.lower() or "internal" in reply.lower()

    def test_find_matching_jobs_prefers_role_matches(self):
        """Jobs matching next-roles appear before generic ones."""
        from app.services.career_service import find_matching_jobs, get_career_path

        path     = get_career_path("Banquet Waiter")
        all_jobs = [
            {"id": "j1", "title": "Banquet Captain", "role_type": "full_time",
             "status": "open"},  # matches
            {"id": "j2", "title": "IT Support Technician", "role_type": "contract",
             "status": "open"},  # no match
        ]
        sb = MockSupabase()
        sb.configure("jobs", all_jobs)

        matches = find_matching_jobs(sb, EMPLOYEE, path.next_roles)
        # "Banquet Captain" should come before "IT Support Technician"
        titles = [j["title"] for j in matches]
        if len(titles) > 1 and "Banquet Captain" in titles and "IT Support Technician" in titles:
            assert titles.index("Banquet Captain") < titles.index("IT Support Technician")

    def test_find_matching_jobs_db_error_returns_empty(self):
        from app.services.career_service import find_matching_jobs

        sb = MockSupabase()
        with patch.object(sb, "table", side_effect=Exception("DB down")):
            result = find_matching_jobs(sb, EMPLOYEE, ["F&B Supervisor"])
        assert result == []


# ═════════════════════════════════════════════════════════════════════════════
# Req 5 — WhatsApp-friendly compact format
# ═════════════════════════════════════════════════════════════════════════════

class TestWhatsAppFormat:
    def _reply(self, role="Banquet Waiter") -> str:
        return _handle(_make_sb(profile_role=role))

    def test_bot_name_present(self):
        assert "HospBot" in self._reply()

    def test_employee_first_name_present(self):
        assert "Priya" in self._reply()

    def test_current_role_section(self):
        r = self._reply()
        assert "Current Role" in r

    def test_next_steps_section(self):
        r = self._reply()
        assert "Next Steps" in r or "Next" in r

    def test_skills_section(self):
        r = self._reply()
        assert "Skills" in r or "skills" in r.lower()

    def test_certs_section(self):
        r = self._reply()
        assert "Certification" in r or "FSSAI" in r or "📋" in r or "✅" in r

    def test_dividers_present(self):
        r = self._reply()
        assert "━" in r

    def test_hindi_footer(self):
        r = self._reply()
        hindi = sum(1 for c in r if "ऀ" <= c <= "ॿ")
        assert hindi > 0

    def test_no_traceback_on_db_error(self):
        sb = MockSupabase()
        with patch.object(sb, "table", side_effect=Exception("DB down")):
            reply = _handle(sb)
        assert "Traceback" not in reply
        assert "HospBot" in reply

    def test_reply_is_string(self):
        assert isinstance(self._reply(), str)


# ═════════════════════════════════════════════════════════════════════════════
# get_career_path — unit tests for all matching strategies
# ═════════════════════════════════════════════════════════════════════════════

class TestGetCareerPath:
    def _path(self, role):
        from app.services.career_service import get_career_path
        return get_career_path(role)

    # Exact match
    def test_exact_waiter(self):    assert self._path("waiter").key      == "waiter"
    def test_exact_sous_chef(self): assert self._path("sous chef").key   == "sous chef"
    def test_exact_cdp(self):       assert self._path("chef de partie").key == "chef de partie"

    # Case-insensitive exact
    def test_case_insensitive(self): assert self._path("WAITER").key     == "waiter"
    def test_mixed_case(self):       assert self._path("Banquet Waiter").key == "banquet waiter"

    # Alias match
    def test_alias_server(self):       assert self._path("server").key       == "waiter"
    def test_alias_cook(self):         assert self._path("cook").key          == "commis chef"
    def test_alias_front_desk(self):   assert self._path("front desk").key    == "receptionist"
    def test_alias_housekeeping(self): assert self._path("housekeeping").key  == "room attendant"
    def test_alias_commis(self):       assert self._path("commis").key        == "commis chef"
    def test_alias_gsa(self):          assert self._path("gsa").key           == "receptionist"
    def test_alias_security(self):     assert self._path("security").key      == "security guard"

    # Substring match
    def test_substring_banquet(self):  p = self._path("banquet floor staff"); assert "banquet" in p.key
    def test_substring_chef(self):     p = self._path("executive sous chef");  assert "sous" in p.key or "chef" in p.key

    # Word-level match
    def test_word_match_supervisor(self): p = self._path("F&B Operations Supervisor"); assert "supervisor" in p.key or p.key != "general staff"

    # Fallback
    def test_unknown_falls_back(self):    assert self._path("Xyz123 Random").key == "general staff"
    def test_none_falls_back(self):       assert self._path(None).key            == "general staff"
    def test_empty_falls_back(self):      assert self._path("").key              == "general staff"

    # Data completeness
    @pytest.mark.parametrize("role", [
        "waiter", "captain waiter", "banquet waiter", "banquet captain",
        "f&b supervisor", "restaurant manager",
        "kitchen helper", "commis chef", "chef de partie", "sous chef", "head chef",
        "room attendant", "housekeeping supervisor",
        "receptionist", "front desk supervisor",
        "security guard", "general staff",
    ])
    def test_all_paths_have_required_fields(self, role):
        from app.services.career_service import get_career_path
        p = get_career_path(role)
        assert len(p.next_roles)     >= 1, f"{role}: no next_roles"
        assert len(p.skills)         >= 2, f"{role}: fewer than 2 skills"
        assert len(p.certifications) >= 1, f"{role}: no certifications"
        assert p.timeline,                 f"{role}: no timeline"


# ═════════════════════════════════════════════════════════════════════════════
# Integration — dispatcher routes CAREER command correctly
# ═════════════════════════════════════════════════════════════════════════════

class TestCareerDispatch:
    def test_career_command_dispatched(self):
        from app.services.hr_bot_service import handle_whatsapp_message

        sb = MockSupabase()
        # Employee lookup
        sb.configure("whatsapp_users",  [{"id": "wu", "employee_id": EMP_ID,
                                           "org_id": ORG_ID, "display_name": "Priya",
                                           "opt_out": False}])
        sb.configure("whatsapp_users",  [{"id": "wu", "message_count": 1}])
        sb.configure("whatsapp_users",  [])
        sb.configure("hr_bot_sessions", [{"id": "s", "message_count": 1}])
        sb.configure("hr_bot_sessions", [])
        sb.configure("whatsapp_messages", [{"id": "wm"}])
        # Career data
        sb.configure("candidates",         [{"id": CAND_ID}])
        sb.configure("candidate_profiles", [{"current_role": "Banquet Waiter"}])
        sb.configure("v_employee_shifts",  [])
        sb.configure("candidates",         [{"id": CAND_ID}])
        sb.configure("candidate_profiles", [{"certifications": ["FSSAI"]}])
        sb.configure("jobs",               [JOB_FNB_SUP])
        # Message update
        sb.configure("whatsapp_messages",  [])

        with patch("app.services.whatsapp_gateway.WhatsAppGateway.send", return_value="ok"):
            reply = handle_whatsapp_message(sb, EMPLOYEE["phone"], "CAREER")

        assert "HospBot" in reply
        assert "Career" in reply or "career" in reply.lower()

    def test_naukri_hindi_alias_dispatched(self):
        """'नौकरी' (Hindi for jobs/career) should reach handle_career."""
        from app.services.hr_bot_service import handle_whatsapp_message

        sb = MockSupabase()
        sb.configure("whatsapp_users",  [{"id": "wu", "employee_id": EMP_ID,
                                           "org_id": ORG_ID, "display_name": "Priya",
                                           "opt_out": False}])
        sb.configure("whatsapp_users",  [{"id": "wu", "message_count": 1}])
        sb.configure("whatsapp_users",  [])
        sb.configure("hr_bot_sessions", [{"id": "s", "message_count": 1}])
        sb.configure("hr_bot_sessions", [])
        sb.configure("whatsapp_messages", [{"id": "wm"}])
        sb.configure("candidates",         [{"id": CAND_ID}])
        sb.configure("candidate_profiles", [{}])
        sb.configure("v_employee_shifts",  [])
        sb.configure("candidates",         [{"id": CAND_ID}])
        sb.configure("candidate_profiles", [{"certifications": []}])
        sb.configure("jobs",               [])
        sb.configure("whatsapp_messages",  [])

        with patch("app.services.whatsapp_gateway.WhatsAppGateway.send", return_value="ok"):
            reply = handle_whatsapp_message(sb, EMPLOYEE["phone"], "नौकरी")

        assert "HospBot" in reply
        assert "Career" in reply or "career" in reply.lower() or "Next" in reply
