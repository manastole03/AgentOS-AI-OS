from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RuntimeContext:
    run_id: UUID
    thread_id: UUID
    actor_user_id: UUID
    tenant_id: str
    account_type: str
    team: str
    allowed_teams: tuple[str, ...]
    memory_mode: str
