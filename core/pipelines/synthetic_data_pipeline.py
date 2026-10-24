# SupremeAI 2.0 - Synthetic Data Pipeline Engine
# বাংলা মন্তব্য: এটি EpisodicMemory ও ইউজার চ্যাট থেকে উচ্চমানের Prompt-Response জোড়া এক্সপোর্ট করে Hugging Face ফাইন-টিউনিংয়ের জন্য ব্যবহার করে।

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.logging_config import logger
from memory.episodic_memory import EpisodicMemory


class SyntheticDataPipeline:
    """
    Synthetic Dataset Generation Pipeline.
    Extracts successful execution patterns from EpisodicMemory and exports fine-tuning JSONL datasets.
    """

    def __init__(self, episodic_memory: EpisodicMemory | None = None):
        self.episodic = episodic_memory or EpisodicMemory()

    async def generate_dataset(
        self, output_path: str = "data/synthetic_ft_dataset.jsonl", min_score: float = 0.8
    ) -> dict[str, Any]:
        """
        Generate a synthetic instruction-tuning dataset from successful past agent executions.
        """
        try:
            past_records = await self.episodic.get_similar_past_tasks(
                query="successful task execution", n=50
            )

            dataset_entries = []
            for item in past_records:
                content = item.get("content", "")
                if "Prompt:" in content and "Response:" in content:
                    parts = content.split("Response:", 1)
                    prompt_text = parts[0].replace("Prompt:", "").strip()
                    response_text = parts[1].strip()

                    dataset_entries.append(
                        {
                            "instruction": prompt_text,
                            "input": "",
                            "output": response_text,
                            "system_prompt": "You are SupremeAI, an autonomous AGI-grade AI coding and reasoning ecosystem.",
                        }
                    )

            # Save dataset JSONL
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                for entry in dataset_entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            result = {
                "status": "success",
                "output_path": str(out_file),
                "total_samples": len(dataset_entries),
            }
            logger.info(
                f"Synthetic Data Pipeline generated {len(dataset_entries)} training samples -> {output_path}"
            )
            return result
        except Exception as e:
            logger.error(f"Synthetic Data Pipeline failed: {e}")
            return {"status": "error", "error": str(e), "total_samples": 0}
