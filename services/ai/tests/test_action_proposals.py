from healthos_ai.api.routes import confirmation_token_digest, proposal_payload_digest


def test_proposal_digest_is_canonical_and_action_bound() -> None:
    first = proposal_payload_digest("book", {"slot_id": "123", "reason": "follow-up"})
    reordered = proposal_payload_digest("book", {"reason": "follow-up", "slot_id": "123"})
    different_action = proposal_payload_digest(
        "reschedule", {"slot_id": "123", "reason": "follow-up"}
    )
    assert first == reordered
    assert first != different_action


def test_confirmation_token_is_bound_to_exact_payload_digest() -> None:
    token = "a" * 40
    first = confirmation_token_digest(token, "1" * 64)
    assert first == confirmation_token_digest(token, "1" * 64)
    assert first != confirmation_token_digest(token, "2" * 64)
