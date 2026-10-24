

# --- Merged from base_scraper.py ---

"""
Base scraper class for SupremeAI resource collection
Provides common functionality for scraping various awesome lists and resource sites
"""

import json
import logging
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any


class BaseResourceScraper(ABC):
    """Base class for all resource scrapers"""

    def __init__(self, name: str, data_dir: Path):
        self.name = name
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Set up logging for the scraper"""
        logger = logging.getLogger(f"scraper.{self.name}")
        logger.setLevel(logging.INFO)

        # Create file handler
        log_file = self.data_dir / f"{self.name}.log"
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.INFO)

        # Create console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        # Add handlers if not already added
        if not logger.handlers:
            logger.addHandler(fh)
            logger.addHandler(ch)

        return logger

    @abstractmethod
    def fetch_data(self) -> Any:
        """Fetch raw data from the source"""

    @abstractmethod
    def parse_data(self, raw_data: Any) -> list[dict[str, Any]]:
        """Parse raw data into standardized format"""

    def save_data(self, data: list[dict[str, Any]], filename: str | None = None) -> Path:
        """Save parsed data to JSON file"""
        if filename is None:
            filename = f"{self.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = self.data_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved {len(data)} items to {filepath}")
        return filepath

    def load_latest_data(self) -> list[dict[str, Any]] | None:
        """Load the most recently saved data file"""
        json_files = list(self.data_dir.glob(f"{self.name}_*.json"))
        if not json_files:
            return None

        # Sort by modification time, get latest
        latest_file = max(json_files, key=lambda f: f.stat().st_mtime)

        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.logger.info(f"Loaded {len(data)} items from {latest_file}")
            return data
        except Exception as e:
            self.logger.error(f"Failed to load data from {latest_file}: {e}")
            return None

    def run(self) -> Path | None:
        """Execute the full scraping process"""
        try:
            self.logger.info(f"Starting scrape for {self.name}")
            start_time = time.time()

            # Fetch raw data
            raw_data = self.fetch_data()
            if raw_data is None:
                self.logger.error("Failed to fetch data")
                return None

            # Parse data
            parsed_data = self.parse_data(raw_data)
            if not parsed_data:
                self.logger.warning("No data parsed from source")
                return None

            # Save data
            filepath = self.save_data(parsed_data)

            elapsed_time = time.time() - start_time
            self.logger.info(f"Scrape completed in {elapsed_time:.2f} seconds")

            return filepath

        except Exception as e:
            self.logger.error(f"Error during scrape: {e}", exc_info=True)
            return None


class AwesomeListScraper(BaseResourceScraper):
    """Scraper for awesome-* lists on GitHub"""

    def __init__(self, name: str, repo_url: str, data_dir: Path):
        super().__init__(name, data_dir)
        self.repo_url = repo_url
        self.readme_url = f"{repo_url.replace('github.com', 'raw.githubusercontent.com')}/master/README.md"

    def fetch_data(self) -> str | None:
        """Fetch README.md from GitHub"""
        try:
            self.logger.info(f"Fetching README from {self.readme_url}")
            with urllib.request.urlopen(self.readme_url) as response:
                return response.read().decode('utf-8')
        except urllib.error.URLError as e:
            self.logger.error(f"Failed to fetch README: {e}")
            return None

    def parse_data(self, content: str) -> list[dict[str, Any]]:
        """Parse awesome list README into structured data"""
        lines = content.split('\n')
        categories = {}
        current_category = None

        for line in lines:
            # Check for category heading (## Category Name)
            if line.startswith('## '):
                current_category = line[3:].strip()
                categories[current_category] = []
            # Check for list item that looks like: - [name](url) - description
            elif current_category and line.strip().startswith('- ['):
                # Extract the part between - [ and ]
                import re
                match = re.match(r'\s*-\s*\[([^\]]+)\]\(([^)]+)\)\s*-\s*(.+)', line.strip())
                if match:
                    name, url, description = match.groups()
                    categories[current_category].append({
                        "name": name.strip(),
                        "url": url.strip(),
                        "description": description.strip(),
                        "category": current_category
                    })
                else:
                    # Try without description
                    match = re.match(r'\s*-\s*\[([^\]]+)\]\(([^)]+)\)', line.strip())
                    if match:
                        name, url = match.groups()
                        categories[current_category].append({
                            "name": name.strip(),
                            "url": url.strip(),
                            "description": "",
                            "category": current_category
                        })

        # Flatten the structure
        all_items = []
        for category_items in categories.values():
            all_items.extend(category_items)

        return all_items


# --- Merged from awesome_python.py ---

"""
Awesome Python scraper for SupremeAI resource collection
Scrapes the awesome-python GitHub repository
"""

import sys
from pathlib import Path

# Add the parent directory to sys.path to import base classes
sys.path.append(str(Path(__file__).parent.parent))

from resource_collection.base_scraper import AwesomeListScraper


class AwesomePythonScraper(AwesomeListScraper):
    """Scraper for awesome-python list"""

    def __init__(self, data_dir: Path):
        super().__init__(
            name="awesome-python",
            repo_url="https://github.com/vinta/awesome-python",
            data_dir=data_dir
        )


def main():
    """Main function to run the scraper"""
    # Set up data directory
    data_dir = Path(__file__).parent.parent / "data" / "awesome-python"

    # Create and run scraper
    scraper = AwesomePythonScraper(data_dir)
    result = scraper.run()

    if result:
        print(f"[SUCCESS] {scraper.name} scraper completed successfully")
        print(f"  Data saved to: {result}")
        return 0
    else:
        print(f"[ERROR] {scraper.name} scraper failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())


# --- Merged from awesome_go.py ---

"""
Awesome Go scraper for SupremeAI resource collection
Scrapes the awesome-go GitHub repository
"""

import sys
from pathlib import Path

# Add the parent directory to sys.path to import base classes
sys.path.append(str(Path(__file__).parent.parent))

from resource_collection.base_scraper import AwesomeListScraper


class AwesomeGoScraper(AwesomeListScraper):
    """Scraper for awesome-go list"""

    def __init__(self, data_dir: Path):
        super().__init__(
            name="awesome-go",
            repo_url="https://github.com/avelino/awesome-go",
            data_dir=data_dir
        )


def main():
    """Main function to run the scraper"""
    # Set up data directory
    data_dir = Path(__file__).parent.parent / "data" / "awesome-go"

    # Create and run scraper
    scraper = AwesomeGoScraper(data_dir)
    result = scraper.run()

    if result:
        print(f"[SUCCESS] {scraper.name} scraper completed successfully")
        print(f"  Data saved to: {result}")
        return 0
    else:
        print(f"[ERROR] {scraper.name} scraper failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())


# --- Merged from awesome_selfhosted.py ---

"""
Awesome Self-Hosted scraper for SupremeAI resource collection
Scrapes the awesome-selfhosted GitHub repository
"""

import sys
from pathlib import Path

# Add the parent directory to sys.path to import base classes
sys.path.append(str(Path(__file__).parent.parent))

from resource_collection.base_scraper import AwesomeListScraper


class AwesomeSelfHostedScraper(AwesomeListScraper):
    """Scraper for awesome-selfhosted list"""

    def __init__(self, data_dir: Path):
        super().__init__(
            name="awesome-selfhosted",
            repo_url="https://github.com/awesome-selfhosted/awesome-selfhosted",
            data_dir=data_dir
        )


def main():
    """Main function to run the scraper"""
    # Set up data directory
    data_dir = Path(__file__).parent.parent / "data" / "awesome-selfhosted"

    # Create and run scraper
    scraper = AwesomeSelfHostedScraper(data_dir)
    result = scraper.run()

    if result:
        print(f"[SUCCESS] {scraper.name} scraper completed successfully")
        print(f"  Data saved to: {result}")
        return 0
    else:
        print(f"[ERROR] {scraper.name} scraper failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())


# --- Merged from client.py ---

"""
Ossinsight API client for SupremeAI resource collection
"""

import sys
from pathlib import Path

# Add the parent directory to sys.path to import base classes
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))

from typing import Any

from base_api_client import BaseAPIClient


class OssinsightClient(BaseAPIClient):
    """Client for OSS Insight API"""

    def __init__(self, data_dir: Path):
        super().__init__(
            name="ossinsight",
            base_url="https://api.ossinsight.io/v1",
            data_dir=data_dir
            # No API key required for basic usage (beta)
        )

    def fetch_data(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch data from OSS Insight API"""
        return self._make_request(endpoint, params)

    def parse_data(self, raw_data: Any, endpoint: str) -> list[dict[str, Any]]:
        """Parse OSS Insight API response into standardized format"""
        if not isinstance(raw_data, dict):
            self.logger.warning(f"Expected dict response from {endpoint}, got {type(raw_data)}")
            return []

        # Handle OSS Insight's specific response format
        # Based on observation: {"type":"sql_endpoint","data":{"columns":[{...}],"rows":[{...}]},"result":{...}}
        if 'type' in raw_data and raw_data.get('type') == 'sql_endpoint' and 'data' in raw_data:
            data_section = raw_data['data']

            # Handle the format where rows are already objects with correct property names
            if 'rows' in data_section and isinstance(data_section['rows'], list):
                rows = data_section['rows']

                # Convert rows to dictionaries (they already are, but ensure they have metadata)
                result = []
                for row in rows:
                    if isinstance(row, dict):
                        # Add metadata
                        row['_api_source'] = 'ossinsight'
                        row['_endpoint'] = endpoint
                        result.append(row)
                    else:
                        self.logger.warning(f"Skipping non-dict row in {endpoint}: {type(row)}")

                return result
            else:
                # Fallback: if no rows but we have data, try to use data directly
                if isinstance(data_section, list):
                    result = []
                    for item in data_section:
                        if isinstance(item, dict):
                            item['_api_source'] = 'ossinsight'
                            item['_endpoint'] = endpoint
                            result.append(item)
                    return result
                elif isinstance(data_section, dict):
                    data_section['_api_source'] = 'ossinsight'
                    data_section['_endpoint'] = endpoint
                    return [data_section]
        else:
            # Handle standard JSON responses
            data = []

            # Check if it's a list response
            if isinstance(raw_data, list):
                data = raw_data
            # Check if it's an object with a 'data' or 'items' or 'list' field
            elif isinstance(raw_data, dict):
                # Common patterns for API responses
                if 'data' in raw_data and isinstance(raw_data['data'], list):
                    data = raw_data['data']
                elif 'items' in raw_data and isinstance(raw_data['items'], list):
                    data = raw_data['items']
                elif 'list' in raw_data and isinstance(raw_data['list'], list):
                    data = raw_data['list']
                elif 'repositories' in raw_data and isinstance(raw_data['repositories'], list):
                    data = raw_data['repositories']
                elif 'collections' in raw_data and isinstance(raw_data['collections'], list):
                    data = raw_data['collections']
                else:
                    # Treat the entire object as a single item
                    data = [raw_data]

            # Ensure each item is a dictionary and add metadata
            result = []
            for item in data:
                if isinstance(item, dict):
                    # Add metadata
                    item['_api_source'] = 'ossinsight'
                    item['_endpoint'] = endpoint
                    result.append(item)
                else:
                    self.logger.warning(f"Skipping non-dict item in {endpoint}: {type(item)}")

            return result


