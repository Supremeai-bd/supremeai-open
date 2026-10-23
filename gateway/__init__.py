"""SupremeAI Gateway — unified provider gateway (issue #336).

``import gateway.main`` is the issue's boot-smoke entry point. Public surface:

    from gateway.main import create_app
    from gateway.config import load_config, parse_routing_policy
"""

from .config import (
    ALLOWED_PROVIDERS,
    ALLOWED_SCOPES,
    ConfigError,
    Endpoint,
    GatewayConfig,
    load_config,
    parse_routing_policy,
)
from .main import GATEWAY_VERSION, create_app, error_response
from .sanitization import *  # noqa: F401,F403
from .provider_chain import AttemptResult, ProviderChainExhausted, execute_chain
from .rate_limit import RateDecision, SlidingWindowLimiter

__version__ = GATEWAY_VERSION

__all__ = [
    "ALLOWED_PROVIDERS",
    "ALLOWED_SCOPES",
    "GATEWAY_VERSION",
    "AttemptResult",
    "ConfigError",
    "Endpoint",
    "GatewayConfig",
    "ProviderChainExhausted",
    "RateDecision",
    "SlidingWindowLimiter",
    "__version__",
    "create_app",
    "error_response",
    "execute_chain",
    "load_config",
    "parse_routing_policy",
]
