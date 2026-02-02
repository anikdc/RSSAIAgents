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
    page_icon="📰",
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

st.title("📰 AI News Briefing")

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
        briefing_type = data.get('briefing_type', 'Trending Narrative')
        st.markdown(f"### 📢 {briefing_type}")
        
        # Main Briefing Card
        with st.container(border=True):
            st.markdown(data['briefing'])
            
        st.markdown(f"**Synthesized from {data.get('trend_size', '?')} sources**")
        
        # Sources for the briefing
        with st.expander("View Briefing Sources"):
            for source in data.get('sources', []):
                st.markdown(f"- [{source.get('title', 'Link')}]({source.get('link', '#')}) - *{source.get('source', 'Unknown')}*")

        if st.button("Refresh"):
            st.rerun()

    with side_col:
        st.subheader("Controls")
        if st.button("🔄 Trigger Agent Run"):
            with st.spinner("Running agent pipeline (Polling -> Clustering -> Synthesis)..."):
                try:
                    orchestrator = Orchestrator()
                    orchestrator.run_pipeline()
                    st.success("Pipeline finished! Refreshing view...")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error running pipeline: {e}")

        st.subheader("📡 Raw Feed (Latest)")
        st.caption("All polled articles in valid window")
        
        raw_feed = data.get('all_articles', [])
        if not raw_feed:
            st.info("No raw articles data available.")
        
        for art in raw_feed:
            with st.container(border=True):
                st.markdown(f"**[{art.get('title', 'Untitled')}]({art.get('link', '#')})**")
                st.caption(f"{art.get('source', 'Unknown')} • {art.get('published', '')[:16]}")

