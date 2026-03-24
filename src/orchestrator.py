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
        
        # Poll Feeds
        articles = self.poller.fetch_feeds(feeds, time_window_hours=24.0) # Using 24h for demo purposes to ensure we get data
        # Note: User request asked for 15 min poll and 1h window for trends. 
        # For initial run/demo, 24h ensures we find something.
        
        if not articles:
            logger.info("No articles found.")
            return

        # Cap at 90 articles to avoid Gemini 100-request/min free tier limit
        articles = articles[:90]

        # Detect Trends
        logger.info(f"Analyzing {len(articles)} articles for trends...")
        clusters_res = self.detector.detect_clusters(articles)
        clusters = clusters_res.get('clusters', [])
        all_articles = clusters_res.get('articles_with_coords', articles)
        
        # Sort all clusters by size
        sorted_clusters = sorted(clusters, key=len, reverse=True)
        valid_clusters = [c for c in sorted_clusters if len(c) >= 2]
        
        trends_output = []
        
        # Process up to top 4 trends
        target_clusters = valid_clusters[:4]
        
        if not target_clusters:
            logger.info("No clusters found. Generating fallback snapshot.")
            target_clusters = [articles[:5]]
            
        for i, cluster in enumerate(target_clusters):
            if len(cluster) >= 5:
                trend_type = "Trending Narrative"
            elif len(cluster) >= 2:
                trend_type = "Emerging Topic"
            else:
                trend_type = "Latest News Snapshot"
                
            urls = []
            seen_links = set()
            for a in cluster:
                link = a['link']
                if link not in seen_links:
                    urls.append(link)
                    seen_links.add(link)
            # Scrape up to 3 articles per trend to keep tokens reasonable
            urls = urls[:3]
            scrape_results = self.scraper.scrape_urls(urls)
            
            trend_num = i + 1
            # Tag the articles in this cluster with the synced UI trend number
            for a in cluster:
                a['ui_trend_num'] = trend_num
                
            logger.info(f"Synthesizing briefing for trend {trend_num} ({trend_type})...")
            briefing_text = self.synthesizer.synthesize_briefing(scrape_results)
            
            trends_output.append({
                "trend_id": trend_num,
                "briefing_type": trend_type,
                "briefing": briefing_text,
                "sources": cluster,
                "trend_size": len(cluster)
            })

        # Save Results
        output = {
            "timestamp": datetime.now().isoformat(),
            "trends": trends_output,
            "all_articles": all_articles[:150] # Save top 150 for the UI cluster map
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
    orchestrator.run_pipeline()
