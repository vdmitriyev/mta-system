import asyncio
import base64

import pytest
from fastapi import HTTPException

from app.captcha import generate_captcha, get_random_text, load_font
from app.security import (
    AttemptLimiter,
    csrf_protect,
    csrf_token,
    generate_pin,
    make_hash,
    random_string,
    verify_hash,
)

KEY = b"key"


class FakeRequest:
    def __init__(self, session=None, form=None):
        self.session = session if session is not None else {}
        self._form = form or {}

    async def form(self):
        return self._form


def test_random_string_has_length_and_ends_with_digits():
    text = random_string(12)
    assert len(text) == 12
    assert text[-2:].isdigit()
    assert text.isalnum()
    assert len(random_string(1)) == 3
    assert random_string() != random_string()


def test_generate_pin_is_four_digits():
    for _ in range(50):
        pin = generate_pin()
        assert len(pin) == 4 and pin.isdigit()
    assert len(generate_pin(6)) == 6


def test_make_hash_depends_on_text_key_and_size():
    assert make_hash("a", KEY) == make_hash("a", KEY)
    assert make_hash("a", KEY) != make_hash("b", KEY)
    assert make_hash("a", KEY) != make_hash("a", b"other")
    assert len(make_hash("a", KEY)) == 32
    assert len(make_hash("a", KEY, auth_size=32)) == 64


def test_verify_hash():
    assert verify_hash("1234", make_hash("1234", KEY), KEY)
    assert not verify_hash("1235", make_hash("1234", KEY), KEY)
    assert not verify_hash("1234", None, KEY)
    assert not verify_hash(None, "x", KEY)


def test_csrf_token_is_kept_in_the_session():
    request = FakeRequest()
    token = csrf_token(request)
    assert len(token) > 20
    assert csrf_token(request) == token


async def _check(request):
    await csrf_protect(request)


def test_csrf_protect():
    good = FakeRequest({"csrf_token": "abc"}, {"csrf_token": "abc"})
    asyncio.run(_check(good))

    for request in (
        FakeRequest({"csrf_token": "abc"}, {"csrf_token": "xyz"}),
        FakeRequest({"csrf_token": "abc"}, {}),
        FakeRequest({}, {"csrf_token": "abc"}),
    ):
        with pytest.raises(HTTPException) as error:
            asyncio.run(_check(request))
        assert error.value.status_code == 403


def test_attempt_limiter_blocks_after_too_many_failures():
    limiter = AttemptLimiter(max_attempts=3, window_seconds=60)
    for _ in range(2):
        limiter.add_failure("a")
    assert not limiter.is_blocked("a")
    limiter.add_failure("a")
    assert limiter.is_blocked("a")
    assert not limiter.is_blocked("b")
    limiter.reset("a")
    assert not limiter.is_blocked("a")


def test_attempt_limiter_forgets_old_failures(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("app.security.time.monotonic", lambda: now[0])
    limiter = AttemptLimiter(max_attempts=1, window_seconds=60)
    limiter.add_failure("a")
    assert limiter.is_blocked("a")
    now[0] += 61
    assert not limiter.is_blocked("a")
    limiter.add_failure("a")
    limiter.reset()
    assert not limiter.is_blocked("a")


def test_captcha_text_and_image():
    text, image = generate_captcha(add_noise=True)
    assert len(text) == 4 and text.isdigit()
    assert base64.b64decode(image).startswith(b"\x89PNG")
    assert generate_captcha()[1]
    assert len(get_random_text(6)) == 6


def test_captcha_font_falls_back_to_the_pillow_font(monkeypatch):
    monkeypatch.setattr("app.captcha.FONT_FILES", ("no-such-font.ttf",))
    assert load_font() is not None
    assert generate_captcha()[0]
