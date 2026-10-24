import contextlib
import os
import time
import uuid
from typing import Any

from core.config import settings
from core.logging_config import logger
from database.supabase_client import db

REWARD_TIERS = [
    {"name": "bronze", "threshold": 1, "reward": 5.0, "credit_bonus": 10},
    {"name": "silver", "threshold": 5, "reward": 10.0, "credit_bonus": 50},
    {"name": "gold", "threshold": 20, "reward": 25.0, "credit_bonus": 250},
    {"name": "platinum", "threshold": 50, "reward": 50.0, "credit_bonus": 1000},
]

FRAUD_INDICATOR_THRESHOLD = 3


class ViralReferralEngine:
    def __init__(self):
        logger.info("Initialized ViralReferralEngine")

    def _local_store(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "data", "referrals.json")

    def _load_local(self):
        path = self._local_store()
        if not os.path.exists(path):
            return {"codes": {}, "wallets": {}}
        try:
            import json

            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            try:
                import loguru

                loguru.logger.error(f"Tool execution error: {e}")
            except Exception as e:
                logger.warning(f"Exception suppressed: {e}")
            return {"codes": {}, "wallets": {}}

    def _save_local(self, data):
        os.makedirs(os.path.dirname(self._local_store()), exist_ok=True)
        import json

        with open(self._local_store(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def generate_referral_code(self, user_id: str) -> dict[str, Any]:
        code = f"SUPREME-{uuid.uuid4().hex[:8].upper()}"
        record = {
            "code": code,
            "referrer_id": user_id,
            "status": "active",
            "created_at": time.time(),
            "expires_at": time.time() + (30 * 24 * 60 * 60),
            "redeemed_count": 0,
            "fraud_score": 0.0,
        }
        if db.client:
            try:
                db.service_client.table("referral_codes").upsert(record).execute()
            except Exception as exc:
                logger.debug(f"Referral code persistence failed: {exc}")
        else:
            data = self._load_local()
            data["codes"][code] = record
            self._save_local(data)
        logger.info(f"Generated referral code {code} for user {user_id}")
        return {"status": "success", "code": code, "expires_at": record["expires_at"]}

    def list_user_codes(self, user_id: str) -> list[dict[str, Any]]:
        out = []
        if db.client:
            try:
                res = (
                    db.service_client.table("referral_codes")
                    .select("*")
                    .eq("referrer_id", user_id)
                    .execute()
                )
                out = res.data or []
            except Exception as exc:
                logger.debug(f"Failed to list codes: {exc}")
        else:
            data = self._load_local()
            for _code, rec in data.get("codes", {}).items():
                if rec.get("referrer_id") == user_id:
                    out.append(rec)
        return out  # type: ignore

    async def process_signup(
        self, new_user_id: str, referral_code: str, meta: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        logger.info(f"Processing referral {referral_code} for new user {new_user_id}")
        referrer_id = None
        record = None
        if db.client:
            try:
                res = (
                    await db.service_client.table("referral_codes")
                    .select("*")
                    .eq("code", referral_code)
                    .eq("status", "active")
                    .execute()
                )
                rows = res.data
                if rows:
                    record = rows[0]
                    referrer_id = record.get("referrer_id")
            except Exception as exc:
                logger.debug(f"Referral lookup failed: {exc}")
        else:
            data = self._load_local()
            record = data.get("codes", {}).get(referral_code)
            if record:
                referrer_id = record.get("referrer_id")

        if not referrer_id or not record:
            return {"status": "skipped", "reason": "invalid_code"}

        if record.get("expires_at", 0) < time.time():
            return {"status": "skipped", "reason": "expired_code"}

        fraud_meta = meta or {}
        if self._is_fraudulent(referrer_id, new_user_id, fraud_meta):
            return {"status": "skipped", "reason": "fraud_detected"}

        reward_info = self._calculate_reward(referrer_id)
        self._credit_wallet(referrer_id, reward_info["credit_bonus"], f"referral:{referral_code}")

        redemption = {
            "code": referral_code,
            "new_user_id": new_user_id,
            "referrer_id": referrer_id,
            "reward_amount": reward_info["reward"],
            "credits_awarded": reward_info["credit_bonus"],
            "metadata": fraud_meta,
            "created_at": time.time(),
        }
        if db.client:
            try:
                await db.service_client.table("referral_redemptions").insert(redemption).execute()
                await (
                    db.service_client.table("referral_codes")
                    .update({"redeemed_count": record.get("redeemed_count", 0) + 1})
                    .eq("code", referral_code)
                    .execute()
                )
            except Exception as exc:
                logger.debug(f"Referral redemption persistence failed: {exc}")
        else:
            data = self._load_local()
            data.setdefault("redemptions", []).append(redemption)
            if record.get("code") in data.get("codes", {}):
                data["codes"][referral_code]["redeemed_count"] = (
                    data["codes"][referral_code].get("redeemed_count", 0) + 1
                )
            self._save_local(data)

        return {
            "status": "success",
            "referrer_id": referrer_id,
            "reward_applied": reward_info["reward"],
            "credits_awarded": reward_info["credit_bonus"],
            "tier": reward_info["tier"],
        }

    def _is_fraudulent(self, referrer_id: str, new_user_id: str, meta: dict[str, Any]) -> bool:
        history: list[dict[str, Any]] = []
        if db.client:
            try:
                res = (
                    db.service_client.table("referral_redemptions")
                    .select("*")
                    .eq("referrer_id", referrer_id)
                    .execute()
                )
                history = res.data or []
            except Exception as exc:
                logger.debug(f"Fraud history lookup failed: {exc}")
        else:
            data = self._load_local()
            history = [
                r for r in data.get("redemptions", []) if r.get("referrer_id") == referrer_id
            ]

        recent_same_ip = 0
        recent_same_device = 0
        cutoff = time.time() - (7 * 24 * 60 * 60)
        for r in history:
            if r.get("created_at", 0) < cutoff:
                continue
            rm = r.get("metadata") or {}
            if meta.get("ip_address") and rm.get("ip_address") == meta.get("ip_address"):
                recent_same_ip += 1
            if meta.get("device_fingerprint") and rm.get("device_fingerprint") == meta.get(
                "device_fingerprint"
            ):
                recent_same_device += 1

        if (
            recent_same_ip >= FRAUD_INDICATOR_THRESHOLD
            or recent_same_device >= FRAUD_INDICATOR_THRESHOLD
        ):
            logger.warning(
                f"Fraud indicators for referrer {referrer_id}: same_ip={recent_same_ip}, same_device={recent_same_device}"
            )
            if db.client:
                with contextlib.suppress(Exception):
                    db.service_client.table("referral_codes").update({"fraud_score": 0.8}).eq(
                        "referrer_id", referrer_id
                    ).execute()
            return True
        return False

    def _calculate_reward(self, referrer_id: str) -> dict[str, Any]:
        count = 0
        if db.client:
            try:
                res = (
                    db.service_client.table("referral_redemptions")
                    .select("id", count="exact")
                    .eq("referrer_id", referrer_id)
                    .execute()
                )
                count = res.count if hasattr(res, "count") else (len(res.data) if res.data else 0)
            except Exception as exc:
                logger.debug(f"Reward tier count failed: {exc}")
        else:
            data = self._load_local()
            count = len(
                [r for r in data.get("redemptions", []) if r.get("referrer_id") == referrer_id]
            )

        tier = REWARD_TIERS[0]
        for t in REWARD_TIERS:
            if count >= t["threshold"]:
                tier = t
        return {
            "reward": tier["reward"],
            "credit_bonus": tier["credit_bonus"],
            "tier": tier["name"],
            "count": count,
        }

    def _credit_wallet(self, user_id: str, amount: float, reason: str) -> dict[str, Any]:
        wallet = self._get_wallet(user_id)
        new_balance = wallet.get("balance", 0.0) + amount
        ledger_entry = {
            "tx_id": str(uuid.uuid4()),
            "user_id": user_id,
            "amount": amount,
            "reason": reason,
            "timestamp": time.time(),
            "balance_after": new_balance,
        }
        if db.client:
            try:
                db.client.table("credit_ledger").insert(ledger_entry).execute()
                db.client.table("credit_wallets").upsert(
                    {
                        "user_id": user_id,
                        "balance": new_balance,
                        "updated_at": time.time(),
                    }
                ).execute()
            except Exception as exc:
                logger.debug(f"Credit wallet update failed: {exc}")
        else:
            data = self._load_local()
            data.setdefault("wallets", {})[user_id] = {
                "user_id": user_id,
                "balance": new_balance,
            }
            data.setdefault("ledger", []).append(ledger_entry)
            self._save_local(data)
        return {
            "balance": new_balance,
            "amount": amount,
            "tx_id": ledger_entry["tx_id"],
        }

    def _get_wallet(self, user_id: str) -> dict[str, Any]:
        if db.client:
            try:
                res = db.client.table("credit_wallets").select("*").eq("user_id", user_id).execute()
                rows = res.data
                if rows:
                    return rows[0]  # type: ignore
            except Exception as exc:
                logger.debug(f"Wallet fetch failed: {exc}")
        else:
            data = self._load_local()
            w = data.get("wallets", {}).get(user_id)
            if w:
                return w
        return {"user_id": user_id, "balance": 0.0}

    def get_wallet_balance(self, user_id: str) -> dict[str, Any]:
        wallet = self._get_wallet(user_id)
        return {"user_id": user_id, "balance": wallet.get("balance", 0.0)}

    def get_ledger(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if db.client:
            try:
                res = (
                    db.client.table("credit_ledger")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("timestamp", desc=True)
                    .limit(limit)
                    .execute()
                )
                out = res.data or []
            except Exception as exc:
                logger.debug(f"Ledger fetch failed: {exc}")
        else:
            data = self._load_local()
            ledger = data.get("ledger", [])
            out = [r for r in ledger if r.get("user_id") == user_id][:limit]
        return out

    def generate_deep_link(self, referral_code: str, platform: str = "generic") -> str:
        """Generate social sharing deep links for a referral code."""
        base_url = getattr(settings, "app_base_url", settings.app_base_url)
        invite_path = f"/invite/{referral_code}"
        deep_link = f"{base_url}{invite_path}"
        links = {
            "twitter": f"https://twitter.com/intent/tweet?text=Join+me+on+SupremeAI!&url={deep_link}",
            "facebook": f"https://www.facebook.com/sharer/sharer.php?u={deep_link}",
            "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={deep_link}",
            "whatsapp": f"https://api.whatsapp.com/send?text=Join+me+on+SupremeAI!+{deep_link}",
            "telegram": f"https://t.me/share/url?url={deep_link}&text=Join+me+on+SupremeAI!",
            "generic": deep_link,
        }
        return links.get(platform.lower(), deep_link)

    def record_social_share(
        self,
        user_id: str,
        referral_code: str,
        platform: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a social share event for the referral code."""
        event = {
            "user_id": user_id,
            "referral_code": referral_code,
            "platform": platform,
            "metadata": meta or {},
            "created_at": time.time(),
        }
        if db.client:
            try:
                db.service_client.table("referral_redemptions").insert(event).execute()
            except Exception as exc:
                logger.debug(f"Social share persistence failed: {exc}")
        else:
            data = self._load_local()
            data.setdefault("social_shares", []).append(event)
            self._save_local(data)
        logger.info(f"Recorded social share on {platform} for user {user_id}")
        return {
            "status": "success",
            "deep_link": self.generate_deep_link(referral_code, platform),
        }

    def _stripe_payout(
        self, user_id: str, amount_cents: int, currency: str = "usd"
    ) -> dict[str, Any]:
        """Create a Stripe payout for a user's referral earnings."""
        if not settings.stripe_api_key:
            logger.debug("Stripe API key not configured; skipping payout")
            return {"status": "skipped", "reason": "stripe_not_configured"}
        try:
            import stripe

            stripe.api_key = settings.stripe_api_key
            # In production you would map user_id to a Stripe Connect account
            payout = stripe.Payout.create(
                amount=amount_cents,
                currency=currency,
                destination=user_id,  # placeholder: connect account id
                method="standard",
            )
            logger.info(f"Stripe payout created for {user_id}: {payout.id}")
            return {
                "status": "success",
                "payout_id": payout.id,
                "amount": amount_cents,
                "currency": currency,
            }
        except Exception as exc:
            logger.error(f"Stripe payout failed for {user_id}: {exc}")
            return {"status": "error", "reason": str(exc)}

    def _credit_stripe_payout(self, user_id: str, reward_info: dict[str, Any]) -> dict[str, Any]:
        """Award referral reward and trigger Stripe payout when eligible."""
        wallet = self._get_wallet(user_id)
        current_balance = wallet.get("balance", 0.0)
        reward_amount = float(reward_info.get("reward", 0.0))
        new_balance = current_balance + reward_amount

        # Credit wallet locally
        self._credit_wallet(user_id, reward_amount, f"referral_payout:{int(time.time())}")

        # Payout threshold (e.g., $50)
        threshold_cents = 5000
        if new_balance * 100 >= threshold_cents and settings.stripe_api_key:
            payout_result = self._stripe_payout(user_id, int(new_balance * 100))
            if payout_result.get("status") == "success":
                # Zero out wallet after successful payout
                self._credit_wallet(user_id, -new_balance, "stripe_payout_cleared")
                return {"status": "paid", "payout": payout_result}
        return {"status": "credited", "balance": new_balance}
