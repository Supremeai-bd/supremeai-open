#!/usr/bin/env python
"""
auto_seed.py
============
Automatic database seeder for SupremeAI 2.0.

Seeds the database with initial data such as:
- Default skills
- Admin user (if not exists)
- Default configuration
- Free tier provider limits (if applicable)

This script should be idempotent - safe to run multiple times.
"""

import os
import sys
from pathlib import Path

# Add the backend directory to the path so we can import from core
backend_dir = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

def seed_database() -> None:
    """Seed the database with initial data."""
    try:
        # Import the necessary modules from your application
        # This will depend on your actual ORM and setup
        # For example, if using SQLAlchemy:
        from core.database import SessionLocal, init_db
        from core.security import get_password_hash
        from models.admin import User

        # from core.models import Skill # Assuming Skill exists somewhere else or comment out if not real
        from models.system_config import SystemConfig

        # Initialize database connection
        db = SessionLocal()

        try:
            # Check if we already have an admin user
            admin_email = os.getenv("ADMIN_EMAIL", None)
            admin_user = db.query(User).filter(User.email == admin_email).first()
            if not admin_user:
                # Create admin user
                admin_user = User(
                    email=admin_email,
                    hashed_password=get_password_hash("SecureRandomPassword123!"),  # Should be changed on first login
                    is_admin=True,
                    is_active=True
                )
                db.add(admin_user)
                print("✅ Created admin user")
            else:
                print("ℹ️ Admin user already exists")

            # Seed default configuration
            config_count = db.query(SystemConfig).count()
            if config_count == 0:
                default_configs = [
                    {"key": "system_maintenance_mode", "value": False, "description": "Whether the system is in maintenance mode", "category": "system"},
                    {"key": "max_concurrent_requests", "value": 100, "description": "Maximum number of concurrent requests", "category": "system"},
                    
                    # Rate Limit Tiers (requests per minute)
                    {"key": "rate_limit_anonymous", "value": {"limit": 10, "window": 60}, "description": "Anonymous user rate limit", "category": "rate_limits"},
                    {"key": "rate_limit_authenticated", "value": {"limit": 60, "window": 60}, "description": "Authenticated user rate limit", "category": "rate_limits"},
                    {"key": "rate_limit_premium", "value": {"limit": 300, "window": 60}, "description": "Premium user rate limit", "category": "rate_limits"},
                    {"key": "rate_limit_admin", "value": {"limit": 1000, "window": 60}, "description": "Admin rate limit", "category": "rate_limits"},
                    
                    # Rate Limit Overrides
                    {"key": "rate_limit_override_chat_stream", "value": {"limit": 30, "window": 60}, "description": "Rate limit for /api/chat/stream", "category": "rate_limits"},
                    {"key": "rate_limit_override_ai_generate", "value": {"limit": 20, "window": 60}, "description": "Rate limit for /api/ai/generate", "category": "rate_limits"},
                    {"key": "rate_limit_override_browser_scrape", "value": {"limit": 5, "window": 60}, "description": "Rate limit for /api/browser/scrape", "category": "rate_limits"},
                    
                    # Retry Budget
                    {"key": "retry_budget_max_tokens", "value": 20, "description": "Max tokens for retry budget", "category": "retry_budget"},
                    {"key": "retry_budget_refill_rate", "value": 1.0, "description": "Refill rate per sec for retry budget", "category": "retry_budget"},
                    
                    # LLM Configurations
                    {"key": "llm_max_tokens_video", "value": 1500, "description": "Max tokens for Video to Code Pipeline", "category": "llm_config"},
                    {"key": "llm_max_tokens_diagram", "value": 1500, "description": "Max tokens for Diagram Parser", "category": "llm_config"},
                    {"key": "self_improve_max_tokens", "value": {"max_tokens": 2048, "temperature": 0.2}, "description": "Params for Self Improvement Agent", "category": "llm_config"},
                    {"key": "swarm_max_tokens", "value": {"max_tokens": 1024, "temperature": 0.3}, "description": "Params for Swarm Coordination", "category": "llm_config"},
                    {"key": "daily_learner_max_tokens", "value": {"max_tokens": 2000, "temperature": 0.3}, "description": "Params for Daily Learner", "category": "llm_config"},
                    {"key": "guardian_ai_temperature", "value": {"temperature": 0.0}, "description": "Params for Guardian AI", "category": "llm_config"},
                ]
                for config_data in default_configs:
                    config = SystemConfig(**config_data)
                    db.add(config)
                print(f"✅ Seeded {len(default_configs)} default configurations")
            else:
                print(f"ℹ️ Skipping seed - {config_count} configurations already exist")

            # Commit all changes
            db.commit()
            print("✅ Database seeding completed successfully")

        except Exception as e:
            db.rollback()
            print(f"❌ Error during seeding: {e}")
            raise
        finally:
            db.close()

    except ImportError as e:
        print(f"❌ Failed to import application modules: {e}")
        print("Make sure you're running this from the project root and the backend is in your PYTHONPATH")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    seed_database()
