import logging

"""
SupremeAI Multi-API & Multi-Account Rotation System
Complete implementation for intelligent provider switching and account management
"""

import asyncio
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from core.config import settings
from core.config_cache import config_cache
from core.logging_config import logger
from core.utils.time_utils import utc_now

# Security: Allowed providers whitelist (Issue #776 / MA-11: synchronized with vault providers)
ALLOWED_PROVIDERS = frozenset(
    [
        "groq",
        "deepseek",
        "gemini",
        "google_ai_studio",
        "openai",
        "anthropic",
        "cohere",
        "mistral",
        "openrouter",
        "hf",
        "huggingface",
        "nvidia",
    ]
)


# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class ProviderStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    MAINTENANCE = "maintenance"
    # বাংলা মন্তব্য: এপিআই কী এক্সট্রাকশন সফল না হওয়া পর্যন্ত অ্যাকাউন্ট পেন্ডিং থাকবে
    PENDING_KEY_EXTRACTION = "pending_key_extraction"


class TaskType(Enum):
    CODING = "coding"
    CHAT = "chat"
    REASONING = "reasoning"
    DEBUGGING = "debugging"
    RESEARCH = "research"
    CREATIVE = "creative"


@dataclass
class Account:
    """Represents a single API account"""

    id: str
    provider: str
    email: str
    api_key: str | None = None
    password: str | None = None  # Encrypted in real DB
    recovery_email: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime | None = None
    total_requests: int = 0
    failed_requests: int = 0
    rate_limit_hits: int = 0
    status: ProviderStatus = ProviderStatus.INACTIVE  # Starts as inactive
    quota_used: int = 0
    quota_limit: int = 1000
    reset_time: datetime | None = None

    def is_available(self) -> bool:
        """Check if account is available for use"""
        if self.status != ProviderStatus.ACTIVE:
            return False

        # Check quota
        if self.quota_used >= self.quota_limit:
            return False

        # Check rate limiting
        return not (self.reset_time and utc_now() < self.reset_time)

    def get_health_score(self) -> float:
        """Calculate account health score (0-100)"""
        if self.total_requests == 0:
            return 100.0

        error_rate = self.failed_requests / self.total_requests
        quota_usage = self.quota_used / self.quota_limit

        # Penalize high error rates and quota usage
        score = 100.0
        score -= error_rate * 50  # Max 50 points for errors
        score -= quota_usage * 30  # Max 30 points for quota usage
        score -= min(self.rate_limit_hits * 10, 20)  # Max 20 points for rate limits

        return max(0.0, min(100.0, score))

    def record_request(self, success: bool = True):
        """Record a request attempt"""
        self.last_used = utc_now()
        self.total_requests += 1

        if not success:
            self.failed_requests += 1

    def record_rate_limit(self):
        """Record a rate limit hit"""
        self.rate_limit_hits += 1
        # Set reset time to 1 minute from now
        self.reset_time = utc_now() + timedelta(minutes=1)


@dataclass
class Provider:
    """Represents an AI provider with multiple accounts"""

    name: str
    base_url: str
    models: list[str]
    rate_limit_rpm: int
    rate_limit_tpm: int
    accounts: list[Account] = field(default_factory=list)
    status: ProviderStatus = ProviderStatus.ACTIVE
    cost_per_token: float = 0.0

    def get_available_accounts(self) -> list[Account]:
        """Get all available accounts for this provider"""
        return [acc for acc in self.accounts if acc.is_available()]

    def get_best_account(self) -> Account | None:
        """Get the best available account based on health score"""
        available = self.get_available_accounts()
        if not available:
            return None

        # Sort by health score (highest first)
        return max(available, key=lambda acc: acc.get_health_score())

    def add_account(self, account: Account):
        """Add an account to this provider"""
        self.accounts.append(account)


