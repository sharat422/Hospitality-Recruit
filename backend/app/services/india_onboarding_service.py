"""
India Digital Onboarding Service

Generates:
  - Indian Appointment Letters with CTC breakup
  - PF Form 2 and ESIC Declaration
  - 5-stage onboarding checklist (Documents→KYC→Certifications→Payroll→Ready)
  - WhatsApp pre-boarding sequence (6 timed messages)
  - Aadhaar eSign integration adapter (Leegality / Digio / demo mode)
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CTC Breakup (India standard)
# ─────────────────────────────────────────────────────────────────────────────

def compute_ctc_breakup(gross_monthly: int) -> dict:
    """
    Compute all CTC components from gross monthly salary (Indian standard).

    Statutory rules applied:
      - ESIC: applicable if gross ≤ ₹21,000/month
      - EPF: 12% of Basic for both employee and employer
      - PT: ₹200/month (standard; varies by state)
    """
    basic            = round(gross_monthly * 0.50)
    hra              = round(basic * 0.50)               # 50% of basic
    special          = gross_monthly - basic - hra        # remainder

    epf_employee     = round(basic * 0.12)
    epf_employer     = round(basic * 0.12)

    esic_applicable  = gross_monthly <= 21_000
    esic_employee    = round(gross_monthly * 0.0075) if esic_applicable else 0
    esic_employer    = round(gross_monthly * 0.0325) if esic_applicable else 0

    pt               = 200  # ₹200/month professional tax

    net_monthly      = gross_monthly - epf_employee - esic_employee - pt
    annual_gross     = gross_monthly * 12
    annual_ctc       = (gross_monthly + epf_employer + esic_employer) * 12
    annual_net       = net_monthly * 12

    return {
        "gross_monthly":      gross_monthly,
        "basic":              basic,
        "hra":                hra,
        "special_allowance":  special,
        "epf_employee":       epf_employee,
        "epf_employer":       epf_employer,
        "esic_applicable":    esic_applicable,
        "esic_employee":      esic_employee,
        "esic_employer":      esic_employer,
        "pt":                 pt,
        "net_monthly":        net_monthly,
        "annual_gross":       annual_gross,
        "annual_ctc":         annual_ctc,
        "annual_net":         annual_net,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Appointment Letter Generator (HTML)
# ─────────────────────────────────────────────────────────────────────────────

def generate_appointment_letter_html(
    org_name: str,
    org_address: str,
    candidate_name: str,
    candidate_address: str,
    role_title: str,
    department: str,
    property_name: str,
    joining_date: date,
    ctc: dict,
    probation_months: int = 6,
    notice_period_days: int = 30,
    letter_date: Optional[date] = None,
) -> str:
    """Generate an Indian Appointment Letter as HTML."""
    if letter_date is None:
        letter_date = date.today()

    jd_str    = joining_date.strftime("%d %B %Y") if joining_date else "___________"
    date_str  = letter_date.strftime("%d %B %Y")

    def inr(v: int) -> str:
        return f"₹{v:,}"

    # Leave policy (standard Indian hospitality)
    annual_leave_cl = 12
    annual_leave_sl = 12
    annual_leave_el = 15

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 12pt; color: #222; margin: 40px; }}
  h1   {{ font-size: 16pt; text-align: center; text-transform: uppercase; color: #1a1a6e; }}
  h2   {{ font-size: 13pt; }}
  .header {{ border-bottom: 2px solid #1a1a6e; padding-bottom: 10px; margin-bottom: 20px; }}
  .org-name {{ font-size: 18pt; font-weight: bold; color: #1a1a6e; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #ccc; padding: 7px 12px; text-align: left; }}
  th {{ background: #f0f0f8; font-weight: bold; }}
  .total-row {{ background: #e8f0fe; font-weight: bold; }}
  .net-row   {{ background: #d4edda; font-weight: bold; }}
  .clause    {{ margin: 10px 0; }}
  .sign-block {{ margin-top: 60px; display: flex; justify-content: space-between; }}
  .sign-col  {{ width: 45%; }}
  .sign-line {{ border-top: 1px solid #555; margin-top: 40px; padding-top: 4px; font-size: 10pt; }}
</style>
</head>
<body>
<div class="header">
  <div class="org-name">{org_name}</div>
  <div>{org_address}</div>
</div>

<p><strong>Date:</strong> {date_str}</p>
<p>
  <strong>{candidate_name}</strong><br/>
  {candidate_address}
</p>

<h2>APPOINTMENT LETTER</h2>

<p>Dear <strong>{candidate_name}</strong>,</p>

<p>We are pleased to appoint you as <strong>{role_title}</strong> in the <strong>{department}</strong> department
at <strong>{property_name}</strong>, a unit of <strong>{org_name}</strong>, with effect from
<strong>{jd_str}</strong>, on the following terms and conditions:</p>

<h2>1. Designation & Department</h2>
<table>
  <tr><th>Designation</th><td>{role_title}</td></tr>
  <tr><th>Department</th><td>{department}</td></tr>
  <tr><th>Place of Posting</th><td>{property_name}</td></tr>
  <tr><th>Date of Joining</th><td>{jd_str}</td></tr>
</table>

<h2>2. Compensation — CTC Breakup</h2>
<p>Your total compensation is structured as follows (amounts in Indian Rupees per month):</p>

<h3>2A. Earnings</h3>
<table>
  <tr><th>Component</th><th>Monthly (₹)</th><th>Annual (₹)</th></tr>
  <tr><td>Basic Salary</td><td>{inr(ctc['basic'])}</td><td>{inr(ctc['basic']*12)}</td></tr>
  <tr><td>House Rent Allowance (HRA)</td><td>{inr(ctc['hra'])}</td><td>{inr(ctc['hra']*12)}</td></tr>
  <tr><td>Special Allowance</td><td>{inr(ctc['special_allowance'])}</td><td>{inr(ctc['special_allowance']*12)}</td></tr>
  <tr class="total-row"><td><strong>Gross Salary</strong></td><td><strong>{inr(ctc['gross_monthly'])}</strong></td><td><strong>{inr(ctc['annual_gross'])}</strong></td></tr>
</table>

<h3>2B. Deductions (Employee Contribution)</h3>
<table>
  <tr><th>Component</th><th>Monthly (₹)</th><th>Note</th></tr>
  <tr><td>Employee Provident Fund (EPF)</td><td>{inr(ctc['epf_employee'])}</td><td>12% of Basic</td></tr>
  {'<tr><td>ESIC Employee Contribution</td><td>' + inr(ctc['esic_employee']) + '</td><td>0.75% of Gross (applicable)</td></tr>' if ctc['esic_applicable'] else '<tr><td>ESIC</td><td>N/A</td><td>Gross exceeds ₹21,000 — not applicable</td></tr>'}
  <tr><td>Professional Tax (PT)</td><td>{inr(ctc['pt'])}</td><td>As per state regulation</td></tr>
  <tr class="net-row"><td><strong>Net Take-Home Salary</strong></td><td><strong>{inr(ctc['net_monthly'])}</strong></td><td><strong>(Annual: {inr(ctc['annual_net'])})</strong></td></tr>
</table>

<h3>2C. Employer Statutory Contributions</h3>
<table>
  <tr><th>Component</th><th>Monthly (₹)</th></tr>
  <tr><td>Employer EPF Contribution</td><td>{inr(ctc['epf_employer'])}</td></tr>
  {'<tr><td>Employer ESIC Contribution</td><td>' + inr(ctc['esic_employer']) + '</td></tr>' if ctc['esic_applicable'] else ''}
  <tr class="total-row"><td><strong>Total Cost to Company (CTC)</strong></td><td><strong>{inr(ctc['annual_ctc'] // 12)}/month ({inr(ctc['annual_ctc'])}/year)</strong></td></tr>
</table>

<h2>3. Probation</h2>
<p>You will be on probation for a period of <strong>{probation_months} months</strong> from your date of joining.
During probation, either party may terminate employment with <strong>7 days' written notice</strong>.
Upon satisfactory completion, your appointment will be confirmed.</p>

<h2>4. Notice Period</h2>
<p>After confirmation, either party may terminate this agreement by giving <strong>{notice_period_days} days'</strong>
written notice or payment in lieu thereof.</p>

<h2>5. Leave Entitlement</h2>
<table>
  <tr><th>Leave Type</th><th>Days per Year</th></tr>
  <tr><td>Casual Leave (CL)</td><td>{annual_leave_cl}</td></tr>
  <tr><td>Sick Leave (SL)</td><td>{annual_leave_sl}</td></tr>
  <tr><td>Earned Leave (EL)</td><td>{annual_leave_el}</td></tr>
</table>
<p>Leave policy is governed by the applicable Shops & Establishments Act of the state.</p>

<h2>6. Statutory Benefits</h2>
<p><strong>Provident Fund (EPF):</strong> You are enrolled under the Employees' Provident Fund and
Miscellaneous Provisions Act, 1952. You and the Company shall each contribute 12% of your Basic Salary
to the EPF account. You are required to submit PF Nomination Form 2 within 30 days of joining.</p>

{'<p><strong>ESIC:</strong> You are covered under the Employees State Insurance Act, 1948. Employee contribution: 0.75% of gross wages; Employer contribution: 3.25% of gross wages.</p>' if ctc['esic_applicable'] else ''}

<h2>7. Confidentiality</h2>
<p>You shall not, during or after employment, disclose any confidential information, trade secrets,
customer data, or proprietary information of {org_name} or its clients to any third party.</p>

<h2>8. Code of Conduct</h2>
<p>You are expected to adhere to {org_name}'s Code of Conduct, Grooming Standards, and Guest Service
Standards at all times. Violation may result in disciplinary action including termination.</p>

<h2>9. Governing Law</h2>
<p>This appointment is governed by the laws of India and the jurisdiction of the courts in the city
where your place of posting is located.</p>

<p>Please sign and return a copy of this letter as a token of your acceptance of the above terms and
conditions within <strong>3 working days</strong>.</p>

<p>We look forward to welcoming you to the {org_name} family.</p>

<div class="sign-block">
  <div class="sign-col">
    <div class="sign-line">For {org_name}<br/>Authorised Signatory</div>
    <br/><br/>
    <div>Name: ___________________________</div>
    <div>Designation: ___________________</div>
  </div>
  <div class="sign-col">
    <div class="sign-line">Accepted by Candidate</div>
    <br/><br/>
    <div>Name: {candidate_name}</div>
    <div>Signature: ____________________</div>
    <div>Date: _________________________</div>
    <div>Aadhaar No. (last 4): __________</div>
  </div>
</div>

</body>
</html>"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# PF Form 2 and ESIC Declaration
# ─────────────────────────────────────────────────────────────────────────────

def generate_pf_form2_data(
    candidate: dict,
    joining_date: date,
    org_name: str,
    org_pf_code: str = "MH/12345",
) -> dict:
    """Generate structured PF Form 2 (Nomination & Declaration) data."""
    name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip()
    return {
        "form_type":        "PF Form 2 — Nomination and Declaration Form",
        "member_name":      name,
        "father_spouse_name": candidate.get("father_name") or candidate.get("spouse_name") or "",
        "date_of_birth":    str(candidate.get("dob") or ""),
        "date_of_joining":  str(joining_date),
        "pf_account_number": f"{org_pf_code}/{candidate.get('id', 'XXXX')[:8].upper()}",
        "establishment_name": org_name,
        "establishment_code": org_pf_code,
        "nominees":         [
            {
                "name":         candidate.get("nominee_name") or "To be filled by employee",
                "relationship": candidate.get("nominee_relationship") or "Spouse/Child/Parent",
                "date_of_birth": str(candidate.get("nominee_dob") or ""),
                "share_pct":    100,
                "guardian_name_if_minor": "",
            }
        ],
        "family_details": [],
        "declaration": (
            f"I, {name}, hereby nominate the person(s) mentioned above to receive "
            "the Provident Fund amount in the event of my death."
        ),
        "place": candidate.get("current_location") or "",
        "date":  str(date.today()),
    }


def generate_esic_declaration_data(
    candidate: dict,
    joining_date: date,
    org_name: str,
    org_esic_code: str = "12-00-123456-000-0001",
) -> dict:
    """Generate ESIC Declaration Form data."""
    name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip()
    return {
        "form_type":         "ESIC Declaration Form",
        "employee_name":     name,
        "date_of_birth":     str(candidate.get("dob") or ""),
        "father_spouse_name": candidate.get("father_name") or candidate.get("spouse_name") or "",
        "gender":            candidate.get("gender") or "",
        "date_of_joining":   str(joining_date),
        "employer_name":     org_name,
        "employer_code":     org_esic_code,
        "dispensary_preference": "",
        "address":           candidate.get("address") or candidate.get("current_location") or "",
        "nominee_name":      candidate.get("nominee_name") or "",
        "nominee_relationship": candidate.get("nominee_relationship") or "",
        "medical_benefit_eligible": True,
        "declaration": (
            f"I, {name}, hereby declare that the above information is true and correct. "
            "I understand that I am covered under the Employees' State Insurance Act, 1948."
        ),
        "date": str(date.today()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Aadhaar eSign Adapter
# ─────────────────────────────────────────────────────────────────────────────

class ESignAdapter:
    """
    Provider-agnostic Aadhaar eSign adapter.
    Supported providers: leegality, digio, signdesk, demo (stub).

    In production, configure ESIGN_PROVIDER and ESIGN_API_KEY in .env.
    """

    SUPPORTED = {"leegality", "digio", "signdesk", "demo"}

    def __init__(self, provider: str = "demo"):
        self.provider = provider if provider in self.SUPPORTED else "demo"

    async def create_sign_request(
        self,
        document_url: str,
        signer_name: str,
        signer_phone: str,
        signer_email: str = "",
        callback_url: str = "",
    ) -> dict:
        """
        Create an eSign request for the appointment letter.

        Returns:
          sign_request_id: str   — provider's reference ID
          sign_url: str          — URL to send to candidate for signing
          status: str            — 'pending'
        """
        if self.provider == "leegality":
            return await self._leegality(document_url, signer_name, signer_phone, signer_email, callback_url)
        elif self.provider == "digio":
            return await self._digio(document_url, signer_name, signer_phone, signer_email, callback_url)
        elif self.provider == "signdesk":
            return await self._signdesk(document_url, signer_name, signer_phone, signer_email, callback_url)
        else:
            return self._demo(signer_name, signer_phone)

    async def _leegality(self, doc_url, name, phone, email, callback) -> dict:
        """
        Leegality eSign API integration.
        Docs: https://developer.leegality.com
        Requires: LEEGALITY_API_KEY in env.
        """
        try:
            from app.core.config import settings
            import httpx
            api_key = getattr(settings, "LEEGALITY_API_KEY", "")
            if not api_key:
                logger.warning("LEEGALITY_API_KEY not configured — falling back to demo")
                return self._demo(name, phone)

            payload = {
                "documentUrl": doc_url,
                "signers": [{"name": name, "phone": phone, "email": email or None}],
                "signatureType": "aadhaar",
                "callbackUrl": callback,
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.leegality.com/v3.0/sign/invite",
                    json=payload,
                    headers={"X-Auth-Token": api_key, "Content-Type": "application/json"},
                )
            data = resp.json()
            return {
                "sign_request_id": data.get("id", ""),
                "sign_url":        data.get("signers", [{}])[0].get("signUrl", ""),
                "status":          "pending",
                "provider":        "leegality",
            }
        except Exception as e:
            logger.error(f"Leegality eSign failed: {e}")
            return self._demo(name, phone)

    async def _digio(self, doc_url, name, phone, email, callback) -> dict:
        """
        Digio eSign API integration.
        Docs: https://www.digio.in/docs/
        Requires: DIGIO_CLIENT_ID + DIGIO_CLIENT_SECRET in env.
        """
        try:
            from app.core.config import settings
            import httpx, base64
            client_id     = getattr(settings, "DIGIO_CLIENT_ID", "")
            client_secret = getattr(settings, "DIGIO_CLIENT_SECRET", "")
            if not client_id:
                return self._demo(name, phone)

            creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            payload = {
                "signers":        [{"identifier": phone, "name": name, "sign_type": "aadhaar"}],
                "file_url":       doc_url,
                "expire_in_days": 7,
                "notify_signers": True,
                "send_sign_link": True,
            }
            async with httpx.AsyncClient(timeout=15) as http:
                resp = await http.post(
                    "https://ext.digio.in:444/v2/client/document/uploadpdf",
                    json=payload,
                    headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
                )
            data = resp.json()
            return {
                "sign_request_id": data.get("id", ""),
                "sign_url":        data.get("signing_parties", [{}])[0].get("sign_link", ""),
                "status":          "pending",
                "provider":        "digio",
            }
        except Exception as e:
            logger.error(f"Digio eSign failed: {e}")
            return self._demo(name, phone)

    async def _signdesk(self, doc_url, name, phone, email, callback) -> dict:
        """SignDesk eSign — stub (add SIGNDESK_API_KEY when ready)."""
        return self._demo(name, phone)

    def _demo(self, name: str, phone: str) -> dict:
        """Stub for testing without real API credentials."""
        req_id = f"DEMO-{uuid.uuid4().hex[:8].upper()}"
        return {
            "sign_request_id": req_id,
            "sign_url":        f"https://demo-esign.hosprecruitapp.com/sign/{req_id}",
            "status":          "pending",
            "provider":        "demo",
        }


# ─────────────────────────────────────────────────────────────────────────────
# WhatsApp Pre-Boarding Sequence
# ─────────────────────────────────────────────────────────────────────────────

PREBOARDING_TEMPLATES = {
    "day0_welcome": (
        "🎉 Congratulations {name}!\n\n"
        "We're delighted to welcome you as *{role}* at *{property}*.\n\n"
        "📅 Joining Date: *{joining_date}*\n"
        "💰 Net Monthly Salary: *₹{net_monthly:,}*\n\n"
        "Your appointment letter will be shared shortly for Aadhaar eSign.\n\n"
        "Please keep original copies of your documents ready.\n\n"
        "Excited to have you on board! 🏨"
    ),
    "day1_team_intro": (
        "Hi {name}! 👋\n\n"
        "Your team at *{property}* is eagerly awaiting your arrival on *{joining_date}*.\n\n"
        "👤 Your reporting manager: *{manager_name}*\n"
        "🏢 Department: *{department}*\n\n"
        "We'll share your manager's contact and your buddy's details closer to your joining date.\n\n"
        "Any questions? Just reply here! 😊"
    ),
    "day3_practical": (
        "Hi {name}! Some practical info for your first day 📋\n\n"
        "🕐 Reporting time: *{reporting_time}*\n"
        "📍 Location: *{reporting_location}*\n\n"
        "✅ Uniform will be issued on Day 1\n"
        "✅ Locker will be assigned\n"
        "✅ Staff meals provided while on duty\n"
        "✅ ID card will be issued during induction\n\n"
        "See you soon! 🏨"
    ),
    "pre7_docs_checklist": (
        "Hi {name}! 📅 Your joining date is in *7 days*!\n\n"
        "Please bring these documents on *{joining_date}*:\n\n"
        "✅ Aadhaar Card (original + 2 copies)\n"
        "✅ PAN Card (original + copy)\n"
        "✅ 4 passport-size photographs\n"
        "✅ Bank passbook / cancelled cheque\n"
        "✅ Previous employment certificates + relieving letter\n"
        "✅ Educational certificates (10th / 12th / degree)\n"
        "✅ PF account number / UAN (if existing)\n"
        "✅ ESIC IP number (if existing)\n\n"
        "Documents not ready? Reply here and we'll help! 🙌"
    ),
    "pre1_reporting": (
        "Hi {name}! Tomorrow is your big day! 🌟\n\n"
        "📍 Report to: *{reporting_location}*\n"
        "🕐 Reporting time: *{reporting_time}*\n"
        "👤 Ask for: *{manager_name}*\n\n"
        "Please wear formal clothes for Day 1.\n"
        "Carry your full documents folder.\n\n"
        "We look forward to seeing you! 🎉"
    ),
    "day1_morning": (
        "🌅 Good morning {name}!\n\n"
        "Welcome to *{property}*! Today your journey begins! 🏨\n\n"
        "Your Day 1 schedule:\n"
        "🕐 *{reporting_time}* — Welcome & induction\n"
        "📋 HR documentation & form filling\n"
        "🗺️ Property tour\n"
        "🍽️ Team lunch\n"
        "👔 Uniform & locker assignment\n\n"
        "Your buddy for the first week: *{manager_name}*\n\n"
        "Excited to have you with us! 💫"
    ),
}


def render_preboarding_message(
    template_key: str,
    candidate_name: str,
    role_title: str,
    property_name: str,
    joining_date: date,
    net_monthly: int = 0,
    manager_name: str = "Your Manager",
    department: str = "",
    reporting_location: str = "",
    reporting_time: str = "09:00 AM",
) -> str:
    """Render a pre-boarding WhatsApp message from template."""
    tpl = PREBOARDING_TEMPLATES.get(template_key, "Hi {name}! Welcome to {property}!")
    jd_str = joining_date.strftime("%d %B %Y") if joining_date else "your joining date"
    return tpl.format(
        name=candidate_name,
        role=role_title,
        property=property_name,
        joining_date=jd_str,
        net_monthly=net_monthly,
        manager_name=manager_name,
        department=department,
        reporting_location=reporting_location or property_name,
        reporting_time=reporting_time,
    )


def schedule_preboarding_messages(
    flow_id: str,
    org_id: str,
    candidate_id: str,
    candidate_phone: str,
    candidate_name: str,
    role_title: str,
    property_name: str,
    joining_date: date,
    offer_date: date,
    net_monthly: int,
    manager_name: str,
    department: str,
    reporting_location: str,
    reporting_time: str,
    sequence_config: list,
) -> list[dict]:
    """
    Build the list of preboarding_messages rows to insert.
    sequence_config: list of {offset_days, reference, template_key, label}
    """
    rows = []
    now = datetime.now(timezone.utc)

    for entry in sequence_config:
        key       = entry["template_key"]
        label     = entry.get("label", key)
        ref       = entry.get("reference", "offer")   # 'offer' or 'joining'
        offset    = int(entry.get("offset_days", 0))

        if ref == "offer":
            base_date = datetime.combine(offer_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            send_at = base_date + timedelta(days=offset)
            # Send at 9 AM IST (UTC+5:30 → UTC 3:30)
            send_at = send_at.replace(hour=3, minute=30)
        else:  # joining
            base_date = datetime.combine(joining_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            send_at = base_date + timedelta(days=offset)
            if offset == 0:
                # Day 1 morning: 7 AM IST = 1:30 AM UTC
                send_at = send_at.replace(hour=1, minute=30)
            else:
                send_at = send_at.replace(hour=3, minute=30)

        # Render message body
        body = render_preboarding_message(
            template_key=key,
            candidate_name=candidate_name,
            role_title=role_title,
            property_name=property_name,
            joining_date=joining_date,
            net_monthly=net_monthly,
            manager_name=manager_name,
            department=department,
            reporting_location=reporting_location,
            reporting_time=reporting_time,
        )

        rows.append({
            "flow_id":        flow_id,
            "org_id":         org_id,
            "candidate_id":   candidate_id,
            "candidate_phone": candidate_phone,
            "template_key":   key,
            "template_label": label,
            "message_body":   body,
            "scheduled_for":  send_at.isoformat(),
            "status":         "scheduled" if send_at > now else "skipped",
        })

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Onboarding Checklist Tasks
# ─────────────────────────────────────────────────────────────────────────────

# 5-stage checklist definition (stage → list of tasks)
CHECKLIST_TEMPLATE = {
    "documents": [
        {"type": "aadhaar_upload",   "label": "Aadhaar Card (original + copy)",   "order": 1},
        {"type": "pan_upload",       "label": "PAN Card (original + copy)",        "order": 2},
        {"type": "passport_photos",  "label": "4 Passport-size Photographs",       "order": 3},
        {"type": "bank_details",     "label": "Bank Account & IFSC Details",       "order": 4},
        {"type": "prev_exp_certs",   "label": "Previous Employment Certificates",  "order": 5, "mandatory": False},
        {"type": "education_certs",  "label": "Educational Certificates",          "order": 6},
    ],
    "kyc": [
        {"type": "video_kyc",        "label": "Video KYC Verification",            "order": 1},
        {"type": "address_verify",   "label": "Address Verification",              "order": 2},
        {"type": "background_check", "label": "Background Verification",           "order": 3, "mandatory": False},
    ],
    "certifications": [
        {"type": "food_safety",      "label": "FSSAI Food Safety Certification",   "order": 1, "mandatory": False},
        {"type": "role_cert",        "label": "Role-specific Certification",        "order": 2, "mandatory": False},
        {"type": "induction_training","label": "Company Induction Training",       "order": 3},
    ],
    "payroll": [
        {"type": "appointment_esign","label": "Appointment Letter — Aadhaar eSign","order": 1},
        {"type": "pf_form2",         "label": "PF Form 2 — Nomination Declaration","order": 2},
        {"type": "esic_declaration", "label": "ESIC Declaration Form",             "order": 3},
        {"type": "bank_setup",       "label": "Salary Account Activation",         "order": 4},
        {"type": "uan_activation",   "label": "UAN Activation / KYC",              "order": 5},
    ],
    "ready": [
        {"type": "id_card_issued",   "label": "Employee ID Card Issued",           "order": 1},
        {"type": "email_setup",      "label": "Official Email Setup",              "order": 2, "mandatory": False},
        {"type": "uniform_issued",   "label": "Uniform Issued",                    "order": 3},
        {"type": "system_access",    "label": "System / Roster Access",            "order": 4, "mandatory": False},
        {"type": "buddy_assigned",   "label": "Buddy Assigned",                    "order": 5},
    ],
}


def build_checklist_tasks(
    flow_id: str,
    org_id: str,
    candidate_id: str,
    joining_date: Optional[date],
    role_title: str,
) -> list[dict]:
    """Generate all checklist task rows for a new onboarding flow."""
    rows = []
    today = date.today()
    joining = joining_date or (today + timedelta(days=14))

    for stage, tasks in CHECKLIST_TEMPLATE.items():
        for task in tasks:
            # Simple due date heuristic per stage
            due_offset = {
                "documents": -7,        # 1 week before joining
                "kyc": -5,
                "certifications": -3,
                "payroll": -2,
                "ready": 0,
            }
            due = joining + timedelta(days=due_offset.get(stage, -1))

            rows.append({
                "flow_id":     flow_id,
                "org_id":      org_id,
                "candidate_id": candidate_id,
                "stage":       stage,
                "task_type":   task["type"],
                "task_label":  task["label"],
                "is_mandatory": task.get("mandatory", True),
                "is_system":   False,
                "status":      "pending",
                "due_date":    str(due),
                "sort_order":  task["order"],
            })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Core service: init onboarding flow
# ─────────────────────────────────────────────────────────────────────────────

def init_onboarding_flow(
    supabase,
    candidate: dict,
    job: dict,
    org_id: str,
    joining_date: Optional[date] = None,
    gross_monthly_inr: Optional[int] = None,
    triggered_by: Optional[str] = None,
) -> dict:
    """
    Create an onboarding flow with all 5-stage checklist tasks.
    Returns the created flow dict.
    """
    cand_name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip()
    role      = job.get("title") or job.get("role_title") or "Staff"
    dept      = job.get("department", "")
    prop      = job.get("property_name") or job.get("location", "")

    flow_payload = {
        "org_id":            org_id,
        "candidate_id":      candidate["id"],
        "job_id":            job.get("id"),
        "candidate_name":    cand_name,
        "role_title":        role,
        "department":        dept,
        "property_name":     prop,
        "manager_name":      job.get("manager_name", ""),
        "manager_phone":     job.get("manager_phone", ""),
        "reporting_location": prop,
        "joining_date":      str(joining_date) if joining_date else None,
        "offer_date":        str(date.today()),
        "current_stage":     "documents",
        "completion_pct":    0,
        "status":            "active",
    }

    try:
        res = supabase.table("onboarding_flows").insert(flow_payload).execute()
        flow = res.data[0] if res.data else flow_payload
        flow_id = flow.get("id", str(uuid.uuid4()))
    except Exception as e:
        logger.error(f"Failed to create onboarding flow: {e}")
        raise

    # Insert checklist tasks
    tasks = build_checklist_tasks(flow_id, org_id, candidate["id"], joining_date, role)
    try:
        supabase.table("onboarding_tasks").insert(tasks).execute()
    except Exception as e:
        logger.error(f"Failed to insert checklist tasks: {e}")

    return {"flow": flow, "tasks": tasks}


def send_due_preboarding_messages(supabase, org_id: Optional[str] = None) -> int:
    """
    Find and send all preboarding messages scheduled to be sent now.
    Called by a periodic job / cron. Returns count sent.
    """
    from app.services.whatsapp_gateway import send_whatsapp

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        query = supabase.table("preboarding_messages").select("*").eq("status", "scheduled").lte("scheduled_for", now_iso)
        if org_id:
            query = query.eq("org_id", org_id)
        rows = query.execute().data or []
    except Exception as e:
        logger.error(f"Failed to fetch preboarding messages: {e}")
        return 0

    sent = 0
    for msg in rows:
        try:
            msg_id = send_whatsapp(msg["candidate_phone"], msg["message_body"])
            supabase.table("preboarding_messages").update({
                "status":          "sent",
                "sent_at":         datetime.now(timezone.utc).isoformat(),
                "whatsapp_msg_id": msg_id or "",
            }).eq("id", msg["id"]).execute()
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send preboarding message {msg['id']}: {e}")
            supabase.table("preboarding_messages").update({
                "status":       "failed",
                "error_detail": str(e),
            }).eq("id", msg["id"]).execute()

    return sent
