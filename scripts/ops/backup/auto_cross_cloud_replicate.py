# --- Merged from auto_cross_cloud_replicate.py ---

#!/usr/bin/env python
"""
auto_cross_cloud_replicate.py
=============================
Automatically replicates critical Firestore data to secondary cloud providers
for disaster recovery and multi-cloud resilience.

This solution implements a change-data-capture approach using Cloud Functions
to replicate writes to secondary databases, but this script provides the
initial synchronization and ongoing reconciliation capabilities.

Environment Variables:
- PRIMARY_PROJECT_ID: Primary Google Cloud project ID
- SECONDARY_PROJECT_ID: Secondary cloud project ID (AWS/Azure/GCP secondary)
- SECRET_BACKEND: Where to store credentials ('secret_manager', 'env_file', 'vc')
- REPLICATE_COLLECTIONS: Comma-separated list of collections to replicate
- SYNC_INTERVAL_MINUTES: How often to run sync (default: 60)
- BATCH_SIZE: Number of documents to process per batch (default: 500)
- DRY_RUN: If true, only show what would be done (default: false)
"""

import hashlib
import json
import logging
import os
import sys
import time
import urllib.request as _url_req
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from google.oauth2 import service_account

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
PRIMARY_PROJECT_ID = os.getenv("PRIMARY_PROJECT_ID")
SECONDARY_PROJECT_ID = os.getenv("SECONDARY_PROJECT_ID")
SECRET_BACKEND = os.getenv("SECRET_BACKEND", "secret_manager")
REPLICATE_COLLECTIONS_STR = os.getenv("REPLICATE_COLLECTIONS", "")
SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "500"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

def load_secondary_credentials() -> service_account.Credentials | None:
    """Load credentials for the secondary cloud provider."""
    if not SECONDARY_PROJECT_ID:
        print("⚠️  No secondary project configured - running in monitoring mode only")
        return None

    try:
        if SECRET_BACKEND == "secret_manager":
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{SECONDARY_PROJECT_ID}/secrets/firestore-sa-key/versions/latest"
            response = client.access_secret_version(request={"name": name})
            key_data = json.loads(response.payload.data.decode("UTF-8"))
            return service_account.Credentials.from_service_account_info(key_data)
        elif SECRET_BACKEND == "env_file":
            # Load from environment variable containing JSON key
            key_json = os.getenv("SECONDARY_SERVICE_ACCOUNT_KEY")
            if key_json:
                key_data = json.loads(key_json)
                return service_account.Credentials.from_service_account_info(key_data)
        elif SECRET_BACKEND == "vc":
            # Load from Volume-mounted credentials (Kubernetes secret)
            key_path = "/etc/secrets/firestore-sa-key.json"
            if os.path.exists(key_path):
                return service_account.Credentials.from_service_account_file(key_path)
    except Exception as e:
        logger.error(f"Failed to load secondary credentials: {e}")
        return None

    return None

def get_firestore_client(project_id: str, credentials: service_account.Credentials | None = None) -> firestore.Client | None:
    """Get a Firestore client for the specified project."""
    try:
        if credentials:
            return firestore.Client(project=project_id, credentials=credentials)
        else:
            # Use default credentials
            return firestore.Client(project=project_id)
    except Exception as e:
        logger.error(f"Failed to create Firestore client for {project_id}: {e}")
        return None

def calculate_document_hash(doc_data: dict[str, Any]) -> str:
    """Calculate a hash of document data for change detection."""
    # Remove fields that might vary (like timestamps) for consistent hashing
    cleaned_data = {k: v for k, v in doc_data.items()
                   if not k.startswith('_') and not k.endswith('_at')}

    # Sort keys for consistent JSON serialization
    sorted_data = json.dumps(cleaned_data, sort_keys=True, default=str)
    return hashlib.md5(sorted_data.encode()).hexdigest()

