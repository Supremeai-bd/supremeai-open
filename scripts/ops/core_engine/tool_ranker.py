"""
AI-Powered Tool Ranker for SupremeAI Core Engine
Ranks tools based on multiple factors including popularity, activity, quality, and relevance
"""

import datetime
import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

try:
    from scripts.core_engine.multicatalog_search import CatalogSource, SearchResult
except ImportError:
    try:
        from multicatalog_search import CatalogSource, SearchResult
    except ImportError:
        class CatalogSource(Enum):
            AWESOME_SELFHOSTED = "awesome-selfhosted"
            AWESOME_GO = "awesome-go"
            AWESOME_PYTHON = "awesome-python"
            OSSINSIGHT = "ossinsight"

        class SearchResult:
            def __init__(self, id: str = "", name: str = "", description: str = "") -> None:
                self.id = id
                self.name = name
                self.description = description


class RankingFactor(Enum):
    """Factors used in the ranking algorithm"""
    POPULARITY = "popularity"        # Stars, followers, usage metrics
    ACTIVITY = "activity"            # Recent commits, releases, issue resolution
    QUALITY = "quality"              # Code quality, documentation, tests
    RELEVANCE = "relevance"          # How well it matches the search query
    FRESHNESS = "freshness"          # How recently updated
    COMMUNITY = "community"          # Contributors, forks, discussions
    MATURITY = "maturity"            # Age, stability, version history


@dataclass
class RankingWeights:
    """Weights for different ranking factors"""
    popularity: float = 0.25
    activity: float = 0.20
    quality: float = 0.15
    relevance: float = 0.20
    freshness: float = 0.10
    community: float = 0.08
    maturity: float = 0.02

    def __post_init__(self):
        # Normalize weights to sum to 1.0
        total = self.popularity + self.activity + self.quality + self.relevance + \
                self.freshness + self.community + self.maturity
        if total > 0:
            self.popularity /= total
            self.activity /= total
            self.quality /= total
            self.relevance /= total
            self.freshness /= total
            self.community /= total
            self.maturity /= total


@dataclass
class RankedResult:
    """A search result with ranking scores"""
    result: 'SearchResult'
    total_score: float
    factor_scores: dict[str, float]
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            'result': {
                'id': self.result.id,
                'name': self.result.name,
                'description': self.result.description,
                'source': self.result.source.value,
                'category': self.result.category,
                'url': self.result.url,
                'metadata': self.result.metadata
            },
            'total_score': self.total_score,
            'factor_scores': self.factor_scores,
            'rank': self.rank
        }


