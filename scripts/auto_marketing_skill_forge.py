#!/usr/bin/env python
"""
auto_marketing_skill_forge.py
=============================
Automatically creates marketing-related skills based on user demand.

Monitors a Firestore collection for skill requests matching marketing platforms
and triggers the skill forging endpoint to generate new skills.

Environment Variables:
- GOOGLE_CLOUD_PROJECT: Google Cloud project ID
- FIREBASE_DATABASE_URL: Firebase Realtime Database URL (if using RTDB)
  OR FIRESTORE_DATABASE_ID: Firestore database ID
- SUPREMEAI_API_BASE_URL: Base URL for the SupremeAI API (default: http://localhost:8000)  # is_local()
- SUPREMEAI_API_KEY: API key for authenticating to the internal API
- POLL_INTERVAL_SECONDS: How often to check for new requests (default: 300)
- MARKETING_PLATFORMS: Comma-separated list of platforms to watch for
  (default: twitter,instagram,facebook,linkedin,tiktok,youtube)
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests

# Add the backend directory to the path
backend_dir = os.path.join(os.path.dirname(__file__), '../../../backend')
sys_path_added = False
if backend_dir not in sys.path:
    sys.path.append(backend_dir)
    sys_path_added = True

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    print(r"⚠️  Firebase Admin SDK not installed. Install with: pip install firebase-admin")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
FIREBASE_DATABASE_ID = os.getenv("FIRESTORE_DATABASE_ID")  # Optional, defaults to project ID
API_BASE_URL = os.getenv("SUPREMEAI_API_BASE_URL", "http://localhost:8000")  # is_local()
API_KEY = os.getenv("SUPREMEAI_API_KEY")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))  # 5 minutes
MARKETING_PLATFORMS = os.getenv(
    "MARKETING_PLATFORMS",
    "twitter,instagram,facebook,linkedin,tiktok,youtube"
).lower().split(",")

# Collection names
REQUESTS_COLLECTION = "skill_requests"
PROCESSED_COLLECTION = "processed_skill_requests"

def initialize_firebase() -> firestore.Client | None:
    """Initialize Firebase Admin SDK and return Firestore client."""
    if not FIREBASE_AVAILABLE:
        logger.error("Firebase SDK not available")
        return None

    try:
        # Check if already initialized
        firebase_admin.get_app()
    except ValueError:
        # Initialize with application default credentials
        cred = credentials.ApplicationDefault()
        options = {}
        if PROJECT_ID:
            options['projectId'] = PROJECT_ID
        if FIREBASE_DATABASE_ID:
            options['databaseId'] = FIREBASE_DATABASE_ID

        firebase_admin.initialize_app(cred, options)

    return firestore.client()

def get_pending_requests(db: firestore.Client) -> list[dict]:
    """
    Fetch pending skill requests that match marketing platforms.

    Returns a list of request documents that need processing.
    """
    try:
        # Check if already initialized
        firebase_admin.get_app()
    except ValueError:
        # Initialize with application default credentials
        cred = credentials.ApplicationDefault()
        options = {}
        if PROJECT_ID:
            options['projectId'] = PROJECT_ID
        if FIREBASE_DATABASE_ID:
            options['databaseId'] = FIREBASE_DATABASE_ID

        firebase_admin.initialize_app(cred, options)
    return firestore.client()

def forge_skill(request_data: dict) -> bool:
    """
    Call the skill forging API to create a new skill based on the request.

    Args:
        request_data: The request document data

    Returns:
        True if successful, False otherwise
    """
    try:
        # Prepare the payload for the forge endpoint
        # Based on the user's example: /api/evolution/forge
        payload = {
            "skill_name": f"{request_data.get('platform', 'unknown')}_marketing_bot",
            "user_demand": request_data.get('description',
                                          f"Create a {request_data.get('platform')} marketing automation skill"),
            "category": "marketing",
            # সিনট্যাক্স এরর ঠিক করা হয়েছে এবং ইউনিকোড সাপোর্ট নিশ্চিত করা হয়েছে
            "platform": request_data.get('platform'),
            "requested_by": request_data.get('user_id', 'anonymous'),
            "priority": request_data.get('priority', 'medium')
        }

        # Make the API call
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}" if API_KEY else ""
        }

        url = f"{API_BASE_URL}/api/evolution/forge"
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if response.status_code == 200:
            result = response.json()
            logger.info(f"Successfully forged skill: {result.get('skill_name')}")
            return True
        else:
            logger.error(f"Failed to forge skill. Status: {response.status_code}, Response: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Network error when forging skill: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error when forging skill: {e}")
        return False

def mark_request_as_processed(db: firestore.Client, request_id: str, success: bool) -> None:
    """
    Move the request to the processed collection and update the original with status.

    Args:
        db: Firestore client
        request_id: The ID of the request document
        success: Whether the forging was successful
    """
    try:
        # Get the original document
        doc_ref = db.collection(REQUESTS_COLLECTION).document(request_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.warning(f"Request document {request_id} not found")
            return

        # Prepare update data
        update_data = {
            "processed_at": datetime.now(timezone.utc),
            "processed_success": success,
            "processing_log": f"Skill forging attempted at {datetime.now(timezone.utc).isoformat()}"
        }

        if success:
            update_data["status"] = "completed"
        else:
            update_data["status"] = "failed"

        # Update the original document
        doc_ref.update(update_data)

        # Optionally, copy to processed collection for audit
        # processed_ref = db.collection(PROCESSED_COLLECTION).document(request_id)
        # processed_ref.set(doc.to_dict() | update_data)

        logger.info(f"Marked request {request_id} as {'success' if success else 'failed'}")

    except Exception as e:
        logger.error(f"Error marking request {request_id} as processed: {e}")

def main() -> None:
    """Main loop that polls for requests and processes them."""
    if not PROJECT_ID:
        print(r"❌ Error: GOOGLE_CLOUD_PROJECT environment variable is not set")
        return

    if not API_KEY:
        print(r"⚠️  Warning: SUPREMEAI_API_KEY not set - API calls may fail")

    print(r"🤖 Starting Marketing Skill Forger")
    print(fr"📊 Monitoring for platforms: {', '.join(MARKETING_PLATFORMS)}")
    print(fr"⏱️  Polling interval: {POLL_INTERVAL} seconds")
    print(fr"🔗 API endpoint: {API_BASE_URL}/api/evolution/forge")

    # Initialize Firebase
    db = initialize_firebase()
    if not db:
        print(r"❌ Failed to initialize Firebase. Exiting.")
        return

    print(r"✅ Firebase initialized successfully")

    try:
        while True:
            print(fr"\n🔍 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new requests...")

            # Get pending requests
            pending_requests = get_pending_requests(db)

            if not pending_requests:
                print(r"📭 No pending requests found")
            else:
                print(fr"📥 Found {len(pending_requests)} pending request(s)")

                for request in pending_requests:
                    request_id = request.get('doc_id')
                    platform = request.get('platform', 'unknown')
                    print(fr"  ⚙️  Processing request {request_id} for platform '{platform}'")

                    # Attempt to forge the skill
                    success = forge_skill(request)

                    # Mark the request as processed
                    mark_request_as_processed(db, request_id, success)

                    if success:
                        print(fr"  ✅ Successfully processed request {request_id}")
                    else:
                        print(fr"  ❌ Failed to process request {request_id}")

            # Wait for the next poll
            print(fr"😴 Sleeping for {POLL_INTERVAL} seconds...")
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print(r"\nCtrl+C received. Shutting down gracefully...")
    except Exception as e:
        print(fr"💥 Unexpected error: {e}")
        raise

if __name__ == "__main__":
    main()
