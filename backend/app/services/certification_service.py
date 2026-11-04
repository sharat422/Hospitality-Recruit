"""Unified employee certification logic across general and existing FSSAI records."""

from __future__ import annotations

from datetime import date

from app.core.business_date import business_today

DEFAULT_ALERT_DAYS = [90, 60, 30, 7, 0]


def certificate_state(expiry_date: str | None, status: str) -> dict:
    if not expiry_date:
        return {"status": status, "days_remaining": None}
    expiry = date.fromisoformat(str(expiry_date)[:10])
    # Expiry is a business date, so "today" must be the hotel's date. Using
    # the UTC date made a certificate read as expired a day early for the
    # 5h30m between 00:00 and 05:30 IST.
    days = (expiry - business_today()).days
    if days < 0:
        effective = "EXPIRED"
    elif days <= 30 and status == "VERIFIED":
        effective = "RENEWAL_DUE"
    else:
        effective = status
    return {"status": effective, "days_remaining": days}


def normalize_employee_certificate(row: dict) -> dict:
    cert_type = row.get("certification_types") or {}
    if isinstance(cert_type, list):
        cert_type = cert_type[0] if cert_type else {}
    state = certificate_state(row.get("expiry_date"), row.get("status") or "PENDING_VERIFICATION")
    return {**row, "source_type": "EMPLOYEE_CERT", "certification_code": cert_type.get("code"),
            "certification_name": cert_type.get("name"), **state}


def normalize_fssai_certificate(row: dict) -> dict:
    state = certificate_state(row.get("expiry_date"), "VERIFIED" if row.get("status") == "ACTIVE" else row.get("status", "ACTIVE"))
    return {**row, "source_type": "FSSAI", "source_id": row.get("id"),
            "certification_code": row.get("cert_type"),
            "certification_name": str(row.get("cert_type") or "FSSAI").replace("_", " ").title(), **state}


def get_employee_candidate_id(supabase, org_id: str, employee: dict) -> str | None:
    rows = (supabase.table("candidates").select("id")
            .eq("org_id", org_id).eq("user_id", employee["id"]).limit(1).execute().data or [])
    if not rows and employee.get("email"):
        rows = (supabase.table("candidates").select("id").eq("org_id", org_id)
                .eq("email", employee["email"]).limit(1).execute().data or [])
    return rows[0]["id"] if rows else None


def get_unified_employee_certifications(supabase, org_id: str, employee: dict) -> list[dict]:
    general = (supabase.table("employee_certifications")
               .select("*,certification_types(code,name,category,is_fssai_managed)")
               .eq("org_id", org_id).eq("employee_id", employee["id"])
               .order("expiry_date").execute().data or [])
    result = [normalize_employee_certificate(row) for row in general]
    candidate_id = get_employee_candidate_id(supabase, org_id, employee)
    if candidate_id:
        fssai = (supabase.table("fssai_certificates").select("*")
                 .eq("org_id", org_id).eq("candidate_id", candidate_id).order("expiry_date").execute().data or [])
        result.extend(normalize_fssai_certificate(row) for row in fssai)
    return sorted(result, key=lambda row: str(row.get("expiry_date") or "9999-12-31"))


def get_role_compliance(supabase, org_id: str, employee: dict) -> dict:
    requirements = (supabase.table("role_certification_requirements")
                    .select("*,certification_types(code,name,category)")
                    .eq("org_id", org_id).execute().data or [])
    role_title = str(employee.get("job_title") or "").strip().lower()
    requirements = [row for row in requirements
                    if str(row.get("role_title") or "").strip().lower() == role_title
                    and (not row.get("property_id") or row.get("property_id") == employee.get("active_property_id"))
                    and (not row.get("department_id") or row.get("department_id") == employee.get("department_id"))]
    certs = get_unified_employee_certifications(supabase, org_id, employee)
    held = {}
    for cert in certs:
        code = cert.get("certification_code")
        if code and cert.get("status") in {"VERIFIED", "RENEWAL_DUE"}:
            held[code] = cert
    items = []
    for requirement in requirements:
        typ = requirement.get("certification_types") or {}
        if isinstance(typ, list):
            typ = typ[0] if typ else {}
        cert = held.get(typ.get("code"))
        items.append({"requirement_id": requirement.get("id"), "code": typ.get("code"),
                      "name": typ.get("name"), "mandatory": requirement.get("is_mandatory", True),
                      "required_before_start": requirement.get("required_before_start", False),
                      "compliant": cert is not None, "certificate": cert})
    mandatory = [item for item in items if item["mandatory"]]
    return {"employee_id": employee["id"], "job_title": employee.get("job_title"),
            "requirements": items, "compliant": all(item["compliant"] for item in mandatory),
            "missing_mandatory": [item for item in mandatory if not item["compliant"]],
            "certificates": certs}
