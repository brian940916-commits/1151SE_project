import hashlib
import hmac
import secrets

ITERATIONS = 600_000


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"{ITERATIONS}:{salt.hex()}:{digest.hex()}"


def matches(password, stored):
    iterations, salt, digest = stored.split(":")
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(candidate.hex(), digest)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()
