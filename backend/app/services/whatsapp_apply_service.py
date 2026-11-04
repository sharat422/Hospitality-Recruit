"""Stateful, low-bandwidth WhatsApp application flow using canonical ATS records."""

from datetime import datetime, timedelta, timezone
import re


START_RE = re.compile(r"^\s*(?:APPLY|आवेदन)\s+([0-9a-f-]{36})\s*$", re.I)


def handle_whatsapp_application(supabase, phone: str, body: str) -> str | None:
    """Return a bot reply when this is an application conversation, else None."""
    start = START_RE.match(body or "")
    if start:
        job_id = start.group(1)
        job_rows = (supabase.table("jobs").select("id,org_id,title,property_id,department_id,property_name")
                    .eq("id", job_id).eq("status", "open").limit(1).execute().data or [])
        if not job_rows:
            return "यह नौकरी उपलब्ध नहीं है। This job is no longer available."
        job = job_rows[0]
        supabase.table("whatsapp_apply_sessions").insert({
            "phone": phone, "org_id": job["org_id"], "job_id": job_id, "state": "NAME",
            "answers": {"job_title": job.get("title"), "property_name": job.get("property_name"),
                        "property_id": job.get("property_id"), "department_id": job.get("department_id")},
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        }).execute()
        return f"नमस्ते! {job.get('title')} के लिए आवेदन शुरू हुआ। अपना पूरा नाम लिखें।\nWelcome! Please reply with your full name."

    sessions = (supabase.table("whatsapp_apply_sessions").select("*").eq("phone", phone)
                .in_("state", ["NAME", "CITY", "EXPERIENCE"])
                .order("updated_at", desc=True).limit(1).execute().data or [])
    if not sessions:
        return None
    session = sessions[0]
    expires_at = datetime.fromisoformat(str(session["expires_at"]).replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        supabase.table("whatsapp_apply_sessions").update({"state": "CANCELLED"}).eq("id", session["id"]).execute()
        return "यह आवेदन सत्र समाप्त हो गया। नौकरी लिंक दोबारा खोलें। / This session expired; reopen the job link."
    answers = dict(session.get("answers") or {})
    text = (body or "").strip()
    if text.upper() == "CANCEL":
        supabase.table("whatsapp_apply_sessions").update({"state": "CANCELLED"}).eq("id", session["id"]).execute()
        return "Application cancelled. आवेदन रद्द हुआ।"
    if session["state"] == "NAME":
        if len(text) < 2:
            return "Please enter your full name / कृपया पूरा नाम लिखें।"
        answers["name"] = text[:150]
        supabase.table("whatsapp_apply_sessions").update({"state": "CITY", "answers": answers}).eq("id", session["id"]).execute()
        return "आप किस शहर में हैं? / Which city are you based in?"
    if session["state"] == "CITY":
        if len(text) < 2:
            return "Please enter a city / कृपया शहर लिखें।"
        answers["city"] = text[:100]
        supabase.table("whatsapp_apply_sessions").update({"state": "EXPERIENCE", "answers": answers}).eq("id", session["id"]).execute()
        return "Hospitality में कितने साल का अनुभव है? केवल संख्या लिखें। / Years of experience?"
    try:
        years = max(0, min(50, int(float(text))))
    except ValueError:
        return "Please reply with a number, for example 0 or 2 / केवल संख्या लिखें।"
    name_parts = answers.get("name", "Candidate").split(" ", 1)
    duplicate = (supabase.table("candidates").select("id,tracking_token").eq("phone", phone)
                 .eq("applied_job_id", session["job_id"]).limit(1).execute().data or [])
    if duplicate:
        candidate = duplicate[0]
        apps = (supabase.table("applications").select("id").eq("candidate_id", candidate["id"])
                .eq("job_id", session["job_id"]).limit(1).execute().data or [{}])
        application_id = apps[0].get("id")
    else:
        candidate = (supabase.table("candidates").insert({
            "org_id": session["org_id"], "job_id": session["job_id"], "applied_job_id": session["job_id"],
            "first_name": name_parts[0], "last_name": name_parts[1] if len(name_parts) > 1 else "",
            "email": f"{phone.lstrip('+')}@whatsapp.apply", "phone": phone, "location": answers.get("city", ""),
            "source": "whatsapp", "pipeline_stage": "applied",
            "raw_data": {"experience_years": years, "apply_channel": "whatsapp_bot"},
        }).execute().data or [{}])[0]
        app = (supabase.table("applications").insert({
            "org_id": session["org_id"], "candidate_id": candidate.get("id"), "job_id": session["job_id"],
            "property_id": answers.get("property_id"), "department_id": answers.get("department_id"),
            "source": "WHATSAPP", "status": "SUBMITTED", "applied_via": "WHATSAPP_BOT",
            "preferred_language": "hi", "form_data": {**answers, "experience_years": years},
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }).execute().data or [{}])[0]
        application_id = app.get("id")
    supabase.table("whatsapp_apply_sessions").update({
        "state": "COMPLETED", "answers": {**answers, "experience_years": years},
        "candidate_id": candidate.get("id"), "application_id": application_id,
    }).eq("id", session["id"]).execute()
    return "धन्यवाद! आवेदन जमा हो गया। हमारी टीम 2-3 कार्य दिवसों में संपर्क करेगी।\nThank you! Your application is submitted."
