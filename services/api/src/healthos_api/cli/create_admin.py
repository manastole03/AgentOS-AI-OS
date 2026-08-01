import argparse
import asyncio
import getpass

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select

from healthos_api.auth.passwords import hash_password
from healthos_api.config import get_settings
from healthos_api.db.models import AccountType, Role, User, UserStatus
from healthos_api.db.session import create_database_engine, create_session_factory


async def create_admin(email: str, password: str) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    factory = create_session_factory(engine)
    try:
        async with factory() as db:
            normalized_email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
            existing = await db.scalar(select(User.id).where(User.email == normalized_email))
            if existing:
                raise ValueError("A user with this email already exists")
            role = await db.scalar(select(Role).where(Role.name == AccountType.ADMIN.value))
            if role is None:
                raise RuntimeError("Run Alembic migrations before creating an administrator")
            db.add(
                User(
                    email=normalized_email,
                    password_hash=hash_password(password),
                    account_type=AccountType.ADMIN,
                    status=UserStatus.ACTIVE,
                    email_verified=True,
                    roles=[role],
                )
            )
            await db.commit()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a HealthOS administrator")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Admin password (minimum 12 characters): ")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters")
    asyncio.run(create_admin(args.email, password))
    print("Administrator created.")  # noqa: T201


if __name__ == "__main__":
    main()
