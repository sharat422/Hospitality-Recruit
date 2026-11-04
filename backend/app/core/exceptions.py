"""Custom exceptions for HospRecruit AI."""


class HospRecruitException(Exception):
    """Base exception for HospRecruit AI."""

    pass


class ScreeningException(HospRecruitException):
    """Exception during AI candidate screening (Pain #1)."""

    pass


class ShiftMatchException(HospRecruitException):
    """Exception during shift matching logic (Pain #2)."""

    pass


class ComplianceException(HospRecruitException):
    """Exception during compliance/onboarding checks (Pain #5)."""

    pass


class IntegrationException(HospRecruitException):
    """Exception during ATS/SMS/payment integrations."""

    pass