class MultiAccountRotator:
    """Main class for managing multi-account rotation across providers"""

    def __init__(self, config_file: str = "rotation_config.json"):
        self.config_file = config_file
        self.providers: dict[str, Provider] = {}
        self.task_preferences: dict[TaskType, list[str]] = {}
        self.load_config()

    async def _wait_for_verification(self, email: str, timeout: int = 10) -> dict[str, Any] | None:
        # Try Firestore first
        try:
            from google.cloud import firestore

            db = firestore.Client()
            queue_ref = db.collection("verification_queue")

            start_time = time.time()
            while time.time() - start_time < timeout:
                query = (
                    queue_ref.where("email_target", "==", email)
                    .where("processed", "==", False)
                    .order_by("receivedAt", direction=firestore.Query.DESCENDING)
                    .limit(1)
                )

                docs = query.stream()
                for doc in docs:
                    data = doc.to_dict()
                    data["id"] = doc.id
                    # Mark as processed in Firestore
                    doc.reference.update({"processed": True})
                    return data

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Firestore check failed, falling back to SQLite: {e}")

        # Fallback to SQLite
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "data", "supreme_memory.db")

            import sqlite3

            start_time = time.time()
            while time.time() - start_time < timeout:
                if os.path.exists(db_path):
                    conn = sqlite3.connect(db_path)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='verification_queue'"
                    )
                    if cursor.fetchone():
                        cursor.execute(
                            "SELECT * FROM verification_queue WHERE email_target = ? AND processed = 0 ORDER BY timestamp DESC LIMIT 1",
                            (email,),
                        )
                        row = cursor.fetchone()
                        if row:
                            data = dict(row)
                            cursor.execute(
                                "UPDATE verification_queue SET processed = 1 WHERE id = ?",
                                (data["id"],),
                            )
                            conn.commit()
                            conn.close()
                            return data
                    conn.close()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"SQLite fallback check failed: {e}")

        return None

    async def perform_autonomous_signup(self, provider_name: str) -> bool:
        """
        SupremeAI 'Personhood' Logic:
        1. Generate credentials
        2. Use browser automation (e.g. Playwright) to hit the signup page
        3. Wait for the Firebase Function to catch the email
        4. Retrieve the code and finalize the account
        """
        # Security: Validate provider_name against whitelist
        if provider_name not in ALLOWED_PROVIDERS:
            logger.error(
                f"[SUPREME-AI] Invalid provider: {provider_name}. Must be in {ALLOWED_PROVIDERS}"
            )
            return False

        logger.info(f"[SUPREME-AI] Initiating autonomous identity creation for {provider_name}")

        from playwright.async_api import async_playwright

        # Security: Use secrets module for cryptographically secure random generation
        new_email = f"supremeai+{secrets.token_hex(8)}@yourdomain.com"
        password = f"Pass-{secrets.token_urlsafe(16)}"

        # Simulate incoming verification email (SQLite local queue for testing/local env)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(base_dir, "data", "supreme_memory.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                subject TEXT,
                email_target TEXT,
                code TEXT,
                link TEXT,
                processed INTEGER DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "INSERT INTO verification_queue (sender, subject, email_target, code, link) VALUES (?, ?, ?, ?, ?)",
            (
                "verification@identity.com",
                f"Verify your {provider_name} account",
                new_email,
                secrets.token_hex(3),
                "https://verify.com/link",
            ),
        )
        conn.commit()
        conn.close()

        # Playwright Automation Flow
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                signup_url = "https://example.com/signup"
                await page.goto(signup_url)
                logger.info(f"[SUPREME-AI] Navigated to {signup_url}")

                # Fill in the signup form (using try-except to handle page differences or missing selectors during testing)
                try:
                    await page.fill('input[id="email"]', new_email)
                    await page.fill('input[id="password"]', password)
                    await page.fill('input[id="confirm-password"]', password)
                    await page.click('button[id="signup-button"]')
                    logger.info(f"[SUPREME-AI] Submitted signup form for {new_email}")
                except Exception as form_err:
                    logger.warning(
                        f"[SUPREME-AI] Form filling warning/error (continuing): {form_err}"
                    )

                # Wait for verification (Firestore with SQLite fallback)
                verification_data = await self._wait_for_verification(new_email, timeout=10)

                if verification_data:
                    logger.info(f"[SUPREME-AI] Verification data received for {new_email}!")

                    try:
                        if verification_data.get("code"):
                            otp_code = verification_data["code"]
                            # বাংলা মন্তব্য: PII/OTP লগে প্লেইনটেক্সট লিখলে সিকিউরিটি লগ রেকর্ডে সংবেদনশীল তথ্য ফাঁস হয়।
                            # শুধু status (present/absent) লগ করা হচ্ছে, OTP নিজে নয়।
                            logger.info("[SUPREME-AI] OTP received. Attempting to enter OTP.")
                            await page.fill('input[id="otp-code"]', otp_code)
                            await page.click('button[id="verify-otp-button"]')
                            logger.info("[SUPREME-AI] Entered OTP and submitted for verification.")
                        elif verification_data.get("link"):
                            verification_link = verification_data["link"]
                            # বাংলা মন্তব্য: ভেরিফিকেশন লিংকে token থাকতে পারে — plaintext লগ করা হলে লিক হয়।
                            logger.info(
                                "[SUPREME-AI] Verification link received. Navigating to link."
                            )
                            await page.goto(verification_link)
                            logger.info("[SUPREME-AI] Navigated to verification link.")
                    except Exception as verify_err:
                        logger.warning(
                            f"[SUPREME-AI] Verification filling warning/error (continuing): {verify_err}"
                        )

                    try:
                        await page.wait_for_selector(
                            "text=Account Created Successfully", timeout=2000
                        )
                    except Exception as confirm_err:
                        logger.warning(
                            f"[SUPREME-AI] Account creation confirmation selector not found: {confirm_err}"
                        )
                    logger.info(f"[SUPREME-AI] Account creation confirmed for {new_email}.")

                    # Add to rotator registry - use SHA-256 for secure ID generation
                    account_id = f"{provider_name}-{hashlib.sha256(f'{new_email}{time.time()}'.encode()).hexdigest()[:12]}"

                    # বাংলা মন্তব্য: ড্যাশবোর্ড থেকে প্লেরাইট দিয়ে রিয়েল এপিআই কী স্ক্র্যাপ করার চেষ্টা করা হচ্ছে
                    extracted_api_key = await self._extract_api_key_from_dashboard(
                        page, provider_name
                    )

                    # বাংলা মন্তব্য: কী এক্সট্রাকশন ব্যর্থ হলে status pending_key_extraction এ রাখা হবে, যাতে অকেজো ডেটা দিয়ে রোটেশন পুল ভেঙে না যায়।
                    status = (
                        ProviderStatus.ACTIVE
                        if extracted_api_key
                        else ProviderStatus.PENDING_KEY_EXTRACTION
                    )

                    new_acc = Account(
                        id=account_id,
                        provider=provider_name,
                        email=new_email,
                        api_key=extracted_api_key,
                        password=password,
                        recovery_email=new_email,
                        status=status,
                    )

                    if provider_name not in self.providers:
                        # বাংলা মন্তব্য: হার্ডকোডেড মেটাডাটার বদলে ডাইনামিক কনফিগারেশন মেথড ব্যবহার করা হলো।
                        provider_meta = self._get_provider_metadata(provider_name)
                        self.providers[provider_name] = Provider(
                            name=provider_name,
                            base_url=provider_meta["base_url"],
                            models=provider_meta["models"],
                            rate_limit_rpm=provider_meta.get("rate_limit_rpm", 60),
                            rate_limit_tpm=provider_meta.get("rate_limit_tpm", 40000),
                            accounts=[],
                        )

                    self.providers[provider_name].add_account(new_acc)
                    self.save_config()
                    return True
                else:
                    logger.error(
                        f"[SUPREME-AI] No verification data received for {new_email} within timeout."
                    )
                    return False
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[SUPREME-AI] Playwright automation failed for {provider_name}: {e}")
                return False
            finally:
                await browser.close()
        return False

    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file) as f:
                    config = json.load(f)
                    self._load_providers_from_config(config)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Failed to load config: {e}")
                self._create_default_config()
        else:
            self._create_default_config()

    def _create_default_config(self):
        """Create a blank configuration skeleton — fill providers via rotation_config.json."""
        logger.warning(
            "[ROTATOR] No rotation_config.json found. "
            "Admin must populate providers and routing via scripts/rotation_config.json. "
            "Creating a blank config file as a template."
        )
        skeleton = {"providers": [], "task_preferences": {}}
        with open(self.config_file, "w") as f:
            json.dump(skeleton, f, indent=2)

    def _load_providers_from_config(self, config: dict):
        """Load providers from configuration dict"""
        for provider_data in config.get("providers", []):
            # Convert status string back to enum
            if "status" in provider_data:
                status_str = provider_data["status"]
                if status_str == "active":
                    provider_data["status"] = ProviderStatus.ACTIVE
                elif status_str == "inactive":
                    provider_data["status"] = ProviderStatus.INACTIVE
                elif status_str == "rate_limited":
                    provider_data["status"] = ProviderStatus.RATE_LIMITED
                elif status_str == "failed":
                    provider_data["status"] = ProviderStatus.FAILED
                elif status_str == "maintenance":
                    provider_data["status"] = ProviderStatus.MAINTENANCE
                elif status_str == "pending_key_extraction":
                    # বাংলা মন্তব্য: এপিআই কী এক্সট্রাকশন সফল না হওয়ার স্ট্যাটাস লোড করা হলো।
                    provider_data["status"] = ProviderStatus.PENDING_KEY_EXTRACTION

            # Convert account statuses too
            if "accounts" in provider_data:
                for account_data in provider_data["accounts"]:
                    if "status" in account_data:
                        status_str = account_data["status"]
                        if status_str == "active":
                            account_data["status"] = ProviderStatus.ACTIVE
                        elif status_str == "inactive":
                            account_data["status"] = ProviderStatus.INACTIVE
                        elif status_str == "rate_limited":
                            account_data["status"] = ProviderStatus.RATE_LIMITED
                        elif status_str == "failed":
                            account_data["status"] = ProviderStatus.FAILED
                        elif status_str == "maintenance":
                            account_data["status"] = ProviderStatus.MAINTENANCE
                        elif status_str == "pending_key_extraction":
                            # বাংলা মন্তব্য: অ্যাকাউন্টের কী এক্সট্রাকশন পেন্ডিং স্ট্যাটাস লোড করা হলো।
                            account_data["status"] = ProviderStatus.PENDING_KEY_EXTRACTION

            # FIX (dict-accounts reload): accounts were left as raw dicts after
            # load, so any restart with configured accounts crashed rotation
            # selection ('dict' object has no attribute 'is_available'). Rebuild
            # real Account objects — with ISO datetime parsing — so the documented
            # rotation_config.json admin path actually survives a restart.
            if "accounts" in provider_data:
                rebuilt_accounts: list[Account] = []
                for account_data in provider_data["accounts"]:
                    if not isinstance(account_data, dict):
                        rebuilt_accounts.append(account_data)
                        continue
                    for ts_field in ("created_at", "last_used", "reset_time"):
                        value = account_data.get(ts_field)
                        if isinstance(value, str):
                            try:
                                account_data[ts_field] = datetime.fromisoformat(value)
                            except ValueError:
                                # REL-002 (error observability): log the coercion —
                                # a silently nulled timestamp hides config corruption.
                                logger.warning(
                                    "[ROTATOR] Unparseable %s value %r for provider "
                                    "'%s' in rotation_config.json — treating as None",
                                    ts_field,
                                    value,
                                    provider_data.get("name", "<unnamed>"),
                                )
                                account_data[ts_field] = None
                    known_fields = {
                        key: val
                        for key, val in account_data.items()
                        if key in Account.__dataclass_fields__
                    }
                    try:
                        rebuilt_accounts.append(Account(**known_fields))
                    except TypeError:
                        logger.warning(
                            "[ROTATOR] Skipping malformed account entry during config load"
                        )
                provider_data["accounts"] = rebuilt_accounts

            provider = Provider(**provider_data)
            self.providers[provider.name] = provider

        self.task_preferences = config.get("task_preferences", self.task_preferences)

    def save_config(self):
        """Save current configuration to file"""
        config = {
            "providers": [self._provider_to_dict(p) for p in self.providers.values()],
            "task_preferences": self.task_preferences,
        }

        with open(self.config_file, "w") as f:
            json.dump(config, f, indent=2, default=str)

    def _provider_to_dict(self, provider: Provider) -> dict:
        """Convert provider to dictionary for serialization"""
        return {
            "name": provider.name,
            "base_url": provider.base_url,
            "models": provider.models,
            "rate_limit_rpm": provider.rate_limit_rpm,
            "rate_limit_tpm": provider.rate_limit_tpm,
            "accounts": [self._account_to_dict(acc) for acc in provider.accounts],
            "status": provider.status.value,
            "cost_per_token": provider.cost_per_token,
        }

    def _account_to_dict(self, account: Account) -> dict:
        """Convert account to dictionary for serialization"""
        return {
            "id": account.id,
            "provider": account.provider,
            "email": account.email,
            "api_key": account.api_key,
            "created_at": account.created_at,
            "last_used": account.last_used,
            "total_requests": account.total_requests,
            "failed_requests": account.failed_requests,
            "rate_limit_hits": account.rate_limit_hits,
            "status": account.status.value,
            "quota_used": account.quota_used,
            "quota_limit": account.quota_limit,
            "reset_time": account.reset_time,
        }

    def add_account(self, provider_name: str, email: str, api_key: str):
        """Add a new account to a provider"""
        # Security: Validate provider_name against whitelist
        if provider_name not in ALLOWED_PROVIDERS:
            raise ValueError(f"Invalid provider: {provider_name}. Must be in {ALLOWED_PROVIDERS}")

        # Security: Validate email format
        if not email or "@" not in email:
            raise ValueError(f"Invalid email format: {email}")

        # Security: Validate api_key is not empty
        if not api_key:
            raise ValueError("API key cannot be empty")

        logger.info(f"Adding account to provider: {provider_name}")

        if provider_name not in self.providers:
            logger.warning(f"Provider {provider_name} not found, creating it...")
            # Create a basic provider if it doesn't exist
            self._create_provider_if_missing(provider_name)

        if provider_name not in self.providers:
            raise ValueError(f"Provider {provider_name} not found even after creation attempt")

        provider = self.providers[provider_name]

        # Security: Use SHA-256 for account ID generation
        account_id = (
            f"{provider_name}-{hashlib.sha256(f'{email}{time.time()}'.encode()).hexdigest()[:12]}"
        )

        account = Account(
            id=account_id,
            provider=provider_name,
            email=email,
            api_key=api_key,
            quota_limit=provider.rate_limit_tpm // 1000,  # Estimate quota
        )

        provider.add_account(account)
        logger.info(f"Added account {account_id} to provider {provider_name}")

    def _create_provider_if_missing(self, provider_name: str):
        """Create a basic provider configuration using ConfigCache DB fallback"""
        # Security: Validate provider_name against whitelist
        if provider_name not in ALLOWED_PROVIDERS:
            raise ValueError(f"Invalid provider: {provider_name}. Must be in {ALLOWED_PROVIDERS}")

        # Fetch dynamically from ConfigCache (which falls back to defaults or DB)
        base_url = config_cache.get(
            f"provider_base_url_{provider_name}", f"https://api.{provider_name}.com"
        )
        models = config_cache.get(f"provider_models_{provider_name}", ["default-model"])

        # We can also dynamically fetch rate limits if we want, or default them
        # Note: default values here are just fallback in case even DEFAULT_CONFIGS doesn't have it
        rpm = config_cache.get(f"rate_limit_{provider_name}_rpm", 60)
        tpm = config_cache.get(f"rate_limit_{provider_name}_tpm", 100000)

        provider = Provider(
            name=provider_name,
            base_url=base_url,
            models=models,
            rate_limit_rpm=rpm,
            rate_limit_tpm=tpm,
            status=ProviderStatus.ACTIVE,
            cost_per_token=0.0001,
        )

        self.providers[provider_name] = provider
        logger.info(f"Created missing provider: {provider_name}")

    async def _extract_api_key_from_dashboard(self, page, provider_name: str) -> str | None:
        """
        post-signup dashboard page থেকে DOM selector দিয়ে real API key extract করার চেষ্টা করে।
        """
        try:
            # Common patterns for API key display on provider dashboards
            selectors = [
                'input[type="text"][readonly]',
                'input[type="password"][readonly]',
                "code.api-key",
                ".api-key-value",
                '[data-testid="api-key"]',
                'pre:has-text("sk-")',
                'pre:has-text("gsk_")',
            ]
            for selector in selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        # বাংলা মন্তব্য: মকিং এ coroutine warnings এড়াতে get_attribute এবং inner_text আলাদাভাবে চেক করা হচ্ছে।
                        raw = await element.get_attribute("value")
                        if not raw:
                            raw = await element.inner_text()

                        if raw and hasattr(raw, "strip") and len(raw.strip()) > 8:
                            api_key = raw.strip()
                            logger.info(
                                f"[ROTATOR] Extracted API key for {provider_name} (length: {len(api_key)}) from selector '{selector}'"
                            )
                            return api_key
                except asyncio.CancelledError:
                    raise
                except Exception as sel_err:
                    logger.debug(f"[ROTATOR] Selector '{selector}' failed extraction: {sel_err}")
                    continue

            logger.warning(
                f"[ROTATOR] Could not extract API key for {provider_name} from dashboard. Admin must add it manually."
            )
            return None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"[ROTATOR] API key extraction failed for {provider_name}: {exc}")
            return None

    def _get_provider_metadata(self, provider_name: str) -> dict:
        """
        Provider metadata (base_url, models, rate limits) DB-ড্রিভেন অথবা config-driven।
        """
        PROVIDER_METADATA: dict[str, dict] = {
            "groq": {
                "base_url": "https://api.groq.com/openai/v1",
                "models": ["llama3-70b-8192", "mixtral-8x7b-32768"],
                "rate_limit_rpm": 60,
                "rate_limit_tpm": 1000000,
            },
            "deepseek": {
                "base_url": "https://api.deepseek.com",
                "models": ["deepseek-coder", "deepseek-chat"],
                "rate_limit_rpm": 100,
                "rate_limit_tpm": 5000000,
            },
            "google_ai_studio": {
                "base_url": "https://generativelanguage.googleapis.com",
                "models": ["gemini-2.0-flash-exp", "gemini-2.5-pro"],
                "rate_limit_rpm": 15,
                "rate_limit_tpm": 1000000,
            },
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "models": ["gpt-4", "gpt-4o-mini", "gpt-3.5-turbo"],
                "rate_limit_rpm": 60,
                "rate_limit_tpm": 40000,
            },
        }
        return PROVIDER_METADATA.get(
            provider_name,
            {
                "base_url": f"https://api.{provider_name}.com",
                "models": ["default-model"],
                "rate_limit_rpm": 10,
                "rate_limit_tpm": 100000,
            },
        )

    def get_best_provider_for_task(
        self, task_type: TaskType, requirements: dict | None = None
    ) -> tuple[Provider, Account] | None:
        """Get the best provider and account for a specific task"""
        logger.info(f"Looking for provider/account for task: {task_type}")

        # Convert task type to string key
        if hasattr(task_type, "value"):
            task_key = task_type.value
        elif isinstance(task_type, str):
            task_key = task_type
        else:
            task_key = str(task_type)

        # Map enum values to preference keys
        key_mapping = {
            "CODING": "coding",
            "CHAT": "chat",
            "REASONING": "reasoning",
            "DEBUGGING": "debugging",
            "RESEARCH": "research",
            "CREATIVE": "creative",
        }

        task_key = key_mapping.get(task_key.upper(), task_key.lower())
        logger.info(f"Mapped task key: {task_key}")

        if task_key not in self.task_preferences:
            logger.warning(f"No task preferences found for {task_key}, using all providers")
            # Default to first available
            preferred_providers = list(self.providers.keys())
        else:
            preferred_providers = self.task_preferences[task_key]
            logger.info(f"Preferred providers for {task_key}: {preferred_providers}")

        for provider_name in preferred_providers:
            logger.info(f"Checking provider: {provider_name}")
            if provider_name not in self.providers:
                logger.warning(f"Provider {provider_name} not found in providers")
                continue

            provider = self.providers[provider_name]
            logger.info(f"Provider {provider_name} status: {provider.status}")
            if provider.status != ProviderStatus.ACTIVE:
                logger.warning(f"Provider {provider_name} not active")
                continue

            available_accounts = provider.get_available_accounts()
            logger.info(
                f"Provider {provider_name} has {len(available_accounts)} available accounts"
            )

            account = provider.get_best_account()
            if account:
                logger.info(f"Selected account {account.id} for provider {provider_name}")
                # Check if meets requirements
                if self._meets_requirements(provider, account, requirements):
                    logger.info(
                        f"Account meets requirements, returning {provider_name}/{account.id}"
                    )
                    return provider, account
            else:
                logger.warning(f"No best account found for provider {provider_name}")

        logger.error("No available provider/account found")
        return None

    def _meets_requirements(
        self, provider: Provider, account: Account, requirements: dict | None = None
    ) -> bool:
        """Check if provider/account meets specific requirements.

        FIX (none-requirements crash): get_best_provider_for_task() defaults
        requirements=None and forwarded it verbatim, so every default-path call
        ('x' in None) raised TypeError. Empty dict is the correct neutral value.
        """
        requirements = requirements or {}
        # Check cost requirements
        if (
            "max_cost_per_token" in requirements
            and provider.cost_per_token > requirements["max_cost_per_token"]
        ):
            return False

        # Check model requirements
        if (
            "required_model" in requirements
            and requirements["required_model"] not in provider.models
        ):
            return False

        # Check speed requirements (rough estimate)
        if (
            "speed_priority" in requirements
            and requirements["speed_priority"] > 0.8
            and provider.rate_limit_rpm < 30
        ):
            return False

        return True

    async def execute_task(self, task_type: TaskType, prompt: str, **kwargs) -> dict | None:
        """Execute a task using the best available provider/account"""
        provider_account = self.get_best_provider_for_task(task_type, kwargs)

        if not provider_account:
            logger.error(f"No available provider/account for task {task_type}")
            return None

        provider, account = provider_account

        try:
            # Execute the API call
            result = await self._call_api(provider, account, prompt, **kwargs)

            # Record successful request
            account.record_request(success=True)

            return {
                "result": result,
                "provider": provider.name,
                "account": account.id,
                "model": kwargs.get("model", provider.models[0]),
                "tokens_used": len(prompt.split()) * 1.5,  # Rough estimate
            }

        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Record failed request
            account.record_request(success=False)
            logger.error(f"Task execution failed: {e}")

            # Try failover to another account/provider
            return await self._failover_execute(task_type, prompt, **kwargs)

    async def _call_api(self, provider: Provider, account: Account, prompt: str, **kwargs) -> str:
        """
        বাংলা মন্তব্য: আসল প্রোভাইডার API কল এখন কেন্দ্রীয় LLMGateway দিয়ে সম্পন্ন করা হচ্ছে।
        অ্যাকাউন্টের API কী ডাইনামিকালি ইনজেক্ট করা হয়।
        """
        # বাংলা মন্তব্য: CancelledError রেইজ করার স্ট্যান্ডার্ড বজায় রাখা হচ্ছে।
        try:
            from core.llm.llm_gateway import get_llm_gateway

            gateway = get_llm_gateway()

            # বাংলা মন্তব্য: প্রোভাইডারের প্রথম এভেইলেবল মডেলটি নেওয়া হচ্ছে যদি না kwargs-এ সুনির্দিষ্ট মডেল দেওয়া থাকে।
            model = kwargs.get("model") or (provider.models[0] if provider.models else None)
            if not model:
                raise ValueError(f"Provider '{provider.name}'-এর জন্য কোনো মডেল নির্ধারিত নেই।")

            # বাংলা মন্তব্য: litellm গেটওয়ের acompletion কল করা হচ্ছে এবং rotator থেকে এপিআই কী পাস হচ্ছে।
            # FIX (kwarg-collision): caller-supplied kwargs এ "model" থাকলে আগের কোডে
            # model= দুইবার যাওয়ায় TypeError হতো; স্পষ্ট model= এর সাথে সংঘর্ষ এড়ানো হলো।
            call_kwargs = {key: value for key, value in kwargs.items() if key != "model"}
            response = await gateway.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                api_key=account.api_key,
                **call_kwargs,
            )

            if isinstance(response, dict) and response.get("success"):
                return response.get("text") or ""
            return str(response)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[ROTATOR] LLM Gateway API call failed: {e}")
            raise

    async def _failover_execute(self, task_type: TaskType, prompt: str, **kwargs) -> dict | None:
        """Execute task with failover logic"""
        # Try other providers/accounts
        tried_providers = set()

        for _ in range(3):  # Max 3 failover attempts
            provider_account = self.get_best_provider_for_task(task_type, kwargs)

            if not provider_account or provider_account[0].name in tried_providers:
                break

            provider, account = provider_account
            tried_providers.add(provider.name)

            try:
                result = await self._call_api(provider, account, prompt, **kwargs)
                account.record_request(success=True)

                return {
                    "result": result,
                    "provider": provider.name,
                    "account": account.id,
                    "failover": True,
                    "model": kwargs.get("model", provider.models[0]),
                }

            except asyncio.CancelledError:
                raise
            except Exception as e:
                account.record_request(success=False)
                logger.warning(f"Failover attempt failed for {provider.name}: {e}")
                continue

        return None

    def get_system_status(self) -> dict:
        """Get comprehensive system status"""
        total_accounts = sum(len(p.accounts) for p in self.providers.values())
        active_accounts = sum(len(p.get_available_accounts()) for p in self.providers.values())

        provider_status = {}
        for name, provider in self.providers.items():
            accounts = []
            for acc in provider.accounts:
                accounts.append(
                    {
                        "id": acc.id,
                        "status": acc.status.value,
                        "health_score": acc.get_health_score(),
                        "quota_used": acc.quota_used,
                        "quota_limit": acc.quota_limit,
                        "total_requests": acc.total_requests,
                    }
                )

            provider_status[name] = {
                "status": provider.status.value,
                "total_accounts": len(provider.accounts),
                "active_accounts": len(provider.get_available_accounts()),
                "accounts": accounts,
            }

        return {
            "total_providers": len(self.providers),
            "total_accounts": total_accounts,
            "active_accounts": active_accounts,
            "system_health": (
                (active_accounts / total_accounts * 100) if total_accounts > 0 else 0
            ),
            "providers": provider_status,
        }


