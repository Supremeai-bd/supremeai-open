from typing import Any

from loguru import logger


class SkillMarketplace:
    """Discovers and queries skills from the external skills registry and GitHub indices."""

    def __init__(self):
        # Local mock index of available remote capabilities
        self.mock_marketplace_index = [
            {
                "name": "web_scraper",
                "version": "1.0.0",
                "description": "Scrapes website contents",
                "dependencies": ["beautifulsoup4", "requests"],
                "code": "def run(url):\n    import requests\n    from bs4 import BeautifulSoup\n    res = requests.get(url)\n    return BeautifulSoup(res.text, 'html.parser').title.text\n",
            },
            {
                "name": "csv_exporter",
                "version": "1.0.0",
                "description": "Exports tabular data to CSV",
                "dependencies": ["pandas"],
                "code": "def run(data, filepath):\n    import pandas as pd\n    df = pd.DataFrame(data)\n    df.to_csv(filepath, index=False)\n    return f'Exported to {filepath}'\n",
            },
        ]

    def search_skills(self, query: str) -> list[dict[str, Any]]:
        logger.info(f"Searching skills marketplace for query: '{query}'")
        query_lower = query.lower()
        matches = []
        for item in self.mock_marketplace_index:
            if (
                query_lower in item["name"].lower()
                or query_lower in item["description"].lower()
            ):
                matches.append(item)
        return matches
