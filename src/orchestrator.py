import time
import json
import logging
import sys
import os
from datetime import datetime

# Ensure root path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.rss_poller import RSSPoller
from src.trend_detector import TrendDetector
from src.scraper_agent import ScraperAgent
from src.synthesis_agent import SynthesisAgent
from src.verification_agent import VerificationAgent

# Logging
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
        self.verifier = VerificationAgent()
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

    def run_pipeline(self, algorithm="dbscan", skip_fetch=False):
        logger.info(f"Starting pipeline run with algorithm: {algorithm}...")
        
        if not skip_fetch:
            feeds = self.load_feeds()

            # ------------------------------
            # 1️⃣ RSS POLLING
            # ------------------------------
            articles = self.poller.fetch_feeds(feeds, time_window_hours=24.0)

            if not articles:
                logger.info("No articles found.")
                return

            # Cap at 90 articles to avoid Gemini 100 request/min free tier limit
            articles = articles[:90]

            # Verify articles
            logger.info("Verifying articles...")
            articles = self.verifier.verify(articles)
        else:
            logger.info("Skipping fetch/verify. Loading existing articles from data file...")
            try:
                with open(DATA_FILE, 'r') as f:
                    data = json.load(f)
                    articles = data.get('all_articles', [])
            except Exception as e:
                logger.error(f"Could not load existing articles: {e}")
                articles = []
                
            if not articles:
                logger.warning("No existing articles to process.")
                return

        # Detect Trends
        logger.info(f"Analyzing {len(articles)} articles for trends using {algorithm}...")
        clusters_res = self.detector.detect_clusters(articles, algorithm=algorithm)
        clusters = clusters_res.get('clusters', [])
        all_articles = clusters_res.get('articles_with_coords', articles)
        
        # Sort all clusters by size
        sorted_clusters = sorted(clusters, key=len, reverse=True)

        valid_clusters = [c for c in sorted_clusters if len(c) >= 2]

        trends_output = []

        target_clusters = valid_clusters[:4]

        if not target_clusters:
            logger.info("No clusters found. Using fallback snapshot.")
            target_clusters = [articles[:5]]


        # ------------------------------
        # 5️⃣ SCRAPING + SYNTHESIS
        # ------------------------------
        for i, cluster in enumerate(target_clusters):

            if len(cluster) >= 5:
                trend_type = "Trending Narrative"
            elif len(cluster) >= 2:
                trend_type = "Emerging Topic"
            else:
                trend_type = "Latest News Snapshot"

            urls = []
            seen_links = set()
            articles_to_scrape = []

            for article in cluster:

                link = article.get("link")

                if link and link not in seen_links:
                    urls.append(link)
                    seen_links.add(link)
                    articles_to_scrape.append(article)

            urls = urls[:3]
            articles_to_scrape = articles_to_scrape[:3]

            scrape_results = self.scraper.scrape_urls(urls)
            
            # Fallback to summary if scraping fails
            for article in articles_to_scrape:
                link = article.get("link")
                if link not in scrape_results or not scrape_results[link].strip():
                    summary = article.get("summary", "")
                    title = article.get("title", "")
                    if summary or title:
                        scrape_results[link] = f"TITLE: {title}\nSUMMARY: {summary}"

            trend_num = i + 1

            for article in cluster:
                article["ui_trend_num"] = trend_num

            logger.info(f"Synthesizing briefing for trend {trend_num}")

            briefing_text = self.synthesizer.synthesize_briefing(scrape_results, sources_meta=articles_to_scrape)

            trends_output.append({
                "trend_id": trend_num,
                "briefing_type": trend_type,
                "briefing": briefing_text,
                "sources": cluster,
                "trend_size": len(cluster)
            })


        # ------------------------------
        # 6️⃣ SAVE OUTPUT
        # ------------------------------
        output = {
            "timestamp": datetime.now().isoformat(),
            "algorithm": algorithm,
            "trends": trends_output,
            "all_articles": all_articles[:150]
        }

        with open(DATA_FILE, "w") as f:
            json.dump(output, f, indent=2)

        logger.info("Briefing generated and saved.")


    def start_loop(self, interval_minutes=15):

        logger.info(f"Starting agent loop every {interval_minutes} minutes.")

        while True:

            try:
                self.run_pipeline()

            except Exception as e:
                logger.error(f"Pipeline failed: {e}")

            logger.info(f"Sleeping {interval_minutes} minutes")

            time.sleep(interval_minutes * 60)


if __name__ == "__main__":

    orchestrator = Orchestrator()

    orchestrator.run_pipeline()