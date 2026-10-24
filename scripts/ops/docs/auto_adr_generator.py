#!/usr/bin/env python
"""
auto_adr_generator.py
=====================
Automatically generates Architecture Decision Records (ADRs) from pull request descriptions.

Creates ADR files in the docs/00-10/adr/ directory following the Michael Nygard template.
Triggered by GitHub Actions when PRs are labeled with 'architecture' or similar.

Environment Variables:
- GITHUB_TOKEN: GitHub API token for accessing PR data
- REPOSITORY: Owner/Repo format (e.g., supremeai/supremeai_2.0)
- ADR_DIR: Directory to store ADRs (default: docs/00-10/adr)
- PULL_REQUEST: PR number (when called bytester (optional, for testing)
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPOSITORY = os.getenv("REPOSITORY")
ADR_DIR = os.getenv("ADR_DIR", "docs/00-10/adr")
PR_NUMBER = os.getenv("PULL_REQUEST")  # For testing or manual trigger

# ADR Template based on Michael Nygard's format
ADR_TEMPLATE = """# {ADR_ID}: {title}

## Status
{status}

## Context
{context}

## Decision
{decision}

## Consequences
### Positive
{positive}

### Negative
{negative}

## Related
{related}

## Notes
*Created on {date}*
*Source: PR #{pr_number} - "{pr_title}"*
"""

def get_next_adr_id() -> str:
    """Get the next ADR ID based on existing files."""
    adr_path = Path(ADR_DIR)
    if not adr_path.exists():
        adr_path.mkdir(parents=True)
        return "0001"

    # Find existing ADRs and get the highest number
    existing_ids = []
    for file in adr_path.glob("[0-9]*.md"):
        try:
            num = int(file.stem.split('-')[0])
            existing_ids.append(num)
        except ValueError:
            continue

    next_num = max(existing_ids) + 1 if existing_ids else 1
    return f"{next_num:04d}"

def fetch_pr_data(pr_number: int) -> dict[str, Any] | None:
    """Fetch pull request data from GitHub API."""
    if not GITHUB_TOKEN or not REPOSITORY:
        logger.error("Missing GITHUB_TOKEN or REPOSITORY environment variables")
        return None

    url = f"https://api.github.com/repos/{REPOSITORY}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch PR #{pr_number}: {e}")
        return None

def extract_adr_info_from_pr(pr_data: dict[str, Any]) -> dict[str, str]:
    """Extract ADR information from PR title and description."""
    title = pr_data.get("title", "")
    body = pr_data.get("body", "") or ""

    # Parse title for ADR format: "ADR: title" or "[ADR] title"
    adr_title = title
    adr_prefixes = ["adr:", "[adr]", "architecture decision record:"]
    for prefix in adr_prefixes:
        if title.lower().startswith(prefix):
            adr_title = title[len(prefix):].strip()
            break

    # Parse body sections
    sections = {
        "context": "Not specified",
        "decision": "Not specified",
        "consequences": {
            "positive": "Not specified",
            "negative": "Not specified"
        },
        "related": "None",
        "status": "Proposed"
    }

    # Look for common section headers in the PR body
    section_patterns = {
        "context": r"##?\s*(?:Context|Background|Problem Statement)\s*\n+(.*?)(?=\n##|\Z)",
        "decision": r"##?\s*(?:Decision|Decision Summary|What we decided)\s*\n+(.*?)(?=\n##|\Z)",
        "positive": r"##?\s*(?:Positive Consequences?|Benefits?|Pros)\s*\n+(.*?)(?=\n##|\Z)",
        "negative": r"##?\s*(?:Negative Consequences?|Drawbacks?|Cons)\s*\n+(.*?)(?=\n##|\Z)",
        "related": r"##?\s*(?:Related|Related Decisions?|References?)\s*\n+(.*?)(?=\n##|\Z)",
        "status": r"##?\s*(?:Status|Status\s*[:\-]?)\s*\n+(.*?)(?=\n##|\Z)"
    }

    for key, pattern in section_patterns.items():
        match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            if content:
                if key in ["positive", "negative"]:
                    sections["consequences"][key] = content
                else:
                    sections[key] = content

    # If no structured sections found, use the whole body as context
    if sections["context"] == "Not specified" and body.strip():
        sections["context"] = body.strip()[:500] + ("..." if len(body.strip()) > 500 else "")

    return {
        "title": adr_title or "Architecture Decision from PR",
        "context": sections["context"],
        "decision": sections["decision"],
        "positive": sections["consequences"]["positive"],
        "negative": sections["consequences"]["negative"],
        "related": sections["related"],
        "status": sections["status"].title() or "Proposed"
    }

def generate_adr(adr_id: str, adr_info: dict[str, str], pr_data: dict[str, Any]) -> str:
    """Generate ADR content from template."""
    return ADR_TEMPLATE.format(
        ADR_ID=adr_id,
        title=adr_info["title"],
        status=adr_info["status"],
        context=adr_info["context"],
        decision=adr_info["decision"],
        positive=adr_info["positive"],
        negative=adr_info["negative"],
        related=adr_info["related"],
        date=datetime.now().strftime("%Y-%m-%d"),
        pr_number=pr_data.get("number", "unknown"),
        pr_title=pr_data.get("title", "Unknown PR")
    )

def save_adr(adr_id: str, content: str, title: str = "adr") -> Path:
    """Save ADR to file."""
    adr_path = Path(ADR_DIR)
    adr_path.mkdir(parents=True, exist_ok=True)

    # Create filename: 0001-title.md
    # Clean title for filename: lowercase, spaces to dashes, remove special chars
    title_slug = re.sub(r'[^\w\s-]', '', title.lower())
    title_slug = re.sub(r'[-\s]+', '-', title_slug).strip('-')

    filename = f"{adr_id}-{title_slug[:50]}.md"  # Limit length
    filepath = adr_path / filename

    filepath.write_text(content, encoding="utf-8")
    return filepath

def main() -> int:
    """Main function to generate ADR from PR."""
    print("📝 Starting ADR generation from pull request...")

    # Determine PR number to process
    pr_number = None
    if PR_NUMBER:
        try:
            pr_number = int(PR_NUMBER)
            print(f"📌 Using PR number from environment: #{pr_number}")
        except ValueError:
            print(f"❌ Invalid PULL_REQUEST number: {PR_NUMBER}")
            return 1
    else:
        # Try to get from GitHub event (when run via GitHub Actions)
        github_event_path = os.getenv("GITHUB_EVENT_PATH")
        if github_event_path and os.path.exists(github_event_path):
            try:
                with open(github_event_path, 'r') as f:
                    event_data = json.load(f)
                if "pull_request" in event_data:
                    pr_number = event_data["pull_request"]["number"]
                    print(f"📌 Got PR number from GitHub event: #{pr_number}")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"⚠️  Could not parse GitHub event: {e}")

    if not pr_number:
        print("❌ No PR number specified. Set PULL_REQUEST environment variable or run via GitHub Actions.")
        return 1

    # Fetch PR data
    print(f"🔍 Fetching data for PR #{pr_number}...")
    pr_data = fetch_pr_data(pr_number)
    if not pr_data:
        return 1

    print(f"📋 Processing PR: {pr_data['title']}")

    # Extract ADR information
    adr_info = extract_adr_info_from_pr(pr_data)

    # Get next ADR ID
    adr_id = get_next_adr_id()
    print(f"🆔 Assigning ADR ID: {adr_id}")

    # Generate ADR content
    adr_content = generate_adr(adr_id, adr_info, pr_data)

    # Save ADR file
    try:
        filepath = save_adr(adr_id, adr_content, adr_info.get("title", "adr"))
        print(f"✅ ADR saved to: {filepath}")
        print(f"📄 ADR {adr_id}: {adr_info['title']}")
        return 0
    except Exception as e:
        print(f"❌ Failed to save ADR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
