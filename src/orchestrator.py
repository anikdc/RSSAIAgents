import json
import logging
import os
import re
import sys
import time
from datetime import datetime

# Ensure root path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.rss_poller import RSSPoller
from src.scraper_agent import ScraperAgent
from src.search_agent import SearchAgent
from src.synthesis_agent import SynthesisAgent
from src.trend_detector import TrendDetector
from src.verification_agent import VerificationAgent


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler(),
    ],
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
        """Load the default general-news feeds from feeds_default.json."""
        try:
            with open("feeds_default.json", "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Could not load feeds: {e}")
            return []

    def _emit_progress(self, progress_callback, phase, **details):
        """Publish a lightweight progress event for API/job callers."""
        if not progress_callback:
            return
        event = {
            "phase": phase,
            "timestamp": datetime.now().isoformat(),
            **details,
        }
        try:
            progress_callback(event)
        except Exception as e:
            logger.warning(f"Progress callback failed during {phase}: {e}")

    def _empty_result(self, algorithm, status="empty", message=None, search_query=None):
        result = {
            "timestamp": datetime.now().isoformat(),
            "algorithm": algorithm,
            "trends": [],
            "all_articles": [],
            "status": status,
        }
        if message:
            result["message"] = message
        if search_query:
            result["search_query"] = search_query
        return result

    def run_search_pipeline(self, user_query, algorithm="hdbscan", write_output=True, progress_callback=None):
        """Run a search-specific pipeline without overriding the default feeds."""
        logger.info(f"Running search pipeline for query: '{user_query}'")
        self._emit_progress(progress_callback, "parsing_search", search_query=user_query)
        search_result = self.search_agent.search(user_query)

        feeds = search_result.get("feeds", [])
        time_window = search_result.get("time_window_hours", 24.0)
        parsed_intent = search_result.get("parsed_intent", {})

        if not feeds:
            logger.warning("Search returned no feeds. Aborting search pipeline.")
            return self._empty_result(
                algorithm=algorithm,
                status="empty",
                message="Search returned no feeds.",
                search_query=user_query,
            )

        if write_output:
            try:
                with open("active_feeds.json", "w") as f:
                    json.dump(feeds, f, indent=2)
                logger.info(f"Saved {len(feeds)} search feeds to active_feeds.json")
            except Exception as e:
                logger.error(f"Failed to save active_feeds.json: {e}")

        return self.run_pipeline(
            algorithm=algorithm,
            skip_fetch=False,
            time_window_hours=time_window,
            search_intent=parsed_intent,
            feeds_override=feeds,
            search_query=user_query,
            write_output=write_output,
            progress_callback=progress_callback,
        )

    def run_pipeline(
        self,
        algorithm="hdbscan",
        skip_fetch=False,
        time_window_hours=24.0,
        search_intent=None,
        feeds_override=None,
        search_query=None,
        write_output=True,
        progress_callback=None,
    ):
        logger.info(f"Starting pipeline run with algorithm: {algorithm}...")
        self._emit_progress(progress_callback, "started", algorithm=algorithm, search_query=search_query)

        if not skip_fetch:
            feeds = feeds_override if feeds_override else self.load_feeds()

            self._emit_progress(
                progress_callback,
                "fetching_feeds",
                feed_count=len(feeds),
                time_window_hours=time_window_hours,
            )
            articles = self.poller.fetch_feeds(feeds, time_window_hours=time_window_hours)
            self._emit_progress(progress_callback, "feeds_fetched", article_count=len(articles))

            if search_intent:
                keywords = set(search_intent.get("filter_keywords", []))
                if not keywords:
                    keywords = set(search_intent.get("topics", []))
                    region = search_intent.get("region")
                    if region:
                        keywords.add(region)

                if keywords:
                    filtered_articles = []
                    for art in articles:
                        content = (art.get("title", "") + " " + art.get("summary", "")).lower()
                        match_count = sum(
                            1
                            for kw in keywords
                            if re.search(r"\b" + re.escape(kw.lower()) + r"\b", content)
                        )
                        if match_count >= 2:
                            filtered_articles.append(art)
                    logger.info(
                        "Filtered from %s to %s articles (requiring 2+ keyword matches from: %s)",
                        len(articles),
                        len(filtered_articles),
                        keywords,
                    )
                    articles = filtered_articles
                    self._emit_progress(progress_callback, "articles_filtered", article_count=len(articles))

            if not articles:
                logger.info("No articles found.")
                return self._empty_result(
                    algorithm=algorithm,
                    status="empty",
                    message="No articles found.",
                    search_query=search_query,
                )

            articles = articles[:90]

            logger.info("Verifying articles...")
            self._emit_progress(progress_callback, "verifying_articles", article_count=len(articles))
            articles = self.verifier.verify(articles)
            self._emit_progress(progress_callback, "articles_verified", article_count=len(articles))
        else:
            logger.info("Skipping fetch/verify. Loading existing articles from data file...")
            try:
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                    articles = data.get("all_articles", [])
            except Exception as e:
                logger.error(f"Could not load existing articles: {e}")
                articles = []

            if not articles:
                logger.warning("No existing articles to process.")
                return self._empty_result(
                    algorithm=algorithm,
                    status="empty",
                    message="No existing articles to process.",
                    search_query=search_query,
                )

        logger.info(f"Analyzing {len(articles)} articles for trends using {algorithm}...")
        self._emit_progress(progress_callback, "clustering", article_count=len(articles), algorithm=algorithm)
        clusters_res = self.detector.detect_clusters(articles, algorithm=algorithm, search_query=search_query)
        clusters = clusters_res.get("clusters", [])
        all_articles = clusters_res.get("articles_with_coords", articles)
        self._emit_progress(progress_callback, "clustered", cluster_count=len(clusters))

        sorted_clusters = sorted(clusters, key=len, reverse=True)
        valid_clusters = [c for c in sorted_clusters if len(c) >= 2]
        target_clusters = valid_clusters[:4]

        if not target_clusters:
            logger.info("No clusters found. Using fallback snapshot.")
            target_clusters = [articles[:5]]

        from concurrent.futures import ThreadPoolExecutor, as_completed

        cluster_prep = []
        for i, cluster in enumerate(target_clusters):
            trend_num = i + 1

            if len(cluster) >= 5:
                trend_type = "Trending Narrative"
            elif len(cluster) >= 2:
                trend_type = "Emerging Topic"
            else:
                trend_type = "Latest News Snapshot"

            cluster_sorted = sorted(
                cluster,
                key=lambda x: x.get("verification_detail", {}).get("credibility_score", 0),
                reverse=True,
            )

            urls = []
            seen_links = set()
            articles_to_scrape = []
            for article in cluster_sorted:
                link = article.get("link")
                if link and link not in seen_links:
                    urls.append(link)
                    seen_links.add(link)
                    articles_to_scrape.append(article)

            urls = urls[:3]
            articles_to_scrape = articles_to_scrape[:3]

            for article in cluster:
                article["ui_trend_num"] = trend_num

            cluster_prep.append(
                {
                    "trend_num": trend_num,
                    "trend_type": trend_type,
                    "cluster": cluster,
                    "urls": urls,
                    "articles_to_scrape": articles_to_scrape,
                }
            )

        all_urls = []
        for cp in cluster_prep:
            all_urls.extend(cp["urls"])

        logger.info(f"Scraping {len(all_urls)} URLs across {len(cluster_prep)} clusters in parallel...")
        self._emit_progress(
            progress_callback,
            "scraping_sources",
            url_count=len(all_urls),
            cluster_count=len(cluster_prep),
        )
        all_scrape_results = self.scraper.scrape_urls(all_urls)
        self._emit_progress(progress_callback, "sources_scraped", url_count=len(all_scrape_results))

        def _synthesize_cluster(cp):
            scrape_results = {}
            for url in cp["urls"]:
                if url in all_scrape_results:
                    scrape_results[url] = all_scrape_results[url]

            for article in cp["articles_to_scrape"]:
                link = article.get("link")
                if link not in scrape_results or not scrape_results[link].strip():
                    summary = article.get("summary", "")
                    title = article.get("title", "")
                    if summary or title:
                        scrape_results[link] = f"TITLE: {title}\nSUMMARY: {summary}"

            logger.info(f"Synthesizing briefing for trend {cp['trend_num']}")
            self._emit_progress(
                progress_callback,
                "synthesizing_briefing",
                trend_id=cp["trend_num"],
                trend_count=len(cluster_prep),
            )
            briefing_text = self.synthesizer.synthesize_briefing(
                scrape_results, sources_meta=cp["articles_to_scrape"]
            )
            return {
                "trend_id": cp["trend_num"],
                "briefing_type": cp["trend_type"],
                "briefing": briefing_text,
                "sources": cp["cluster"],
                "trend_size": len(cp["cluster"]),
            }

        logger.info(f"Synthesizing {len(cluster_prep)} trends in parallel...")
        trends_output = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(_synthesize_cluster, cp): cp["trend_num"]
                for cp in cluster_prep
            }
            for future in as_completed(futures):
                trend_num = futures[future]
                try:
                    result = future.result()
                    trends_output.append(result)
                except Exception as e:
                    logger.error(f"Synthesis failed for trend {trend_num}: {e}")

        trends_output.sort(key=lambda t: t["trend_id"])

        output = {
            "timestamp": datetime.now().isoformat(),
            "algorithm": algorithm,
            "trends": trends_output,
            "all_articles": all_articles[:150],
            "status": "complete",
        }
        if search_query:
            output["search_query"] = search_query

        if write_output:
            self._emit_progress(progress_callback, "saving_results")
            with open(DATA_FILE, "w") as f:
                json.dump(output, f, indent=2)

        logger.info("Briefing generated and saved.")
        self._emit_progress(
            progress_callback,
            "complete",
            trend_count=len(trends_output),
            article_count=len(output["all_articles"]),
        )
        return output

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
