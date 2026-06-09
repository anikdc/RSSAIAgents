import logging
import os

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sklearn.cluster import DBSCAN, HDBSCAN, KMeans
from sklearn.preprocessing import normalize


load_dotenv()
logger = logging.getLogger(__name__)


class TrendDetector:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not found. Embeddings will fail.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)

        # DBSCAN parameters.
        self.eps = 0.10
        self.min_samples = 2

    def _result(self, clusters=None, articles=None):
        return {
            "clusters": clusters or [],
            "articles_with_coords": articles or [],
        }

    def _annotate_as_noise(self, articles):
        for article in articles:
            article["cluster"] = -1
            article["x"] = 0.0
            article["y"] = 0.0
        return articles

    def vectorize_texts(self, texts):
        """Get embeddings for a list of texts using Gemini."""
        if not texts:
            return []
        if not self.client:
            return []

        try:
            embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
            result = self.client.models.embed_content(
                model=embedding_model,
                contents=texts,
                config=types.EmbedContentConfig(task_type="CLUSTERING"),
            )
            embeddings = [embedding.values for embedding in (result.embeddings or [])]
            if len(embeddings) != len(texts):
                logger.error(
                    "Embedding count mismatch: requested %s texts but received %s embeddings from %s.",
                    len(texts),
                    len(embeddings),
                    embedding_model,
                )
            return embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []

    def detect_clusters(self, articles, algorithm="dbscan", search_query=None):
        """
        Vectorize headlines and cluster related articles.

        Supported algorithms: dbscan, hdbscan, kmeans.
        If search_query is provided, articles are filtered by semantic similarity.
        The query is embedded in the same batch as the headlines.
        """
        if not articles:
            return self._result()

        headlines = []
        for art in articles:
            summary = art.get("summary", "")[:100]
            headlines.append(f"{art['title']} {summary}")

        if search_query:
            headlines.append(search_query)

        vectors = self.vectorize_texts(headlines)

        if not vectors:
            logger.warning("No embeddings generated. Returning articles without clusters.")
            return self._result(articles=self._annotate_as_noise(articles))

        if search_query and vectors:
            query_vec = np.array(vectors.pop())

            from sklearn.metrics.pairwise import cosine_similarity

            article_arr = np.array(vectors)
            sims = cosine_similarity(query_vec.reshape(1, -1), article_arr)[0]

            threshold = 0.55
            kept_indices = [i for i, s in enumerate(sims) if s >= threshold]
            dropped = len(articles) - len(kept_indices)
            logger.info(
                "Semantic filter: %s -> %s articles (dropped %s, threshold=%s)",
                len(articles),
                len(kept_indices),
                dropped,
                threshold,
            )

            articles = [articles[i] for i in kept_indices]
            vectors = [vectors[i] for i in kept_indices]

            if not articles:
                logger.warning("All articles filtered out by semantic relevance. Returning empty.")
                return self._result()

        if len(vectors) != len(articles):
            logger.error(
                "Cannot cluster because embedding/article counts differ: %s embeddings for %s articles.",
                len(vectors),
                len(articles),
            )
            return self._result(articles=self._annotate_as_noise(articles))

        if len(vectors) < 2:
            logger.info("Need at least 2 embedded articles to cluster; got %s.", len(vectors))
            return self._result(articles=self._annotate_as_noise(articles))

        x_vectors = np.array(vectors)
        algorithm = algorithm.lower().strip()

        if algorithm == "hdbscan":
            x_norm = normalize(x_vectors)
            model = HDBSCAN(
                min_cluster_size=min(len(x_norm), max(2, self.min_samples)),
                copy=False,
            )
            model.fit(x_norm)
            labels = model.labels_
        elif algorithm == "kmeans":
            k = min(len(x_vectors), max(2, min(len(x_vectors) // 5, 20)))
            x_norm = normalize(x_vectors)
            model = KMeans(n_clusters=k, random_state=42, n_init="auto")
            model.fit(x_norm)
            labels = model.labels_
        else:
            model = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric="cosine")
            model.fit(x_vectors)
            labels = model.labels_

        try:
            from sklearn.decomposition import PCA

            if len(x_vectors) >= 2:
                pca = PCA(n_components=2)
                coords = pca.fit_transform(x_vectors)
            else:
                coords = [[0.0, 0.0] for _ in range(len(x_vectors))]
        except Exception as e:
            logger.error(f"PCA failed: {e}")
            coords = [[0.0, 0.0] for _ in range(len(x_vectors))]

        clusters_map = {}
        for index, label in enumerate(labels):
            articles[index]["cluster"] = int(label)
            articles[index]["x"] = float(coords[index][0])
            articles[index]["y"] = float(coords[index][1])

            if label == -1:
                continue

            if label not in clusters_map:
                clusters_map[label] = []
            clusters_map[label].append(articles[index])

        return {
            "clusters": list(clusters_map.values()),
            "articles_with_coords": articles,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    detector = TrendDetector()

    mock_articles = [
        {"title": "New iPhone 16 released with AI features", "source": "TechCrunch"},
        {"title": "Apple announces iPhone 16 today", "source": "The Verge"},
        {"title": "iPhone 16: Everything you need to know", "source": "Wired"},
        {"title": "Apple Intelligence comes to iPhone 16", "source": "CNET"},
        {"title": "Review of the new iPhone 16", "source": "NYT"},
        {"title": "SpaceX launches Starship", "source": "BBC"},
        {"title": "Local cat stuck in tree", "source": "Local"},
    ]

    if detector.api_key:
        result = detector.detect_clusters(mock_articles, algorithm="dbscan")
        clusters = result.get("clusters", [])
        for i, cluster in enumerate(clusters):
            print(f"Cluster {i}: {len(cluster)} articles")
            for art in cluster:
                print(f" - {art['title']}")
    else:
        print("Skipping run, no API key.")
