""" """

from typing import Annotated

import pytest

pytest.importorskip(
    "jwt", reason="pyjwt is not installed; install `lihil[auth]` to run JWT tests"
)

from ididi import Ignore
from jwt import PyJWT
from msgspec import Struct, convert

from lihil import LocalClient, Param, use
from lihil.interface import T
from lihil.plugins.auth.jwt import JWTAuthParam

"""
write an endpoint that requires a function dependency which requires JWTAuthParam
"""


class JWTDecoder:
    def __init__(self, jwt_secret: str, jwt_algos: list[str]):
        self.jwt_secret = jwt_secret
        self.jwt_algos = jwt_algos

        self._jwt = PyJWT()

    def decode(self, raw: bytes, payload_type: type[T]) -> T:
        token = raw.decode("utf-8").removeprefix("Bearer ")
        decoded = self._jwt.decode(
            token, key=self.jwt_secret, algorithms=self.jwt_algos
        )
        return convert(decoded, payload_type)


class TestSecrets:
    class JWTSettings:
        secret: str = "my secret"
        algorithms: list[str] = ["HS256"]

    jwt: JWTSettings = JWTSettings()


def get_jwt_decoder(secrets: TestSecrets) -> JWTDecoder:
    algos: list[str] = secrets.jwt.algorithms
    return JWTDecoder(secrets.jwt.secret, algos)


def secret_provider() -> TestSecrets:
    return TestSecrets()


class LoginResponse(Struct):
    user_id: str


class ExtendedClaims(Struct):
    user_id: str
    tenant_id: str
    scopes: list[str]
    tier: str | None = None


class TenantContext(Struct):
    tenant_id: str
    region: str
    locale: str


class UserPreferences(Struct):
    tenant_id: str
    theme: str
    region: str
    locale: str
    variant: str | None = None


class DashboardSummary(Struct):
    user_id: str
    tenant_id: str
    locale: str
    region: str
    theme: str
    view: str
    request_id: str
    tier: str | None = None
    variant: str | None = None


class AuditPayload(Struct):
    action: str
    severity: int
    description: str
    metadata: dict[str, str] | None = None


class AuditContext(Struct):
    user_id: str
    tenant_id: str
    action: str
    severity: int
    trace_token: str
    locale: str
    region: str
    view_id: str
    reviewer: str | None = None


class AuditResponse(Struct):
    user_id: str
    action: str
    severity: int
    tenant_id: str
    trace_token: str
    view: str
    locale: str
    region: str
    reviewer: str | None = None


async def get_user_id(
    auth_header: Annotated[bytes, JWTAuthParam],
    decoder: Annotated[JWTDecoder, use(get_jwt_decoder, reuse=True)],
) -> Ignore[str]:
    decoded = decoder.decode(auth_header, LoginResponse)
    return decoded.user_id


async def get_age(age: int, path_int: Annotated[int, Param("path")]) -> Ignore[int]:
    return age + path_int


async def get_claims(
    auth_header: Annotated[bytes, Param("header", alias="Authorization")],
    decoder: Annotated[JWTDecoder, use(get_jwt_decoder, reuse=True)],
) -> Ignore[ExtendedClaims]:
    return decoder.decode(auth_header, ExtendedClaims)


async def get_tenant_context(
    claims: Annotated[ExtendedClaims, use(get_claims, reuse=True)],
    tenant_hint: Annotated[str, Param("path")],
    region: Annotated[str, Param("header", alias="X-Region")],
    locale: Annotated[str, Param("query", alias="locale")],
    tenant_override: Annotated[str | None, Param("query", alias="tenant")] = None,
) -> Ignore[TenantContext]:
    tenant_id = tenant_override or claims.tenant_id or tenant_hint
    return TenantContext(tenant_id=tenant_id, region=region, locale=locale)


async def get_preferences(
    tenant_ctx: Annotated[TenantContext, use(get_tenant_context)],
    theme: Annotated[str, Param("cookie", alias="theme")],
    variant: Annotated[str | None, Param("query", alias="variant")] = None,
) -> Ignore[UserPreferences]:
    return UserPreferences(
        tenant_id=tenant_ctx.tenant_id,
        theme=theme,
        region=tenant_ctx.region,
        locale=tenant_ctx.locale,
        variant=variant,
    )


async def parse_audit_payload(
    payload: Annotated[AuditPayload, Param("body")]
) -> Ignore[AuditPayload]:
    return payload


async def build_audit_context(
    claims: Annotated[ExtendedClaims, use(get_claims, reuse=True)],
    prefs: Annotated[UserPreferences, use(get_preferences)],
    payload: Annotated[AuditPayload, use(parse_audit_payload)],
    trace_token: Annotated[str, Param("cookie", alias="trace")],
    view_id: Annotated[str, Param("path", alias="view_id")],
    reviewer: Annotated[str | None, Param("query", alias="reviewer")] = None,
) -> Ignore[AuditContext]:
    return AuditContext(
        user_id=claims.user_id,
        tenant_id=prefs.tenant_id,
        action=payload.action,
        severity=payload.severity,
        trace_token=trace_token,
        reviewer=reviewer,
        locale=prefs.locale,
        region=prefs.region,
        view_id=view_id,
    )


