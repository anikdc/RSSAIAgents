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
    st.caption(f"Last updated: {last_update.strftime('%Y-%m-%d %H:%M:%S')}")
    
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
                    st.markdown(trend['briefing'])
                    
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
                        elif status == "uncertain":
                            badge = "🟡 UNCERTAIN"
                        else:
                            badge = "🔴 SUSPICIOUS"

                        st.markdown(
                            f"- [{source.get('title','Link')}]({source.get('link','#')}) "
                            f"({domain})  \n"
                            f"{badge} • Credibility Score: **{score}**"
                        )
                st.divider()

        if st.button("Refresh"):
            st.rerun()

    with side_col:
        st.subheader("Controls")
        if st.button("Trigger Agent Run"):
            with st.spinner("Running agent pipeline (Polling -> Clustering -> Synthesis)..."):
                try:
                    orchestrator = Orchestrator()
                    orchestrator.run_pipeline()
                    st.success("Pipeline finished! Refreshing view...")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error running pipeline: {e}")

        st.subheader("Trend Cluster Map")
        raw_feed = data.get('all_articles', [])
        if raw_feed:
            plot_data = []
            for art in raw_feed:
                trend_num = art.get('ui_trend_num', -1)
                if trend_num == -1:
                    continue # Filter out noise and minor clusters not in top 4
                
                # Ensure it's rendered as 1-indexed string categories to match summary
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

