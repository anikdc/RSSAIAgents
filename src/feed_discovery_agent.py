import requests
from bs4 import BeautifulSoup
import feedparser
import json
import os
from urllib.parse import urlparse

class FeedDiscoveryAgent:

    def __init__(self, cache_file="feeds_db.json"):
        self.headers = {
            "User-Agent": "Mozilla/5.0"
        }
        self.cache_file = cache_file
        self.cache = self.load_cache()

        # ✅ Strong seed sources (expandable)
        self.seed_sites = [
            # Tech
            "https://techcrunch.com",
            "https://www.theverge.com",
            "https://www.wired.com",
            "https://arstechnica.com",
            "https://venturebeat.com",

            # Global news
            "https://www.bbc.com",
            "https://www.reuters.com",
            "https://www.aljazeera.com",

            # Business
            "https://www.bloomberg.com",
            "https://www.forbes.com",

            # India
            "https://www.thehindu.com",
            "https://indianexpress.com",
            "https://www.livemint.com",
        ]


    # -----------------------------
    # Cache handling
    # -----------------------------
    def load_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r") as f:
                return json.load(f)
        return {"working": [], "failed": []}


    def save_cache(self):
        with open(self.cache_file, "w") as f:
            json.dump(self.cache, f, indent=2)


    # -----------------------------
    # Extract RSS links from site
    # -----------------------------
    def discover_from_site(self, base_url):
        try:
            res = requests.get(base_url, headers=self.headers, timeout=5)
            soup = BeautifulSoup(res.text, "html.parser")

            feeds = []

            for link in soup.find_all("link"):
                href = link.get("href", "")

                if any(x in href.lower() for x in ["rss", "feed", "xml"]):
                    if href.startswith("/"):
                        href = base_url.rstrip("/") + href

                    feeds.append(href)

            return feeds

        except:
            return []


    # -----------------------------
    # Validate RSS feed
    # -----------------------------
    def validate_feed(self, url):
        if url in self.cache["failed"]:
            return False

        try:
            feed = feedparser.parse(url)

            if len(feed.entries) > 0:
                self.cache["working"].append(url)
                return True
            else:
                self.cache["failed"].append(url)
                return False

        except:
            self.cache["failed"].append(url)
            return False


    # -----------------------------
    # Get feeds from seed sites
    # -----------------------------
    def get_seed_feeds(self):
        feeds = []

        for site in self.seed_sites:
            discovered = self.discover_from_site(site)

            for f in discovered:
                if self.validate_feed(f):
                    feeds.append(f)

        return feeds


    # -----------------------------
    # Expand sources using articles
    # -----------------------------
    def expand_from_articles(self, articles):
        new_sites = set()

        for article in articles:
            url = article.get("link", "")
            domain = urlparse(url).netloc

            if domain:
                new_sites.add(f"https://{domain}")

        feeds = []

        for site in new_sites:
            discovered = self.discover_from_site(site)

            for f in discovered:
                if self.validate_feed(f):
                    feeds.append(f)

        return feeds


    # -----------------------------
    # Main function
    # -----------------------------
    def get_feeds(self, articles=None):

        feeds = set(self.cache["working"])  # start from cache

        # Step 1: seed sources
        seed_feeds = self.get_seed_feeds()
        feeds.update(seed_feeds)

        # Step 2: expand if articles available
        if articles:
            expanded = self.expand_from_articles(articles)
            feeds.update(expanded)

        self.save_cache()

        return list(feeds)