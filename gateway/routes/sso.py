from __future__ import annotations

import secrets
import time

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import settings
from core.logging_config import logger

_sso_instance = None
_sso_error = None


def get_sso_service():
    # বাংলা মন্তব্য: মেমরি ওভারহেড কমাতে SSOIntegrator অলসভাবে (lazy) লোড করা হচ্ছে।
    global _sso_instance, _sso_error
    if _sso_instance is None and _sso_error is None:
        try:
            from tools.sso_integrator import SSOIntegrator

            _sso_instance = SSOIntegrator()
        except Exception as exc:
            logger.warning(f"SSOIntegrator unavailable; SSO features disabled: {exc}")
            _sso_error = exc
    return _sso_instance


router = APIRouter(prefix="/auth/sso", tags=["sso"])
_oidc_state_store: dict[str, float] = {}
_oidc_state_ttl_seconds = 600  # 10 minutes TTL for OIDC state
_last_oidc_cleanup = 0.0
_oidc_cleanup_interval = 300.0  # Cleanup every 5 minutes
_oidc_state_max_size = 10000  # Maximum number of states to prevent unbounded growth
_oidc_state_store: dict[str, float] = {}
_oidc_state_ttl_seconds = 600  # 10 minutes TTL for OIDC state
_last_oidc_cleanup = 0.0
_oidc_cleanup_interval = 300.0  # Cleanup every 5 minutes


def _cleanup_expired_oidc_states():
    """Clean up expired OIDC state entries to prevent memory leak.

    বাংলা মন্তব্য: OIDC state store-এ পুরনো entry মুছে দেওয়া হচ্ছে
    যাতে memory leak না হয়। প্রতি ৫ মিনিটে একবার cleanup হয়।
    """
    import time

    global _last_oidc_cleanup

    now = time.time()
    if now - _last_oidc_cleanup < _oidc_cleanup_interval:
        return

    _last_oidc_cleanup = now
    expired_keys = [
        key
        for key, timestamp in _oidc_state_store.items()
        if now - timestamp > _oidc_state_ttl_seconds
    ]
    for key in expired_keys:
        del _oidc_state_store[key]
    if expired_keys:
        logger.debug(f"Cleaned up {len(expired_keys)} expired OIDC state entries")

    # বাংলা মন্তব্য: যদি store-এর আকার সীমার বাইরে হয়, তাহলে পুরনো entry মুছে দাও
    if len(_oidc_state_store) > _oidc_state_max_size:
        # সবচেয়ে পুরনো entry মুছে দাও (FIFO-style)
        sorted_states = sorted(_oidc_state_store.items(), key=lambda x: x[1])
        keys_to_remove = [
            k for k, _ in sorted_states[: len(_oidc_state_store) - _oidc_state_max_size]
        ]
        for key in keys_to_remove:
            del _oidc_state_store[key]
        logger.warning(
            f"OIDC state store exceeded max size. Removed {len(keys_to_remove)} oldest entries."
        )


class SAMLAssertionRequest(BaseModel):
    assertion: str


class OIDCDiscoveryRequest(BaseModel):
    issuer: str
    redirect_uri: str
    client_id: str
    scope: str = "openid profile email"


class OIDCLoginResponse(BaseModel):
    authorization_url: str
    state: str


class SSOLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    roles: list[str]
    email: str
    method: str


class OIDCCallbackRequest(BaseModel):
    code: str
    state: str
    provider: str = "generic"


class ProviderSSORequest(BaseModel):
    client_id: str | None = None
    redirect_uri: str | None = None
    state: str | None = None
    scope: str = "openid profile email"


@router.post("/oidc/discovery", response_model=OIDCLoginResponse)
async def oidc_discovery(payload: OIDCDiscoveryRequest):
    _cleanup_expired_oidc_states()
    state = secrets.token_urlsafe(16)
    _oidc_state_store[state] = time.time()
    auth_url = (
        f"{payload.issuer}/authorize"
        f"?response_type=code"
        f"&client_id={payload.client_id}"
        f"&redirect_uri={payload.redirect_uri}"
        f"&scope={payload.scope}"
        f"&state={state}"
    )
    return OIDCLoginResponse(authorization_url=auth_url, state=state)


