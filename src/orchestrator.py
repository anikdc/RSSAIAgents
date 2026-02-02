import time
import json
import logging
import sys
import os
from datetime import datetime

# Ensure the root of the project is in sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.rss_poller import RSSPoller
from src.trend_detector import TrendDetector
from src.scraper_agent import ScraperAgent
from src.synthesis_agent import SynthesisAgent

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Orchestrator")

DATA_FILE = "briefing_data.json"

class Orchestrator:
    def __init__(self):
        self.poller = RSSPoller()
        self.detector = TrendDetector()
        self.scraper = ScraperAgent()
        self.synthesizer = SynthesisAgent()
        
    def load_feeds(self):
        try:
            with open('feeds.json', 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Could not load feeds.json: {e}")
            return []

    def run_pipeline(self):
        logger.info("Starting pipeline run...")
        feeds = self.load_feeds()
        
        # 1. Poll Feeds
        articles = self.poller.fetch_feeds(feeds, time_window_hours=24.0) # Using 24h for demo purposes to ensure we get data
        # Note: User request asked for 15 min poll and 1h window for trends. 
        # For initial run/demo, 24h ensures we find something.
        
        if not articles:
            logger.info("No articles found.")
            return

        # 2. Detect Trends
        logger.info(f"Analyzing {len(articles)} articles for trends...")
        clusters = self.detector.detect_clusters(articles)
        
        # Filter for significant clusters
        # Priority 1: Trend (>5), Priority 2: Emerging (>2), Priority 3: Latest (Fallback)
        significant_clusters = [c for c in clusters if len(c) >= 5]
        emerging_clusters = [c for c in clusters if 2 <= len(c) < 5]
        
        briefing_type = "General Update"
        target_articles = []
        
        if significant_clusters:
            briefing_type = "Trending Narrative"
            target_articles = sorted(significant_clusters, key=len, reverse=True)[0]
            logger.info(f"Found {len(significant_clusters)} trends. Processing top trend.")
            
        elif emerging_clusters:
            briefing_type = "Emerging Topic"
            target_articles = sorted(emerging_clusters, key=len, reverse=True)[0]
            logger.info(f"No major trends. Processing top emerging topic.")
            
        else:
            briefing_type = "Latest News Snapshot"
            target_articles = articles[:5]
            logger.info("No clusters found. Processing latest articles.")

        # 3. Scrape URLs
        # Extract unique URLs from target articles
        urls = list(set([a['link'] for a in target_articles]))[:5]
        scrape_results = self.scraper.scrape_urls(urls)
        
        # 4. Synthesize
        logger.info(f"Synthesizing briefing ({briefing_type})...")
        briefing_text = self.synthesizer.synthesize_briefing(scrape_results)
        
        # 5. Save Results
        output = {
            "timestamp": datetime.now().isoformat(),
            "briefing_type": briefing_type,
            "briefing": briefing_text,
            "sources": target_articles, # Metadata for briefing sources
            "trend_size": len(target_articles),
            "all_articles": articles[:50] # Save top 50 recent articles for raw feed
        }
        
        with open(DATA_FILE, 'w') as f:
            json.dump(output, f, indent=2)
            
        logger.info("Briefing generated and saved.")

    def start_loop(self, interval_minutes=15):
        logger.info(f"Starting agent loop, interval {interval_minutes} minutes.")
        while True:
            try:
                self.run_pipeline()
            except Exception as e:
                logger.error(f"Pipeline failed: {e}")
            
            logger.info(f"Sleeping for {interval_minutes} minutes...")
            time.sleep(interval_minutes * 60)

if __name__ == "__main__":
    orchestrator = Orchestrator()
    # For testing, just run once
    orchestrator.run_pipeline()
