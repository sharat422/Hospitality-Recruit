"""
Main FastAPI application entry point.
Pain points embedded throughout API design + architecture.

Startup validation:
  • Data localisation guard runs on every startup.
  • Hard violations (wrong S3 region) are logged as errors.
  • Warnings (cross-border PII config) are logged but do not block startup.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from app.core.config import settings
from app.routers import (
    smart_recruitment,
    india_onboarding,
    candidates,
    shifts,
    screening,
    sms,
    onboarding,
    analytics,
    talent_pool,
    billing,
    demo,
    matching,
    ai_screening,
    engagement,
    mobile_experience,
    compliance,
    referrals,
    india_referrals,
    employees,
    admin_referrals,
    india_compliance,
    kyc,
    fssai,
    labour,
    dpdp,
    diversity,
    hr_bot,
    whatsapp,
    hotel_management,
    rbac,
    job_distribution,
    candidate_ats,
    attendance,
    workforce_schedules,
    leave_management,
    payroll,
    employee_self_service,
    certifications,
    performance,
    training_career,
    employee_retention,
    employee_engagement,
    employee_exit,
    grievance_management,
    salary_advances,
    accommodation_transport,
    reports,
    global_search,
    hospitality_ai_assistant,
    pms,
    attendance_codes,
    staff_ops_i18n,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — startup validation
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context — runs data localisation validation on startup.
    Logs errors for hard violations; logs warnings for soft misconfigurations.
    Does NOT exit on warnings (allows dev/staging with relaxed config).
    """
    from app.services.data_localization import validate_startup_config

    logger.info("=== HospRecruit startup — data localisation validation ===")
    result = validate_startup_config(settings)

    if not result["ok"]:
        # Log each violation as ERROR so monitoring alerts fire
        for issue in result["issues"]:
            logger.error("[STARTUP] DATA LOCALISATION VIOLATION: %s", issue)
        logger.error(
            "[STARTUP] %d data localisation violation(s) detected. "
            "Review .env: AWS_REGION must be ap-south-1. "
            "See docs/DATA_LOCALIZATION.md",
            len(result["issues"]),
        )
        # We do NOT sys.exit here — allows unit tests and dev to keep running.
        # In production CI/CD, add a health-check gate that reads /data-localization.

    yield  # App runs here

    logger.info("=== HospRecruit shutdown ===")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="HospRecruit AI: Solving hospitality recruiting friction since 2026",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(smart_recruitment.router,   prefix="/api/v1/recruit",          tags=["Smart Recruitment"])
app.include_router(india_onboarding.router,   prefix="/api/v1/india-onboarding",  tags=["India Onboarding"])
app.include_router(candidates.router,      prefix="/api/v1/candidates",      tags=["Module 1 & 3 & 7"])
app.include_router(shifts.router,          prefix="/api/v1/shifts",           tags=["Module 2"])
app.include_router(screening.router,       prefix="/api/v1/screening",        tags=["Module 1"])
app.include_router(sms.router,             prefix="/api/v1/sms",              tags=["Module 4"])
app.include_router(onboarding.router,      prefix="/api/v1/onboarding",       tags=["Module 5"])
app.include_router(analytics.router,       prefix="/api/v1/analytics",        tags=["Module 6"])
app.include_router(talent_pool.router,     prefix="/api/v1/talent-pool",      tags=["Module 7"])
if settings.BILLING_ENABLED:
    app.include_router(billing.router,         prefix="/api/v1",                  tags=["Module 8"])
