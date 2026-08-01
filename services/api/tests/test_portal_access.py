import pytest

from healthos_api.db.models import AccountType
from healthos_api.portal.access import PORTAL_MODULES, authorize_module
from healthos_api.portal.service import _consent_scopes


def test_patient_spec_modules_are_available() -> None:
    expected = {
        "vitals",
        "allergies",
        "vaccinations",
        "visits",
        "medications",
        "appointments",
        "lab_bookings",
        "insurance",
        "buy_insurance",
        "claims",
        "cost_estimates",
        "consents",
        "ai_assistant",
    }
    assert expected <= set(PORTAL_MODULES[AccountType.PATIENT])


def test_cross_role_module_is_rejected() -> None:
    with pytest.raises(PermissionError):
        authorize_module(AccountType.PATIENT, "user_management")


def test_consent_scopes_accept_normalized_csv_or_array() -> None:
    assert _consent_scopes({"scopes": "visits, lab_reports"}) == {"visits", "lab_reports"}
    assert _consent_scopes({"scopes": ["visits", "*"]}) == {"visits", "*"}
