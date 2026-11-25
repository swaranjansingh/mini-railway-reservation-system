import hashlib
import bcrypt


def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt with salt.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against the stored bcrypt hash.
    """
    plain_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    try:
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        return False


def hash_token(raw_token: str) -> str:
    """
    Compute a deterministic SHA-256 hash for secure token storage and lookup.
    """
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()
