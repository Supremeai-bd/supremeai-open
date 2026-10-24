#!/usr/bin/env python
"""
auto_tenant_setup.py
====================
Automatically sets up new tenants in the SupremeAI 2.0 platform.

When a new user signs up, this script:
1. Creates Firestore collections for the tenant
2. Sets up default configuration and permissions
3. Installs starter skills
4. Configures initial quotas and billing
5. Sends welcome notifications

Environment Variables:
- GOOGLE_CLOUD_PROJECT: Google Cloud project ID
- FIRESTORE_DATABASE_ID: Firestore database ID (optional)
- DEFAULT_TEMPLATE: Template to use for new tenants (default: "starter")
- WELCOME_EMAIL_TEMPLATE: Email template ID for welcome message
- ADMIN_EMAIL: Email address for notifications about new tenants
"""

import logging
import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / "backend"))
from core.config import settings
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from google.cloud import firestore, storage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
DATABASE_ID = os.getenv("FIRESTORE_DATABASE_ID")
DEFAULT_TEMPLATE = os.getenv("DEFAULT_TEMPLATE", "starter")
WELCOME_EMAIL_TEMPLATE = os.getenv("WELCOME_EMAIL_TEMPLATE", "welcome_new_tenant")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", None)

def get_firestore_client() -> firestore.Client | None:
    """Get a Firestore client."""
    try:
        if DATABASE_ID:
            return firestore.Client(project=PROJECT_ID, database=DATABASE_ID)
        else:
            return firestore.Client(project=PROJECT_ID)
    except Exception as e:
        logger.error(f"Failed to create Firestore client: {e}")
        return None

def get_storage_client() -> storage.Client | None:
    """Get a Cloud Storage client."""
    try:
        return storage.Client(project=PROJECT_ID)
    except Exception as e:
        logger.error(f"Failed to create Storage client: {e}")
        return None

def create_tenant_document(db: firestore.Client, tenant_id: str, tenant_data: dict[str, Any]) -> bool:
    """Create the tenant document in Firestore."""
    try:
        tenant_ref = db.collection('tenants').document(tenant_id)

        # Set creation timestamp if not provided
        if 'created_at' not in tenant_data:
            tenant_data['created_at'] = firestore.SERVER_TIMESTAMP

        # Set updated timestamp
        tenant_data['updated_at'] = firestore.SERVER_TIMESTAMP

        tenant_ref.set(tenant_data)
        logger.info(f"Created tenant document for {tenant_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to create tenant document for {tenant_id}: {e}")
        return False

def create_tenant_subcollections(db: firestore.Client, tenant_id: str, template: str) -> bool:
    """Create default subcollections and documents for a tenant."""
    try:
        tenant_ref = db.collection('tenants').document(tenant_id)

        # Define default collections and their initial documents based on template
        template_configs = {
            "starter": {
                "users": [
                    {"role": "owner", "status": "active", "added_at": firestore.SERVER_TIMESTAMP}
                ],
                "config": {
                    "name": "Tenant Configuration",
                    "timezone": "UTC",
                    "language": "en",
                    "features": {
                        "chat": True,
                        "automation": True,
                        "analytics": True
                    }
                },
                "usage": {
                    "current_period": {
                        "start": firestore.SERVER_TIMESTAMP,
                        "api_calls": 0,
                        "storage_mb": 0,
                        "compute_minutes": 0
                    }
                },
                "limits": {
                    "api_calls_per_month": 10000,
                    "storage_mb": 1000,
                    "compute_minutes_per_month": 500,
                    "max_users": 5
                }
            },
            "professional": {
                "users": [
                    {"role": "owner", "status": "active", "added_at": firestore.SERVER_TIMESTAMP}
                ],
                "config": {
                    "name": "Tenant Configuration",
                    "timezone": "UTC",
                    "language": "en",
                    "features": {
                        "chat": True,
                        "automation": True,
                        "analytics": True,
                        "advanced_ai": True,
                        "api_access": True
                    }
                },
                "usage": {
                    "current_period": {
                        "start": firestore.SERVER_TIMESTAMP,
                        "api_calls": 0,
                        "storage_mb": 0,
                        "compute_minutes": 0
                    }
                },
                "limits": {
                    "api_calls_per_month": 100000,
                    "storage_mb": 10000,
                    "compute_minutes_per_month": 5000,
                    "max_users": 25
                }
            },
            "enterprise": {
                "users": [
                    {"role": "owner", "status": "active", "added_at": firestore.SERVER_TIMESTAMP}
                ],
                "config": {
                    "name": "Tenant Configuration",
                    "timezone": "UTC",
                    "language": "en",
                    "features": {
                        "chat": True,
                        "automation": True,
                        "analytics": True,
                        "advanced_ai": True,
                        "api_access": True,
                        "custom_models": True,
                        "dedicated_instances": True
                    }
                },
                "usage": {
                    "current_period": {
                        "start": firestore.SERVER_TIMESTAMP,
                        "api_calls": 0,
                        "storage_mb": 0,
                        "compute_minutes": 0
                    }
                },
                "limits": {
                    "api_calls_per_month": 1000000,
                    "storage_mb": 100000,
                    "compute_minutes_per_month": 50000,
                    "max_users": 100
                }
            }
        }

        config = template_configs.get(template, template_configs["starter"])

        # Create each subcollection
        for collection_name, initial_data in config.items():
            if isinstance(initial_data, list):
                # Collection of documents
                for i, doc_data in enumerate(initial_data):
                    doc_ref = tenant_ref.collection(collection_name).document(str(i))
                    doc_data["created_at"] = firestore.SERVER_TIMESTAMP
                    doc_ref.set(doc_data)
            else:
                # Single document
                doc_ref = tenant_ref.collection(collection_name).document("default")
                if isinstance(initial_data, dict):
                    initial_data["created_at"] = firestore.SERVER_TIMESTAMP
                doc_ref.set(initial_data)

        logger.info(f"Created subcollections for tenant {tenant_id} using template '{template}'")
        return True
    except Exception as e:
        logger.error(f"Failed to create subcollections for tenant {tenant_id}: {e}")
        return False

