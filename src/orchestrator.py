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
from src.classification_agent import ClassificationAgent


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
        self.classifier = ClassificationAgent()
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

        # ------------------------------
        # 1️⃣ RSS POLLING
        # ------------------------------
        articles = self.poller.fetch_feeds(feeds, time_window_hours=24.0)

        if not articles:
            logger.info("No articles found.")
            return

        articles = articles[:90]

        logger.info(f"Fetched {len(articles)} articles")


        # ------------------------------
        # 2️⃣ VERIFICATION
        # ------------------------------
        logger.info("Running verification agent...")

        verified_articles = []

        for article in articles:

            try:
                result = self.verifier.verify(article, articles)

                # keep verified + uncertain
                if result.get("verification_status") != "suspicious":
                    verified_articles.append(result)

            except Exception as e:
                logger.warning(f"Verification failed: {e}")

        logger.info(f"{len(verified_articles)} articles passed verification")

        if not verified_articles:
            logger.warning("No verified articles.")
            return


        # ------------------------------
        # 3️⃣ CLASSIFICATION
        # ------------------------------
        logger.info("Running classification agent...")

        try:
            classified_articles = self.classifier.classify(verified_articles)

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            classified_articles = verified_articles


        # ------------------------------
        # 4️⃣ TREND DETECTION
        # ------------------------------
        logger.info("Detecting trends...")

        clusters_res = self.detector.detect_clusters(classified_articles)

        clusters = clusters_res.get("clusters", [])
        all_articles = clusters_res.get("articles_with_coords", classified_articles)

        sorted_clusters = sorted(clusters, key=len, reverse=True)

        valid_clusters = [c for c in sorted_clusters if len(c) >= 2]

        trends_output = []

        target_clusters = valid_clusters[:4]

        if not target_clusters:
            logger.info("No clusters found. Using fallback snapshot.")
            target_clusters = [classified_articles[:5]]


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

            for article in cluster:

                link = article.get("link")

                if link and link not in seen_links:
                    urls.append(link)
                    seen_links.add(link)

            urls = urls[:3]

            scrape_results = self.scraper.scrape_urls(urls)

            trend_num = i + 1

            for article in cluster:
                article["ui_trend_num"] = trend_num

            logger.info(f"Synthesizing briefing for trend {trend_num}")

            briefing_text = self.synthesizer.synthesize_briefing(scrape_results)

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