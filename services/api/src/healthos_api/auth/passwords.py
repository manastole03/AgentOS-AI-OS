from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hasher.hash("healthos-dummy-password-never-used")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def verify_dummy_password(password: str) -> None:
    password_hasher.verify(password, DUMMY_PASSWORD_HASH)
