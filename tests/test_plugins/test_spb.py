# from lihil.plugins.supabase import func

import pytest
from msgspec import ValidationError, convert

from lihil.plugins.auth.supabase import auth_types


def test_validate_typeddict():

    data = {"provider": "google", "token": "asdfadsf"}

    result = convert(data, auth_types.SignInWithIdTokenCredentials)
    assert isinstance(result, dict)

    fail_data = {"provider": "google", "token": 3.5}

    with pytest.raises(ValidationError):
        convert(fail_data, auth_types.SignInWithIdTokenCredentials)