@router.post("/oidc/{provider}/authorize", response_model=OIDCLoginResponse)
async def oidc_provider_authorize(provider: str, payload: ProviderSSORequest):
    _cleanup_expired_oidc_states()
    sso_service = get_sso_service()
    if sso_service is None:
        raise HTTPException(status_code=503, detail="SSO service is unavailable")
    client_id = payload.client_id or getattr(settings, "oidc_client_id", "")
    redirect_uri = payload.redirect_uri or getattr(settings, "oidc_redirect_uri", "")
    state = payload.state or secrets.token_urlsafe(16)
    _oidc_state_store[state] = time.time()
    try:
        auth_url = sso_service.get_oidc_auth_url(
            provider=provider,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            scope=payload.scope,
        )
        return OIDCLoginResponse(authorization_url=auth_url, state=state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/oidc/{provider}/callback", response_model=SSOLoginResponse)
async def oidc_provider_callback(provider: str, payload: OIDCCallbackRequest):
    sso_service = get_sso_service()
    if sso_service is None:
        raise HTTPException(status_code=503, detail="SSO service is unavailable")
    getattr(settings, "oidc_client_id", "")
    getattr(settings, "oidc_client_secret", "")
    getattr(settings, "oidc_redirect_uri", "")
    if not payload.state or payload.state not in _oidc_state_store:
        raise HTTPException(status_code=400, detail="Invalid or expired OIDC state parameter")
    _oidc_state_store.pop(payload.state, None)
    result = await sso_service.process_oidc_response(
        provider=provider,
        code=payload.code,
        state=payload.state,
    )
    if result.get("status") != "success":
        raise HTTPException(
            status_code=401, detail=result.get("message", "OIDC authentication failed")
        )
    primary_role = (result.get("roles") or ["viewer"])[0]
    token_data = {
        "sub": result.get("user_id", "unknown"),
        "role": primary_role,
        "email": result.get("email", ""),
        "method": result.get("method", f"oidc:{provider}"),
    }
    if jwt is None:
        raise HTTPException(status_code=503, detail="JWT library is unavailable")
    access_token = jwt.encode(token_data, settings.jwt_secret, algorithm="HS256")
    return SSOLoginResponse(
        access_token=access_token,
        user_id=token_data["sub"],
        roles=result.get("roles", []),
        email=token_data["email"],
        method=token_data["method"],
    )


@router.get("/oidc/{provider}/logout")
async def oidc_logout(provider: str):
    sso_service = get_sso_service()
    if sso_service is None:
        raise HTTPException(status_code=503, detail="SSO service is unavailable")
    logout_url = ""
    try:
        cfg = sso_service.OIDC_PROVIDERS.get(provider.lower(), {})
        base = cfg.get("end_session_endpoint", "").format(
            domain=getattr(settings, "oidc_domain", ""),
            tenant=getattr(settings, "oidc_tenant", ""),
        )
        logout_url = base or ""
    except Exception as exc:
        # বল মনতবয: logout URL তরত বযরথ হল খল string ফরত যত; নরব সযলপর বদল
        # ডবগ লগ যকত কর হল যত OIDC কনফগ সমসয বঝ যয়
        logger.debug(f"Failed to build OIDC logout URL for provider {provider}: {exc}")
    return {"logout_url": logout_url, "provider": provider}


@router.post("/saml", response_model=SSOLoginResponse)
async def saml_login(payload: SAMLAssertionRequest):
    sso_service = get_sso_service()
    if sso_service is None:
        raise HTTPException(status_code=503, detail="SSO service is unavailable")
    result = await sso_service.process_sso_response({"SAMLResponse": payload.assertion})
    if result.get("status") != "success":
        raise HTTPException(
            status_code=401, detail=result.get("message", "SAML authentication failed")
        )
    roles = result.get("roles", ["viewer"])
    primary_role = roles[0] if roles else "viewer"
    token_data = {
        "sub": result.get("user_id", "unknown"),
        "role": primary_role,
        "email": result.get("email", ""),
        "method": result.get("method", "saml"),
    }
    if jwt is None:
        raise HTTPException(status_code=503, detail="JWT library is unavailable")
    access_token = jwt.encode(token_data, settings.jwt_secret, algorithm="HS256")
    return SSOLoginResponse(
        access_token=access_token,
        user_id=token_data["sub"],
        roles=roles,
        email=token_data["email"],
        method=token_data["method"],
    )


@router.get("/metadata")
async def sso_metadata():
    sso_service = get_sso_service()
    if sso_service is None:
        raise HTTPException(status_code=503, detail="SSO service is unavailable")
    metadata = sso_service.get_metadata()
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=metadata.get("body", ""),
        media_type=metadata.get("content_type", "application/xml"),
    )
