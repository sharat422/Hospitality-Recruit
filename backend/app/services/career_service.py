"""
career_service.py — Hospitality career path intelligence for the HR Bot.

Three public functions:
  detect_current_role(supabase, employee) → Optional[str]
  get_career_path(role)                  → CareerPath
  find_matching_jobs(supabase, employee, next_roles) → list[dict]

Internal helpers:
  _get_employee_certs(supabase, employee) → list[str]
  _normalise_role(role)                  → str
  _resolve_path(normalised)              → CareerPath
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Career path data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CareerPath:
    display:          str               # human-readable current role name
    next_roles:       list[str]         # ordered: nearest promotion first
    skills:           list[str]         # skills to acquire
    certifications:   list[str]         # certs needed for advancement
    timeline:         str = ""          # rough timeline e.g. "1–2 years"
    key:              str = ""          # internal lookup key


# ─────────────────────────────────────────────────────────────────────────────
# Career paths — hospitality domain
# ─────────────────────────────────────────────────────────────────────────────

_PATHS: dict[str, CareerPath] = {

    # ── F&B Service ───────────────────────────────────────────────────────────
    "waiter": CareerPath(
        display        = "Waiter / Server",
        next_roles     = ["Captain Waiter", "F&B Supervisor", "Banquet Captain"],
        skills         = ["Table service & etiquette", "Menu & beverage knowledge",
                          "Upselling techniques", "Guest complaint handling"],
        certifications = ["FSSAI Basic Food Hygiene", "FOSTAC"],
        timeline       = "1–2 years",
        key            = "waiter",
    ),
    "captain waiter": CareerPath(
        display        = "Captain Waiter",
        next_roles     = ["F&B Supervisor", "Restaurant Manager", "Banquet Manager"],
        skills         = ["Team supervision & training", "Table management",
                          "Guest escalation handling", "Shift reporting"],
        certifications = ["FSSAI", "Food Safety Supervisor Certificate"],
        timeline       = "1–3 years",
        key            = "captain waiter",
    ),
    "banquet waiter": CareerPath(
        display        = "Banquet Waiter",
        next_roles     = ["Banquet Captain", "Banquet Supervisor", "F&B Supervisor"],
        skills         = ["Banquet setup & breakdown", "High-volume service",
                          "Event coordination basics", "Team communication"],
        certifications = ["FSSAI Basic Food Hygiene", "FOSTAC"],
        timeline       = "1–2 years",
        key            = "banquet waiter",
    ),
    "banquet captain": CareerPath(
        display        = "Banquet Captain",
        next_roles     = ["Banquet Manager", "Events Supervisor", "F&B Supervisor"],
        skills         = ["Event planning basics", "Team leadership",
                          "Vendor coordination", "Cost awareness"],
        certifications = ["FSSAI", "FOSTAC Supervisor"],
        timeline       = "2–3 years",
        key            = "banquet captain",
    ),
    "f&b supervisor": CareerPath(
        display        = "F&B Supervisor",
        next_roles     = ["Assistant F&B Manager", "Restaurant Manager", "Bar Manager"],
        skills         = ["P&L reading", "Staff scheduling & payroll",
                          "SOP development", "Inventory management"],
        certifications = ["FSSAI License", "Food Safety Management Certificate"],
        timeline       = "2–4 years",
        key            = "f&b supervisor",
    ),
    "restaurant manager": CareerPath(
        display        = "Restaurant Manager",
        next_roles     = ["F&B Manager", "Director of F&B", "General Manager"],
        skills         = ["Revenue & yield management", "Menu engineering",
                          "Guest experience strategy", "Labour law compliance"],
        certifications = ["FSSAI License", "Hospitality Management Diploma"],
        timeline       = "3–5 years",
        key            = "restaurant manager",
    ),

    # ── Kitchen / Culinary ────────────────────────────────────────────────────
    "kitchen helper": CareerPath(
        display        = "Kitchen Helper",
        next_roles     = ["Commis Chef", "Cook", "Kitchen Steward"],
        skills         = ["Knife skills", "Kitchen hygiene (HACCP)",
                          "Food storage & labelling", "Station prep"],
        certifications = ["FSSAI Basic Food Hygiene", "FOSTAC"],
        timeline       = "6 months – 1 year",
        key            = "kitchen helper",
    ),
    "commis chef": CareerPath(
        display        = "Commis Chef",
        next_roles     = ["Chef de Partie", "Senior Cook", "Pastry Commis"],
        skills         = ["Culinary techniques", "Station management",
                          "Recipe adherence", "Food costing basics"],
        certifications = ["FSSAI", "FOSTAC", "Culinary Diploma"],
        timeline       = "1–2 years",
        key            = "commis chef",
    ),
    "chef de partie": CareerPath(
        display        = "Chef de Partie (CDP)",
        next_roles     = ["Sous Chef", "Senior CDP", "Pastry Chef"],
        skills         = ["Section leadership", "Training junior chefs",
                          "Menu development contribution", "Stock control"],
        certifications = ["FSSAI", "Culinary Arts Certificate", "HACCP Advanced"],
        timeline       = "2–3 years",
        key            = "chef de partie",
    ),
    "sous chef": CareerPath(
        display        = "Sous Chef",
        next_roles     = ["Head Chef", "Executive Sous Chef", "Kitchen Manager"],
        skills         = ["Kitchen operations management", "Cost control & budgeting",
                          "Staff performance management", "Menu creation"],
        certifications = ["FSSAI License", "Food Safety Management", "First Aid"],
        timeline       = "2–4 years",
        key            = "sous chef",
    ),
    "head chef": CareerPath(
        display        = "Head Chef",
        next_roles     = ["Executive Chef", "F&B Director", "Culinary Director"],
        skills         = ["Strategic menu planning", "P&L ownership",
                          "Brand & quality standards", "Vendor negotiation"],
        certifications = ["FSSAI License", "Hospitality Leadership Certificate"],
        timeline       = "3–5 years",
        key            = "head chef",
    ),

    # ── Housekeeping ─────────────────────────────────────────────────────────
    "room attendant": CareerPath(
        display        = "Room Attendant",
        next_roles     = ["Housekeeping Supervisor", "Laundry Supervisor", "Floor Supervisor"],
        skills         = ["Cleaning & sanitation standards", "Chemical handling",
                          "Linen & amenities management", "Guest privacy protocols"],
        certifications = ["Housekeeping Certificate", "Chemical Handling Safety"],
        timeline       = "1–2 years",
        key            = "room attendant",
    ),
    "housekeeping supervisor": CareerPath(
        display        = "Housekeeping Supervisor",
        next_roles     = ["Asst. Executive Housekeeper", "Floor Manager", "Laundry Manager"],
        skills         = ["Team scheduling", "Quality inspection rounds",
                          "Inventory & supplies management", "Guest complaint resolution"],
        certifications = ["Housekeeping Management Certificate", "First Aid"],
        timeline       = "2–3 years",
        key            = "housekeeping supervisor",
    ),

    # ── Front Office ─────────────────────────────────────────────────────────
    "receptionist": CareerPath(
        display        = "Receptionist / Front Desk Agent",
        next_roles     = ["Senior Receptionist", "Concierge", "Front Desk Supervisor"],
        skills         = ["PMS software (Opera/IDS)", "Check-in/check-out procedures",
                          "Revenue per room upselling", "Guest relations"],
        certifications = ["Hospitality Front Office Certificate", "Fire Safety"],
        timeline       = "1–2 years",
        key            = "receptionist",
    ),
    "front desk supervisor": CareerPath(
        display        = "Front Desk Supervisor",
        next_roles     = ["Front Office Manager", "Guest Relations Manager", "Night Manager"],
        skills         = ["Shift management", "Yield optimisation",
                          "Complaint resolution", "Staff training & appraisals"],
        certifications = ["Hotel Management Diploma", "PMS Advanced"],
        timeline       = "2–3 years",
        key            = "front desk supervisor",
    ),

    # ── Security ─────────────────────────────────────────────────────────────
    "security guard": CareerPath(
        display        = "Security Guard",
        next_roles     = ["Security Supervisor", "Security Manager", "Facilities Coordinator"],
        skills         = ["Access control", "Emergency response",
                          "CCTV monitoring", "Incident reporting"],
        certifications = ["PSARA License", "First Aid Certificate", "Fire Safety"],
        timeline       = "1–3 years",
        key            = "security guard",
    ),

    # ── General / Unknown ─────────────────────────────────────────────────────
    "general staff": CareerPath(
        display        = "Hospitality Staff",
        next_roles     = ["Department Supervisor", "Team Leader", "Department Coordinator"],
        skills         = ["Communication & teamwork", "Customer service excellence",
                          "Department-specific technical skills", "Basic computer literacy"],
        certifications = ["FSSAI Basic Food Hygiene", "First Aid"],
        timeline       = "1–2 years",
        key            = "general staff",
    ),
}

# Alias map: keyword fragments → canonical path key
_ALIASES: dict[str, str] = {
    "server":               "waiter",
    "food server":          "waiter",
    "service staff":        "waiter",
    "table staff":          "waiter",
    "banquet server":       "banquet waiter",
    "banquet staff":        "banquet waiter",
    "kitchen crew":         "kitchen helper",
    "kitchen steward":      "kitchen helper",
    "dishwasher":           "kitchen helper",
    "cook":                 "commis chef",
    "junior cook":          "commis chef",
    "commis":               "commis chef",
    "cdp":                  "chef de partie",
    "line chef":            "chef de partie",
    "pastry chef":          "chef de partie",
    "front desk":           "receptionist",
    "front office agent":   "receptionist",
    "guest service agent":  "receptionist",
    "gsa":                  "receptionist",
    "room cleaner":         "room attendant",
    "housekeeper":          "room attendant",
    "housekeeping":         "room attendant",
    "guard":                "security guard",
    "security":             "security guard",
    "f&b":                  "waiter",
    "food and beverage":    "waiter",
    "food & beverage":      "waiter",
    "hotel staff":          "general staff",
    "general":              "general staff",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def detect_current_role(supabase, employee: dict) -> Optional[str]:
    """
    Req 1 — Infer the employee's current role.

    Source priority:
      1. candidate_profiles.current_role  (explicit, set at screening)
      2. v_employee_shifts.role           (most recent confirmed shift)
      3. v_candidate_shifts.role          (hired-candidate fallback)
      4. shift_matches + shifts           (raw query fallback)
      Returns None if role cannot be determined.
    """
    # ── 1. candidate_profiles ─────────────────────────────────────────────────
    try:
        cand_id = _get_candidate_id(supabase, employee)
        if cand_id:
            res = (
                supabase.table("candidate_profiles")
                .select("current_role")
                .eq("candidate_id", cand_id)
                .limit(1)
                .execute()
            )
            role = (res.data or [{}])[0].get("current_role")
            if role:
                return role.strip()
    except Exception as exc:
        logger.debug("candidate_profiles role lookup failed: %s", exc)

    # ── 2. v_employee_shifts — most recent shift's role ───────────────────────
    try:
        res = (
            supabase.table("v_employee_shifts")
            .select("role")
            .eq("employee_id", employee["employee_id"])
            .order("start_date", desc=True)
            .limit(1)
            .execute()
        )
        role = (res.data or [{}])[0].get("role")
        if role:
            return role.strip()
    except Exception as exc:
        logger.debug("v_employee_shifts role lookup failed: %s", exc)

    # ── 3. v_candidate_shifts ─────────────────────────────────────────────────
    if employee.get("source") == "candidates":
        try:
            res = (
                supabase.table("v_candidate_shifts")
                .select("role")
                .eq("candidate_id", employee["employee_id"])
                .order("start_date", desc=True)
                .limit(1)
                .execute()
            )
            role = (res.data or [{}])[0].get("role")
            if role:
                return role.strip()
        except Exception as exc:
            logger.debug("v_candidate_shifts role lookup failed: %s", exc)

    # ── 4. Raw shift_matches fallback ─────────────────────────────────────────
    try:
        cand_id = cand_id or _get_candidate_id(supabase, employee)
        if cand_id:
            sm_res = (
                supabase.table("shift_matches")
                .select("shift_id")
                .eq("candidate_id", cand_id)
                .in_("status", ["confirmed", "matched"])
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if sm_res.data:
                s_res = (
                    supabase.table("shifts")
                    .select("role")
                    .eq("id", sm_res.data[0]["shift_id"])
                    .limit(1)
                    .execute()
                )
                role = (s_res.data or [{}])[0].get("role")
                if role:
                    return role.strip()
    except Exception as exc:
        logger.debug("shift fallback role lookup failed: %s", exc)

    return None


def get_career_path(role: Optional[str]) -> CareerPath:
    """
    Req 2+3 — Return the CareerPath for the given role.

    Matching order:
      1. Exact key match
      2. Alias map match
      3. Substring match (role ⊆ key or key ⊆ role)
      4. Word-level match (shared meaningful word)
      5. Fallback to "general staff"
    """
    if not role:
        return _PATHS["general staff"]

    normalised = _normalise_role(role)

    # 1. Exact
    if normalised in _PATHS:
        return _PATHS[normalised]

    # 2. Alias
    for alias, key in _ALIASES.items():
        if alias in normalised or normalised in alias:
            return _PATHS[key]

    # 3. Substring
    for key, path in _PATHS.items():
        if key in normalised or normalised in key:
            return path

    # 4. Shared word (length > 3 to avoid noise words)
    norm_words = set(w for w in normalised.split() if len(w) > 3)
    for key, path in _PATHS.items():
        key_words = set(w for w in key.split() if len(w) > 3)
        if norm_words & key_words:
            return path

    return _PATHS["general staff"]


def get_employee_certs(supabase, employee: dict) -> list[str]:
    """
    Retrieve the employee's existing certifications from candidate_profiles.
    Returns a list of certification name strings (normalised to lowercase).
    """
    try:
        cand_id = _get_candidate_id(supabase, employee)
        if not cand_id:
            return []
        res = (
            supabase.table("candidate_profiles")
            .select("certifications")
            .eq("candidate_id", cand_id)
            .limit(1)
            .execute()
        )
        raw = (res.data or [{}])[0].get("certifications") or []
        if isinstance(raw, list):
            return [str(c).lower().strip() for c in raw if c]
        return []
    except Exception as exc:
        logger.debug("cert fetch failed: %s", exc)
        return []


def find_matching_jobs(
    supabase,
    employee:   dict,
    next_roles: list[str],
) -> list[dict]:
    """
    Req 4 — Return open internal jobs that align with the employee's next roles.

    Matching strategy:
      For each open job, check if its title or role_type shares a meaningful word
      with any of the next_roles. Returns up to 3 matches.
      Falls back to returning up to 3 any open jobs if no specific match.
    """
    try:
        res = (
            supabase.table("jobs")
            .select("id, title, role_type, description, required_qualifications, status")
            .eq("org_id", employee["org_id"])
            .eq("status", "open")
            .limit(15)
            .execute()
        )
        all_jobs = res.data or []
    except Exception as exc:
        logger.warning("jobs fetch failed: %s", exc)
        return []

    if not all_jobs:
        return []

    # Build keyword set from next_roles (words longer than 3 chars)
    role_words: set[str] = set()
    for r in next_roles:
        role_words.update(w.lower() for w in r.split() if len(w) > 3)

    matched, unmatched = [], []
    for job in all_jobs:
        title     = (job.get("title")     or "").lower()
        role_type = (job.get("role_type") or "").lower()
        combined  = f"{title} {role_type}"
        if any(w in combined for w in role_words):
            matched.append(job)
        else:
            unmatched.append(job)

    # Return matched first, then fill from unmatched up to 3 total
    result = matched[:3]
    if len(result) < 3:
        result += unmatched[: 3 - len(result)]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_role(role: str) -> str:
    """Lowercase, strip, collapse spaces."""
    return " ".join(role.lower().split())


def _get_candidate_id(supabase, employee: dict) -> Optional[str]:
    """Return the candidates table UUID for this employee."""
    if employee.get("source") == "candidates":
        return employee["employee_id"]
    try:
        res = (
            supabase.table("candidates")
            .select("id")
            .eq("phone", employee.get("phone", ""))
            .eq("org_id", employee["org_id"])
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]["id"]
    except Exception:
        pass
    return None
