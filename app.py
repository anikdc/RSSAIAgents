import streamlit as st
import json
import os
import time
from datetime import datetime
import sys

# Allow importing from src
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.orchestrator import Orchestrator

st.set_page_config(
    page_title="AI News Briefing",
    page_icon="",
    layout="wide"
)

DATA_FILE = "briefing_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return None

st.title("AI News Briefing")

data = load_data()

if not data:
    st.info("Waiting for the Agent to generate the first briefing...")
    st.text("Make sure 'src/orchestrator.py' is running.")
    
    if st.button("Refresh"):
        st.rerun()
else:
    # Header
    last_update = datetime.fromisoformat(data['timestamp'])
    algo_used = data.get('algorithm', 'dbscan').title()
    st.caption(f"Last updated: {last_update.strftime('%Y-%m-%d %H:%M:%S')} • Algorithm: {algo_used}")
    
    # Layout with sidebar-like structure or just columns
    main_col, side_col = st.columns([2, 1])
    
    with main_col:
        st.header("Trending Now")
        trends = data.get('trends', [])
        
        if not trends:
            st.info("No trends detected.")
        else:
            for trend in trends:
                st.markdown(f"### Trend {trend['trend_id']}") #: {trend['briefing_type']}
                
                # Main Briefing Card
                with st.container(border=True):
                    st.markdown(trend['briefing'].replace('$', '\\$'))
                    
                st.markdown(f"**Synthesized from {trend.get('trend_size', '?')} sources**")
                
                # Sources for the briefing natively grouped
                with st.expander(f"View Topics for Trend {trend['trend_id']}"):
                    for source in trend.get('sources', []):
                        verification = source.get("verification_detail", {})
                        status = source.get("verification_status", "unknown")

                        score = verification.get("credibility_score", "?")
                        domain = verification.get("domain", "unknown")

                        if status == "verified":
                            badge = "🟢 VERIFIED"
                        elif status == "likely":
                            badge = "🔵 LIKELY"
                        elif status == "uncertain":
                            badge = "🟡 UNCERTAIN"
                        else:
                            badge = "🔴 UNVERIFIED"

                        st.markdown(
                            f"- [{source.get('title','Link')}]({source.get('link','#')}) "
                            f"({domain})  \n"
                            f"{badge} • Credibility Score: **{score}**"
                        )
                st.divider()

        if st.button("Refresh"):
            st.rerun()

    with side_col:
        st.subheader("Smart Search")
        search_query = st.text_input("Search for news...", placeholder="e.g. 'news about technology', 'iran news'")
        
        # We need the algorithm choice early for the search pipeline
        algorithm_choice = st.selectbox(
            "Clustering Algorithm",
            ("DBSCAN", "HDBSCAN", "KMeans"),
            index=1,
            help="Select the algorithm to use for clustering the news trends."
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Search & Run", use_container_width=True):
                if search_query:
                    with st.spinner("Finding feeds and running pipeline..."):
                        try:
                            orchestrator = Orchestrator()
                            orchestrator.run_search_pipeline(search_query, algorithm=algorithm_choice.lower())
                            st.success("Search complete!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Search error: {e}")
                else:
                    st.warning("Please enter a query.")
                    
        with col2:
            if os.path.exists('active_feeds.json'):
                if st.button("Reset Feeds", help="Return to default feeds", use_container_width=True):
                    try:
                        os.remove('active_feeds.json')
                        st.success("Reset to defaults.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error resetting: {e}")

        st.divider()
        st.subheader("Controls")
        
        force_fetch = st.checkbox("Fetch and verify new articles", value=False, help="Uncheck to quickly re-cluster existing articles without re-verifying.")

        if st.button("Trigger Agent Run"):
            with st.spinner(f"Running agent pipeline with {algorithm_choice}..."):
                try:
                    orchestrator = Orchestrator()
                    orchestrator.run_pipeline(algorithm=algorithm_choice.lower(), skip_fetch=not force_fetch)
                    st.success("Pipeline finished! Refreshing view...")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error running pipeline: {e}")

        st.subheader("Trend Cluster Map")
        show_noise = st.checkbox("Show noisy articles", value=False, help="Visualize unclustered articles (-1) in a distinct color.")
        raw_feed = data.get('all_articles', [])
        if raw_feed:
            plot_data = []
            for art in raw_feed:
                trend_num = art.get('ui_trend_num', -1)
                
                if trend_num == -1:
                    if not show_noise:
                        continue # Filter out noise unless requested
                    cluster_label = "Noise"
                else:
                    cluster_label = f"Trend {trend_num}"
                
                plot_data.append({
                    "x": art.get('x', 0.0),
                    "y": art.get('y', 0.0),
                    "Cluster": cluster_label,
                })
                
            # Streamlit scatter chart supports lists of dicts
            st.scatter_chart(plot_data, x="x", y="y", color="Cluster")
            
        st.subheader("Raw Feed (Latest)")
        st.caption("All polled articles in valid window")
        
        if not raw_feed:
            st.info("No raw articles data available.")
        
        for art in raw_feed[:15]: # Show top 15 in sidebar to avoid overflow
            with st.container(border=True):
                st.markdown(f"**[{art.get('title', 'Untitled')}]({art.get('link', '#')})**")
                st.caption(f"{art.get('source', 'Unknown')} • {art.get('published', '')[:16]}")