class ToolRanker:
    """
    AI-powered tool ranker that scores and ranks tools based on multiple factors
    """

    def __init__(self, weights: RankingWeights = None):
        """
        Initialize the ranker

        Args:
            weights: Custom weights for ranking factors (uses defaults if None)
        """
        self.weights = weights or RankingWeights()
        self.logger = self._setup_logger()

        # Cache for computed metrics to avoid recalculation
        self._metrics_cache: dict[str, dict[str, float]] = {}

    def _setup_logger(self) -> logging.Logger:
        """Set up logging for the ranker"""
        logger = logging.getLogger("tool_ranker")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def rank_results(
        self,
        results: list['SearchResult'],
        query: str = "",
        context: dict[str, Any] | None = None
    ) -> list[RankedResult]:
        """
        Rank a list of search results

        Args:
            results: List of search results to rank
            query: Original search query (for relevance boosting)
            context: Additional context for ranking (user preferences, etc.)

        Returns:
            List of RankedResult objects sorted by total score (descending)
        """
        if not results:
            return []

        self.logger.info(f"Ranking {len(results)} results for query: '{query}'")

        ranked_results = []

        for result in results:
            # Calculate individual factor scores
            factor_scores = self._calculate_factor_scores(result, query, context)

            # Calculate weighted total score
            total_score = (
                factor_scores.get('popularity', 0.0) * self.weights.popularity +
                factor_scores.get('activity', 0.0) * self.weights.activity +
                factor_scores.get('quality', 0.0) * self.weights.quality +
                factor_scores.get('relevance', 0.0) * self.weights.relevance +
                factor_scores.get('freshness', 0.0) * self.weights.freshness +
                factor_scores.get('community', 0.0) * self.weights.community +
                factor_scores.get('maturity', 0.0) * self.weights.maturity
            )

            ranked_result = RankedResult(
                result=result,
                total_score=total_score,
                factor_scores=factor_scores,
                rank=0  # Will be set after sorting
            )

            ranked_results.append(ranked_result)

        # Sort by total score (descending)
        ranked_results.sort(key=lambda x: x.total_score, reverse=True)

        # Assign ranks
        for i, ranked_result in enumerate(ranked_results):
            ranked_result.rank = i + 1

        self.logger.info(f"Ranking complete. Top score: {ranked_results[0].total_score:.3f}" if ranked_results else "No results to rank")

        return ranked_results

    def _calculate_factor_scores(
        self,
        result: 'SearchResult',
        query: str,
        context: dict[str, Any] | None = None
    ) -> dict[str, float]:
        """
        Calculate individual factor scores for a result

        Returns:
            Dictionary mapping factor names to scores (0.0-1.0)
        """
        # Use cache if available
        cache_key = f"{result.id}_{result.source.value}_{hash(query)}"
        if cache_key in self._metrics_cache:
            return self._metrics_cache[cache_key]

        scores = {}

        # Get the raw item data
        item = result.metadata if hasattr(result, 'metadata') and result.metadata else {}

        # Calculate each factor score
        scores['popularity'] = self._calculate_popularity_score(item, result.source)
        scores['activity'] = self._calculate_activity_score(item, result.source)
        scores['quality'] = self._calculate_quality_score(item, result.source)
        scores['relevance'] = result.relevance_score  # Already calculated by search engine
        scores['freshness'] = self._calculate_freshness_score(item, result.source)
        scores['community'] = self._calculate_community_score(item, result.source)
        scores['maturity'] = self._calculate_maturity_score(item, result.source)

        # Cache the results
        self._metrics_cache[cache_key] = scores

        return scores

    def _calculate_popularity_score(self, item: dict[str, Any], source: 'CatalogSource') -> float:
        """Calculate popularity score based on stars, followers, usage metrics"""
        score = 0.0

        if source == CatalogSource.AWESOME_SELFHOSTED:
            # For self-hosted, we might look at stars if available in metadata
            # Since our scraped data might not have stars, we'll use category popularity heuristics
            category = item.get('category', '').lower()
            popular_categories = ['docker', 'database', 'web', 'api', 'monitoring']
            if any(pop_cat in category for pop_cat in popular_categories):
                score = 0.8
            else:
                score = 0.5

        elif source == CatalogSource.AWESOME_GO:
            # For Go packages, look for stars if available
            stars = item.get('stars', 0)
            if isinstance(stars, (int, float)) and stars > 0:
                # Logarithmic scaling for stars
                score = min(1.0, math.log10(max(stars, 1)) / math.log10(10000))  # Normalize to 10k stars
            else:
                score = 0.3  # Default for unknown popularity

        elif source == CatalogSource.AWESOME_PYTHON:
            # For Python packages, similar approach
            stars = item.get('stars', 0)
            if isinstance(stars, (int, float)) and stars > 0:
                score = min(1.0, math.log10(max(stars, 1)) / math.log10(10000))
            else:
                score = 0.3

        elif source == CatalogSource.OSSINSIGHT:
            # For OSS Insight, we might have star counts or similar metrics
            # Looking at our data structure, we have repository data
            # This would need to be enhanced based on actual OSS Insight data structure
            stars = item.get('star_count', 0) or item.get('stars', 0)
            if isinstance(stars, (int, float)) and stars > 0:
                score = min(1.0, math.log10(max(stars, 1)) / math.log10(10000))
            else:
                score = 0.4  # Slightly higher default for curated collections

        return max(0.0, min(1.0, score))

    def _calculate_activity_score(self, item: dict[str, Any], source: 'CatalogSource') -> float:
        """Calculate activity score based on recent commits, releases, issue resolution"""
        score = 0.5  # Default middle score

        # This would be enhanced with actual activity data from APIs
        # For now, we'll use heuristics based on available data

        if source == CatalogSource.OSSINSIGHT:
            # OSS Insight might have commit frequency data
            # Placeholder implementation
            score = 0.6
        elif source in [CatalogSource.AWESOME_GO, CatalogSource.AWESOME_PYTHON]:
            # For language-specific awesome lists, assume moderate activity
            score = 0.5
        else:
            # For general software lists
            score = 0.5

        return max(0.0, min(1.0, score))

    def _calculate_quality_score(self, item: dict[str, Any], source: 'CatalogSource') -> float:
        """Calculate quality score based on code quality, documentation, tests"""
        score = 0.5  # Default

        # Check for quality indicators in metadata
        has_docs = bool(item.get('documentation') or item.get('docs') or
                       item.get('readme') or item.get('wiki'))
        has_tests = bool(item.get('tests') or item.get('testing') or
                        item.get('test_coverage'))
        license_info = item.get('license', '')

        # Boost score for quality indicators
        if has_docs:
            score += 0.2
        if has_tests:
            score += 0.2
        if license_info and 'MIT' in license_info.upper():
            score += 0.1  # Permissive license bonus
        elif license_info and 'APACHE' in license_info.upper():
            score += 0.1

        return max(0.0, min(1.0, score))

    def _calculate_freshness_score(self, item: dict[str, Any], source: 'CatalogSource') -> float:
        """Calculate freshness score based on how recently updated"""
        # Look for date fields
        date_fields = ['updated_at', 'last_updated', 'push_date', 'released_at', 'date']
        latest_date = None

        for field in date_fields:
            if item.get(field):
                try:
                    # Try to parse various date formats
                    if isinstance(item[field], str):
                        # Try ISO format first
                        if 'T' in item[field]:
                            dt = datetime.fromisoformat(item[field].replace('Z', '+00:00'))
                        else:
                            dt = datetime.strptime(item[field], '%Y-%m-%d')
                    elif isinstance(item[field], (int, float)):
                        # Unix timestamp
                        dt = datetime.fromtimestamp(item[field])
                    else:
                        continue

                    if latest_date is None or dt > latest_date:
                        latest_date = dt
                except (ValueError, TypeError):
                    continue

        if latest_date:
            # Calculate days since last update
            days_old = (datetime.now() - latest_date).days

            # Scoring: <30 days = 1.0, <90 days = 0.8, <180 days = 0.6, <365 days = 0.4, else 0.2
            if days_old < 30:
                score = 1.0
            elif days_old < 90:
                score = 0.8
            elif days_old < 180:
                score = 0.6
            elif days_old < 365:
                score = 0.4
            else:
                score = 0.2
        else:
            # No date info available
            score = 0.5

        return max(0.0, min(1.0, score))

    def _calculate_community_score(self, item: dict[str, Any], source: 'CatalogSource') -> float:
        """Calculate community score based on contributors, forks, discussions"""
        score = 0.5  # Default

        # Look for community metrics
        forks = item.get('forks', 0) or item.get('fork_count', 0)
        contributors = item.get('contributors', 0) or item.get('contributor_count', 0)
        watchers = item.get('watchers', 0) or item.get('watcher_count', 0)

        if isinstance(forks, (int, float)) and forks > 0:
            score += min(0.3, math.log10(max(forks, 1)) / math.log10(1000))  # Up to 0.3 for 1k forks
        if isinstance(contributors, (int, float)) and contributors > 0:
            score += min(0.2, math.log10(max(contributors, 1)) / math.log10(100))  # Up to 0.2 for 100 contributors
        if isinstance(watchers, (int, float)) and watchers > 0:
            score += min(0.2, math.log10(max(watchers, 1)) / math.log10(1000))  # Up to 0.2 for 1k watchers

        return max(0.0, min(1.0, score))

    def _calculate_maturity_score(self, item: dict[str, Any], source: 'CatalogSource') -> float:
        """Calculate maturity score based on age, version history, stability"""
        score = 0.5  # Default

        # Look for version/maturity indicators
        # Look for version/maturity indicators
        version = item.get('version') or item.get('release') or item.get('current_version')
        if isinstance(version, str):
            try:
                import re
                version_numbers = re.findall(r'\d+', version)
                if len(version_numbers) >= 1:
                    major_version = int(version_numbers[0])
                    if major_version >= 2:
                        score += 0.3
                    elif major_version >= 1:
                        score += 0.2
                    else:
                        score += 0.1  # 0.x versions get some credit
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Silenced error: {e}")

        # Check for stability indicators
        status = item.get('status', '').lower()
        if any(stable_indicator in status for stable_indicator in ['stable', 'production', 'lts', 'release']):
            score += 0.2

        return max(0.0, min(1.0, score))


