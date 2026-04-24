import feedparser
import datetime
from datetime import timezone
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

class RSSPoller:
    def __init__(self):
        pass

    def _fetch_single_feed(self, feed_url, cutoff_time):
        """Fetch and parse a single RSS feed. Returns a list of article dicts."""
        articles = []
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo:
                logger.warning(f"Feed {feed_url} has parsing warnings (bozo): {feed.bozo_exception}")
                
            if not getattr(feed, 'entries', []):
                logger.warning(f"No entries could be parsed from feed {feed_url}")
                return articles
            
            source_title = feed.feed.get('title', feed_url)
            
            for entry in feed.entries:
                published_dt = self._parse_date(entry)
                
                if not published_dt:
                    continue
                    
                # Ensure timezone awareness for comparison
                if published_dt.tzinfo is None:
                    published_dt = published_dt.replace(tzinfo=timezone.utc)
                
                if published_dt > cutoff_time:
                    articles.append({
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'summary': entry.get('summary', ''),
                        'published': published_dt.isoformat(),
                        'source': source_title,
                        'id': entry.get('id', entry.get('link', ''))
                    })
        except Exception as e:
            logger.error(f"Failed to process feed {feed_url}: {e}")
        return articles

    def fetch_feeds(self, feeds_list, time_window_hours=2.0):
        """
        Fetches articles from a list of RSS feeds in parallel.
        Returns a list of articles published within the last time_window_hours.
        """
        now = datetime.datetime.now(timezone.utc)
        cutoff_time = now - datetime.timedelta(hours=time_window_hours)
        
        logger.info(f"Fetching {len(feeds_list)} feeds in parallel...")
        
        articles = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(self._fetch_single_feed, url, cutoff_time): url
                for url in feeds_list
            }
            for future in as_completed(futures):
                feed_url = futures[future]
                try:
                    result = future.result()
                    articles.extend(result)
                except Exception as e:
                    logger.error(f"Thread failed for feed {feed_url}: {e}")
                
        logger.info(f"Collected {len(articles)} articles from the last {time_window_hours} hours.")
        return articles

    def _parse_date(self, entry):
        """Helper to parse date from feed entry"""
        if 'published_parsed' in entry and entry.published_parsed:
            return datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed), timezone.utc)
        elif 'updated_parsed' in entry and entry.updated_parsed:
            return datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed), timezone.utc)
        return None

if __name__ == "__main__":
    # Test run
    import json
    logging.basicConfig(level=logging.INFO)
    with open('feeds_default.json', 'r') as f:
        feeds = json.load(f)
    
    poller = RSSPoller()
    recent = poller.fetch_feeds(feeds, time_window_hours=8.0) # Longer window for testing
    for art in recent:
        print(f"- [{art['source']}] {art['title']}")
