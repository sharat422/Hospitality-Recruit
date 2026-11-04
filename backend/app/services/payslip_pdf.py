"""
payslip_pdf.py — PDF generation and S3 upload for payslips.

Depends on fpdf2 (optional). If not installed, generate_payslip_pdf()
returns None and callers fall back to the plain-text WhatsApp summary.

PDF layout:
  • Company header + "Pay Slip — Month Year"
  • Employee info (name, attendance, payment method)
  • Earnings table (gross, basic, HRA, DA, allowances, overtime, bonus)
  • Deductions table (EPF, ESIC, Professional Tax, TDS, other)
  • Net pay — highlighted green
  • Footer: "CONFIDENTIAL — system generated"

S3 upload:
  Uploads to ap-south-1 under payslips/{org_id}/{employee_id}/{year}_{mm}.pdf.
  Returns the public S3 URL or None if credentials are not configured.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_MONTH_NAME = {
    1: "January",  2: "February", 3: "March",    4: "April",
    5: "May",      6: "June",     7: "July",      8: "August",
    9: "September",10: "October", 11: "November", 12: "December",
}


# ─────────────────────────────────────────────────────────────────────────────
# PDF generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_payslip_pdf(
    payslip:       dict,
    employee_name: str,
    org_name:      str = "HospRecruit",
) -> Optional[bytes]:
    """
    Generate a PDF payslip from a payslips table row dict.
    Returns raw PDF bytes, or None if fpdf2 is not installed.
    """
    try:
        from fpdf import FPDF  # fpdf2, not the old fpdf
    except ImportError:
        logger.debug("fpdf2 not installed — PDF generation unavailable")
        return None

    month      = payslip.get("month", 0)
    year       = payslip.get("year", 0)
    month_name = _MONTH_NAME.get(month, str(month))

    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()

    # ── Header ────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, org_name, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 13)
    pdf.cell(0, 7, f"Pay Slip  —  {month_name} {year}",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(6)

    # ── Employee info ─────────────────────────────────────────────────────────
    _kv(pdf, "Employee", employee_name)
    method = payslip.get("payment_method", "BANK_TRANSFER").replace("_", " ").title()
    _kv(pdf, "Payment Method", method)
    if payslip.get("paid_at"):
        _kv(pdf, "Paid On", str(payslip["paid_at"])[:10])
    if payslip.get("working_days") and payslip.get("present_days"):
        _kv(pdf, "Attendance",
            f"{payslip['present_days']} / {payslip['working_days']} days")
    pdf.ln(6)

    # ── Earnings ──────────────────────────────────────────────────────────────
    _section_header(pdf, "EARNINGS")
    _money_row(pdf, "Gross Salary",  payslip.get("gross_salary_inr", 0))
    if payslip.get("basic_salary_inr"):
        _money_row(pdf, "Basic Salary", payslip["basic_salary_inr"])
    for field, label in [
        ("hra_inr",        "House Rent Allowance (HRA)"),
        ("da_inr",         "Dearness Allowance (DA)"),
        ("allowances_inr", "Other Allowances"),
        ("overtime_inr",   "Overtime"),
        ("bonus_inr",      "Bonus"),
    ]:
        val = float(payslip.get(field) or 0)
        if val > 0:
            _money_row(pdf, label, val)
    pdf.ln(5)

    # ── Deductions ────────────────────────────────────────────────────────────
    _section_header(pdf, "DEDUCTIONS")
    has_ded = False
    for field, label in [
        ("epf_deduction_inr",    "EPF (Employee Provident Fund)"),
        ("esic_deduction_inr",   "ESIC"),
        ("professional_tax_inr", "Professional Tax"),
        ("tds_inr",              "TDS"),
        ("other_deductions_inr", "Other Deductions"),
    ]:
        val = float(payslip.get(field) or 0)
        if val > 0:
            _money_row(pdf, label, val)
            has_ded = True
    if not has_ded:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 7, "  No deductions", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # ── Net pay ───────────────────────────────────────────────────────────────
    net = float(payslip.get("net_salary_inr") or 0)
    pdf.set_fill_color(34, 139, 34)     # Forest green
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 11, f"  NET PAY:  {_fmt_inr(net)}",
             fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    # ── Footer ────────────────────────────────────────────────────────────────
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5,
             "This is a system-generated payslip. No signature required.",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5,
             "CONFIDENTIAL — For the named employee only. Do not share.",
             align="C", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────────────────────
# S3 upload
# ─────────────────────────────────────────────────────────────────────────────

def upload_payslip_to_s3(
    pdf_bytes:   bytes,
    org_id:      str,
    employee_id: str,
    month:       int,
    year:        int,
) -> Optional[str]:
    """
    Upload payslip PDF to S3 ap-south-1.
    Key format: payslips/{org_id}/{employee_id}/{year}_{month:02d}.pdf
    Returns public HTTPS URL or None if credentials are not configured.
    """
    try:
        import boto3
        from app.core.config import settings

        if not settings.AWS_S3_BUCKET or not settings.AWS_ACCESS_KEY_ID:
            logger.debug("S3 not configured — skipping payslip upload")
            return None

        key = f"payslips/{org_id}/{employee_id}/{year}_{month:02d}.pdf"
        s3  = boto3.client(
            "s3",
            region_name          = "ap-south-1",
            aws_access_key_id    = settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key= settings.AWS_SECRET_ACCESS_KEY,
        )
        encryption = "aws:kms" if getattr(settings, "AWS_KMS_KEY_ID", None) else "AES256"
        put_args = {
            "Bucket": settings.AWS_S3_BUCKET, "Key": key, "Body": pdf_bytes,
            "ContentType": "application/pdf", "ServerSideEncryption": encryption,
        }
        if encryption == "aws:kms":
            put_args["SSEKMSKeyId"] = settings.AWS_KMS_KEY_ID
        s3.put_object(**put_args)
        # Return a presigned URL valid for 24 hours so WhatsApp can fetch it
        url = s3.generate_presigned_url(
            "get_object",
            Params     = {"Bucket": settings.AWS_S3_BUCKET, "Key": key},
            ExpiresIn  = 86400,
        )
        logger.info("Payslip uploaded to S3: %s", key)
        return url

    except ImportError:
        logger.debug("boto3 not installed — S3 upload unavailable")
        return None
    except Exception as exc:
        logger.warning("S3 payslip upload failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Internal PDF helpers
# ─────────────────────────────────────────────────────────────────────────────

def _section_header(pdf, title: str) -> None:
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 8, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")


def _money_row(pdf, label: str, amount) -> None:
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(130, 7, f"  {label}")
    pdf.cell(0, 7, _fmt_inr(float(amount or 0)),
             align="R", new_x="LMARGIN", new_y="NEXT")


def _kv(pdf, label: str, value: str) -> None:
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(55, 7, f"{label}:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")


def _fmt_inr(amount: float) -> str:
    return f"Rs. {amount:,.2f}"
