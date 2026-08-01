from uuid import uuid4

import pytest
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from healthos_ai.api.schemas import RunRequest
from healthos_ai.auth import Identity
from healthos_ai.config import Settings
from healthos_ai.llm import LLMGateway
from healthos_ai.rag import chunk_text
from healthos_ai.security import DataCipher
from healthos_ai.teams import TeamName, allowed_teams
from healthos_ai.teams.definitions import TEAM_DEFINITIONS
from healthos_ai.teams.factory import TeamAgentFactory


def test_cipher_authenticates_sensitive_run_data() -> None:
    cipher = DataCipher("aGVhbHRob3MtbG9jYWwtYWkta2V5LTMyLWJ5dGVzISE=")
    encrypted = cipher.encrypt("minimum necessary PHI")

    assert b"minimum necessary PHI" not in encrypted
    assert cipher.decrypt(encrypted) == "minimum necessary PHI"


def test_chunker_is_deterministic_and_overlapping() -> None:
    content = " ".join(f"word-{index}" for index in range(1000))
    chunks = chunk_text(content, size=300, overlap=50)

    assert len(chunks) > 2
    assert all(len(chunk) <= 300 for chunk in chunks)
    assert chunks == chunk_text(content, size=300, overlap=50)


def test_rbac_restricts_clinical_and_infrastructure_teams() -> None:
    patient_teams = allowed_teams("patient")
    admin_teams = allowed_teams("admin")

    assert TeamName.CLINICAL not in patient_teams
    assert TeamName.INFRASTRUCTURE not in patient_teams
    assert set(admin_teams) == set(TeamName)


def test_identity_tenant_scope_defaults_to_actor() -> None:
    actor_id = uuid4()
    identity = Identity(id=actor_id, email="patient@example.test", account_type="patient")

    assert identity.tenant_id == str(actor_id)


def test_run_request_enforces_prompt_boundary() -> None:
    with pytest.raises(ValidationError):
        RunRequest(prompt="x" * 30_001)


def test_deep_agent_team_compiles_without_provider_call() -> None:
    settings = Settings(_env_file=None)
    team = TeamAgentFactory(settings, LLMGateway(settings), [], []).create(TeamName.PATIENT)

    assert isinstance(team, CompiledStateGraph)


def test_specified_specialist_families_are_registered() -> None:
    names = {
        team: {specialist.name for specialist in definition.specialists}
        for team, definition in TEAM_DEFINITIONS.items()
    }
    assert {"patient_assistant", "symptom_assessment", "medical_records", "medication"} <= names[
        TeamName.PATIENT
    ]
    assert {
        "eligibility_verification",
        "claims",
        "prior_authorization",
        "cost_estimation",
    } <= names[TeamName.INSURANCE]
    assert {"clinical_documentation", "medical_coding", "referral_coordinator"} <= names[
        TeamName.CLINICAL
    ]
    assert {"ocr", "extraction", "classification", "validation", "summarization"} == names[
        TeamName.DOCUMENT_INTELLIGENCE
    ]
