import secrets
import string

PATIENT_ID_PREFIX = "PAT"
PATIENT_ID_RANDOM_LENGTH = 12
PATIENT_ID_ALPHABET = string.ascii_uppercase + string.digits


def generate_patient_id() -> str:
    """Generate a non-sequential, exactly 15-character public patient identifier."""
    suffix = "".join(secrets.choice(PATIENT_ID_ALPHABET) for _ in range(PATIENT_ID_RANDOM_LENGTH))
    return f"{PATIENT_ID_PREFIX}{suffix}"