app.include_router(demo.router,            prefix="/api/v1/demo",             tags=["demo"])
app.include_router(matching.router,        prefix="/api/v1/matching",         tags=["AI Matching"])
app.include_router(ai_screening.router,    prefix="/api/v1/ai-screening",     tags=["AI Screening"])
app.include_router(engagement.router,      prefix="/api/v1/engagement",       tags=["Engagement"])
app.include_router(mobile_experience.router, prefix="/api/v1/mobile",         tags=["Mobile Experience"])
app.include_router(compliance.router,      prefix="/api/v1/compliance",       tags=["Compliance"])
app.include_router(referrals.router,       prefix="/api/v1/referrals",        tags=["Referrals"])
app.include_router(india_referrals.router, prefix="/api/v1/india-referrals",  tags=["India Referrals"])
app.include_router(employees.router,       prefix="/api/v1",                  tags=["Employees"])
app.include_router(admin_referrals.router, prefix="/api/v1/admin-referrals",  tags=["Admin Referrals"])
app.include_router(india_compliance.router,prefix="/api/v1/india-compliance", tags=["India Compliance"])
app.include_router(kyc.router,             prefix="/api/v1/kyc",              tags=["KYC"])
app.include_router(fssai.router,           prefix="/api/v1/fssai",            tags=["FSSAI"])
app.include_router(labour.router,          prefix="/api/v1/labour",           tags=["Labour Compliance"])
app.include_router(dpdp.router,            prefix="/api/v1/dpdp",             tags=["DPDP Privacy"])
app.include_router(diversity.router,       prefix="/api/v1/diversity",         tags=["Diversity"])
app.include_router(hr_bot.router,          prefix="/api/v1/hr-bot",            tags=["HR Bot"])
app.include_router(whatsapp.router,        prefix="/api/whatsapp",              tags=["WhatsApp Webhook"])
app.include_router(hotel_management.router,prefix="/api/v1/hotels",             tags=["Hotel & Multi-Property"])
app.include_router(rbac.router,            prefix="/api/v1/rbac",               tags=["Role-Based Access Control"])
app.include_router(job_distribution.router,prefix="/api/v1/distribution",       tags=["Job Distribution"])
app.include_router(candidate_ats.router,    prefix="/api/v1/ats",                tags=["Candidate ATS"])
app.include_router(attendance.router,       prefix="/api/v1/attendance",         tags=["Attendance"])
app.include_router(workforce_schedules.router, prefix="/api/v1/workforce-schedules", tags=["Workforce Scheduling"])
app.include_router(leave_management.router, prefix="/api/v1/leave", tags=["Leave Management"])
app.include_router(payroll.router, prefix="/api/v1/payroll", tags=["Payroll"])
app.include_router(employee_self_service.router, prefix="/api/v1/employee-self-service", tags=["Employee Self Service"])
app.include_router(certifications.router, prefix="/api/v1/certifications", tags=["Certifications"])
app.include_router(performance.router, prefix="/api/v1/performance", tags=["Performance Management"])
app.include_router(training_career.router, prefix="/api/v1/learning-career", tags=["Training & Career"])
app.include_router(employee_retention.router, prefix="/api/v1/employee-retention", tags=["Employee Retention"])
app.include_router(employee_engagement.router, prefix="/api/v1/employee-engagement", tags=["Employee Engagement"])
app.include_router(employee_exit.router, prefix="/api/v1/employee-exit", tags=["Employee Exit"])
app.include_router(grievance_management.router, prefix="/api/v1/grievances", tags=["Grievance Management"])
app.include_router(salary_advances.router, prefix="/api/v1/salary-advances", tags=["Salary Advances"])
app.include_router(accommodation_transport.router, prefix="/api/v1/facilities", tags=["Employee Accommodation & Transport"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reporting"])
app.include_router(global_search.router, prefix="/api/v1/search", tags=["Global Search"])
app.include_router(hospitality_ai_assistant.router, prefix="/api/v1/assistant", tags=["Hospitality AI Assistant"])
app.include_router(pms.router, prefix="/api/v1/pms", tags=["Hotel PMS Integration"])
app.include_router(attendance_codes.router, prefix="/api/v1/attendance-codes", tags=["Attendance Codes"])
app.include_router(staff_ops_i18n.router, prefix="/api/v1/staff-ops", tags=["Staff Ops — Language"])


# ─────────────────────────────────────────────────────────────────────────────
# Health + info endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Health check — also returns data localisation compliance summary."""
    from app.services.data_localization import validate_startup_config, get_compliance_summary
    validation = validate_startup_config(settings)
    return {
        "status":              "ok",
        "data_localization":   get_compliance_summary(),
        "localization_ok":     validation["ok"],
        "localization_issues": validation["issues"],
    }


@app.get("/data-localization")
async def data_localization_status():
    """
    Machine-readable data localisation compliance status.
    Use this endpoint in CI/CD health-gate to detect misconfigurations.
    Returns HTTP 200 even on violations — check the 'ok' field.
    """
    from app.services.data_localization import validate_startup_config, get_compliance_summary
    validation = validate_startup_config(settings)
    return {
        **get_compliance_summary(),
        "ok":       validation["ok"],
        "issues":   validation["issues"],
        "warnings": validation["warnings"],
    }


@app.get("/")
async def root():
    """API root."""
    return {
        "name":    "HospRecruit AI",
        "version": settings.API_VERSION,
        "docs":    "/docs",
    }
