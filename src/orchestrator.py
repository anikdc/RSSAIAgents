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
from src.search_agent import SearchAgent

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
        self.search_agent = SearchAgent()


    def load_feeds(self):
        try:
            if os.path.exists('active_feeds.json'):
                with open('active_feeds.json', 'r') as f:
                    feeds = json.load(f)
                    if feeds:
                        return feeds
            
            with open('feeds.json', 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Could not load feeds: {e}")
            return []

    def run_search_pipeline(self, user_query, algorithm="hdbscan"):
        logger.info(f"Running search pipeline for query: '{user_query}'")
        search_result = self.search_agent.search(user_query)
        
        feeds = search_result.get("feeds", [])
        time_window = search_result.get("time_window_hours", 24.0)
        
        parsed_intent = search_result.get("parsed_intent", {})
        
        if not feeds:
            logger.warning("Search returned no feeds. Aborting search pipeline.")
            return
            
        # Write to active_feeds.json non-destructively
        try:
            with open('active_feeds.json', 'w') as f:
                json.dump(feeds, f, indent=2)
            logger.info(f"Saved {len(feeds)} feeds to active_feeds.json")
        except Exception as e:
            logger.error(f"Failed to save active_feeds.json: {e}")
            
        # Run standard pipeline with the new time window and search intent
        self.run_pipeline(algorithm=algorithm, skip_fetch=False, time_window_hours=time_window, search_intent=parsed_intent)

    def run_pipeline(self, algorithm="hdbscan", skip_fetch=False, time_window_hours=24.0, search_intent=None):
        logger.info(f"Starting pipeline run with algorithm: {algorithm}...")
        
        if not skip_fetch:
            feeds = self.load_feeds()

            # ------------------------------
            # 1️⃣ RSS POLLING
            # ------------------------------
            articles = self.poller.fetch_feeds(feeds, time_window_hours=time_window_hours)
            
            # Apply keyword filtering if this is a search
            if search_intent:
                # Use LLM-generated filter_keywords for comprehensive matching
                # Falls back to topics + region if filter_keywords wasn't generated
                keywords = set(search_intent.get("filter_keywords", []))
                if not keywords:
                    keywords = set(search_intent.get("topics", []))
                    region = search_intent.get("region")
                    if region:
                        keywords.add(region)
                
                if keywords:
                    filtered_articles = []
                    for art in articles:
                        content = (art.get('title', '') + ' ' + art.get('summary', '')).lower()
                        # If any keyword is in the content, keep the article
                        if any(kw.lower() in content for kw in keywords):
                            filtered_articles.append(art)
                    logger.info(f"Filtered from {len(articles)} to {len(filtered_articles)} articles using keywords: {keywords}")
                    articles = filtered_articles

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
            
            # Sort articles in cluster by credibility_score descending before picking
            # We want the most credible articles to be sent to the Synthesizer
            cluster_sorted = sorted(
                cluster, 
                key=lambda x: x.get("verification_detail", {}).get("credibility_score", 0), 
                reverse=True
            )

            for article in cluster_sorted:

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

            # Uncomment the line below if you face Groq API rate limits (HTTP 429).
            # This forces the loop to wait 1 minute before processing the next trend,
            # which allows the Tokens Per Minute (TPM) limit to reset.
            # import time; time.sleep(60)


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