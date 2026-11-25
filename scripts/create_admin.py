import argparse
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlmodel import Session, select

from app.config import get_settings
from app.database import engine, init_db
from app.models.user import User, UserRole
from app.security.password import hash_password

settings = get_settings()


def provision_admin(name: str, email: str, password: str) -> None:
    """
    Provision an administrator account securely.
    Ensures idempotency by checking if the email already exists.
    """
    init_db()
    normalized_email = email.strip().lower()

    if settings.ENVIRONMENT == "production":
        insecure_defaults = [
            "AdminSecurePassword123!",
            "admin",
            "password",
            "admin123",
            "changeme",
        ]
        if len(password) < 12 or password in insecure_defaults:
            print("[!] Security Violation: Cannot provision administrator with a default or weak password in production.")
            sys.exit(1)

    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.email == normalized_email)
        ).first()

        if existing:
            if existing.role != UserRole.ADMIN:
                print(f"[!] User with email '{normalized_email}' already exists with role '{existing.role.value}'.")
                print("[-] Cannot overwrite existing passenger account with admin.")
                sys.exit(1)
            else:
                print(f"[i] Administrator account for '{normalized_email}' already exists. No action needed.")
                return

        admin_user = User(
            name=name.strip(),
            email=normalized_email,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin_user)
        session.commit()
        session.refresh(admin_user)
        print(f"[✓] Administrator account successfully created:")
        print(f"    Name:  {admin_user.name}")
        print(f"    Email: {admin_user.email}")
        print(f"    Role:  {admin_user.role.value}")


def main():
    parser = argparse.ArgumentParser(description="Securely provision an administrator account.")
    parser.add_argument("--name", default=settings.INITIAL_ADMIN_NAME, help="Admin display name")
    parser.add_argument("--email", default=settings.INITIAL_ADMIN_EMAIL, help="Admin email address")
    parser.add_argument("--password", default=settings.INITIAL_ADMIN_PASSWORD, help="Admin password")

    args = parser.parse_args()
    provision_admin(name=args.name, email=args.email, password=args.password)


if __name__ == "__main__":
    main()