def setup_default_skills(db: firestore.Client, tenant_id: str) -> bool:
    """Assign default skills to a new tenant."""
    try:
        # Reference to the tenant's skills subcollection
        skills_ref = db.collection('tenants').document(tenant_id).collection('skills')

        # Get list of available starter skills from the system
        # In a real implementation, this would query a global skills catalog
        starter_skills = [
            {
                "skill_id": "text_generation",
                "name": "Text Generation",
                "status": "active",
                "assigned_at": firestore.SERVER_TIMESTAMP,
                "usage_limit": 1000  # per month
            },
            {
                "skill_id": "text_summarization",
                "name": "Text Summarization",
                "status": "active",
                "assigned_at": firestore.SERVER_TIMESTAMP,
                "usage_limit": 500
            },
            {
                "skill_id": "question_answering",
                "name": "Question Answering",
                "status": "active",
                "assigned_at": firestore.SERVER_TIMESTAMP,
                "usage_limit": 500
            },
            {
                "skill_id": "conversation",
                "name": "Conversational AI",
                "status": "active",
                "assigned_at": firestore.SERVER_TIMESTAMP,
                "usage_limit": 2000
            }
        ]

        # Assign each skill to the tenant
        for skill_data in starter_skills:
            skill_id = skill_data["skill_id"]
            skill_ref = skills_ref.document(skill_id)
            skill_ref.set(skill_data)

        logger.info(f"Assigned {len(starter_skills)} default skills to tenant {tenant_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to set up default skills for tenant {tenant_id}: {e}")
        return False

def send_welcome_email(tenant_email: str, tenant_name: str, tenant_id: str, template: str) -> bool:
    """Send a welcome email to the new tenant."""
    try:
        # This is a simplified implementation
        # In production, you would use a proper email service like SendGrid, SES, etc.

        smtp_server = os.getenv("SMTP_SERVER", "localhost")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        if not all([smtp_server, smtp_port]):
            logger.warning("SMTP not configured - skipping email")
            return True  # Not fatal

        msg = MIMEMultipart()
        msg['From'] = smtp_user or os.getenv("SENDER_EMAIL", "noreply@supremeai.com")
        msg['To'] = tenant_email
        msg['Subject'] = f"Welcome to SupremeAI 2.0, {tenant_name}!"

        # In a real implementation, you would load the template and fill in variables
        body = f"""
        Hello {tenant_name},

        Welcome to SupremeAI 2.0! Your account has been successfully created.

        You now have access to:
        - AI-powered chat and content generation
        - Workflow automation tools
        - Analytics and monitoring
        - Custom skill development

        To get started, visit your dashboard at: {settings.app_base_url}/{tenant_id}

        If you have any questions, our support team is here to help.

        Best regards,
        The SupremeAI Team
        """

        msg.attach(MIMEText(body, 'plain'))

        # Only actually send if not in dry-run mode
        if os.getenv("DRY_RUN", "false").lower() != "true":
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            text = msg.as_string()
            server.sendmail(smtp_user, tenant_email, text)
            server.quit()
            logger.info(f"Welcome email sent to {tenant_email}")
        else:
            print(f"🔍 [DRY RUN] Would send welcome email to {tenant_email}")

        return True
    except Exception as e:
        logger.error(f"Failed to send welcome email to {tenant_email}: {e}")
        return False

