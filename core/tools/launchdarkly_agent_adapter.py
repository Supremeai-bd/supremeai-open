import logging

# LaunchDarkly AgentControl and LangChain Production Adapter
# বাংলা মন্তব্য: লঞ্চডার্কলি এজেন্টস কন্ট্রোল এবং ল্যাংচেইন ইন্টিগ্রেশনের একটি পূর্ণাঙ্গ ও কার্যকরী উদাহরণ
import os
import sys

from core.config import settings
from core.logging_config import logger

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import ldclient
    from langchain_anthropic import ChatAnthropic
    from langchain_community.callbacks import get_openai_callback
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
    from ldai import AIAgentConfig, AIAgentConfigDefault, LDAIClient, ModelConfig
    from ldai.tracker import TokenUsage
    from ldclient.config import Config
    from ldclient.context import Context
    from ldobserve import ObservabilityConfig, ObservabilityPlugin, observe

    from core.logging_config import logger

    INTEGRATION_OK = True
except ImportError as e:
    logger.error(f"Failed to import required libraries: {e}")
    INTEGRATION_OK = False


def handle_agent_call_langchain(
    config: "AIAgentConfig",
    user_input: str,
) -> str:
    """
    LaunchDarkly AgentConfig এবং LangChain এর সাহায্যে এজেন্ট কল হ্যান্ডেল করে।
    """
    tracker = config.create_tracker()

    # বাংলা মন্তব্য: লঞ্চডার্কলি থেকে ডায়নামিক মডেল নির্ধারণ, অন্যথায় ডিফল্ট মডেল ব্যবহার
    default_model = (
        "gemini-2.5-flash"
        if getattr(settings, "gemini_api_key", None)
        else "claude-3-5-sonnet-20241022"
    )
    model_name = config.model.name if (config.model and config.model.name) else default_model

    # বাংলা মন্তব্য: লঞ্চডার্কলি মডেল প্রোভাইডার প্রিফিক্স (যেমন: "Gemini.") থাকলে তা বাদ দেওয়া হচ্ছে
    if "." in model_name:
        model_name = model_name.split(".")[-1]

    # বাংলা মন্তব্য: মডেল টাইপ অনুযায়ী সঠিক ল্যাংচেইন লাইব্রেরি সিলেক্ট করা হচ্ছে
    if "gemini" in model_name.lower():
        llm = ChatGoogleGenerativeAI(model=model_name)
    else:
        llm = ChatAnthropic(model=model_name)

    messages = []
    if config.instructions:
        messages.append(SystemMessage(content=config.instructions))
    messages.append(HumanMessage(content=user_input))

    # বাংলা মন্তব্য: লঞ্চডার্কলি অবজারভেবিলিটি ব্যবহার করে কাস্টম লগ রেকর্ড এবং স্প্যান স্টার্ট করা হচ্ছে
    observe.record_log("Executing LangChain Agent Call", logging.INFO, {"model": model_name})

    try:
        with observe.start_span("langchain-invoke", attributes={"model": model_name}) as span:
            span.set_attribute("custom-langchain-attribute", "custom-value")

            # বাংলা মন্তব্য: টোকেন ট্র্যাকিংয়ের জন্য ল্যাংচেইন কলব্যাক প্রোভাইডার ব্যবহার করা হচ্ছে
            with get_openai_callback() as cb:
                response = llm.invoke(messages)

            # লঞ্চডার্কলি ট্র্যাকার ব্যবহার করে ম্যাট্রিক্স রেকর্ড করা হচ্ছে
            tracker.track_tokens(
                TokenUsage(
                    input=cb.prompt_tokens,
                    output=cb.completion_tokens,
                    total=cb.total_tokens,
                )
            )
            tracker.track_success()
            return str(response.content)
    except Exception as exc:
        tracker.track_error()
        logger.error(f"LangChain invocation failed: {exc}")
        raise exc from exc


if __name__ == "__main__":
    if not INTEGRATION_OK:
        logger.info("❌ Setup failed: missing packages.")
        sys.exit(1)

    # বাংলা মন্তব্য: লঞ্চডার্কলি ক্লায়েন্ট কনফিগারেশন এবং অবজারভেবিলিটি প্লাগইন ইনিশিয়ালাইজেশন
    sdk_key = getattr(settings, "launchdarkly_sdk_key", os.getenv("LAUNCHDARKLY_SDK_KEY"))
    if not sdk_key:
        logger.error("LAUNCHDARKLY_SDK_KEY is not set. Exiting.")
        sys.exit(1)

    ldclient.set_config(
        Config(
            sdk_key,
            plugins=[
                ObservabilityPlugin(
                    ObservabilityConfig(
                        service_name="supremeai-langchain-example",
                        service_version="1.0.0",
                    )
                )
            ],
        )
    )
    aiclient = LDAIClient(ldclient.get())
    context = Context.builder("user-123").kind("user").build()

    default_model = (
        "gemini-2.5-flash"
        if getattr(settings, "gemini_api_key", None)
        else "claude-3-5-sonnet-20241022"
    )
    config = aiclient.agent_config(
        "supremes-writing-assistant",
        context,
        default=AIAgentConfigDefault(
            enabled=True,
            model=ModelConfig(name=default_model),
            instructions="You are a helpful writing assistant.",
        ),
    )

    logger.info("Evaluating AgentConfig...")
    if config.enabled:
        try:
            result = handle_agent_call_langchain(
                config, "Hello, write a short tagline for SupremeAI."
            )
            logger.info(f"Result: {result}")
        except Exception as e:
            logger.info(f"Error during runtime execution: {e}")
    else:
        logger.info("Config is disabled in LaunchDarkly.")
