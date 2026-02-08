import json
import os
import sys
import logging
from src.trend_detector import TrendDetector
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugClustering")

def debug_clustering():
    # Load data
    try:
        with open('briefing_data.json', 'r') as f:
            data = json.load(f)
            articles = data.get('all_articles', [])
    except FileNotFoundError:
        logger.error("briefing_data.json not found.")
        return

    if not articles:
        logger.error("No articles found in briefing_data.json")
        return

    # Inspect all articles
    subset = articles
    logger.info(f"Loaded {len(articles)} articles. Inspecting distances and clustering for all.")

    detector = TrendDetector()
    headlines = []
    for art in subset:
        summary = art.get('summary', '')[:100]
        headlines.append(f"{art['title']} {summary}")
    
    vectors = detector.vectorize_texts(headlines)
    
    if not vectors:
        logger.error("No vectors returned.")
        return

    from sklearn.metrics.pairwise import cosine_distances
    import numpy as np
    
    X = np.array(vectors)
    dists = cosine_distances(X)
    
    logger.info("\n--- Pairwise Cosine Distances (First 5x5) ---")
    for i in range(min(5, len(subset))):
        row = []
        for j in range(min(5, len(subset))):
            d = dists[i][j]
            row.append(f"{d:.3f}")
        logger.info(f"Art {i}: {row}")
        logger.info(f"  > {subset[i]['title'][:50]}...")

    # Calculate average distance + variance to guess eps
    all_dists = dists[np.triu_indices(len(subset), k=1)]
    if len(all_dists) > 0:
        logger.info(f"\nStats: Min={all_dists.min():.3f}, Max={all_dists.max():.3f}, Mean={all_dists.mean():.3f}, Median={np.median(all_dists):.3f}")

    # Run clustering on ALL articles as before
    # Run clustering on ALL articles using the (newly tuned) class defaults
    logger.info("\n--- Running Clustering with Defaults (eps=0.18, min=2) ---")
    clusters = detector.detect_clusters(articles)

    
    logger.info(f"Total clusters returned: {len(clusters)}")
    
    for i, cluster in enumerate(clusters):
        logger.info(f"--- Cluster {i} (Size: {len(cluster)}) ---")
        for art in cluster:
            logger.info(f"   > {art['title']} ({art['source']})")

    # Analyze why maybe only 1 is significant (>=5)
    significant = [c for c in clusters if len(c) >= 5]
    logger.info(f"Significant Clusters (>=5): {len(significant)}")

if __name__ == "__main__":
    debug_clustering()
