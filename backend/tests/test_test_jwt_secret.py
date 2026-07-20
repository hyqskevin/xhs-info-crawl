import warnings

from jwt.warnings import InsecureKeyLengthWarning

from app.core.config import get_settings
from app.core.security import create_access_token


def test_pytest_uses_jwt_secret_of_at_least_32_bytes() -> None:
    assert len(get_settings().secret_key.encode("utf-8")) >= 32


def test_access_token_creation_has_no_short_key_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", InsecureKeyLengthWarning)
        token = create_access_token({"sub": "test-user", "role": "admin"})

    assert token
