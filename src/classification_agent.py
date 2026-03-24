# src/classification_agent.py

from sentence_transformers import SentenceTransformer
from sklearn.cluster import DBSCAN

class ClassificationAgent:

    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.clusterer = DBSCAN(eps=0.5, min_samples=2, metric='cosine')

    def classify(self, articles):

        texts = [article["title"] for article in articles]

        embeddings = self.model.encode(texts)

        labels = self.clusterer.fit_predict(embeddings)

        for i, article in enumerate(articles):
            article["cluster"] = int(labels[i])

        return articles