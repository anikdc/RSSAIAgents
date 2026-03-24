from urllib.parse import urlparse
import logging
from sentence_transformers import SentenceTransformer, util

logger = logging.getLogger(__name__)


class VerificationAgent:

    def __init__(self):
        # lightweight semantic model
        self.model = SentenceTransformer("all-MiniLM-L6-v2")


    # -----------------------------
    # Extract domain
    # -----------------------------
    def extract_domain(self, url):
        try:
            domain = urlparse(url).netloc.lower()

            if domain.startswith("www."):
                domain = domain[4:]

            return domain

        except Exception:
            return ""


    # -----------------------------
    # Domain validation
    # -----------------------------
    def check_domain_valid(self, domain):
        return domain and "." in domain and len(domain) > 5


    # -----------------------------
    # Semantic Similarity Detection
    # -----------------------------
    def count_similar_articles(self, article_index, embeddings):

        emb1 = embeddings[article_index]

        similar_count = 0

        for i, emb2 in enumerate(embeddings):

            if i == article_index:
                continue

            similarity = util.cos_sim(emb1, emb2).item()

            if similarity > 0.65:
                similar_count += 1

        return similar_count


    # -----------------------------
    # Verification Logic
    # -----------------------------
    def verify(self, articles):

        titles = [a.get("title", "") for a in articles]

        # Encode all titles once (very important optimization)
        embeddings = self.model.encode(
            titles,
            convert_to_tensor=True,
            show_progress_bar=False
        )

        verified_articles = []

        for idx, article in enumerate(articles):

            url = article.get("link", "")
            credibility_score = 0

            # Domain check
            domain = self.extract_domain(url)

            if self.check_domain_valid(domain):
                credibility_score += 30

            # URL structure
            if url.startswith("http"):
                credibility_score += 20

            # Cross-source semantic verification
            similar_articles = self.count_similar_articles(idx, embeddings)

            credibility_score += similar_articles * 20

            # Final decision
            if credibility_score >= 70:
                status = "verified"
            elif credibility_score >= 40:
                status = "uncertain"
            else:
                status = "suspicious"

            article["verification_status"] = status

            article["verification_detail"] = {
                "domain": domain,
                "similar_articles": similar_articles,
                "credibility_score": credibility_score
            }

            verified_articles.append(article)

        return verified_articles