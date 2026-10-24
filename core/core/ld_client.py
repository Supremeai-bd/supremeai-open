"""This module centralizes the initialization and management of the LaunchDarkly AI client for the SupremeAI backend. It provides dynamic feature flagging, experimentation, and observability capabilities for AI-driven features, ensuring flexible control and monitoring of AI models and components. The module gracefully handles missing SDK dependencies and environment configurations, providing a robust integration point for LaunchDarkly services within the highly scalable AI ecosystem.

Key Components:
- `init_ld_client()`: Initializes the LaunchDarkly AI client, configuring it with an SDK key and integrating observability plugins for telemetry.
- `ld_ai_client`: The globally accessible instance of the initialized `LDAIClient`, or `None` if initialization fails due to missing keys or SDKs.
- `get_ld_ai_components()`: Retrieves the initialized LaunchDarkly AI client along with essential AI-related configuration and context classes, returning `None` for unavailable components.

Dependencies:
- `os`: For accessing environment variables such as `LAUNCHDARKLY_SDK_KEY`, `SERVICE_NAME`, and `SERVICE_VERSION`.
- `loguru`: For robust and structured logging of client initialization status, warnings, and errors.
- `ldclient`: The core LaunchDarkly Python SDK, used for general feature flagging and configuration management.
- `ldai`: The LaunchDarkly AI SDK, providing specific functionalities for AI model management, experimentation, and completion configurations.
- `ldobserve`: The LaunchDarkly Observability SDK, used for integrating telemetry and monitoring into the LaunchDarkly client.
"""

# Central LaunchDarkly Client Initialization
# বাংলা মন্তব্য: লঞ্চডার্কলি এজেন্টস কন্ট্রোল এবং ওপেনটেলিমেট্রি মনিটরিং কনফিগার করার জন্য সেন্ট্রাল ক্লায়েন্ট ফাইল

import os

from core.logging_config import logger

# Safe import to handle missing packages or environments
try:
    import ldclient
    from ldai import LDAIClient
    from ldclient.config import Config
    from ldobserve import ObservabilityConfig, ObservabilityPlugin

    LD_SUPPORTED = True
except ImportError as e:
    logger.warning(f"LaunchDarkly SDK libraries not fully installed or import failed: {e}")
    LD_SUPPORTED = False


def init_ld_client() -> "LDAIClient | None":
    if not LD_SUPPORTED:
        return None

    sdk_key = os.getenv("LAUNCHDARKLY_SDK_KEY")
    if not sdk_key:
        logger.warning(
            "LAUNCHDARKLY_SDK_KEY is not set in environment. LaunchDarkly integration disabled."
        )
        return None

    try:
        # বাংলা মন্তব্য: লঞ্চডার্কলি কোর ক্লায়েন্ট কনফিগারেশন এবং অবজারভেবিলিটি প্লাগইন ইন্টিগ্রেশন
        ldclient.set_config(
            Config(
                sdk_key,
                plugins=[
                    ObservabilityPlugin(
                        ObservabilityConfig(
                            service_name=os.getenv("SERVICE_NAME", "supremeai-backend"),
                            service_version=os.getenv("SERVICE_VERSION", "2.0.0"),
                        )
                    )
                ],
            )
        )
        logger.info("LaunchDarkly AI Client successfully initialized with Observability.")
        return LDAIClient(ldclient.get())
    except Exception as e:
        logger.error(f"Failed to initialize LaunchDarkly client: {e}")
        return None


# গ্লোবাল ক্লায়েন্ট রেফারেন্স (Global Client Reference)
ld_ai_client = init_ld_client()


def get_ld_ai_components():
    """
    LaunchDarkly AI components load করে।
    সব ব্যর্থ হলে (None, None, None, None, None) return করে।
    """
    try:
        from ldai import AICompletionConfigDefault, LDMessage, ModelConfig
        from ldclient.context import Context

        return ld_ai_client, AICompletionConfigDefault, LDMessage, ModelConfig, Context
    except Exception as exc:
        logger.warning(f"LaunchDarkly AI components unavailable: {exc}")
        return None, None, None, None, None
