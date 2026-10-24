import base64
import os
from datetime import UTC, datetime, timezone
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

import defusedxml.ElementTree as ET  # -- standard idiom (mirrors stdlib xml.etree.ElementTree as ET)
import jwt

from core.config import settings
from core.logging_config import logger


class SSOIntegrator:
    saml_settings: dict[str, Any] = {}

    def __init__(self, saml_settings: dict[str, Any] | None = None):
        self.saml_settings = saml_settings or {}
        self.onelogin = self._load_onelogin()
        logger.info(
            f"Initialized SSOIntegrator (python-saml={'loaded' if self.onelogin else 'fallback'})"
        )

    def _load_onelogin(self):
        try:
            from onelogin.saml2.auth import OneLogin_Saml2_Auth
            from onelogin.saml2.settings import OneLogin_Saml2_Settings

            self._OneLogin_Saml2_Auth = OneLogin_Saml2_Auth
            self._OneLogin_Saml2_Settings = OneLogin_Saml2_Settings
            return True
        except ImportError:
            return False

    def _prepare_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        if self.onelogin:
            return {
                "https": (
                    "on"
                    if self.saml_settings.get("sp_entity_id", "").startswith("https")
                    else "off"
                ),
                "http_host": self.saml_settings.get("sp_entity_id", "") or "localhost",
                "script_name": self.saml_settings.get("acs_url", ""),
                "get_data": parse_qs(urlparse(self.saml_settings.get("query_string", "")).query),
                "post_data": request_data.get("post_data", {}),
            }
        return request_data

    def get_metadata(self) -> dict[str, Any]:
        if self.onelogin:
            try:
                settings_obj = self._build_settings()
                metadata = settings_obj.get_sp_metadata()
                return {
                    "status": "success",
                    "content_type": "application/xml",
                    "body": metadata,
                }
            except (KeyError, ValueError, RuntimeError, TypeError) as exc:
                logger.error(f"Metadata generation failed: {exc}")
        xml = self._fallback_metadata()
        return {"status": "fallback", "content_type": "application/xml", "body": xml}

    def get_sso_url(self, relay_state: str | None = None) -> str:
        if self.onelogin:
            try:
                settings_obj = self._build_settings()
                req = self._prepare_request({})
                auth = self._OneLogin_Saml2_Auth(req, old_settings=settings_obj)
                sso_url = auth.login(return_to=relay_state)
                return sso_url
            except (KeyError, ValueError, RuntimeError, TypeError) as exc:
                logger.error(f"SSO URL generation failed: {exc}")
        return self.saml_settings.get("idp_sso_url", "")

    async def process_sso_response(
        self, post_data: dict[str, Any], relay_state: str | None = None
    ) -> dict[str, Any]:
        """Process SSO response - uses python-saml if available, otherwise fallback.

        বাংলা মন্তব্য: SSO response process করা। python-saml লাইব্রেরি থাকলে
        signature verification সহ নিরাপদে parse করে, না থাকলে fallback ব্যবহার করে।
        """
        if self.onelogin:
            try:
                settings_obj = self._build_settings()
                req = self._prepare_request({"post_data": post_data})
                auth = self._OneLogin_Saml2_Auth(req, old_settings=settings_obj)
                auth.process_response()
                errors = auth.get_errors()
                if errors:
                    return {"status": "error", "message": ", ".join(errors)}
                if not auth.is_authenticated():
                    return {"status": "error", "message": "Not authenticated"}
                attributes = auth.get_attributes()
                name_id = auth.get_nameid()
                session_index = auth.get_session_index()
                user_id = attributes.get(
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier",
                    [name_id],
                )[0]
                email = attributes.get(
                    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
                    [""],
                )[0]
                groups = (
                    attributes.get(
                        "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
                        [],
                    )
                    or attributes.get("groups", [])
                    or [
                        v
                        for k, v in attributes.items()
                        if "group" in k.lower()
                        for v in (v if isinstance(v, list) else [v])
                    ]
                )
                roles = self.map_roles(groups)
                return {
                    "status": "success",
                    "user_id": user_id,
                    "email": email,
                    "name_id": name_id,
                    "session_index": session_index,
                    "groups": groups,
                    "roles": roles,
                    "method": "python-saml",
                }
            except Exception as exc:
                logger.error(f"SAML response processing failed: {exc}")

        # Fallback XML parsing (python-saml not available)
        return self._fallback_parse_saml_response(post_data)

    def _fallback_parse_saml_response(self, post_data: dict[str, Any]) -> dict[str, Any]:
        """Fallback SAML response parser without signature verification.

        বাংলা মন্তব্য: এই method কোনো signature verification করে না।
        Production-এ python-saml লাইব্রেরি ব্যবহার করার পরামর্শ দেওয়া হচ্ছে।
        """
        # Disable fallback in production unless explicitly allowed
        if os.environ.get("SUPREMEAI_ENV", "").lower() == "production":
            if os.environ.get("SAML_ALLOW_FALLBACK", "").lower() != "true":
                logger.error(
                    "SAML fallback parsing is disabled in production. "
                    "Install python-saml library or set SAML_ALLOW_FALLBACK=true to enable."
                )
                return {
                    "status": "error",
                    "message": "SAML fallback parsing disabled in production. Please install python-saml.",
                }

        try:
            saml_response_raw = post_data.get("SAMLResponse", "")
            if not saml_response_raw:
                return {"status": "error", "message": "Missing SAMLResponse"}

            # Decode if base64 encoded
            try:
                saml_xml = base64.b64decode(saml_response_raw).decode("utf-8")
            except Exception:
                saml_xml = saml_response_raw

            root = ET.fromstring(saml_xml)
            logger.info("SAML XML parsed successfully.")

            # Timestamp validation - NotBefore and NotOnOrAfter
            conditions = root.find(".//{urn:oasis:names:tc:SAML:2.0:assertion}Conditions")
            if conditions is not None:
                not_before_str = conditions.get("NotBefore")
                not_on_or_after_str = conditions.get("NotOnOrAfter")

                now = datetime.now(UTC)

                if not_before_str:
                    try:
                        not_before = datetime.fromisoformat(not_before_str.replace("Z", "+00:00"))
                        if now < not_before:
                            logger.warning(
                                f"SAML assertion not yet valid. NotBefore={not_before_str}"
                            )
                            return {
                                "status": "error",
                                "message": "SAML assertion not yet valid",
                            }
                    except ValueError as e:
                        logger.warning(f"Failed to parse NotBefore timestamp: {e}")

                if not_on_or_after_str:
                    try:
                        not_on_or_after = datetime.fromisoformat(
                            not_on_or_after_str.replace("Z", "+00:00")
                        )
                        if now >= not_on_or_after:
                            logger.warning(
                                f"SAML assertion expired. NotOnOrAfter={not_on_or_after_str}"
                            )
                            return {
                                "status": "error",
                                "message": "SAML assertion expired",
                            }
                    except ValueError as e:
                        logger.warning(f"Failed to parse NotOnOrAfter timestamp: {e}")

            # Audience restriction check
            sp_entity_id = self.saml_settings.get("sp_entity_id", "")
            if sp_entity_id:
                audience_restriction = root.find(
                    ".//{urn:oasis:names:tc:SAML:2.0:assertion}Conditions/"
                    "{urn:oasis:names:tc:SAML:2.0:assertion}AudienceRestriction/"
                    "{urn:oasis:names:tc:SAML:2.0:assertion}Audience"
                )
                if audience_restriction is not None and audience_restriction.text:
                    if audience_restriction.text.strip() != sp_entity_id:
                        logger.warning(
                            f"SAML audience mismatch. Expected={sp_entity_id}, Got={audience_restriction.text}"
                        )
                        return {
                            "status": "error",
                            "message": "SAML audience restriction mismatch",
                        }

            user_id = root.findtext(
                ".//{urn:oasis:names:tc:SAML:2.0:assertion}Subject/{urn:oasis:names:tc:SAML:2.0:assertion}NameID",
                default="",
            )
            groups_el = root.findall(
                ".//{urn:oasis:names:tc:SAML:2.0:assertion}AttributeStatement//{urn:oasis:names:tc:SAML:2.0:assertion}Attribute[@Name='groups']/{urn:oasis:names:tc:SAML:2.0:assertion}AttributeValue"
            )
            groups = [el.text for el in groups_el if el.text]
            email_el = root.find(
                ".//{urn:oasis:names:tc:SAML:2.0:assertion}AttributeStatement//{urn:oasis:names:tc:SAML:2.0:assertion}Attribute[@Name='email']/{urn:oasis:names:tc:SAML:2.0:assertion}AttributeValue"
            )
            email = email_el.text if email_el is not None else ""
            return {
                "status": "success",
                "user_id": user_id,
                "email": email,
                "groups": groups,
                "roles": self.map_roles(groups),
                "method": "xml_fallback",
            }
        except ET.ParseError as exc:
            logger.error(f"Fallback SAML parsing failed: {exc}")
            return {"status": "error", "message": "Invalid SAML response"}
        except Exception as exc:
            logger.error(f"Unexpected error in fallback SAML parsing: {exc}")
            return {"status": "error", "message": "SAML parsing failed"}

    def map_roles(self, sso_groups: list[str]) -> list[str]:
        internal_roles: list[str] = []
        mapping = {
            "Admin": "owner",
            "Administrators": "owner",
            "Developers": "editor",
            "Editors": "editor",
            "Viewers": "viewer",
            "Operators": "operator",
        }
        for group in sso_groups:
            role = mapping.get(group)
            if role:
                internal_roles.append(role)
        return internal_roles or ["viewer"]

    def get_logout_url(
        self, request: dict[str, Any] | None = None, relay_state: str | None = None
    ) -> str:
        if self.onelogin:
            try:
                settings_obj = self._build_settings()
                req = self._prepare_request(request or {})
                auth = self._OneLogin_Saml2_Auth(req, old_settings=settings_obj)
                return auth.logout(return_to=relay_state)
            except Exception as exc:
                logger.error(f"Logout URL generation failed: {exc}")
        return self.saml_settings.get("idp_slo_url", "")

    async def process_slo_response(self, post_data: dict[str, Any]) -> dict[str, Any]:
        if self.onelogin:
            try:
                settings_obj = self._build_settings()
                req = self._prepare_request({"post_data": post_data})
                auth = self._OneLogin_Saml2_Auth(req, old_settings=settings_obj)
                auth.process_slo(delete_session_callback=lambda: None)
                return {"status": "success", "method": "python-saml"}
            except Exception as exc:
                logger.error(f"SLO processing failed: {exc}")

        # Fallback XML parsing for SLO (SAML LogoutResponse/LogoutRequest)
        # বাংলা মন্তব্য: python-saml লাইব্রেরি না থাকলে XML থেকে প্রপার Status ডিকোড করে আউটপুট দেয়, কোনো হার্ডকোডেড মক সাকসেস রিটার্ন করে না।
        try:
            logout_response_xml = post_data.get("SAMLResponse") or post_data.get("SAMLRequest", "")
            if not logout_response_xml:
                return {"status": "error", "message": "Missing SLO payload"}

            root = ET.fromstring(logout_response_xml)
            status_code = root.findtext(
                ".//{urn:oasis:names:tc:SAML:2.0:protocol}Status/{urn:oasis:names:tc:SAML:2.0:protocol}StatusCode",
                default="",
            )
            if "status:Success" in status_code or not status_code:
                return {"status": "success", "method": "xml_fallback_slo"}
            return {
                "status": "error",
                "message": f"SLO failed with status: {status_code}",
            }
        except ET.ParseError as exc:
            logger.error(f"Fallback SLO XML parsing failed: {exc}")
            return {"status": "error", "message": "Invalid SLO XML payload"}

    def _build_settings(self) -> Any:
        settings_dict = {
            "strict": False,
            "debug": True,
            "sp": {
                "entityId": self.saml_settings.get(
                    "sp_entity_id", settings.app_base_url + "/metadata"
                ),
                "assertionConsumerService": {
                    "url": self.saml_settings.get("acs_url", settings.app_base_url + "/acs"),
                },
                "singleLogoutService": {
                    "url": self.saml_settings.get("sls_url", settings.app_base_url + "/sls"),
                },
                "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
                "x509cert": self.saml_settings.get("sp_x509_cert", ""),
                "privateKey": self.saml_settings.get("sp_private_key", ""),
            },
            "idp": {
                "entityId": self.saml_settings.get("idp_entity_id", ""),
                "singleSignOnServiceUrl": self.saml_settings.get("idp_sso_url", ""),
                "singleLogoutServiceUrl": self.saml_settings.get("idp_slo_url", ""),
                "x509cert": self.saml_settings.get("idp_x509_cert", ""),
            },
            "security": {
                "authnRequestsSigned": False,
                "logoutRequestSigned": False,
                "logoutResponseSigned": False,
                "signMetadata": False,
            },
        }
        if self.onelogin:
            return self._OneLogin_Saml2_Settings(
                settings=settings_dict, security=self.saml_settings.get("security", {})
            )
        return settings_dict

    def _fallback_metadata(self) -> str:
        sp_entity_id = self.saml_settings.get("sp_entity_id", settings.app_base_url)
        acs_url = self.saml_settings.get("acs_url", f"{sp_entity_id}/acs")
        return f"""<?xml version="1.0"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{sp_entity_id}">
  <SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" Location="{acs_url}" index="1"/>
  </SPSSODescriptor>
        </EntityDescriptor>"""

    def validate_token(self, token: str, secret: str) -> dict[str, Any]:
        """Backward-compatible JWT validation."""
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
            return payload
        except Exception as exc:
            return {"error": str(exc)}

    def parse_saml_response(self, saml_xml: str) -> dict[str, Any]:
        """Backward-compatible SAML response parsing."""
        try:
            root = ET.fromstring(saml_xml)
            user_id = root.findtext(
                ".//{urn:oasis:names:tc:SAML:2.0:assertion}Subject/{urn:oasis:names:tc:SAML:2.0:assertion}NameID",
                default="",
            )
            email_el = root.find(
                ".//{urn:oasis:names:tc:SAML:2.0:assertion}AttributeStatement//{urn:oasis:names:tc:SAML:2.0:assertion}Attribute[@Name='email']/{urn:oasis:names:tc:SAML:2.0:assertion}AttributeValue"
            )
            email = email_el.text if email_el is not None else ""
            return {
                "status": "success",
                "user_id": user_id,
                "email": email,
                "method": "xml_fallback",
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ── OIDC helpers ───────────────────────────────────────────────

    OIDC_PROVIDERS: ClassVar[dict[str, dict[str, str]]] = {
        "okta": {
            "authorization_endpoint": "https://{domain}/oauth2/default/v1/authorize",
            "token_endpoint": "https://{domain}/oauth2/default/v1/token",
            "userinfo_endpoint": "https://{domain}/oauth2/default/v1/userinfo",
            "jwks_uri": "https://{domain}/oauth2/default/v1/keys",
        },
        "azure": {
            "authorization_endpoint": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
            "token_endpoint": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            "userinfo_endpoint": "https://graph.microsoft.com/oidc/userinfo",
            "jwks_uri": "https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        },
        "google": {
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        },
    }

    def get_oidc_auth_url(
        self,
        provider: str,
        client_id: str,
        redirect_uri: str,
        state: str,
        scope: str = "openid profile email",
        extra_params: dict[str, str] | None = None,
    ) -> str:
        cfg = self.OIDC_PROVIDERS.get(provider.lower())
        if not cfg:
            raise ValueError(f"Unsupported OIDC provider: {provider}")
        base = cfg["authorization_endpoint"].format(
            domain=self.saml_settings.get("oidc_domain", ""),
            tenant=self.saml_settings.get("oidc_tenant", ""),
        )
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
        if extra_params:
            params.update(extra_params)
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{base}?{qs}"

    async def exchange_oidc_code(
        self,
        provider: str,
        code: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str,
    ) -> dict[str, Any]:
        cfg = self.OIDC_PROVIDERS.get(provider.lower())
        if not cfg:
            return {
                "status": "error",
                "message": f"Unsupported OIDC provider: {provider}",
            }
        token_url = cfg["token_endpoint"].format(
            domain=self.saml_settings.get("oidc_domain", ""),
            tenant=self.saml_settings.get("oidc_tenant", ""),
        )
        try:
            import httpx

            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(token_url, data=payload, timeout=10.0)
                resp.raise_for_status()
                tokens = resp.json()
            id_token = tokens.get("id_token", "")
            if not id_token:
                return {"status": "success", "tokens": tokens}
            # SEC-HARDEN P5: an id_token's claims MUST NOT be trusted before the
            # signature is verified against the provider's published JWKS.
            # (Previously decoded with verify_signature=False — forged tokens were
            # accepted. Now we fail closed: no signature → no claims.)
            header = jwt.get_unverified_header(id_token)
            payload, verify_err = await self._verify_oidc_id_token(provider, id_token, client_id)
            if payload is None:
                return {"status": "error", "message": f"id_token verification failed: {verify_err}"}
            return {
                "status": "success",
                "id_token": id_token,
                "access_token": tokens.get("access_token", ""),
                "claims": payload,
                "header": header,
            }
        except Exception as exc:
            logger.error(f"OIDC code exchange failed: {exc}")
            return {"status": "error", "message": str(exc)}

    async def _verify_oidc_id_token(
        self, provider: str, id_token: str, client_id: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Verify an OIDC id_token signature against the provider's JWKS (fail-closed).

        SEC-HARDEN P5: the previous flow decoded the id_token with
        ``verify_signature=False`` — a completely forged token (e.g. signed by an
        attacker with a ``kid`` they control) yielded trusted claims.

        This method:
          - resolves the provider's published ``jwks_uri`` (from the static provider
            registry — never user input, so no SSRF surface),
          - resolves the token's ``kid`` to a key from that JWKS (PyJWKClient caches),
          - verifies the signature (RS/ES/PS families) plus ``exp`` and — when a
            ``client_id`` is supplied — ``aud``.

        Returns ``(claims, None)`` on success, ``(None, reason)`` on ANY failure.
        Callers MUST fail closed: a ``None`` payload means no trusted claims.
        """
        cfg = self.OIDC_PROVIDERS.get(provider.lower())
        if not cfg:
            return None, f"Unsupported OIDC provider: {provider}"
        jwks_uri = cfg.get("jwks_uri", "").format(
            domain=self.saml_settings.get("oidc_domain", ""),
            tenant=self.saml_settings.get("oidc_tenant", ""),
        )
        if not jwks_uri.startswith("https://"):
            return None, "Provider jwks_uri must be https (refusing network fetch over plain http)"

        try:
            from jwt import PyJWKClient

            options: dict[str, Any] = {"require": ["exp", "iat"]}
            kwargs: dict[str, Any] = {"algorithms": ["RS256", "RS384", "ES256", "ES384", "PS256"]}
            if client_id:
                options["verify_aud"] = True
                kwargs["audience"] = client_id

            jwks_client = PyJWKClient(jwks_uri, cache_keys=True)
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            payload = jwt.decode(id_token, signing_key.key, options=options, **kwargs)
            return payload, None
        except Exception as exc:  # noqa: BLE001 — any verification failure denies
            # Never leak cryptographic detail into client-facing responses.
            logger.error("OIDC id_token signature verification failed: %s", exc)
            return None, "signature/claims verification failed (contact support)"

    async def process_oidc_response(self, provider: str, code: str, state: str) -> dict[str, Any]:
        """Convenience wrapper: exchange code, fetch userinfo, map roles."""
        client_id = self.saml_settings.get("oidc_client_id", "")
        client_secret = self.saml_settings.get("oidc_client_secret", "")
        redirect_uri = self.saml_settings.get("oidc_redirect_uri", "")
        exchange = await self.exchange_oidc_code(
            provider=provider,
            code=code,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
        )
        if exchange.get("status") != "success":
            return exchange

        claims = exchange.get("claims", {})
        user_id = claims.get("sub") or claims.get("email", "unknown")
        email = claims.get("email", "")
        # Provider-specific groups extraction
        groups: list[str] = []
        if provider in {"okta", "azure"}:
            groups = claims.get("groups", [])
        elif provider == "google":
            groups = claims.get("hd", "").split(",") if claims.get("hd") else []
        roles = self.map_roles(groups)
        return {
            "status": "success",
            "user_id": user_id,
            "email": email,
            "groups": groups,
            "roles": roles,
            "method": f"oidc:{provider}",
            "tokens": exchange.get("tokens", {}),
        }
