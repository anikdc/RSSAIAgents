import json
import os
import logging
from urllib.parse import urlparse
from datetime import datetime, timezone
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)

# Module-level cache: load the model once, reuse across all instances
_SENTENCE_MODEL = None

def _get_sentence_model():
    global _SENTENCE_MODEL
    if _SENTENCE_MODEL is None:
        logger.info("Loading SentenceTransformer model (first time)...")
        _SENTENCE_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return _SENTENCE_MODEL


class VerificationAgent:

    def __init__(self, feeds_path="feeds_default.json"):
        # Lightweight semantic model for cross-source corroboration (cached)
        self.model = _get_sentence_model()

        # Load trusted domains from feeds_default.json
        self.trusted_domains = self._load_trusted_domains(feeds_path)


    # -----------------------------------------
    # Load trusted domains from feeds_default.json
    # -----------------------------------------
    def _load_trusted_domains(self, feeds_path):
        """
        Extract base domains from feeds_default.json URLs.
        These are considered editorially trusted sources.
        """
        trusted = set()
        try:
            with open(feeds_path, "r") as f:
                feeds = json.load(f)
            for url in feeds:
                domain = self._extract_domain(url)
                if domain:
                    trusted.add(domain)
        except Exception as e:
            logger.warning(f"Could not load feeds_default.json for trusted domains: {e}")
        
        logger.info(f"Loaded {len(trusted)} trusted domains: {trusted}")
        return trusted


    # -----------------------------------------
    # Extract domain from a URL
    # -----------------------------------------
    def _extract_domain(self, url):
        try:
            domain = urlparse(url).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            # Strip subdomains for feed URLs like feeds.bbci.co.uk -> bbci.co.uk
            # But keep meaningful ones like rss.nytimes.com -> nytimes.com
            parts = domain.split(".")
            if len(parts) > 2:
                # Keep last two parts for standard TLDs (.com, .org)
                # Keep last three for country TLDs (.co.uk)
                if parts[-2] in ("co", "com", "org", "net"):
                    domain = ".".join(parts[-3:])
                else:
                    domain = ".".join(parts[-2:])
            return domain
        except Exception:
            return ""


    # -----------------------------------------
    # Check if domain is in trusted sources
    # -----------------------------------------
    def _is_trusted_source(self, domain):
        return domain in self.trusted_domains


    # -----------------------------------------
    # Cross-Source Corroboration
    # Returns count of unique corroborating domains
    # -----------------------------------------
    def _count_corroborating_domains(self, article_index, embeddings, articles):
        """
        Find articles semantically similar to the given one,
        then count how many UNIQUE domains they come from.
        5 articles from nytimes.com = 1 corroborating domain, not 5.
        """
        emb1 = embeddings[article_index]
        source_domain = self._extract_domain(articles[article_index].get("link", ""))

        corroborating_domains = set()

        for i, emb2 in enumerate(embeddings):
            if i == article_index:
                continue

            similarity = util.cos_sim(emb1, emb2).item()

            if similarity > 0.65:
                other_domain = self._extract_domain(articles[i].get("link", ""))
                # Only count if it's a DIFFERENT domain
                if other_domain and other_domain != source_domain:
                    corroborating_domains.add(other_domain)

        return corroborating_domains


    # -----------------------------------------
    # Content Completeness Score
    # -----------------------------------------
    def _content_completeness_score(self, article):
        """
        Check if the article has meaningful metadata.
        Up to 15 points.
        """
        score = 0

        # Has a real headline (not empty, not too short)
        title = article.get("title", "")
        if len(title) > 20:
            score += 5

        # Has a non-empty summary
        summary = article.get("summary", "")
        if len(summary.strip()) > 0:
            score += 5

        # Has a published date
        if article.get("published"):
            score += 5

        return score


    # -----------------------------------------
    # Recency Score
    # -----------------------------------------
    def _recency_score(self, article):
        """
        How recent is the article? Up to 10 points.
        Articles within 6 hours get full points, decaying to 0 at 48h+.
        """
        published = article.get("published", "")
        if not published:
            return 0

        try:
            pub_dt = datetime.fromisoformat(published)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            age_hours = (now - pub_dt).total_seconds() / 3600

            if age_hours <= 6:
                return 10
            elif age_hours <= 12:
                return 7
            elif age_hours <= 24:
                return 4
            elif age_hours <= 48:
                return 2
            else:
                return 0
        except Exception:
            return 0


    # -----------------------------------------
    # Main Verification Logic
    # -----------------------------------------
    def verify(self, articles):
        """
        Score each article on a 0-100 credibility scale.

        Scoring breakdown:
          - Trusted Source:            0 - 35 pts  (domain is in feeds_default.json)
          - Cross-Source Corroboration: 0 - 40 pts  (unique domains reporting same story)
          - Content Completeness:      0 - 15 pts  (headline, summary, date present)
          - Recency:                   0 - 10 pts  (how fresh the article is)

        Thresholds:
          80-100  -> verified
          50-79   -> likely
          20-49   -> uncertain
          0-19    -> unverified
        """
        titles = [a.get("title", "") for a in articles]

        # Encode all titles once
        embeddings = self.model.encode(
            titles,
            convert_to_tensor=True,
            show_progress_bar=False
        )

        verified_articles = []

        for idx, article in enumerate(articles):

            credibility_score = 0
            domain = self._extract_domain(article.get("link", ""))

            # --- 1. Trusted Source (0-35) ---
            source_score = 35 if self._is_trusted_source(domain) else 0

            # --- 2. Cross-Source Corroboration (0-40) ---
            corroborating = self._count_corroborating_domains(idx, embeddings, articles)
            num_corroborating = len(corroborating)

            # Diminishing returns: 1st = 20, 2nd = 12, 3rd+ = 8 (capped at 40)
            if num_corroborating >= 3:
                corroboration_score = 40
            elif num_corroborating == 2:
                corroboration_score = 32
            elif num_corroborating == 1:
                corroboration_score = 20
            else:
                corroboration_score = 0

            # --- 3. Content Completeness (0-15) ---
            completeness_score = self._content_completeness_score(article)

            # --- 4. Recency (0-10) ---
            recency = self._recency_score(article)

            # --- Final Score ---
            credibility_score = source_score + corroboration_score + completeness_score + recency

            # Determine status
            if credibility_score >= 80:
                status = "verified"
            elif credibility_score >= 50:
                status = "likely"
            elif credibility_score >= 20:
                status = "uncertain"
            else:
                status = "unverified"

            article["verification_status"] = status
            article["verification_detail"] = {
                "domain": domain,
                "is_trusted_source": self._is_trusted_source(domain),
                "corroborating_domains": list(corroborating),
                "source_score": source_score,
                "corroboration_score": corroboration_score,
                "completeness_score": completeness_score,
                "recency_score": recency,
                "credibility_score": credibility_score,
            }

            verified_articles.append(article)

        return verified_articles