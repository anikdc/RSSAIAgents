import os
from google import genai
from google.genai import types
import numpy as np
from sklearn.cluster import DBSCAN, KMeans, HDBSCAN
from sklearn.preprocessing import normalize
import logging
from dotenv import load_dotenv

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
        
        # DBSCAN parameters:
        # eps is the maximum distance between two samples for one to be considered as in the neighborhood of the other.
        # min_samples is the number of samples (or total weight) in a neighborhood for a point to be considered as a core point.
        # Cosine distance ranges from 0 to 2. Gemini embeddings are often densely packed.
        self.eps = 0.10 # lowered from 0.25 to prevent mega-clusters
        self.min_samples = 2 # Minimum articles to form a cluster

    def _result(self, clusters=None, articles=None):
        return {
            "clusters": clusters or [],
            "articles_with_coords": articles or [],
        }

    def _annotate_as_noise(self, articles):
        for article in articles:
            article['cluster'] = -1
            article['x'] = 0.0
            article['y'] = 0.0
        return articles
        
    def vectorize_texts(self, texts):
        """
        Get embeddings for a list of texts using Gemini.
        """
        if not texts:
            return []
        if not self.client:
            return []
        
        try:
            # Pull embedding model from .env fallback to gemini-embedding-001
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
        Takes a list of articles, vectorizes headlines, and clusters them.
        Returns a list of clusters (each cluster is a list of articles).
        Supported algorithms: "dbscan", "hdbscan", "kmeans"
        
        If search_query is provided, articles are filtered by semantic similarity
        to the query before clustering (zero extra API cost — query is embedded
        in the same batch as the headlines).
        """
        if not articles:
            return self._result()
            
        headlines = []
        for art in articles:
            summary = art.get('summary', '')[:100]
            headlines.append(f"{art['title']} {summary}")
        
        # If search mode, append query to the same batch (free embedding)
        if search_query:
            headlines.append(search_query)
        
        vectors = self.vectorize_texts(headlines)
        
        if not vectors:
            logger.warning("No embeddings generated. Returning articles without clusters.")
            return self._result(articles=self._annotate_as_noise(articles))
        
        # Pop the query vector back out and filter by cosine similarity
        if search_query and vectors:
            query_vec = np.array(vectors.pop())  # last vector is the query
            
            from sklearn.metrics.pairwise import cosine_similarity
            article_arr = np.array(vectors)
            sims = cosine_similarity(query_vec.reshape(1, -1), article_arr)[0]
            
            threshold = 0.55
            kept_indices = [i for i, s in enumerate(sims) if s >= threshold]
            dropped = len(articles) - len(kept_indices)
            logger.info(f"Semantic filter: {len(articles)} → {len(kept_indices)} articles (dropped {dropped}, threshold={threshold})")
            
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
            
        X = np.array(vectors)
        
        # Compute Clustering based on selected algorithm
        algorithm = algorithm.lower().strip()
        
        if algorithm == "hdbscan":
            # HDBSCAN clusters dynamically. It doesn't strictly need eps.
            # Normalizing X to L2 makes euclidean distance equivalent to cosine distance.
            X_norm = normalize(X)
            model = HDBSCAN(
                min_cluster_size=min(len(X_norm), max(2, self.min_samples)),
                copy=False,
            )
            model.fit(X_norm)
            labels = model.labels_
            
        elif algorithm == "kmeans":
            # KMeans requires knowing K. We guess ~10 articles per trend on average
            k = min(len(X), max(2, min(len(X) // 5, 20)))
            # KMeans uses euclidean distance, so we L2 normalize the vectors first
            # to make it behave similarly to spherical k-means / cosine similarity
            X_norm = normalize(X)
            model = KMeans(n_clusters=k, random_state=42, n_init="auto")
            model.fit(X_norm)
            labels = model.labels_
            
        else: # Default to dbscan
            model = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric='cosine')
            model.fit(X)
            labels = model.labels_
        
        # Compute 2D coordinates for cluster map
        try:
            from sklearn.decomposition import PCA
            if len(X) >= 2:
                pca = PCA(n_components=2)
                coords = pca.fit_transform(X)
            else:
                coords = [[0.0, 0.0] for _ in range(len(X))]
        except Exception as e:
            logger.error(f"PCA failed: {e}")
            coords = [[0.0, 0.0] for _ in range(len(X))]
        
        clusters_map = {}
        for index, label in enumerate(labels):
            # Attach cluster and coords to article for UI map
            articles[index]['cluster'] = int(label)
            articles[index]['x'] = float(coords[index][0])
            articles[index]['y'] = float(coords[index][1])

            if label == -1:
                continue # Noise
            
            if label not in clusters_map:
                clusters_map[label] = []
            clusters_map[label].append(articles[index])
            
        # Return both clusters and the annotated articles list
        return {
            "clusters": list(clusters_map.values()),
            "articles_with_coords": articles
        }

if __name__ == "__main__":
    # Mock test
    logging.basicConfig(level=logging.INFO)
    detector = TrendDetector()
    
    mock_articles = [
        {"title": "New iPhone 16 released with AI features", "source": "TechCrunch"},
        {"title": "Apple announces iPhone 16 today", "source": "The Verge"},
        {"title": "iPhone 16: Everything you need to know", "source": "Wired"},
        {"title": "Apple Intelligence comes to iPhone 16", "source": "CNET"},
        {"title": "Review of the new iPhone 16", "source": "NYT"},
        {"title": "SpaceX launches Starship", "source": "BBC"}, # Outlier
        {"title": "Local cat stuck in tree", "source": "Local"}, # Outlier
    ]
    
    # Note: This will fail without API key
    if detector.api_key:
        result = detector.detect_clusters(mock_articles, algorithm="dbscan")
        clusters = result.get('clusters', [])
        for i, cluster in enumerate(clusters):
            print(f"Cluster {i}: {len(cluster)} articles")
            for art in cluster:
                print(f" - {art['title']}")
    else:
        print("Skipping run, no API Key.")