async def get_dashboard_summary(
    claims: Annotated[ExtendedClaims, use(get_claims, reuse=True)],
    preferences: Annotated[UserPreferences, use(get_preferences)],
    request_id: Annotated[str, Param("header", alias="X-Request-Id")],
    view_name: Annotated[str, Param("query", alias="view")],
) -> DashboardSummary:
    return DashboardSummary(
        user_id=claims.user_id,
        tenant_id=preferences.tenant_id,
        locale=preferences.locale,
        region=preferences.region,
        theme=preferences.theme,
        view=view_name,
        tier=claims.tier,
        variant=preferences.variant,
        request_id=request_id,
    )


async def log_audit_event(
    audit_context: Annotated[AuditContext, use(build_audit_context)],
    view_name: Annotated[str, Param("query", alias="view")],
) -> AuditResponse:
    return AuditResponse(
        user_id=audit_context.user_id,
        action=audit_context.action,
        severity=audit_context.severity,
        tenant_id=audit_context.tenant_id,
        trace_token=audit_context.trace_token,
        reviewer=audit_context.reviewer,
        view=view_name,
        locale=audit_context.locale,
        region=audit_context.region,
    )


FAKE_USER_DB = {
    "user123": {"user_id": "user123", "name": "Alice"},
}


class User(Struct):
    name: str
    age: int


async def get_me(
    user_id: Annotated[str, use(get_user_id)], age: Annotated[int, use(get_age)]
) -> User:
    return User(name=FAKE_USER_DB[user_id]["name"], age=age)


async def test_jwt_auth_param():
    lc = LocalClient()
    ep = await lc.make_endpoint(get_me, path="/me/{path_int}")

    resp = await lc.call_endpoint(
        ep,
        headers={
            "Authorization": "Bearer "
            + PyJWT().encode({"user_id": "user123"}, "my secret", algorithm="HS256")
        },
        query_params={"age": "30"},
        path_params={"path_int": "5"},
    )
    assert await resp.json() == {"name": "Alice", "age": 35}


async def test_nested_dependency_chain_with_multiple_param_sources():
    lc = LocalClient()
    ep = await lc.make_endpoint(
        get_dashboard_summary, path="/tenants/{tenant_hint}/dashboards/{view_id}"
    )

    token_payload = {
        "user_id": "user123",
        "tenant_id": "tenant-token",
        "scopes": ["dash:read"],
        "tier": "gold",
    }
    token = PyJWT().encode(token_payload, "my secret", algorithm="HS256")

    resp = await lc.call_endpoint(
        ep,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Region": "us-east-1",
            "X-Request-Id": "req-xyz",
            "cookie": "theme=contrast; trace=trace-999",
        },
        query_params={
            "age": "30",
            "locale": "en-US",
            "tenant": "tenant-query",
            "variant": "beta",
            "view": "summary",
        },
        path_params={"tenant_hint": "tenant-path", "view_id": "main"},
    )

    assert await resp.json() == {
        "user_id": "user123",
        "tenant_id": "tenant-query",
        "locale": "en-US",
        "region": "us-east-1",
        "theme": "contrast",
        "view": "summary",
        "tier": "gold",
        "variant": "beta",
        "request_id": "req-xyz",
    }


async def test_dependency_chain_combines_body_and_cookie_params():
    lc = LocalClient()
    ep = await lc.make_endpoint(
        log_audit_event, path="/tenants/{tenant_hint}/dashboards/{view_id}"
    )

    token_payload = {
        "user_id": "user999",
        "tenant_id": "tenant-token",
        "scopes": ["audit:write"],
        "tier": "silver",
    }
    token = PyJWT().encode(token_payload, "my secret", algorithm="HS256")

    resp = await lc.call_endpoint(
        ep,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Region": "eu-central-1",
            "cookie": "theme=light; trace=trace-123",
        },
        query_params={
            "locale": "fr-FR",
            "tenant": "tenant-audit",
            "variant": "stable",
            "view": "audit",
            "reviewer": "moderator",
        },
        path_params={"tenant_hint": "tenant-fallback", "view_id": "detail"},
        body={
            "action": "login",
            "severity": 3,
            "description": "User logged in from dashboard",
        },
    )

    assert await resp.json() == {
        "user_id": "user999",
        "action": "login",
        "severity": 3,
        "tenant_id": "tenant-audit",
        "trace_token": "trace-123",
        "reviewer": "moderator",
        "view": "audit",
        "locale": "fr-FR",
        "region": "eu-central-1",
    }
