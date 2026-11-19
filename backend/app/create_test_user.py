import argparse
import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import engine
from app.models import User, UserRole


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local development user.")
    parser.add_argument("--email", required=True, help="Email address for the local user")
    parser.add_argument("--role", choices=[role.value for role in UserRole], default=UserRole.EMPLOYEE.value)
    args = parser.parse_args()

    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")

    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not password or password != confirmation:
        raise ValueError("Passwords must be non-empty and match")

    with Session(engine) as db:
        if db.scalar(select(User).where(User.email == args.email)) is not None:
            raise ValueError("A user with that email already exists")
        db.add(
            User(
                email=args.email,
                password_hash=hash_password(password),
                role=UserRole(args.role),
            )
        )
        db.commit()

    print(f"Created local {args.role} user: {args.email}")


if __name__ == "__main__":
    main()