def main_ossinsight():
    """Main function to run the ossinsight.io API client"""

    # Set up data directory
    data_dir = Path(__file__).parent.parent.parent / "data" / "ossinsight"

    # Create client
    client = OssinsightClient(data_dir)

    # Define endpoints to fetch based on OSS Insight API documentation
    endpoints = [
        {
            'endpoint': 'trends/repos/',
            'params': {
                'period': 'daily',
                'language': 'All'
            },
            'name': 'trending_daily_all'
        },
        {
            'endpoint': 'trends/repos/',
            'params': {
                'period': 'weekly',
                'language': 'All'
            },
            'name': 'trending_weekly_all'
        },
        {
            'endpoint': 'trends/repos/',
            'params': {
                'period': 'monthly',
                'language': 'Python'
            },
            'name': 'trending_monthly_python'
        },
        {
            'endpoint': 'repos/pingcap/tidb',  # Example repository
            'name': 'repo_pingcap_tidb'
        },
        {
            'endpoint': 'collections/',
            'name': 'collections_list'
        }
    ]

    # Run the client
    result = client.run(endpoints)

    if result:
        print("[SUCCESS] Ossinsight client completed successfully")
        print(f"  Data saved to: {result}")
        return 0
    else:
        print("[ERROR] Ossinsight client failed")
        return 1


if __name__ == "__main__":
    sys.exit(main_ossinsight())


# --- Merged from test.py ---

#!/usr/bin/env python3
"""
Test script for Ossinsight API client
"""

import sys
from pathlib import Path

# Add the resource_collection directory to sys.path
current_dir = Path(__file__).parent
resource_collection_dir = current_dir.parent
sys.path.insert(0, str(resource_collection_dir))

# Also add the parent of resource_collection to access base_api_client
root_dir = resource_collection_dir.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from ossinsight.client import main_ossinsight

if __name__ == "__main__":
    sys.exit(main_ossinsight())
