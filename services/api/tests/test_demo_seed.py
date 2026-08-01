from healthos_api.cli.seed_demo import ACCOUNTS, record_specs
from healthos_api.db.models import AccountType
from healthos_api.portal.access import PORTAL_MODULES


def test_demo_seed_has_an_account_and_sample_for_every_portal_module() -> None:
    specs = record_specs(
        ACCOUNTS[AccountType.PATIENT].user_id,
        ACCOUNTS[AccountType.PATIENT].user_id,
        ACCOUNTS[AccountType.DOCTOR].user_id,
    )

    assert set(ACCOUNTS) == set(AccountType)
    for account_type, modules in PORTAL_MODULES.items():
        assert set(specs[account_type]) == set(modules)


def test_demo_patient_has_permanent_fifteen_character_health_id() -> None:
    patient_id = "PATDEMO00000001"

    assert len(patient_id) == 15
    assert patient_id.startswith("PAT")