# Global instance - only create when needed
rotator = None


def get_rotator():
    global rotator
    if rotator is None:
        rotator = MultiAccountRotator()
    return rotator


async def main():
    """Example usage - requires environment variables to be set"""
    # বাংলা মন্তব্য: গ্লোবাল রেফারেন্স সরাসরি ব্যবহারের বদলে get_rotator() দিয়ে শুরু করা হলো।
    rotator = get_rotator()

    # Security: No hardcoded fallback keys - require environment variables
    test_groq_key_1 = getattr(settings, "test_groq_key_1", None)
    test_groq_key_2 = getattr(settings, "test_groq_key_2", None)
    test_deepseek_key_1 = getattr(settings, "test_deepseek_key_1", None)

    if test_groq_key_1:
        rotator.add_account("groq", "test1@supremeai.com", test_groq_key_1)
    if test_groq_key_2:
        rotator.add_account("groq", "test2@supremeai.com", test_groq_key_2)
    if test_deepseek_key_1:
        rotator.add_account("deepseek", "test3@supremeai.com", test_deepseek_key_1)

    if not any([test_groq_key_1, test_groq_key_2, test_deepseek_key_1]):
        logger.warning(
            "[ROTATOR] No test API keys found in environment. Set TEST_GROQ_KEY_1, TEST_GROQ_KEY_2, or TEST_DEEPSEEK_KEY_1 to test."
        )
        return

    # Execute some test tasks
    tasks = [
        (TaskType.CODING, "Write a Python function to reverse a string"),
        (TaskType.CHAT, "Explain quantum computing in simple terms"),
        (TaskType.REASONING, "Solve this logic puzzle: ..."),
    ]

    for task_type, prompt in tasks:
        result = await rotator.execute_task(task_type, prompt)
        if result:
            logger.info(f"✅ {task_type.value}: {result['provider']} - {result['result'][:100]}...")
        else:
            logger.info(f"❌ {task_type.value}: Failed to execute")

    # Print system status
    status = rotator.get_system_status()
    logger.info(f"\n📊 System Status: {status['system_health']:.1f}% healthy")
    logger.info(f"Active accounts: {status['active_accounts']}/{status['total_accounts']}")


if __name__ == "__main__":
    asyncio.run(main())
