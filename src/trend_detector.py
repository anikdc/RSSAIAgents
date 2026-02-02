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
        # Cosine distance ranges from 0 to 2. Tightly clustered might be < 0.2
        self.eps = 0.25 
        self.min_samples = 3 # Lowered slightly to capture smaller emerging trends, user asked for >5 for trigger but detection can be lower
        
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
            
        headlines = [f"{art['title']} {art.get('summary', '')[:100]}" for art in articles]
        vectors = self.vectorize_texts(headlines)
        
        if not vectors:
            return []
            
        X = np.array(vectors)
        
        # Compute DBSCAN
        # metric='cosine' expects distance, so eps is cosine distance threshold
        db = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric='cosine').fit(X)
        labels = db.labels_
        
        clusters_map = {}
        for idx, label in enumerate(labels):
            if label == -1:
                continue # Noise
            
            if label not in clusters_map:
                clusters_map[label] = []
            clusters_map[label].append(articles[idx])
            
        # Filter for user requirement: >5 vectors (or maybe >=5)
        # The user said ">5 vectors cluster tightly". 
        # I'll stick to returning all valid clusters for now, key filtering can happen in orchestrator.
        return list(clusters_map.values())

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
        clusters = detector.detect_clusters(mock_articles)
        for i, cluster in enumerate(clusters):
            print(f"Cluster {i}: {len(cluster)} articles")
            for art in cluster:
                print(f" - {art['title']}")
    else:
        print("Skipping run, no API Key.")
