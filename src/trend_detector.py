import os
import google.generativeai as genai
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_distances
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class TrendDetector:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not found. Embeddings will fail.")
        else:
            genai.configure(api_key=self.api_key)
        
        # DBSCAN parameters:
        # eps is the maximum distance between two samples for one to be considered as in the neighborhood of the other.
        # min_samples is the number of samples (or total weight) in a neighborhood for a point to be considered as a core point.
        # Cosine distance ranges from 0 to 2. Gemini embeddings are often densely packed.
        self.eps = 0.10 # Significantly lowered from 0.25 to prevent mega-clusters
        self.min_samples = 2 # Minimum articles to form a cluster
        
    def vectorize_texts(self, texts):
        """
        Get embeddings for a list of texts using Gemini.
        """
        if not texts:
            return []
        
        try:
            # text-embedding-004 is a good model choice
            result = genai.embed_content(
                model="gemini-embedding-001",
                content=texts,
                task_type="clustering",
            )
            return result['embedding']
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []

    def detect_clusters(self, articles):
        """
        Takes a list of articles, vectorizes headlines, and clusters them.
        Returns a list of clusters (each cluster is a list of articles).
        """
        if not articles:
            return []
            
        headlines = []
        for art in articles:
            summary = art.get('summary', '')[:100]
            headlines.append(f"{art['title']} {summary}")
        vectors = self.vectorize_texts(headlines)
        
        if not vectors:
            return []
            
        X = np.array(vectors)
        
        # Compute DBSCAN
        # metric='cosine' expects distance, so eps is cosine distance threshold
        db = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric='cosine').fit(X)
        labels = db.labels_
        
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
        for idx, label in enumerate(labels):
            # Attach cluster and coords to article for UI map
            articles[idx]['cluster'] = int(label)
            articles[idx]['x'] = float(coords[idx][0])
            articles[idx]['y'] = float(coords[idx][1])

            if label == -1:
                continue # Noise
            
            if label not in clusters_map:
                clusters_map[label] = []
            clusters_map[label].append(articles[idx])
            
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
        result = detector.detect_clusters(mock_articles)
        clusters = result.get('clusters', [])
        for i, cluster in enumerate(clusters):
            print(f"Cluster {i}: {len(cluster)} articles")
            for art in cluster:
                print(f" - {art['title']}")
    else:
        print("Skipping run, no API Key.")
