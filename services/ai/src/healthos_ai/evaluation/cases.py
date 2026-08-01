from dataclasses import dataclass

from healthos_ai.teams import TeamName


@dataclass(frozen=True)
class RoutingCase:
    name: str
    prompt: str
    expected_team: TeamName
    account_type: str


ROUTING_CASES = (
    RoutingCase(
        "patient-navigation",
        "Help me prepare for my upcoming appointment",
        TeamName.PATIENT,
        "patient",
    ),
    RoutingCase(
        "claim-status",
        "Explain the denial reason in this claim record",
        TeamName.INSURANCE,
        "insurance",
    ),
    RoutingCase(
        "clinical-evidence",
        "Summarize the cited evidence for clinician review",
        TeamName.CLINICAL,
        "doctor",
    ),
    RoutingCase(
        "hospital-operations",
        "Find the bottleneck in the discharge workflow",
        TeamName.ADMINISTRATIVE,
        "hospital",
    ),
    RoutingCase(
        "platform-incident", "Analyze elevated API error rates", TeamName.INFRASTRUCTURE, "admin"
    ),
    RoutingCase(
        "document-extraction",
        "Extract the policy number from an uploaded document",
        TeamName.DOCUMENT_INTELLIGENCE,
        "insurance",
    ),
)