def sync_collection_primary_to_secondary(
    primary_client: firestore.Client,
    secondary_client: firestore.Client | None,
    collection_path: str
) -> dict[str, int]:
    """
    Synchronize a collection from primary to secondary database.

    Returns:
        Dict with counts: {'processed': int, 'inserted': int, 'updated': int, 'skipped': int, 'errors': int}
    """
    stats = {'processed': 0, 'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

    if not secondary_client:
        print("⚠️  Secondary client not available - skipping actual replication")
        # Still count for reporting
        collection_ref = primary_client.collection(collection_path)
        docs = collection_ref.limit(BATCH_SIZE).stream()
        for doc in docs:
            stats['processed'] += 1
        return stats

    try:
        collection_ref = primary_client.collection(collection_path)

        # Process in batches
        docs = collection_ref.limit(BATCH_SIZE).stream()

        batch = secondary_client.batch()
        batch_count = 0

        for doc in docs:
            stats['processed'] += 1

            try:
                doc_data = doc.to_dict()
                doc_id = doc.id

                # Calculate hash for change detection
                doc_hash = calculate_document_hash(doc_data)

                # Add hash to metadata for tracking
                doc_data['_sync_metadata'] = {
                    'source_project': 'primary',
                    'synced_at': datetime.now(timezone.utc).isoformat(),
                    'hash': doc_hash
                }

                # Reference to document in secondary
                doc_ref = secondary_client.collection(collection_path).document(doc_id)

                # Check if document exists and has changed
                existing_doc = doc_ref.get()
                if existing_doc.exists:
                    existing_data = existing_doc.to_dict()
                    existing_hash = None
                    if '_sync_metadata' in existing_data and 'hash' in existing_data['_sync_metadata']:
                        existing_hash = existing_data['_sync_metadata']['hash']

                    if existing_hash == doc_hash:
                        stats['skipped'] += 1
                        continue  # No change
                    else:
                        stats['updated'] += 1
                else:
                    stats['inserted'] += 1

                # Add to batch
                batch.set(doc_ref, doc_data)
                batch_count += 1

                # Commit batch when full
                if batch_count >= 100:  # Firestore batch limit is 500, but we'll be conservative
                    if not DRY_RUN:
                        batch.commit()
                    else:
                        print(f"🔍 [DRY RUN] Would commit batch of {batch_count} writes to {collection_path}")
                    batch = secondary_client.batch()
                    batch_count = 0

            except Exception as e:
                logger.error(f"Error processing document {doc.id} in {collection_path}: {e}")
                stats['errors'] += 1

        # Commit remaining items in batch
        if batch_count > 0:
            if not DRY_RUN:
                batch.commit()
            else:
                print(f"🔍 [DRY RUN] Would commit final batch of {batch_count} writes to {collection_path}")

    except Exception as e:
        logger.error(f"Error synchronizing collection {collection_path}: {e}")
        stats['errors'] += 1

    return stats


def send_discord_alert(severity: str, message: str):
    """Send alert to Discord webhook (critical alerts only)."""
    discord_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if severity == "critical" and discord_url:
        payload = json.dumps({"content": f"\U0001f6a8 **Cross-Cloud Replication** | {message}"}).encode()
        req = _url_req.Request(discord_url, data=payload,
                               headers={"Content-Type": "application/json"})
        try:
            _url_req.urlopen(req)
        except Exception as alert_err:
            logger.exception(f"Failed to send Discord alert webhook: {alert_err}")
    logger.log(logging.CRITICAL if severity == "critical" else logging.INFO, message)


def replicate_with_retry(
    primary_client: firestore.Client,
    secondary_client: firestore.Client | None,
    collection: str,
    max_retries: int = 3,
) -> dict[str, int]:
    """
    Retry wrapper for sync_collection_primary_to_secondary.
    Exponential backoff: 1s, 2s, 4s.
    After all retries exhausted, sends a critical Discord alert.
    """
    for attempt in range(max_retries):
        try:
            return sync_collection_primary_to_secondary(
                primary_client, secondary_client, collection
            )
        except Exception as e:
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                f"Replication attempt {attempt + 1}/{max_retries} failed for "
                f"{collection}: {e}. Retrying in {wait}s..."
            )
            if attempt < max_retries - 1:
                time.sleep(wait)

    # All retries exhausted
    send_discord_alert(
        "critical",
        f"Replication FAILED for collection `{collection}` after {max_retries} retries"
    )
    return {'processed': 0, 'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 1}

def main() -> int:
    """Main function to execute cross-cloud replication."""
    print("🔄 Starting Cross-Cloud Replication...")

    # Validate configuration
    if not PRIMARY_PROJECT_ID:
        print("❌ Error: PRIMARY_PROJECT_ID environment variable is not set")
        return 1

    if not SECONDARY_PROJECT_ID:
        print("⚠️  Warning: SECONDARY_PROJECT_ID not set - running in analysis mode only")

    # Parse collections to replicate
    replicate_collections = []
    if REPLICATE_COLLECTIONS_STR:
        replicate_collections = [c.strip() for c in REPLICATE_COLLECTIONS_STR.split(",") if c.strip()]
        print(f"📋 Will replicate collections: {', '.join(replicate_collections)}")
    else:
        print("⚠️  No specific collections specified - will need to implement discovery")
        # For now, we'll need to specify collections
        print("💡 Set REPLICATE_COLLECTIONS environment variable to specify which collections to replicate")
        return 1

    # Initialize clients
    print("🔌 Connecting to primary Firestore...")
    primary_client = get_firestore_client(PRIMARY_PROJECT_ID)
    if not primary_client:
        return 1

    print("🔌 Connecting to secondary Firestore...")
    secondary_credentials = load_secondary_credentials()
    secondary_client = None
    if SECONDARY_PROJECT_ID:
        secondary_client = get_firestore_client(SECONDARY_PROJECT_ID, secondary_credentials)
        if not secondary_client:
            print("⚠️  Warning: Could not connect to secondary - continuing in analysis mode")

    if DRY_RUN:
        print("🔍 RUNNING IN DRY-RUN MODE - No actual changes will be made")

    # Synchronize each collection
    total_stats = {'processed': 0, 'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0}

    for collection_name in replicate_collections:
        print(f"\n\U0001f4ca Synchronizing collection: {collection_name}")
        stats = replicate_with_retry(
            primary_client,
            secondary_client,
            collection_name
        )

        # Accumulate stats
        for key in total_stats:
            total_stats[key] += stats.get(key, 0)

        print(f"   📈 Processed: {stats['processed']}, Inserted: {stats['inserted']}, "
              f"Updated: {stats['updated']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")

    # Print summary
    print("\n📊 Synchronization Summary:")
    print(f"   📄 Total processed: {total_stats['processed']}")
    print(f"   ➕ Total inserted: {total_stats['inserted']}")
    print(f"   🔄 Total updated: {total_stats['updated']}")
    print(f"   ⏭️  Total skipped: {total_stats['skipped']}")
    print(f"   ❌ Total errors: {total_stats['errors']}")

    if total_stats['errors'] > 0:
        print("\n⚠️  Some errors occurred during synchronization - check logs for details")
        return 1
    elif DRY_RUN:
        print("\n✅ Dry run completed successfully - no changes made")
        return 0
    else:
        print("\n✅ Synchronization completed successfully!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
