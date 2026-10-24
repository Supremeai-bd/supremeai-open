"""
Multi-Catalog Search Engine for SupremeAI Core Engine
Provides unified search across all collected resource catalogs
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class CatalogSource(Enum):
    """Enumeration of available catalog sources"""
    AWESOME_SELFHOSTED = "awesome-selfhosted"
    AWESOME_GO = "awesome-go"
    AWESOME_PYTHON = "awesome-python"
    OSSINSIGHT = "ossinsight"
    # Future: LIBHUNT, ALTERNATIVETO, SELFH_ST, LIBRARIES_IO


@dataclass
class SearchResult:
    """Represents a search result from any catalog"""
    id: str
    name: str
    description: str
    source: CatalogSource
    category: str | None = None
    url: str | None = None
    metadata: dict[str, Any] | None = None
    relevance_score: float = 0.0
    matched_fields: list[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.matched_fields is None:
            self.matched_fields = []


class MultiCatalogSearchEngine:
    """
    Search engine that indexes and searches across multiple catalog sources
    """

    def __init__(self, data_root: Path | None = None):
        """
        Initialize the search engine

        Args:
            data_root: Root directory containing the collected data
                      Defaults to scripts/data relative to this file
        """
        if data_root is None:
            # Default to scripts/data relative to this file
            self.data_root = Path(__file__).parent.parent / "data"
        else:
            self.data_root = Path(data_root)

        self.logger = self._setup_logger()
        self.index: dict[CatalogSource, list[dict[str, Any]]] = {}
        self.last_indexed: dict[CatalogSource, datetime] = {}
        self._build_index()

    def _setup_logger(self) -> logging.Logger:
        """Set up logging for the search engine"""
        logger = logging.getLogger("multicatalog_search")
        logger.setLevel(logging.INFO)

        # Create handler if not exists
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def _get_catalog_path(self, source: CatalogSource) -> Path:
        """Get the filesystem path for a catalog source"""
        return self.data_root / source.value

    def _load_catalog_data(self, source: CatalogSource) -> list[dict[str, Any]]:
        """
        Load all data files for a given catalog source

        Returns:
            List of all items from all data files for this source
        """
        catalog_path = self._get_catalog_path(source)
        if not catalog_path.exists():
            self.logger.warning(f"Catalog path does not exist: {catalog_path}")
            return []

        all_items = []
        json_files = list(catalog_path.glob("*.json"))

        if not json_files:
            self.logger.warning(f"No JSON files found in {catalog_path}")
            return []

        self.logger.info(f"Loading {len(json_files)} files from {source.value}")

        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Handle both single objects and arrays
                if isinstance(data, dict):
                    # Check if it's a single item or a collection with standard keys
                    if any(key in data for key in ['name', 'id', 'repo_name', 'collection_name']):
                        all_items.append(data)
                    else:
                        # Might be a wrapper object, look for common array keys
                        for key in ['data', 'items', 'results', 'repositories', 'collections']:
                            if key in data and isinstance(data[key], list):
                                all_items.extend(data[key])
                                break
                        else:
                            # Treat as single item if no array found
                            all_items.append(data)
                elif isinstance(data, list):
                    all_items.extend(data)
                else:
                    self.logger.warning(f"Unexpected data type in {json_file}: {type(data)}")

            except Exception as e:
                self.logger.error(f"Error loading {json_file}: {e}")

        return all_items

    def _build_index(self):
        """Build search index from all available catalog data"""
        self.logger.info("Building search index...")

        # Initialize index for all known sources
        for source in CatalogSource:
            self.index[source] = []

        # Load and index data from each source
        for source in CatalogSource:
            try:
                start_time = datetime.now()
                items = self._load_catalog_data(source)
                self.index[source] = items
                self.last_indexed[source] = datetime.now()

                elapsed = (datetime.now() - start_time).total_seconds()
                self.logger.info(
                    f"Indexed {len(items)} items from {source.value} in {elapsed:.2f}s"
                )
            except Exception as e:
                self.logger.error(f"Failed to index {source.value}: {e}")
                self.index[source] = []

        total_items = sum(len(items) for items in self.index.values())
        self.logger.info(f"Index build complete. Total items: {total_items}")

    def refresh_index(self, source: CatalogSource | None = None):
        """
        Refresh the index for a specific source or all sources

        Args:
            source: Specific source to refresh, or None for all
        """
        if source is None:
            self.logger.info("Refreshing all catalog indices")
            self._build_index()
        else:
            self.logger.info(f"Refreshing index for {source.value}")
            start_time = datetime.now()
            items = self._load_catalog_data(source)
            self.index[source] = items
            self.last_indexed[source] = datetime.now()
            elapsed = (datetime.now() - start_time).total_seconds()
            self.logger.info(
                f"Refreshed {len(items)} items from {source.value} in {elapsed:.2f}s"
            )

    def _calculate_relevance(
        self,
        item: dict[str, Any],
        query: str,
        fields_to_search: list[str] | None = None
    ) -> tuple[float, list[str]]:
        """
        Calculate relevance score for an item against a query

        Returns:
            Tuple of (score, matched_fields)
        """
        if fields_to_search is None:
            # Default fields to search
            fields_to_search = ['name', 'description', 'repo_name', 'collection_name']

        query_lower = query.lower()
        score = 0.0
        matched_fields = []

        for field in fields_to_search:
            if field in item and isinstance(item[field], str):
                field_value = item[field].lower()
                if query_lower in field_value:
                    # Basic relevance scoring - can be enhanced with TF-IDF, etc.
                    # Exact match gets higher score
                    if query_lower == field_value:
                        score += 1.0
                    # Starts with query gets medium score
                    elif field_value.startswith(query_lower):
                        score += 0.8
                    # Contains query gets lower score
                    else:
                        score += 0.5
                    matched_fields.append(field)

        # Normalize score by number of fields searched
        if fields_to_search:
            score = score / len(fields_to_search)

        return score, matched_fields

    def search(
        self,
        query: str,
        sources: list[CatalogSource] | None = None,
        limit: int = 50,
        min_score: float = 0.1
    ) -> list[SearchResult]:
        """
        Search across catalog sources

        Args:
            query: Search query string
            sources: List of sources to search (None for all)
            limit: Maximum number of results to return
            min_score: Minimum relevance score threshold

        Returns:
            List of SearchResult objects sorted by relevance
        """
        if not query.strip():
            return []

        if sources is None:
            sources = list(CatalogSource)

        self.logger.info(f"Searching for: '{query}' across {[s.value for s in sources]}")

        all_results = []

        for source in sources:
            if source not in self.index:
                continue

            items = self.index[source]
            if not items:
                continue

            # Determine fields to search based on source
            fields_to_search = ['name', 'description']
            if source == CatalogSource.AWESOME_SELFHOSTED:
                fields_to_search.extend(['category'])
            elif source == CatalogSource.AWESOME_GO or source == CatalogSource.AWESOME_PYTHON:
                fields_to_search.extend(['repo_name'])  # if present
            elif source == CatalogSource.OSSINSIGHT:
                fields_to_search.extend(['name'])  # collections have 'name' field

            # Search through items
            for item in items:
                score, matched_fields = self._calculate_relevance(
                    item, query, fields_to_search
                )

                if score >= min_score:
                    # Extract common fields with fallbacks
                    name = (
                        item.get('name') or
                        item.get('repo_name') or
                        item.get('collection_name') or
                        item.get('id', 'unknown')
                    )

                    description = (
                        item.get('description') or
                        item.get('repo_description') or
                        ''
                    )

                    # Get category if available
                    category = item.get('category')

                    # Get URL if available
                    url = (
                        item.get('url') or
                        item.get('repo_url') or
                        item.get('html_url') or
                        ''
                    )

                    result = SearchResult(
                        id=str(item.get('id', '')),
                        name=str(name),
                        description=str(description),
                        source=source,
                        category=category,
                        url=url,
                        metadata=item,  # Store full item as metadata
                        relevance_score=score,
                        matched_fields=matched_fields
                    )

                    all_results.append(result)

        # Sort by relevance score (descending)
        all_results.sort(key=lambda x: x.relevance_score, reverse=True)

        # Apply limit
        limited_results = all_results[:limit]

        self.logger.info(
            f"Found {len(all_results)} matches, returning top {len(limited_results)}"
        )

        return limited_results

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the indexed data"""
        stats = {}
        total_items = 0

        for source in CatalogSource:
            count = len(self.index.get(source, []))
            stats[source.value] = {
                'item_count': count,
                'last_indexed': self.last_indexed.get(source, None)
            }
            total_items += count

        stats['total_items'] = total_items
        stats['index_age_seconds'] = {
            source.value: (datetime.now() - self.last_indexed.get(source, datetime.now())).total_seconds()
            for source in CatalogSource if source in self.last_indexed
        }

        return stats


