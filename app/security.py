import hmac
import secrets
import string
import time
from collections import defaultdict
from hashlib import blake2b
from threading import Lock

from fastapi import HTTPException, Request

CSRF_SESSION_KEY = "csrf_token"
CSRF_FIELD = "csrf_token"


def random_string(str_length: int = 10) -> str:
    """Random password of letters and digits. The last two characters are digits."""

    str_length = max(str_length, 3)
    characters = string.ascii_letters + string.digits
    text = "".join(secrets.choice(characters) for _ in range(str_length - 2))
    digits = "".join(secrets.choice(string.digits) for _ in range(2))
    return text + digits


def generate_pin(max_numbers: int = 4) -> str:
    return str(secrets.randbelow(10**max_numbers)).zfill(max_numbers)


def make_hash(plain_txt: str, hash_key: bytes, auth_size: int = 16) -> str:
    """Keyed hash (BLAKE2b) of the given text"""

    h = blake2b(digest_size=auth_size, key=hash_key)
    h.update(plain_txt.encode("utf-8"))
    return h.hexdigest()


def verify_hash(plain_txt: str, hash_txt: str, hash_key: bytes) -> bool:
    if plain_txt is None or hash_txt is None:
        return False
    return hmac.compare_digest(make_hash(plain_txt, hash_key), str(hash_txt))


def csrf_token(request: Request) -> str:
    """Gets the CSRF token of the session (creates it on first use)"""

    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


async def csrf_protect(request: Request) -> None:
    """FastAPI dependency for POST routes: the form must contain the CSRF token"""

    form = await request.form()
    sent = form.get(CSRF_FIELD)
    expected = request.session.get(CSRF_SESSION_KEY)
    if (
        not expected
        or not isinstance(sent, str)
        or not hmac.compare_digest(sent, expected)
    ):
        raise HTTPException(
            status_code=403,
            detail="The form has expired. Go back, reload the page and try again.",
        )


class AttemptLimiter:
    """Limits failed attempts per key (e.g. logins per client and e-mail).

    Kept in memory: each worker process counts on its own.
    """

    def __init__(self, max_attempts: int = 10, window_seconds: int = 900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts = defaultdict(list)
        self._lock = Lock()

    def _recent(self, key: str) -> list:
        limit = time.monotonic() - self.window_seconds
        recent = [moment for moment in self._attempts[key] if moment > limit]
        if recent:
            self._attempts[key] = recent
        else:
            self._attempts.pop(key, None)
        return recent

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.max_attempts

    def add_failure(self, key: str) -> None:
        with self._lock:
            self._recent(key)
            self._attempts[key].append(time.monotonic())

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._attempts.clear()
            else:
                self._attempts.pop(key, None)
