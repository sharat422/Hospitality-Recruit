"""
smart_recruitment_service.py — Smart Recruitment for Indian hotel hiring.

Covers:
  • Bilingual JD generation (Hindi + English) via Claude
  • Pipeline management (applied→screened→interview→offer→hired)
  • Bulk actions (shortlist, reject, WhatsApp invite, stage update)
  • Mobile OTP for 60-second apply form
  • QR-code URL construction + scan tracking
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.services.otp_service import (
    generate_otp,
    hash_otp,
    normalize_india_phone,
    validate_india_phone,
    verify_otp_hash,
)

logger = logging.getLogger(__name__)

# Allowed pipeline stages in order
PIPELINE_STAGES = ["applied", "screened", "shortlisted", "interview", "selected", "offer", "offer_accepted", "onboarding", "hired"]
TERMINAL_STAGES = ["rejected", "withdrawn"]

# Allowed candidate sources (Req 3)
CANDIDATE_SOURCES = [
    "naukri", "apna", "workindia", "shine", "indeed_india",
    "whatsapp", "referral", "walk_in", "job_fair", "placement", "qr_code", "other",
]

# Stage timestamp field mapping
_STAGE_TS = {
    "screened":  "screened_at",
    "shortlisted": "shortlisted_at",
    "interview": "interview_at",
    "selected": "selected_at",
    "offer":     "offered_at",
    "offer_accepted": "offer_accepted_at",
    "onboarding": "onboarding_at",
    "hired":     "hired_at",
}


# ─────────────────────────────────────────────────────────────────────────────
# JD generation — bilingual Hindi + English
# ─────────────────────────────────────────────────────────────────────────────

def generate_jd_bilingual(
    role_display:  str,
    property_name: str,
    department:    str,
    city:          str  = "",
    salary_min:    int  = 0,
    salary_max:    int  = 0,
    experience_min:int  = 0,
    requirements: Optional[dict] = None,
) -> dict[str, str]:
    """
    Generate job descriptions in English and Hindi using Claude.
    Returns {"english": "...", "hindi": "..."}.
    Falls back to a template-based version if Claude is unavailable.
    """
    try:
        from anthropic import Anthropic
        from app.core.config import settings

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        salary_str = ""
        if salary_min and salary_max:
            salary_str = f"Salary range: ₹{salary_min:,} – ₹{salary_max:,} per month."
        elif salary_min:
            salary_str = f"Salary from ₹{salary_min:,} per month."

        exp_str = (
            f"Minimum {experience_min} year(s) of experience required."
            if experience_min else "Freshers are welcome to apply."
        )

        requirements = requirements or {}
        context = ", ".join(f"{key}: {value}" for key, value in requirements.items() if value not in (None, "", [], {}))
        prompt = (
            f"Write a job description for a {role_display} position at "
            f"{property_name}, {department} department"
            f"{', ' + city if city else ''}. "
            f"{exp_str} {salary_str} Additional role details: {context or 'none supplied'}.\n\n"
            f"Requirements:\n"
            f"1. Keep it concise: 80-100 words in English, 80-100 words in Hindi.\n"
            f"2. Mention the property name and department.\n"
            f"3. Include 3-4 key responsibilities.\n"
            f"4. End with a WhatsApp-friendly apply CTA.\n"
            f"5. The Hindi must be in Devanagari script and natural Indian Hindi.\n\n"
            f"Reply in this EXACT JSON format:\n"
            f'{{"english": "...", "hindi": "..."}}'
        )

        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = msg.content[0].text.strip()
        # Extract JSON from response
        start = text.find("{")
        end   = text.rfind("}") + 1
        result = json.loads(text[start:end])
        return {
            "english": result.get("english", ""),
            "hindi":   result.get("hindi", ""),
        }

    except Exception as exc:
        logger.warning("Claude JD generation failed, using template: %s", exc)
        return _template_jd(role_display, property_name, department, city,
                            salary_min, salary_max, experience_min, requirements or {})


def _template_jd(
    role:          str,
    property_name: str,
    department:    str,
    city:          str,
    salary_min:    int,
    salary_max:    int,
    experience_min:int,
    requirements: Optional[dict] = None,
) -> dict[str, str]:
    """Fallback template-based JD when Claude is unavailable."""
    exp = f"{experience_min}+ year(s) exp" if experience_min else "Freshers welcome"
    sal = f"₹{salary_min:,}–{salary_max:,}/month" if salary_min and salary_max else "As per industry standards"
    loc = city or "India"

    requirements = requirements or {}
    benefits = [label for key, label in (
        ("accommodation_provided", "Accommodation"), ("food_provided", "Meals"),
        ("transportation_provided", "Transportation")) if requirements.get(key)]
    extras_en = f" Benefits: {', '.join(benefits)} provided." if benefits else ""
    extras_hi = f" सुविधाएं: {', '.join(benefits)} उपलब्ध।" if benefits else ""
    english = (
        f"We are hiring a {role} for {property_name} ({department} Department), {loc}. "
        f"{exp}. Salary: {sal}. "
        f"Key duties: guest service, team coordination, maintaining quality standards. "
        f"Send your CV on WhatsApp or apply via the link below.{extras_en}"
    )
    hindi = (
        f"{property_name} ({department} विभाग), {loc} में {role} की भर्ती हो रही है। "
        f"{'न्यूनतम ' + str(experience_min) + ' वर्ष अनुभव आवश्यक।' if experience_min else 'फ्रेशर्स का स्वागत है।'} "
        f"वेतन: {sal}। "
        f"मुख्य जिम्मेदारियां: अतिथि सेवा, टीम समन्वय, गुणवत्ता मानक। "
        f"WhatsApp पर CV भेजें या नीचे दिए लिंक से आवेदन करें।{extras_hi}"
    )
    return {"english": english, "hindi": hindi}


def generate_job_board_versions(job: dict) -> dict[str, dict[str, str]]:
    """Generate channel-specific English/Hindi copy with deterministic fallback."""
    base_en = job.get("jd_english") or job.get("description") or ""
    base_hi = job.get("jd_hindi") or ""
    title = job.get("title") or "Hospitality role"
    city = job.get("location_city") or job.get("location_state") or "India"
    salary = ""
    if job.get("salary_min_inr") and job.get("salary_max_inr"):
        salary = f"₹{job['salary_min_inr']:,}-₹{job['salary_max_inr']:,}/month"
    apply_url = job.get("apply_url") or ""
    return {
        "naukri": {"english": f"{title} | {city} | {salary}\n{base_en}".strip(), "hindi": base_hi},
        "apna": {"english": f"Hiring: {title}\nLocation: {city}\nSalary: {salary or 'Competitive'}\n{base_en[:500]}\nApply: {apply_url}".strip(), "hindi": f"भर्ती: {title}\nस्थान: {city}\n{base_hi[:500]}\nआवेदन: {apply_url}".strip()},
        "indeed_india": {"english": f"{title}\n\n{base_en}\n\nLocation: {city}. {salary}".strip(), "hindi": base_hi},
        "linkedin": {"english": f"We're hiring a {title} in {city}.\n\n{base_en}\n\nApply now: {apply_url}".strip(), "hindi": base_hi},
        "whatsapp": {"english": f"🏨 {title} vacancy in {city}\n💰 {salary or 'Salary discussed at interview'}\nApply: {apply_url}".strip(), "hindi": f"🏨 {city} में {title} की भर्ती\n💰 {salary or 'वेतन इंटरव्यू में तय होगा'}\nआवेदन: {apply_url}".strip()},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline management
# ─────────────────────────────────────────────────────────────────────────────

def get_pipeline(supabase, org_id: str, job_id: Optional[str] = None) -> dict:
    """
    Return the full recruitment pipeline grouped by stage.
    Each stage contains a list of candidate cards.
    """
    try:
        q = (
            supabase.table("candidates")
            .select(
                "id, first_name, last_name, email, phone, source, source_detail, "
                "pipeline_stage, qualified, screening_result, "
                "screened_at, interview_at, offered_at, hired_at, "
                "rejection_reason, rejection_stage, offer_salary_inr, "
                "applied_via_qr, applied_job_id, created_at, updated_at"
            )
            .eq("org_id", org_id)
            .neq("pipeline_stage", "rejected")   # show rejected in separate view
            .order("created_at", desc=True)
            .limit(500)
        )
        if job_id:
            q = q.eq("applied_job_id", job_id)

        res = q.execute()
        candidates = res.data or []
    except Exception as exc:
        logger.error("pipeline fetch failed: %s", exc)
        return {s: [] for s in PIPELINE_STAGES}

    # Group by stage
    pipeline: dict[str, list] = {s: [] for s in PIPELINE_STAGES}
    for c in candidates:
        stage = c.get("pipeline_stage") or "applied"
        if stage not in pipeline:
            stage = "applied"
        pipeline[stage].append({
            "id":             c["id"],
            "name":           f"{c.get('first_name', '')} {c.get('last_name', '')}".strip(),
            "phone":          c.get("phone"),
            "email":          c.get("email"),
            "source":         c.get("source") or "other",
            "source_detail":  c.get("source_detail"),
            "stage":          stage,
            "qualified":      c.get("qualified", False),
            "score":          _extract_score(c.get("screening_result")),
            "applied_via_qr": c.get("applied_via_qr", False),
            "offer_salary":   c.get("offer_salary_inr"),
            "rejection_reason": c.get("rejection_reason"),
            "applied_at":     c.get("created_at"),
        })

    return pipeline


def move_candidate_stage(
    supabase,
    org_id:       str,
    candidate_id: str,
    new_stage:    str,
    notes:        Optional[str] = None,
    offer_salary: Optional[int] = None,
    rejection_reason: Optional[str] = None,
) -> dict:
    """Move a candidate to a new pipeline stage and set the relevant timestamp."""
    if new_stage not in PIPELINE_STAGES + TERMINAL_STAGES:
        raise ValueError(f"Invalid stage: {new_stage}. Must be one of {PIPELINE_STAGES + TERMINAL_STAGES}")

    now    = datetime.utcnow().isoformat()
    update: dict = {
        "pipeline_stage": new_stage,
        "updated_at":     now,
    }

    # Set stage timestamp
    ts_col = _STAGE_TS.get(new_stage)
    if ts_col:
        update[ts_col] = now

    # Extra fields per stage
    if new_stage in {"screened", "shortlisted"}:
        update["qualified"] = True
    elif new_stage == "interview" and notes:
        update["interview_notes"] = notes
    elif new_stage == "offer" and offer_salary:
        update["offer_salary_inr"] = offer_salary
    elif new_stage == "hired":
        update["hired_at"] = now
    elif new_stage == "rejected":
        if rejection_reason:
            update["rejection_reason"] = rejection_reason
            # Stage where rejected
            res = supabase.table("candidates").select("pipeline_stage").eq("id", candidate_id).limit(1).execute()
            prev_stage = (res.data or [{}])[0].get("pipeline_stage", "applied")
            update["rejection_stage"] = prev_stage

    updated = supabase.table("candidates").update(update).eq("id", candidate_id).eq("org_id", org_id).execute()
    if new_stage == "hired" and getattr(updated, "data", None):
        candidate = updated.data[0]
        distribution_id = candidate.get("distribution_id")
        if distribution_id:
            try:
                app = (supabase.table("applications").select("id").eq("candidate_id", candidate_id)
                       .eq("job_id", candidate.get("applied_job_id")).limit(1).execute().data or [{}])[0]
                if hasattr(supabase, "rpc") and candidate.get("source_detail"):
                    supabase.rpc("record_distribution_conversion", {
                        "p_token": candidate["source_detail"], "p_event_type": "HIRE",
                        "p_candidate_id": candidate_id, "p_application_id": app.get("id"),
                    }).execute()
                    return {"updated": True, "new_stage": new_stage}
                dist = (supabase.table("job_distributions").select("hire_count").eq("id", distribution_id)
                        .limit(1).execute().data or [{}])[0]
                supabase.table("job_distribution_events").insert({
                    "org_id": org_id, "distribution_id": distribution_id,
                    "job_id": candidate.get("applied_job_id"), "candidate_id": candidate_id,
                    "application_id": app.get("id"), "event_type": "HIRE",
                }).execute()
                supabase.table("job_distributions").update({
                    "hire_count": int(dist.get("hire_count") or 0) + 1,
                }).eq("id", distribution_id).execute()
            except Exception as exc:
                logger.warning("hire attribution failed for candidate %s: %s", candidate_id, exc)
    return {"updated": True, "new_stage": new_stage}


# ─────────────────────────────────────────────────────────────────────────────
# Bulk actions
# ─────────────────────────────────────────────────────────────────────────────

def bulk_action(
    supabase,
    org_id:        str,
    candidate_ids: list[str],
    action:        str,
    data:          dict,
) -> dict:
    """
    Perform a bulk action on a list of candidates.

    Actions:
      shortlist    → move to 'screened'
      reject       → move to 'rejected' with reason
      invite       → send WhatsApp interview invite
      stage        → move to arbitrary stage (data.stage)
    """
    if not candidate_ids:
        return {"processed": 0}

    processed = 0
    errors    = []

    for cid in candidate_ids:
        try:
            if action == "shortlist":
                move_candidate_stage(supabase, org_id, cid, "shortlisted")

            elif action == "reject":
                move_candidate_stage(
                    supabase, org_id, cid, "rejected",
                    rejection_reason=data.get("reason", "Not selected at this stage"),
                )

            elif action == "invite":
                _send_whatsapp_invite(supabase, org_id, cid, data)

            elif action == "stage":
                new_stage = data.get("stage")
                if new_stage:
                    move_candidate_stage(
                        supabase, org_id, cid, new_stage,
                        notes        = data.get("notes"),
                        offer_salary = data.get("offer_salary"),
                        rejection_reason = data.get("reason"),
                    )
            processed += 1
        except Exception as exc:
            logger.warning("bulk_action failed for %s: %s", cid, exc)
            errors.append({"candidate_id": cid, "error": str(exc)})

    # Update job source stats if shortlisting
    if action == "shortlist" and data.get("job_id"):
        _refresh_job_source_stats(supabase, org_id, data["job_id"])

    return {"processed": processed, "errors": errors}


def _send_whatsapp_invite(supabase, org_id: str, candidate_id: str, data: dict) -> None:
    """Send a WhatsApp interview invitation to the candidate."""
    try:
        res = (
            supabase.table("candidates")
            .select("phone, first_name, last_name")
            .eq("id", candidate_id)
            .eq("org_id", org_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return

        c      = res.data[0]
        phone  = c.get("phone")
        name   = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()

        interview_date = data.get("interview_date", "")
        job_title      = data.get("job_title", "the position")
        property_name  = data.get("property_name", "our property")

        msg = (
            f"नमस्ते {name}! 🙏\n\n"
            f"आपका {job_title} के लिए आवेदन shortlist हुआ है — *{property_name}*\n\n"
            f"Interview विवरण:\n"
            f"📅 {interview_date or 'HR से confirm होगा'}\n\n"
            f"कृपया confirm करें या अधिक जानकारी के लिए HR से संपर्क करें।\n\n"
            f"---\n"
            f"Hi {name}! Your application for *{job_title}* at {property_name} "
            f"has been shortlisted.\n"
            f"Interview: {interview_date or 'HR will confirm the date'}\n"
            f"Reply YES to confirm or contact HR for details. 🏨"
        )

        if phone:
            from app.services.whatsapp_gateway import send_whatsapp
            send_whatsapp(phone, msg)

    except Exception as exc:
        logger.warning("WhatsApp invite failed for %s: %s", candidate_id, exc)


def _refresh_job_source_stats(supabase, org_id: str, job_id: str) -> None:
    """Recompute and cache source statistics for a job."""
    try:
        res = (
            supabase.table("candidates")
            .select("source")
            .eq("applied_job_id", job_id)
            .execute()
        )
        from collections import Counter
        counts = Counter(c.get("source") or "other" for c in (res.data or []))
        supabase.table("jobs").update(
            {"source_stats": dict(counts)}
        ).eq("id", job_id).execute()
    except Exception as exc:
        logger.debug("source stats refresh failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Mobile OTP apply (Req 4 + 5)
# ─────────────────────────────────────────────────────────────────────────────

def send_apply_otp(supabase, phone: str, job_id: str, org_id: str) -> dict:
    """
    Generate a 6-digit OTP and send it via Twilio SMS.
    Returns {"sent": True} on success.
    """
    if not validate_india_phone(phone):
        return {"sent": False, "error": "Enter a valid Indian mobile number"}
    phone = normalize_india_phone(phone)
    otp = generate_otp()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    # Upsert OTP session
    supabase.table("mobile_otp_sessions").insert({
        "phone":      phone,
        "otp":        None,
        "otp_hash":   hash_otp(otp),
        "job_id":     job_id,
        "org_id":     org_id,
        "expires_at": expires_at,
    }).execute()

    # Send SMS via Twilio
    try:
        from twilio.rest import Client
        from app.core.config import settings
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body  = f"आपका HospRecruit OTP है: {otp}. 10 मिनट में expire होगा। (Your OTP: {otp})",
            from_ = settings.TWILIO_PHONE_NUMBER,
            to    = phone,
        )
        logger.info("OTP sent to %s", phone)
    except Exception as exc:
        logger.error("OTP SMS failed for %s: %s", phone, exc)
        return {"sent": False, "error": "SMS delivery failed"}

    return {"sent": True}


def check_apply_otp(supabase, phone: str, otp: str, job_id: str, org_id: str) -> dict:
    """Verify an OTP before the form is shown and issue a one-time form token."""
    if not validate_india_phone(phone):
        return {"verified": False, "error": "Invalid mobile number"}
    phone = normalize_india_phone(phone)
    now = datetime.now(timezone.utc)
    res = (
        supabase.table("mobile_otp_sessions")
        .select("id, otp, otp_hash, expires_at, verified, attempts")
        .eq("phone", phone).eq("job_id", job_id).eq("org_id", org_id)
        .eq("verified", False).order("created_at", desc=True).limit(1).execute()
    )
    if not res.data:
        return {"verified": False, "error": "OTP not found or already used"}
    session = res.data[0]
    attempts = int(session.get("attempts") or 0) + 1
    if attempts > 3:
        supabase.table("mobile_otp_sessions").update({"attempts": attempts}).eq("id", session["id"]).execute()
        return {"verified": False, "error": "Too many incorrect attempts"}
    expires = datetime.fromisoformat(str(session["expires_at"]).replace("Z", "+00:00"))
    if now > expires:
        return {"verified": False, "error": "OTP expired"}
    valid = verify_otp_hash(otp.strip(), session.get("otp_hash") or "")
    if not valid and session.get("otp"):  # compatibility with pre-migration sessions
        valid = secrets.compare_digest(str(session["otp"]), otp.strip())
    if not valid:
        supabase.table("mobile_otp_sessions").update({"attempts": attempts}).eq("id", session["id"]).execute()
        return {"verified": False, "error": "Incorrect OTP"}
    token = str(uuid.uuid4())
    supabase.table("mobile_otp_sessions").update({
        "attempts": attempts, "verification_token": token,
        "otp_verified_at": now.isoformat(),
    }).eq("id", session["id"]).execute()
    return {"verified": True, "verification_token": token}


def verify_apply_otp(
    supabase,
    phone:   str,
    otp:     Optional[str],
    job_id:  str,
    org_id:  str,
    form:    dict,
) -> dict:
    """
    Verify OTP and create the candidate record.
    form keys (5 fields max, Req 5):
      name, experience_years, current_city, source, source_detail (optional)
    Returns {"verified": True, "candidate_id": "..."}
    """
    now = datetime.now(timezone.utc)

    phone = normalize_india_phone(phone)
    verification_token = form.get("verification_token")
    # Find a valid pre-verified session, with legacy direct OTP compatibility.
    res = (
        supabase.table("mobile_otp_sessions")
        .select("id, otp, otp_hash, verification_token, otp_verified_at, expires_at, verified, attempts")
        .eq("phone",  phone)
        .eq("job_id", job_id)
        .eq("verified", False)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return {"verified": False, "error": "OTP not found or already used"}

    session = res.data[0]

    # Check expiry
    expires = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
    if now > expires:
        return {"verified": False, "error": "OTP expired"}

    token_valid = bool(verification_token and secrets.compare_digest(
        str(session.get("verification_token") or ""), str(verification_token)
    ))
    if not token_valid:
        attempts = int(session.get("attempts") or 0) + 1
        if attempts > 3:
            return {"verified": False, "error": "Too many incorrect attempts"}
        supplied = (otp or "").strip()
        otp_valid = verify_otp_hash(supplied, session.get("otp_hash") or "")
        if not otp_valid and session.get("otp"):
            otp_valid = secrets.compare_digest(str(session["otp"]), supplied)
        if not otp_valid:
            supabase.table("mobile_otp_sessions").update({"attempts": attempts}).eq("id", session["id"]).execute()
            return {"verified": False, "error": "Incorrect OTP"}

    # Resolve a signed distribution token to prevent source spoofing.
    distribution = None
    distribution_token = form.get("distribution_token")
    if distribution_token:
        dist_res = (supabase.table("job_distributions").select("*")
                    .eq("attribution_token", distribution_token).eq("job_id", job_id)
                    .eq("org_id", org_id).eq("status", "PUBLISHED").limit(1).execute())
        distribution = (dist_res.data or [None])[0]
        if not distribution:
            return {"verified": False, "error": "Invalid or inactive distribution link"}

    # Consume only after all pre-application validation has succeeded.
    supabase.table("mobile_otp_sessions").update(
        {"verified": True}
    ).eq("id", session["id"]).execute()

    source_aliases = {"employee_referral": "referral", "indeed": "indeed_india"}
    attributed_source = source_aliases.get(distribution.get("channel_key"), distribution.get("channel_key")) if distribution else form.get("source", "other")

    # Create candidate record
    name_parts = form.get("name", "Candidate").split(" ", 1)
    first_name = name_parts[0]
    last_name  = name_parts[1] if len(name_parts) > 1 else ""

    # Check for duplicate (same phone + job)
    dup = (
        supabase.table("candidates")
        .select("id, tracking_token")
        .eq("phone", phone)
        .eq("applied_job_id", job_id)
        .limit(1)
        .execute()
    )
    if dup.data:
        existing_app = (supabase.table("applications").select("id").eq("candidate_id", dup.data[0]["id"])
                        .eq("job_id", job_id).limit(1).execute().data or [{}])[0]
        return {"verified": True, "candidate_id": dup.data[0]["id"],
                "application_id": existing_app.get("id"),
                "tracking_token": dup.data[0].get("tracking_token"), "duplicate": True}

    insert = {
        "org_id":          org_id,
        "job_id":          job_id,
        "applied_job_id":  job_id,
        "first_name":      first_name,
        "last_name":       last_name,
        "email":           f"{phone.lstrip('+').replace(' ', '')}@whatsapp.apply",
        "phone":           phone,
        "source":          attributed_source,
        "source_detail":   str(distribution.get("attribution_token")) if distribution else form.get("source_detail"),
        "pipeline_stage":  "applied",
        "location":        form.get("current_city", ""),
        "applied_via_qr":  form.get("via_qr", False),
        "distribution_id": distribution.get("id") if distribution else None,
        "raw_data": {
            "experience_years": form.get("experience_years", 0),
            "current_city":     form.get("current_city", ""),
            "apply_channel":    "mobile_otp",
        },
    }

    cand_res = supabase.table("candidates").insert(insert).execute()
    candidate_id = (cand_res.data or [{}])[0].get("id")

    # Every candidate application is also recorded in the canonical applications table.
    job_row = (supabase.table("jobs").select("property_id,department_id").eq("id", job_id).eq("org_id", org_id)
               .limit(1).execute().data or [{}])[0]
    app_payload = {
        "org_id": org_id, "candidate_id": candidate_id, "job_id": job_id,
        "property_id": job_row.get("property_id"), "department_id": job_row.get("department_id"),
        "source": attributed_source.upper(),
        "source_ref": str(distribution.get("attribution_token")) if distribution else form.get("source_detail"),
        "status": "SUBMITTED", "applied_via": "QR_SCAN" if form.get("via_qr") else "MOBILE_WEB",
        "distribution_id": distribution.get("id") if distribution else None,
        "attribution_token": distribution.get("attribution_token") if distribution else None,
        "form_data": form,
        "completion_time_seconds": form.get("completion_time_seconds"),
        "preferred_language": form.get("preferred_language", "hi"),
        "low_bandwidth_mode": bool(form.get("low_bandwidth_mode")),
        "submitted_at": now.isoformat(),
    }
    app_res = supabase.table("applications").insert(app_payload).execute()
    application_id = (app_res.data or [{}])[0].get("id")
    if distribution:
        try:
            if hasattr(supabase, "rpc"):
                supabase.rpc("record_distribution_conversion", {
                    "p_token": str(distribution["attribution_token"]), "p_event_type": "APPLICATION",
                    "p_candidate_id": candidate_id, "p_application_id": application_id,
                }).execute()
                _refresh_job_source_stats(supabase, org_id, job_id)
            else:
                supabase.table("job_distribution_events").insert({
                    "org_id": org_id, "distribution_id": distribution["id"], "job_id": job_id,
                    "candidate_id": candidate_id, "application_id": application_id,
                    "event_type": "APPLICATION", "source_ref": str(distribution["attribution_token"]),
                }).execute()
                supabase.table("job_distributions").update({
                    "application_count": int(distribution.get("application_count") or 0) + 1,
                }).eq("id", distribution["id"]).execute()
        except Exception as exc:
            logger.warning("application attribution failed for candidate %s: %s", candidate_id, exc)
    _refresh_job_source_stats(supabase, org_id, job_id)

    tracking = (cand_res.data or [{}])[0].get("tracking_token")
    if not tracking:
        tracking_row = (supabase.table("candidates").select("tracking_token").eq("id", candidate_id)
                        .limit(1).execute().data or [{}])[0]
        tracking = tracking_row.get("tracking_token")
    return {"verified": True, "candidate_id": candidate_id, "application_id": application_id,
            "tracking_token": tracking, "source": attributed_source}


# ─────────────────────────────────────────────────────────────────────────────
# QR code URL construction (Req 6)
# ─────────────────────────────────────────────────────────────────────────────

def build_apply_url(base_url: str, job_id: str, org_id: str, source: str = "qr_code") -> dict:
    """
    Return the apply URL and a QR-image URL.
    QR images are generated via api.qrserver.com (no library needed).
    """
    apply_url = f"{base_url}/india-apply/{job_id}?org={org_id}&src={source}"
    qr_url    = (
        f"https://api.qrserver.com/v1/create-qr-code/"
        f"?size=300x300&margin=10&data={apply_url}"
    )
    return {"apply_url": apply_url, "qr_url": qr_url}


def log_qr_scan(supabase, job_id: str, org_id: str, source: str, ip: str, ua: str) -> None:
    """Record a QR code scan for analytics."""
    try:
        supabase.table("job_qr_scans").insert({
            "job_id":     job_id,
            "org_id":     org_id,
            "source":     source,
            "ip_address": ip,
            "user_agent": ua,
        }).execute()
        # Also increment job source_stats
        res = supabase.table("jobs").select("source_stats").eq("id", job_id).limit(1).execute()
        if res.data:
            stats = res.data[0].get("source_stats") or {}
            stats["qr_code"] = stats.get("qr_code", 0) + 1
            supabase.table("jobs").update({"source_stats": stats}).eq("id", job_id).execute()
    except Exception as exc:
        logger.debug("qr scan log failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_score(screening_result: Optional[dict]) -> Optional[float]:
    if not screening_result:
        return None
    return screening_result.get("overall_score") or screening_result.get("score")
