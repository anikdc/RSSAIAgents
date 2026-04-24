import requests
from bs4 import BeautifulSoup
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class ScraperAgent:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def _scrape_single(self, url):
        """Scrape a single URL. Returns (url, text) or (url, None) on failure."""
        try:
            logger.info(f"Scraping {url}...")
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return url, self._extract_content(response.text)
            else:
                logger.warning(f"Failed to fetch {url}: Status {response.status_code}")
                return url, None
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return url, None

    def scrape_urls(self, urls):
        """
        Visits a list of URLs in parallel and scrapes their content.
        Returns a map of URL -> Cleaned Text.
        """
        results = {}
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(self._scrape_single, url) for url in urls]
            for future in as_completed(futures):
                url, text = future.result()
                if text:
                    results[url] = text
        return results

    def _extract_content(self, html):
        """
        Basic boilerplate removal using BeautifulSoup.
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
            script.decompose()

        # Get text
        text = soup.get_text(separator=' ')
        
        # Break into lines and remove leading/trailing space on each
        lines = []
        for line in text.splitlines():
            lines.append(line.strip())
        # Break multi-headlines into a line each
        chunks = []
        for line in lines:
            for phrase in line.split("  "):
                chunks.append(phrase.strip())
        # Drop blank lines
        final_chunks = []
        for chunk in chunks:
            if chunk:
                final_chunks.append(chunk)
        text = '\n'.join(final_chunks)
        
        # Limit to reasonable length (e.g., 5000 chars) to fit context window if needed, 
        # though Gemini can handle large context.
        return text[:10000]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = ScraperAgent()
    # Test with a known URL
    test_url = "https://www.example.com"
    content = scraper.scrape_urls([test_url])
    print(content)
