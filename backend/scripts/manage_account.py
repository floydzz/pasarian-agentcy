"""Local operator recovery. Passwords are read privately and never logged."""
import argparse
import getpass
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import delete, select
from app.db import SessionLocal
from app.models import LoginSession, User
from app.security import hash_password

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("email", help="Existing owner or team account email")
args = parser.parse_args()
password = getpass.getpass("New password (at least 12 characters): ")
if len(password) < 12 or len(password) > 128 or password != getpass.getpass("Repeat new password: "):
    raise SystemExit("Passwords must match and contain 12–128 characters")
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.email == args.email.strip().lower()).with_for_update())
    if user is None:
        raise SystemExit("Account not found")
    user.password_hash = hash_password(password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.commit()
print("Password updated. Existing sessions were revoked. Login rate limits still apply.")
