# backend/evolution/artifact_integrity.py
"""Cryptographic Artifact Integrity and Hashing Gate for Self-Evolution."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.logging_config import logger
from evolution.change_proposal import (
    ChangeProposalManager,
    ProposalState,
    get_change_manager,
)


def canonical_artifact_hash(code: str, schema: dict[str, Any] | None = None) -> str:
    """Compute SHA-256 canonical hash of code and schema."""
    hasher = hashlib.sha256()
    hasher.update(code.strip().encode("utf-8"))
    if schema:
        canonical_schema_json = json.dumps(schema, sort_keys=True)
        hasher.update(canonical_schema_json.encode("utf-8"))
    return hasher.hexdigest()


class ArtifactIntegrityGate:
    """Enforces cryptographic artifact hash verification before installer deployment."""

    @staticmethod
    def verify_and_authorize(
        proposal_id: str,
        code_to_deploy: str,
        schema_to_deploy: dict[str, Any] | None = None,
        proposal_manager: ChangeProposalManager | None = None,
    ) -> bool:
        proposal_mgr = proposal_manager or get_change_manager()
        proposal = proposal_mgr.proposals.get(proposal_id)
        if not proposal:
            logger.error(
                f"🚨 Integrity Gate Blocked: Proposal [{proposal_id}] not found in governance registry."
            )
            return False

        if proposal.state != ProposalState.PROMOTED:
            logger.error(
                f"🚨 Integrity Gate Blocked: Proposal [{proposal_id}] is in state {proposal.state.value}, not PROMOTED."
            )
            return False

        expected_code = proposal.diff_content.get("code", "")
        expected_schema = proposal.diff_content.get("schema", {})

        current_hash = canonical_artifact_hash(code_to_deploy, schema_to_deploy)
        expected_hash = canonical_artifact_hash(expected_code, expected_schema)

        if current_hash != expected_hash:
            logger.error(
                f"🚨 Integrity Violation: Deployment code hash {current_hash[:10]} does not match proposal hash {expected_hash[:10]}!"
            )
            return False

        logger.info(
            f"🛡️ Artifact Integrity Verified for Proposal [{proposal_id}] (SHA-256: {current_hash[:12]})."
        )
        return True
