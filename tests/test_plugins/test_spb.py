# from lihil.plugins.supabase import func

import pytest
from msgspec import convert, ValidationError

from lihil.plugins.auth.supabase import SignInWithIdTokenCredentials


def test_validate_typeddict():

    data = {"provider": "google", "token": "asdfadsf"}

    result = convert(data, SignInWithIdTokenCredentials)
    assert isinstance(result, dict)

    fail_data = {"provider": "google", "token": 3.5}

    with pytest.raises(ValidationError):
        convert(fail_data, SignInWithIdTokenCredentials)
