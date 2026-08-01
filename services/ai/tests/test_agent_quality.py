from healthos_ai.evaluation import ROUTING_CASES
from healthos_ai.teams import TEAM_DEFINITIONS, allowed_teams
from healthos_ai.teams.factory import SAFETY_PROMPT


def test_golden_routes_respect_account_authorization() -> None:
    for case in ROUTING_CASES:
        assert case.expected_team in allowed_teams(case.account_type), case.name


def test_every_team_has_specialists_and_safety_boundary() -> None:
    assert "autonomous clinical decisions" in SAFETY_PROMPT
    assert "coverage determinations" in SAFETY_PROMPT
    assert "tenant-authorized" in SAFETY_PROMPT
    for team in TEAM_DEFINITIONS.values():
        assert len(team.specialists) >= 2
        assert team.allowed_account_types
        assert all(specialist.instructions for specialist in team.specialists)
