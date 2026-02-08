import logging
import requests
from src.scraper_agent import ScraperAgent

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReproduceIssue")

def test_scraping():
    # URLs from the emerging clusters we saw in debug_verification.txt
    urls = [
        "https://www.theverge.com/tech/875433/tumblr-jeff-donofrio-ceo-washington-post-layoffs",
        "https://www.nytimes.com/2026/02/07/technology/washington-post-will-lewis.html",
        "https://www.nytimes.com/2026/02/08/style/these-ai-dreamers-dont-fit-the-stereotype.html",
        "https://jonathanwhiting.com/writing/blog/games_in_c/" 
    ]
    
    scraper = ScraperAgent()
    
    logger.info(f"Attempting to scrape {len(urls)} URLs...")
    results = scraper.scrape_urls(urls)
    
    logger.info(f"Scraped {len(results)} pages successfully.")
    
    if not results:
        logger.error("Reproduced: No content scraped! This causes 'No content to synthesize'.")
    else:
        for url, text in results.items():
            logger.info(f" - {url}: {len(text)} chars extracted.")
            if len(text) < 100:
                logger.warning(f"   WARNING: Content very short: {text}")

if __name__ == "__main__":
    test_scraping()
