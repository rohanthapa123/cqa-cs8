"""
Create or promote an admin account.

Usage (from project root):

    python -m backend.create_admin <email> <username> <password>

If a user with the given email already exists, they are promoted to admin
(username/password arguments are ignored in that case). Otherwise a new admin
user is created.
"""

import sys

from backend.core.database import Base, SessionLocal, engine
from backend.core.security import hash_password
from backend.models.analysis import Analysis  # noqa: F401 (register table)
from backend.models.user import User


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python -m backend.create_admin <email> <username> <password>")
        raise SystemExit(1)

    email, username, password = sys.argv[1], sys.argv[2], sys.argv[3]

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            existing.role = "admin"
            db.commit()
            print(f"Promoted existing user '{existing.username}' ({email}) to admin.")
            return

        admin = User(
            email=email,
            username=username,
            hashed_password=hash_password(password),
            role="admin",
        )
        db.add(admin)
        db.commit()
        print(f"Created admin user '{username}' ({email}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
