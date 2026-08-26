import argparse
import getpass

from app.database import SessionLocal
from app.models import User
from app.services.auth_service import AuthService


def main() -> None:
    parser = argparse.ArgumentParser(description="Buat admin pertama Entok Vision.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    password = getpass.getpass("Password admin (minimal 8 karakter): ")
    if len(password) < 8:
        raise SystemExit("Password minimal 8 karakter.")
    db = SessionLocal()
    try:
        username = args.username.strip().lower()
        if db.query(User).filter(User.username == username).first():
            raise SystemExit("Username sudah digunakan.")
        db.add(User(username=username, full_name=args.name.strip(), password_hash=AuthService().hash_password(password), role="admin"))
        db.commit()
        print(f"Admin '{username}' berhasil dibuat.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
