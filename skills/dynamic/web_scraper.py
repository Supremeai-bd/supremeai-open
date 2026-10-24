import httpx
from bs4 import BeautifulSoup


def run(url: str):
    """Scrapes page content from a URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = httpx.get(url, headers=headers, timeout=10.0)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string if soup.title else "No Title"

        # Get head texts
        headings = [h.text.strip() for h in soup.find_all(["h1", "h2", "h3"])][:10]

        return {
            "success": True,
            "title": title,
            "headings": headings,
            "text_preview": soup.get_text()[:500].strip(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
