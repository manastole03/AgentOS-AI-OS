from uuid import uuid4

import pytest
from pydantic import ValidationError

from healthos_api.api.routes.platform import _definition_actions
from healthos_api.db.models import ApplicationDefinition
from healthos_api.platform.schemas import ConsentCreate, DefinitionCreate


def test_configuration_rejects_executable_or_unknown_rule_keys() -> None:
    with pytest.raises(ValidationError):
        DefinitionCreate(
            kind="form",
            key="claim_form",
            rules=[{"when": {"field": "status"}, "javascript": "alert(1)"}],
        )


def test_consent_requires_exactly_one_grantee() -> None:
    with pytest.raises(ValidationError):
        ConsentCreate(purpose="treatment", scopes=["encounters"])
    with pytest.raises(ValidationError):
        ConsentCreate(
            grantee_user_id=uuid4(),
            grantee_organization_id=uuid4(),
            purpose="treatment",
            scopes=["encounters"],
        )


def test_workflow_actions_are_filtered_by_accountable_role() -> None:
    definition = ApplicationDefinition(
        id=uuid4(),
        kind="workflow",
        key="claim_review",
        version=1,
        status="published",
        account_types=["insurance"],
        locale="en-US",
        schema={
            "initial": "draft",
            "states": {
                "draft": {
                    "transitions": [
                        {"action": "submit", "to": "review"},
                        {"action": "deny", "to": "denied", "roles": ["reviewer"]},
                    ]
                }
            },
        },
        presentation={},
        rules=[],
    )
    assert _definition_actions(definition, "draft", {"insurance"}) == ["submit"]
    assert _definition_actions(definition, "draft", {"insurance", "reviewer"}) == [
        "submit",
        "deny",
    ]
