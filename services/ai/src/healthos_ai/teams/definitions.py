from dataclasses import dataclass
from enum import StrEnum


class TeamName(StrEnum):
    PATIENT = "patient"
    INSURANCE = "insurance"
    CLINICAL = "clinical"
    ADMINISTRATIVE = "administrative"
    INFRASTRUCTURE = "infrastructure"
    DOCUMENT_INTELLIGENCE = "document_intelligence"


@dataclass(frozen=True)
class Specialist:
    name: str
    description: str
    instructions: str


@dataclass(frozen=True)
class TeamDefinition:
    name: TeamName
    description: str
    allowed_account_types: frozenset[str]
    model_setting: str
    specialists: tuple[Specialist, ...]


def _specialist(name: str, purpose: str) -> Specialist:
    return Specialist(
        name,
        purpose,
        f"You are the {name} specialist. {purpose}. Use only authorized context, cite "
        "retrieved evidence, state uncertainty, and never invent facts.",
    )


TEAM_DEFINITIONS = {
    TeamName.PATIENT: TeamDefinition(
        TeamName.PATIENT,
        "Patient navigation, education, and care coordination",
        frozenset({"patient", "doctor", "hospital", "admin"}),
        "patient_model",
        (
            _specialist(
                "patient_assistant", "Guide patients through non-emergency healthcare workflows"
            ),
            _specialist(
                "symptom_assessment",
                "Provide informational triage, never a diagnosis; identify emergency warning "
                "signs and route to emergency, urgent, or routine care",
            ),
            _specialist("medical_records", "Explain and organize the authorized lifelong record"),
            _specialist("medication", "Support medication schedules and safety reminders"),
            _specialist("appointment", "Find and coordinate care and diagnostic appointments"),
            _specialist("telemedicine", "Prepare telemedicine visits and follow-up actions"),
        ),
    ),
    TeamName.INSURANCE: TeamDefinition(
        TeamName.INSURANCE,
        "Benefits, claims, prior authorization, and coverage support",
        frozenset({"patient", "hospital", "insurance", "admin"}),
        "insurance_model",
        (
            _specialist("benefits_analyst", "Interpret supplied benefit and eligibility evidence"),
            _specialist(
                "eligibility_verification",
                "Verify eligibility using integrated payer evidence without determining coverage",
            ),
            _specialist(
                "claims",
                "Support claims and prior-authorization workflows without making coverage "
                "determinations",
            ),
            _specialist("prior_authorization", "Prepare authorization evidence for human review"),
            _specialist("policy", "Explain and compare supplied policy terms in plain language"),
            _specialist("cost_estimation", "Estimate pre-service costs and state uncertainty"),
        ),
    ),
    TeamName.CLINICAL: TeamDefinition(
        TeamName.CLINICAL,
        "Clinician-facing evidence synthesis and workflow support",
        frozenset({"doctor", "hospital", "admin"}),
        "clinical_model",
        (
            _specialist(
                "physician_assistant",
                "Synthesize authorized clinical evidence for licensed physicians",
            ),
            _specialist("nurse_assistant", "Support nursing preparation and follow-up workflows"),
            _specialist("care_coordinator", "Coordinate consented longitudinal care plans"),
            _specialist("referral_coordinator", "Coordinate referrals and specialist handoffs"),
            _specialist("clinical_documentation", "Draft clinical documentation for attestation"),
            _specialist("medical_coding", "Suggest codes that require qualified human review"),
        ),
    ),
    TeamName.ADMINISTRATIVE: TeamDefinition(
        TeamName.ADMINISTRATIVE,
        "Healthcare operations, scheduling, coding, and compliance support",
        frozenset({"doctor", "hospital", "insurance", "admin"}),
        "administrative_model",
        (
            _specialist("billing", "Support healthcare billing workflows"),
            _specialist("revenue_cycle", "Analyze revenue-cycle work queues and denials"),
            _specialist("insurance_verification", "Coordinate payer verification"),
            _specialist("scheduling_coordination", "Coordinate provider, facility, and lab slots"),
            _specialist("customer_support", "Resolve support cases with appropriate escalation"),
            _specialist("escalation", "Route high-risk cases to accountable human operators"),
        ),
    ),
    TeamName.INFRASTRUCTURE: TeamDefinition(
        TeamName.INFRASTRUCTURE,
        "Platform reliability, security, and data operations",
        frozenset({"admin"}),
        "infrastructure_model",
        (
            _specialist("workflow_orchestrator", "Coordinate governed multi-agent workflows"),
            _specialist("planner", "Create bounded execution plans"),
            _specialist("router", "Route work to the least-privileged capable team"),
            _specialist("memory_manager", "Govern durable memory reads and writes"),
            _specialist("knowledge_retrieval", "Retrieve tenant-scoped evidence"),
            _specialist("tool_executor", "Execute allowlisted tools with validation"),
            _specialist("guardrails", "Enforce healthcare safety and human review rules"),
            _specialist("security_compliance", "Enforce least privilege and compliance controls"),
            _specialist("audit_logger", "Record metadata-only audit evidence"),
            _specialist("monitoring", "Monitor reliability, latency, and agent quality"),
        ),
    ),
    TeamName.DOCUMENT_INTELLIGENCE: TeamDefinition(
        TeamName.DOCUMENT_INTELLIGENCE,
        "Document classification, extraction, normalization, and retrieval",
        frozenset({"patient", "doctor", "hospital", "insurance", "admin"}),
        "document_model",
        (
            _specialist("ocr", "Convert authorized scanned documents into reviewable text"),
            _specialist("extraction", "Extract structured facts with source citations"),
            _specialist("classification", "Classify authorized healthcare documents"),
            _specialist("validation", "Validate extracted fields and flag uncertainty"),
            _specialist("summarization", "Summarize documents with traceable source citations"),
        ),
    ),
}


def allowed_teams(account_type: str) -> list[TeamName]:
    return [
        name
        for name, team in TEAM_DEFINITIONS.items()
        if account_type in team.allowed_account_types
    ]
