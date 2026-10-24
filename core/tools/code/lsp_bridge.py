# বাংলা মন্তব্য: VS Code এক্সটেনশনের জন্য Language Server Protocol (LSP) Bridge।
# এই মডিউলটি ইউজারের টাইপ করা কোডের আগের ও পরের কনটেক্সট পড়ে
# GitHub Copilot-এর মত ডাইনামিক ইনলাইন কোড কমপ্লিশন জেনারেট করে।

from core.llm.llm_gateway import GatewayManager
from core.logging_config import logger


class LanguageServerBridge:
    def __init__(self, gateway: GatewayManager = None):
        self.gateway = gateway or GatewayManager()

    async def get_inline_completion(self, prefix: str, suffix: str, file_path: str) -> str:
        """
        Generates contextual inline code completions.
        Args:
            prefix: Code before the cursor
            suffix: Code after the cursor
            file_path: The active file path
        Returns:
            The suggested code completion string
        """
        try:
            logger.info(f"Generating LSP inline completion for {file_path}")

            # Construct a clear context window for the LLM
            prompt = (
                f"You are an expert AI pair programmer. Complete the code for the following file: {file_path}\n"
                f"Provide ONLY the raw code that belongs exactly at the cursor position. Do not include markdown formatting or explanations.\n\n"
                f"<context_before>\n{prefix}\n</context_before>\n"
                f"<cursor>\n"
                f"<context_after>\n{suffix}\n</context_after>\n"
            )

            # বাংলা: আগে model="deepseek/deepseek-coder" হার্ডকোড ছিল — DeepSeek down হলে code completion সম্পূর্ণ বন্ধ হতো।
            # এখন task_type="coding" দিয়ে gateway নিজে best available coding model বাছবে + failover chain ব্যবহার করবে।
            response = await self.gateway.acompletion(
                prompt=prompt,
                task_type="coding",
                stream=False,
            )

            completion_text = response.get("text", "").strip()

            # Cleanup common markdown code blocks if the LLM hallucinated them
            if completion_text.startswith("```"):
                completion_lines = completion_text.splitlines()
                if len(completion_lines) > 2:
                    completion_text = "\n".join(completion_lines[1:-1])

            return completion_text

        except Exception as e:
            logger.error(f"LSP bridge completion failed: {e}")
            return ""


# Singleton instance
lsp_bridge = LanguageServerBridge()
