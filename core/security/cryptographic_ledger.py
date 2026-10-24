import hashlib
import json
import time
from typing import Any

from fastapi import BackgroundTasks

from core.logging_config import logger


class CryptographicLedger:
    """
    Zero-Trust Cryptographic Ledger & Audit Trail Engine.
    SHA-256 Hash Chaining ব্যবহার করে অপরিবর্তনীয় অডিট লগ তৈরি করে।
    FastAPI BackgroundTasks এর মাধ্যমে অ্যাসিনক্রোনাস রাইট নিশ্চিত করে যাতে রিকোয়েস্ট লেটেন্সি না বাড়ে।
    """

    def __init__(self):
        self.genesis_hash = "0" * 64
        self.last_hash = self.genesis_hash
        self.chain: list[dict[str, Any]] = []

    def _compute_hash(
        self, previous_hash: str, timestamp: float, agent_id: str, payload: dict[str, Any]
    ) -> str:
        """
        SHA-256 Hash Chaining: current_hash = SHA256(previous_hash + timestamp + agent_id + payload)
        """
        payload_str = json.dumps(payload, sort_keys=True)
        raw_string = f"{previous_hash}{timestamp}{agent_id}{payload_str}"
        return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

    def record_entry_sync(
        self, agent_id: str, action: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        অডিট লগে নতুন এন্ট্রি সরাসরি যোগ করা।
        """
        timestamp = time.time()
        current_hash = self._compute_hash(self.last_hash, timestamp, agent_id, payload)

        block = {
            "index": len(self.chain) + 1,
            "previous_hash": self.last_hash,
            "timestamp": timestamp,
            "agent_id": agent_id,
            "action": action,
            "payload": payload,
            "hash": current_hash,
        }

        self.last_hash = current_hash
        self.chain.append(block)
        logger.info(
            f"[CryptographicLedger] Recorded entry #{block['index']} Hash: {current_hash[:12]}..."
        )
        return block

    def record_entry_async(
        self, background_tasks: BackgroundTasks, agent_id: str, action: str, payload: dict[str, Any]
    ) -> None:
        """
        FastAPI BackgroundTasks এর সাহায্যে নন-ব্লকিংভাবে অডিট লগ রাইট করা।
        """
        background_tasks.add_task(self.record_entry_sync, agent_id, action, payload)

    def compute_merkle_root(self) -> str:
        """
        দৈনিক বা নির্দিষ্ট সময় পর সমস্ত লগের Merkle Root Hash তৈরি করা।
        """
        if not self.chain:
            return self.genesis_hash

        hashes = [b["hash"] for b in self.chain]
        while len(hashes) > 1:
            if len(hashes) % 2 != 0:
                hashes.append(hashes[-1])
            new_hashes = []
            for i in range(0, len(hashes), 2):
                combined = hashes[i] + hashes[i + 1]
                new_hashes.append(hashlib.sha256(combined.encode("utf-8")).hexdigest())
            hashes = new_hashes

        return hashes[0]

    def verify_chain_integrity(self) -> bool:
        """
        লেজারের হাশ চেইনে কোনো ডেটা ম্যানিপুলেশন হয়েছে কি না যাচাই করা।
        """
        prev = self.genesis_hash
        for block in self.chain:
            expected_hash = self._compute_hash(
                prev, block["timestamp"], block["agent_id"], block["payload"]
            )
            if block["hash"] != expected_hash:
                logger.error(
                    f"[CryptographicLedger] Tampering detected at block #{block['index']}!"
                )
                return False
            prev = block["hash"]
        return True