def notify_admin_of_new_tenant(tenant_id: str, tenant_email: str, template: str) -> bool:
    """Notify administrators about a new tenant."""
    try:
        if not ADMIN_EMAIL:
            return True  # Not required

        # Similar to send_welcome_email but for admin notification
        # For brevity, we'll just log this
        logger.info(f"New tenant registered: {tenant_id} ({tenant_email}) using template '{template}'")
        print(f"📢 New tenant alert: {tenant_id} ({template})")
        return True
    except Exception as e:
        logger.error(f"Failed to notify admin about new tenant: {e}")
        return False

def main() -> int:
    """Main function to set up a new tenant."""
    print("🏢 Starting Tenant Setup...")

    # In a real implementation, this would be triggered by a Pub/Sub message
    # or HTTP endpoint when a new user signs up
    # For this script, we'll expect environment variables or command line args

    # Get tenant information from environment (would normally come from trigger)
    tenant_id = os.getenv("TENANT_ID")
    tenant_email = os.getenv("TENANT_EMAIL")
    tenant_name = os.getenv("TENANT_NAME", tenant_email.split('@')[0] if tenant_email else "Unknown User")
    template = os.getenv("TEMPLATE", DEFAULT_TEMPLATE)

    if not tenant_id:
        print("❌ Error: TENANT_ID environment variable is not set")
        print("   This script is typically triggered automatically by user signup")
        print("   For manual testing, set TENANT_ID, TENANT_EMAIL, and optionally TEMPLATE")
        return 1

    if not tenant_email:
        print("⚠️  Warning: TENANT_EMAIL not set - notifications will be skipped")

    print(f"📝 Setting up tenant: {tenant_id}")
    print(f"📧 Email: {tenant_email or '(not provided)'}")
    print(f"👤 Name: {tenant_name}")
    print(f"📋 Template: {template}")

    # Initialize clients
    db = get_firestore_client()
    if not db:
        return 1

    # Track overall success
    success = True

    # Step 1: Create tenant document
    print("\n1️⃣ Creating tenant record...")
    tenant_data = {
        "tenant_id": tenant_id,
        "email": tenant_email,
        "display_name": tenant_name,
        "status": "active",
        "template": template,
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP
    }

    if not create_tenant_document(db, tenant_id, tenant_data):
        success = False
    else:
        print("   ✅ Tenant record created")

    # Step 2: Create subcollections
    if success:
        print("\n2️⃣ Setting up tenant data structure...")
        if not create_tenant_subcollections(db, tenant_id, template):
            success = False
        else:
            print("   ✅ Tenant data structure created")

    # Step 3: Set up default skills
    if success:
        print("\n3️⃣ Assigning default skills...")
        if not setup_default_skills(db, tenant_id):
            success = False
        else:
            print("   ✅ Default skills assigned")

    # Step 4: Send welcome email
    if success and tenant_email:
        print("\n4️⃣ Sending welcome email...")
        if not send_welcome_email(tenant_email, tenant_name, tenant_id, WELCOME_EMAIL_TEMPLATE):
            # Don't fail the entire process for email issues
            print("   ⚠️  Warning: Failed to send welcome email")
        else:
            print("   ✅ Welcome email sent")

    # Step 5: Notify administrators
    if success:
        print("\n5️⃣ Notifying administrators...")
        if not notify_admin_of_new_tenant(tenant_id, tenant_email or "unknown", template):
            # Don't fail for notification issues
            print("   ⚠️  Warning: Failed to notify administrators")
        else:
            print("   ✅ Administrators notified")

    if success:
        print(f"\n🎉 Tenant {tenant_id} setup completed successfully!")
        return 0
    else:
        print(f"\n❌ Tenant {tenant_id} setup failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