def demo_search():
    """Demonstration of the search engine functionality"""
    print("=" * 60)
    print("SUPREMEAI MULTI-CATALOG SEARCH ENGINE DEMO")
    print("=" * 60)

    # Initialize search engine
    engine = MultiCatalogSearchEngine()

    # Show stats
    stats = engine.get_stats()
    print("\nIndex Statistics:")
    for source, info in stats.items():
        if source != 'total_items' and source != 'index_age_seconds':
            print(f"  {source}: {info['item_count']} items")
    print(f"  Total: {stats['total_items']} items")

    # Example searches
    test_queries = [
        "docker",
        "machine learning",
        "web framework",
        "database",
        "api",
        "authentication",
        "monitoring",
        "testing"
    ]

    for query in test_queries:
        print(f"\nSearching for: '{query}'")
        results = engine.search(query, limit=5)

        if results:
            for i, result in enumerate(results, 1):
                print(f"  {i}. [{result.source.value}] {result.name}")
                print(f"     Score: {result.relevance_score:.2f}")
                if result.description:
                    desc = result.description[:100] + "..." if len(result.description) > 100 else result.description
                    print(f"     Description: {desc}")
                if result.category:
                    print(f"     Category: {result.category}")
        else:
            print("  No results found")

    print("\n" + "=" * 60)
    print("Demo complete")


if __name__ == "__main__":
    demo_search()
