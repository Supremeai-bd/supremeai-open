"""
Governance Agent for SupremeAI 2.0
Manages access controls, decision-making oversight, and policy enforcement.
"""

import asyncio
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.cache.redis_manager import redis_manager
from core.errors.error_bus import with_error_bus
from core.llm.token_deductor import TokenDeductor
from core.logging_config import logger
from core.utils.background_tasks import track_task


@dataclass
class AccessControlResult:
    """Data class to hold access control results."""

    user_id: str
    resource: str
    action: str
    allowed: bool
    reason: str
    timestamp: datetime
    session_id: str


@dataclass
class DecisionRecord:
    """Data class to hold decision records."""

    decision_id: str
    user_id: str
    decision_type: str
    decision_data: dict[str, Any]
    approval_required: bool
    approved_by: str | None
    approval_timestamp: datetime | None
    status: str  # pending, approved, rejected, executed
    timestamp: datetime


class GovernanceAgent:
    """Agent that manages access controls and decision-making oversight."""

    def __init__(self):
        self.name = "Governance Agent"
        self.token_deductor = TokenDeductor()
        self.access_control_key = "governance:access_control"
        self.decision_records_key = "governance:decisions"
        self.policy_key = "governance:policies"
        self.audit_log_key = "governance:audit_log"
        self.max_audit_entries = 1000

        # Initialize default policies
        self.default_policies = {
            "critical_actions_require_approval": True,
            "admin_privileges_required_for": ["delete_data", "modify_config", "manage_users"],
            "rate_limit_thresholds": {
                "high_risk": 5,  # per minute
                "medium_risk": 20,
                "low_risk": 100,
            },
            "approval_hierarchy": {
                "low_risk": ["user", "manager"],
                "medium_risk": ["manager", "director"],
                "high_risk": ["director", "executive"],
            },
        }

        # Risk levels for different actions
        self.action_risk_levels = {
            "read": "low_risk",
            "write": "medium_risk",
            "delete": "high_risk",
            "execute_code": "high_risk",
            "modify_config": "high_risk",
            "access_sensitive_data": "high_risk",
            "create_user": "medium_risk",
            "delete_user": "high_risk",
            "modify_permissions": "high_risk",
        }

    async def initialize_policies(self):
        """Initialize governance policies in Redis."""
        try:
            existing_policies = await redis_manager.get(self.policy_key)
            if not existing_policies:
                await redis_manager.set_with_ttl(
                    self.policy_key,
                    json.dumps(self.default_policies),
                    ttl=2592000,  # 30 days
                )
                logger.info("Default governance policies initialized")
        except Exception as e:
            logger.error(f"Error initializing governance policies: {e}")

    async def check_access(
        self, user_id: str, resource: str, action: str, session_id: str | None = None
    ) -> AccessControlResult:
        """
        Check if a user has access to perform an action on a resource.

        Args:
            user_id: ID of the user requesting access
            resource: Resource being accessed
            action: Action being performed
            session_id: Session identifier

        Returns:
            AccessControlResult indicating whether access is granted
        """
        try:
            # Get user role and permissions
            user_role = await self._get_user_role(user_id)
            user_permissions = await self._get_user_permissions(user_id)

            # Determine risk level of action
            risk_level = self.action_risk_levels.get(action, "medium_risk")

            # Check if user has direct permission
            permission_key = f"{resource}:{action}"
            has_permission = permission_key in user_permissions

            # Apply governance rules based on risk level
            allowed = False
            reason = ""

            if risk_level == "low_risk":
                allowed = has_permission
                reason = (
                    "Low-risk action with appropriate permissions"
                    if allowed
                    else "Insufficient permissions for low-risk action"
                )
            elif risk_level == "medium_risk":
                if has_permission and user_role in ["user", "manager", "director", "executive"]:
                    allowed = True
                    reason = "Medium-risk action permitted for authorized role"
                else:
                    allowed = False
                    reason = "Insufficient role for medium-risk action"
            elif risk_level == "high_risk":
                if has_permission and user_role in ["director", "executive"]:
                    allowed = True
                    reason = "High-risk action permitted for executive role"
                else:
                    allowed = False
                    reason = "Executive role required for high-risk action"

            # Log the access attempt
            access_result = AccessControlResult(
                user_id=user_id,
                resource=resource,
                action=action,
                allowed=allowed,
                reason=reason,
                timestamp=datetime.utcnow(),
                session_id=session_id or secrets.token_hex(16),
            )

            await self._log_access_attempt(access_result)

            return access_result

        except Exception as e:
            logger.error(f"Error checking access: {e}")
            return AccessControlResult(
                user_id=user_id,
                resource=resource,
                action=action,
                allowed=False,
                reason=f"Access check failed: {e!s}",
                timestamp=datetime.utcnow(),
                session_id=session_id or secrets.token_hex(16),
            )

    async def record_decision(
        self,
        user_id: str,
        decision_type: str,
        decision_data: dict[str, Any],
        requires_approval: bool = True,
    ) -> DecisionRecord:
        """
        Record a decision for governance oversight.

        Args:
            user_id: ID of the user making the decision
            decision_type: Type of decision being recorded
            decision_data: Data about the decision
            requires_approval: Whether the decision needs approval

        Returns:
            DecisionRecord of the recorded decision
        """
        try:
            decision_id = f"decision_{secrets.token_hex(8)}"

            # Determine if approval is required based on risk
            risk_level = self.action_risk_levels.get(decision_type, "medium_risk")
            approval_required = requires_approval or risk_level in ["high_risk", "medium_risk"]

            decision_record = DecisionRecord(
                decision_id=decision_id,
                user_id=user_id,
                decision_type=decision_type,
                decision_data=decision_data,
                approval_required=approval_required,
                approved_by=None,
                approval_timestamp=None,
                status="pending" if approval_required else "executed",
                timestamp=datetime.utcnow(),
            )

            # Store decision in Redis
            await self._store_decision(decision_record)

            # Log the decision
            await self._log_governance_event(
                "decision_recorded",
                {
                    "decision_id": decision_id,
                    "user_id": user_id,
                    "decision_type": decision_type,
                    "requires_approval": approval_required,
                },
            )

            return decision_record

        except Exception as e:
            logger.error(f"Error recording decision: {e}")
            raise

    async def approve_decision(
        self, decision_id: str, approver_id: str, approval_reason: str = ""
    ) -> bool:
        """
        Approve a pending decision.

        Args:
            decision_id: ID of the decision to approve
            approver_id: ID of the user approving
            approval_reason: Reason for approval

        Returns:
            Boolean indicating success
        """
        try:
            # Get the decision record
            decision = await self._get_decision(decision_id)
            if not decision:
                logger.warning(f"Decision {decision_id} not found")
                return False

            if decision.status != "pending":
                logger.warning(f"Decision {decision_id} is not in pending state")
                return False

            # Verify approver has appropriate permissions
            approver_role = await self._get_user_role(approver_id)
            decision_risk = self.action_risk_levels.get(decision.decision_type, "medium_risk")

            approval_allowed = False
            if decision_risk in self.default_policies["approval_hierarchy"]:
                allowed_roles = self.default_policies["approval_hierarchy"][decision_risk]
                approval_allowed = approver_role in allowed_roles
            else:
                approval_allowed = True  # Default to allow if not specified

            if not approval_allowed:
                logger.warning(
                    f"User {approver_id} with role {approver_role} cannot approve {decision_risk} decision"
                )
                return False

            # Update the decision record
            decision.approved_by = approver_id
            decision.approval_timestamp = datetime.utcnow()
            decision.status = "approved"

            await self._store_decision(decision)

            # Log the approval
            await self._log_governance_event(
                "decision_approved",
                {
                    "decision_id": decision_id,
                    "approver_id": approver_id,
                    "approval_reason": approval_reason,
                },
            )

            return True

        except Exception as e:
            logger.error(f"Error approving decision: {e}")
            return False

    async def enforce_policy(
        self, user_id: str, action: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Enforce governance policies for an action.

        Args:
            user_id: ID of the user performing the action
            action: Action being performed
            context: Additional context for policy enforcement

        Returns:
            Dictionary with policy enforcement results
        """
        try:
            # Get user info
            user_role = await self._get_user_role(user_id)

            # Get rate limiting info
            rate_limit_result = await self._check_rate_limit(user_id, action)

            # Get policy settings
            policies = await self._get_policies()

            # Check if action requires approval
            risk_level = self.action_risk_levels.get(action, "medium_risk")
            requires_approval = policies.get(
                "critical_actions_require_approval", True
            ) and action in policies.get("admin_privileges_required_for", [])

            # Determine if user has sufficient privileges
            has_privileges = True
            if action in policies.get("admin_privileges_required_for", []):
                has_privileges = user_role in ["admin", "director", "executive"]

            result = {
                "action_permitted": has_privileges and rate_limit_result["within_limit"],
                "requires_approval": requires_approval,
                "risk_level": risk_level,
                "user_role": user_role,
                "has_privileges": has_privileges,
                "rate_limit_info": rate_limit_result,
                "policy_compliant": has_privileges and rate_limit_result["within_limit"],
                "next_action": (
                    "proceed"
                    if (
                        has_privileges
                        and rate_limit_result["within_limit"]
                        and not requires_approval
                    )
                    else "review"
                ),
            }

            # Log policy enforcement
            await self._log_governance_event(
                "policy_enforced", {"user_id": user_id, "action": action, "result": result}
            )

            return result

        except Exception as e:
            logger.error(f"Error enforcing policy: {e}")
            return {"action_permitted": False, "error": str(e), "next_action": "reject"}

    @with_error_bus("_get_user_role")
    async def _get_user_role(self, user_id: str) -> str:
        """Get the role of a user."""
        # This would typically integrate with the auth system
        # For now, we'll return a default role
        try:
            # In a real implementation, this would fetch from the auth system
            # For demonstration, return 'user' as default
            return "user"
        except Exception:
            return "user"

    @with_error_bus("_get_user_permissions")
    async def _get_user_permissions(self, user_id: str) -> list[str]:
        """Get the permissions of a user."""
        try:
            # In a real implementation, this would fetch from the auth system
            # For demonstration, return some default permissions
            return ["read_profile", "read_dashboard"]
        except Exception:
            # বাংলা: পারমিশন ফেচ ফেইল করলে fail-closed (কোনো পারমিশন নেই) — এররটি লগ করা হলো যাতে অদৃশ্য না থাকে
            logger.warning(
                "Failed to fetch user permissions; defaulting to no permissions (fail-closed).",
                exc_info=True,
            )
            return []

    async def _check_rate_limit(self, user_id: str, action: str) -> dict[str, Any]:
        """Check if user is within rate limits for an action."""
        try:
            risk_level = self.action_risk_levels.get(action, "medium_risk")
            threshold = self.default_policies["rate_limit_thresholds"].get(risk_level, 20)

            # Create a key for this user-action combination
            rate_key = f"rate_limit:{user_id}:{action}:{datetime.utcnow().strftime('%Y%m%d%H%M')}"  # per-minute

            # Get current count
            current_count_str = await redis_manager.get(rate_key)
            current_count = int(current_count_str) if current_count_str else 0

            within_limit = current_count < threshold

            # Increment the counter
            await redis_manager.set_with_ttl(
                rate_key, str(current_count + 1), ttl=60
            )  # 1 minute TTL

            return {
                "within_limit": within_limit,
                "current_count": current_count + 1,
                "threshold": threshold,
                "risk_level": risk_level,
            }
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return {
                "within_limit": True,  # Default to allow if we can't check
                "error": str(e),
                "current_count": 0,
                "threshold": 0,
            }

    async def _store_decision(self, decision: DecisionRecord):
        """Store a decision record in Redis."""
        try:
            decision_data = {
                "decision_id": decision.decision_id,
                "user_id": decision.user_id,
                "decision_type": decision.decision_type,
                "decision_data": decision.decision_data,
                "approval_required": decision.approval_required,
                "approved_by": decision.approved_by,
                "approval_timestamp": decision.approval_timestamp.isoformat()
                if decision.approval_timestamp
                else None,
                "status": decision.status,
                "timestamp": decision.timestamp.isoformat(),
            }

            # Get existing decisions
            existing_decisions = await redis_manager.get(self.decision_records_key)
            if existing_decisions:
                decisions_list = json.loads(existing_decisions)
            else:
                decisions_list = []

            decisions_list.append(decision_data)

            # Keep only the last N decisions
            max_decisions = 500
            if len(decisions_list) > max_decisions:
                decisions_list = decisions_list[-max_decisions:]

            await redis_manager.set_with_ttl(
                self.decision_records_key,
                json.dumps(decisions_list),
                ttl=2592000,  # 30 days
            )
        except Exception as e:
            logger.error(f"Error storing decision: {e}")

    async def _get_decision(self, decision_id: str) -> DecisionRecord | None:
        """Get a decision record from Redis."""
        try:
            existing_decisions = await redis_manager.get(self.decision_records_key)
            if not existing_decisions:
                return None

            decisions_list = json.loads(existing_decisions)
            for decision_data in decisions_list:
                if decision_data["decision_id"] == decision_id:
                    return DecisionRecord(
                        decision_id=decision_data["decision_id"],
                        user_id=decision_data["user_id"],
                        decision_type=decision_data["decision_type"],
                        decision_data=decision_data["decision_data"],
                        approval_required=decision_data["approval_required"],
                        approved_by=decision_data["approved_by"],
                        approval_timestamp=(
                            datetime.fromisoformat(decision_data["approval_timestamp"])
                            if decision_data["approval_timestamp"]
                            else None
                        ),
                        status=decision_data["status"],
                        timestamp=datetime.fromisoformat(decision_data["timestamp"]),
                    )

            return None
        except Exception as e:
            logger.error(f"Error getting decision: {e}")
            return None

    async def _log_access_attempt(self, access_result: AccessControlResult):
        """Log an access control attempt."""
        try:
            log_entry = {
                "type": "access_attempt",
                "user_id": access_result.user_id,
                "resource": access_result.resource,
                "action": access_result.action,
                "allowed": access_result.allowed,
                "reason": access_result.reason,
                "session_id": access_result.session_id,
                "timestamp": access_result.timestamp.isoformat(),
            }

            await self._add_to_audit_log(log_entry)
        except Exception as e:
            logger.error(f"Error logging access attempt: {e}")

    async def _log_governance_event(self, event_type: str, data: dict[str, Any]):
        """Log a governance event."""
        try:
            log_entry = {
                "type": event_type,
                "data": data,
                "timestamp": datetime.utcnow().isoformat(),
            }

            await self._add_to_audit_log(log_entry)
        except Exception as e:
            logger.error(f"Error logging governance event: {e}")

    async def _add_to_audit_log(self, entry: dict[str, Any]):
        """Add an entry to the audit log."""
        try:
            # Get existing audit log
            existing_log = await redis_manager.get(self.audit_log_key)
            if existing_log:
                audit_log = json.loads(existing_log)
            else:
                audit_log = []

            # Add new entry
            audit_log.append(entry)

            # Keep only the last N entries
            if len(audit_log) > self.max_audit_entries:
                audit_log = audit_log[-self.max_audit_entries :]

            await redis_manager.set_with_ttl(
                self.audit_log_key,
                json.dumps(audit_log),
                ttl=2592000,  # 30 days
            )
        except Exception as e:
            logger.error(f"Error adding to audit log: {e}")

    async def _get_policies(self) -> dict[str, Any]:
        """Get current governance policies."""
        try:
            policies_json = await redis_manager.get(self.policy_key)
            if policies_json:
                return json.loads(policies_json)
            else:
                return self.default_policies
        except Exception as e:
            logger.error(f"Error getting policies: {e}")
            return self.default_policies


# Global instance
governance_agent = GovernanceAgent()

# Initialize policy on module load — শুধুমাত্র একটা event loop চলমান থাকলেই টাস্ক শিডিউল করা হয়;
# বাংলা: import-time-এ event loop না থাকলে RuntimeError এড়ানো হয়, আর টাস্কের রেফারেন্স ট্র্যাক করে
# রাখা হয় যাতে GC হয়ে মাঝপথে বাতিল না হয়ে যায় (RUF006)।
try:
    track_task(asyncio.get_running_loop().create_task(governance_agent.initialize_policies()))
except RuntimeError:
    logger.debug(
        "No running event loop at import time; skipping eager policy init "
        "(call initialize_policies() explicitly during app startup instead)."
    )
