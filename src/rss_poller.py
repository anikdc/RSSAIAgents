import feedparser
import datetime
from datetime import timezone
import time
import logging

logger = logging.getLogger(__name__)

class RSSPoller:
    def __init__(self):
        pass

    def fetch_feeds(self, feeds_list, time_window_hours=1.0):
        """
        Fetches articles from a list of RSS feeds.
        Returns a list of articles published within the last time_window_hours.
        """
        articles = []
        now = datetime.datetime.now(timezone.utc)
        cutoff_time = now - datetime.timedelta(hours=time_window_hours)
        
        logger.info(f"Fetching {len(feeds_list)} feeds...")
        
        for feed_url in feeds_list:
            try:
                feed = feedparser.parse(feed_url)
                if feed.bozo:
                    logger.warning(f"Error parsing feed {feed_url}: {feed.bozo_exception}")
                    continue
                
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
    with open('feeds.json', 'r') as f:
        feeds = json.load(f)
    
    poller = RSSPoller()
    recent = poller.fetch_feeds(feeds, time_window_hours=8.0) # Longer window for testing
    for art in recent:
        print(f"- [{art['source']}] {art['title']}")