def demo_ranker():
    """Demonstration of the ranker functionality"""
    print("=" * 60)
    print("SUPREMEAI AI-POWERED TOOL RANKER DEMO")
    print("=" * 60)

    # Import the search engine to get some results to rank
    from multicatalog_search import MultiCatalogSearchEngine

    # Initialize components
    search_engine = MultiCatalogSearchEngine()
    ranker = ToolRanker()

    # Get some search results
    query = "docker"
    search_results = search_engine.search(query, limit=10)

    print(f"\nOriginal search results for '{query}' ({len(search_results)} found):")
    for i, result in enumerate(search_results[:5], 1):
        print(f"  {i}. [{result.source.value}] {result.name} (score: {result.relevance_score:.2f})")

    # Rank the results
    ranked_results = ranker.rank_results(search_results, query)

    print(f"\nRanked results for '{query}':")
    for i, ranked_result in enumerate(ranked_results[:5], 1):
        result = ranked_result.result
        print(f"  {i}. [{result.source.value}] {result.name}")
        print(f"     Total Score: {ranked_result.total_score:.3f}")
        print(f"     Factors: P{ranked_result.factor_scores.get('popularity', 0):.2f} "
              f"A{ranked_result.factor_scores.get('activity', 0):.2f} "
              f"Q{ranked_result.factor_scores.get('quality', 0):.2f} "
              f"R{ranked_result.factor_scores.get('relevance', 0):.2f} "
              f"F{ranked_result.factor_scores.get('freshness', 0):.2f} "
              f"C{ranked_result.factor_scores.get('community', 0):.2f} "
              f"M{ranked_result.factor_scores.get('maturity', 0):.2f}")
        if result.description:
            desc = result.description[:80] + "..." if len(result.description) > 80 else result.description
            print(f"     Description: {desc}")
        print()

    print("=" * 60)
    print("Ranker demo complete")


if __name__ == "__main__":
    # Configure logging for demo
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    demo_ranker()
