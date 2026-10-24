

# --- Merged from base_api_client.py ---

"""
Base API client class for SupremeAI resource collection
Provides common functionality for API-based resource collection
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


class BaseAPIClient(ABC):
    """Base class for all API clients"""

    def __init__(self, name: str, data_dir: Path, base_url: str, api_key: str | None = None):
        self.name = name
        self.data_dir = data_dir
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger = self._setup_logger()
        self.session = requests.Session()
        # Set default headers
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'SupremeAI-ResourceCollector/1.0'
        })
        if api_key:
            self.session.headers.update({'Authorization': f'Bearer {api_key}'})

    def _setup_logger(self) -> logging.Logger:
        """Set up logging for the API client"""
        logger = logging.getLogger(f"api_client.{self.name}")
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
    def fetch_data(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch data from the API endpoint"""

    @abstractmethod
    def parse_data(self, raw_data: Any, endpoint: str) -> list[dict[str, Any]]:
        """Parse raw API data into standardized format"""

    def _make_request(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Make HTTP request to API endpoint"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            self.logger.info(f"Making request to {url}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {e}")
            return None
        except ValueError as e:
            self.logger.error(f"Failed to parse JSON response: {e}")
            return None

    def save_data(self, data: list[dict[str, Any]], filename: str | None = None) -> Path:
        """Save parsed data to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{self.name}_{timestamp}.json"

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

    def run(self, endpoints: list[dict[str, Any]]) -> Path | None:
        """Execute the API client for multiple endpoints

        Args:
            endpoints: List of dicts with keys:
                - endpoint: API endpoint path
                - params: Optional query parameters
                - name: Optional name for the data file

        Returns:
            Path to the saved data file, or None if failed
        """
        try:
            self.logger.info(f"Starting API collection for {self.name}")
            start_time = time.time()

            all_data = []

            for endpoint_config in endpoints:
                endpoint = endpoint_config['endpoint']
                params = endpoint_config.get('params', {})
                name = endpoint_config.get('name', endpoint.replace('/', '_'))

                self.logger.info(f"Fetching data from endpoint: {endpoint}")

                # Fetch raw data
                raw_data = self.fetch_data(endpoint, params)
                if raw_data is None:
                    self.logger.warning(f"Failed to fetch data from {endpoint}")
                    continue

                # Parse data
                parsed_data = self.parse_data(raw_data, endpoint)
                if not parsed_data:
                    self.logger.warning(f"No data parsed from {endpoint}")
                    continue

                # Add source endpoint information to each item
                for item in parsed_data:
                    if isinstance(item, dict):
                        item['_source_endpoint'] = endpoint
                        if name:
                            item['_source_name'] = name

                all_data.extend(parsed_data)
                self.logger.info(f"Retrieved {len(parsed_data)} items from {endpoint}")

            if not all_data:
                self.logger.warning("No data collected from any endpoints")
                return None

            # Save combined data
            filepath = self.save_data(all_data)

            elapsed_time = time.time() - start_time
            self.logger.info(f"API collection completed in {elapsed_time:.2f} seconds")

            return filepath

        except Exception as e:
            self.logger.error(f"Error during API collection: {e}", exc_info=True)
            return None
