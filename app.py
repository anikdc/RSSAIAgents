import streamlit as st
import json
import os
import time
from datetime import datetime
import sys
import feedparser

# Allow importing from src
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.secrets_helper import load_secrets
from src.orchestrator import Orchestrator

# Load API keys from .env (local) and/or st.secrets (cloud)
load_secrets()

st.set_page_config(
    page_title="AI News Briefing",
    page_icon="",
    layout="wide"
)

DATA_FILE = "briefing_data.json"
FEEDS_DB_FILE = "feeds_db.json"
TRUSTED_FEEDS_FILE = "feeds_default.json"

REGION_OPTIONS = ["global", "us", "uk", "europe", "india", "middle-east", "other"]

def load_data():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return None

# ── Feed Management Helpers ──────────────────────────────────────────

def load_feeds_db():
    """Load the master feed database."""
    if not os.path.exists(FEEDS_DB_FILE):
        return []
    try:
        with open(FEEDS_DB_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_feeds_db(data):
    """Write the master feed database."""
    with open(FEEDS_DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_trusted_feeds():
    """Load the trusted/default feed URL list."""
    if not os.path.exists(TRUSTED_FEEDS_FILE):
        return []
    try:
        with open(TRUSTED_FEEDS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_trusted_feeds(data):
    """Write the trusted/default feed URL list."""
    with open(TRUSTED_FEEDS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def validate_feed_url(url):
    """Attempt to parse an RSS/Atom feed. Returns (ok, message)."""
    try:
        feed = feedparser.parse(url)
        if feed.bozo and not getattr(feed, 'entries', []):
            return False, f"Could not parse feed: {feed.bozo_exception}"
        if not getattr(feed, 'entries', []):
            return False, "Feed parsed but contains zero entries."
        return True, f"Valid feed — {len(feed.entries)} entries found."
    except Exception as e:
        return False, f"Validation error: {e}"

def add_feed(url, name, categories_str, region, trusted):
    """
    Validate and add a feed to the database (and optionally to trusted feeds).
    Returns (success: bool, message: str).
    """
    url = url.strip()
    name = name.strip()
    if not url:
        return False, "Feed URL is required."
    if not name:
        return False, "Feed name is required."

    # Check for duplicates in DB
    db = load_feeds_db()
    existing_urls = {f["url"] for f in db}
    if url in existing_urls:
        return False, "This feed URL already exists in the database."

    # Validate the feed
    ok, msg = validate_feed_url(url)
    if not ok:
        return False, f"Invalid feed — {msg}"

    # Parse categories
    categories = [c.strip().lower() for c in categories_str.split(",") if c.strip()]

    # Add to DB
    db.append({
        "url": url,
        "name": name,
        "categories": categories,
        "region": region
    })
    save_feeds_db(db)

    # Optionally add to trusted feeds
    if trusted:
        trusted_list = load_trusted_feeds()
        if url not in trusted_list:
            trusted_list.append(url)
            save_trusted_feeds(trusted_list)

    return True, msg

def remove_feed_from_db(url):
    """Remove a feed from the DB (and from trusted if present)."""
    db = load_feeds_db()
    db = [f for f in db if f["url"] != url]
    save_feeds_db(db)
    # Also clean up trusted list
    trusted = load_trusted_feeds()
    if url in trusted:
        trusted.remove(url)
        save_trusted_feeds(trusted)

def remove_feed_from_trusted(url):
    """Remove a feed only from the trusted list (keep it in DB)."""
    trusted = load_trusted_feeds()
    if url in trusted:
        trusted.remove(url)
        save_trusted_feeds(trusted)


st.title("AI News Briefing")

data = load_data()

if not data:
    st.info("No briefing data yet. Generate your first briefing below.")

    col1, col2 = st.columns(2)
    with col1:
        init_algo = st.selectbox("Algorithm", ("HDBSCAN", "DBSCAN", "KMeans"), key="init_algo")
    with col2:
        init_fetch = st.checkbox("Fetch fresh articles", value=True, key="init_fetch")

    if st.button("Generate Briefing", type="primary", use_container_width=True):
        with st.spinner("Running the full pipeline — this may take a minute…"):
            try:
                orchestrator = Orchestrator()
                orchestrator.run_pipeline(algorithm=init_algo.lower(), skip_fetch=not init_fetch)
                st.success("Briefing generated!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Pipeline error: {e}")
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

        st.divider()
        st.subheader("Generate Briefing")
        st.caption("Fetches news from your default feeds, clusters trends, and generates a fresh briefing.")
        
        force_fetch = st.checkbox("Fetch fresh articles", value=True, help="Uncheck to quickly re-cluster existing articles without re-fetching and re-verifying.")

        if st.button("Generate Briefing", type="primary", use_container_width=True):
            with st.spinner(f"Running pipeline with {algorithm_choice}..."):
                try:
                    orchestrator = Orchestrator()
                    orchestrator.run_pipeline(algorithm=algorithm_choice.lower(), skip_fetch=not force_fetch)
                    st.success("Briefing generated! Refreshing...")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

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

        # ── Feed Manager ─────────────────────────────────────────
        st.divider()
        st.subheader("Feed Manager")

        # Add New Feed
        with st.expander("Add New Feed"):
            new_url = st.text_input("Feed URL", placeholder="https://example.com/rss/feed.xml", key="new_feed_url")
            new_name = st.text_input("Feed Name", placeholder="e.g. TechCrunch AI", key="new_feed_name")
            new_cats = st.text_input("Categories", placeholder="technology, ai, startups", key="new_feed_cats",
                                     help="Comma-separated tags used by Smart Search to match this feed to queries.")
            new_region = st.selectbox("Region", REGION_OPTIONS, key="new_feed_region")
            new_trusted = st.checkbox("Add to trusted (default) feeds", value=False, key="new_feed_trusted",
                                      help="Trusted feeds are polled automatically during every general briefing.")

            if st.button("Add Feed", use_container_width=True, key="btn_add_feed"):
                with st.spinner("Validating feed..."):
                    ok, msg = add_feed(new_url, new_name, new_cats, new_region, new_trusted)
                if ok:
                    st.success(f"Feed added. {msg}")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)

        # Manage Existing Feeds
        with st.expander("Manage Feeds"):
            tab_trusted, tab_db = st.tabs(["Trusted Feeds", "Database"])

            with tab_trusted:
                trusted_feeds = load_trusted_feeds()
                if not trusted_feeds:
                    st.info("No trusted feeds configured.")
                else:
                    for idx, url in enumerate(trusted_feeds):
                        col_url, col_btn = st.columns([4, 1])
                        with col_url:
                            st.caption(url)
                        with col_btn:
                            if st.button("Remove", key=f"rm_trusted_{idx}", help="Remove from trusted feeds"):
                                remove_feed_from_trusted(url)
                                st.rerun()

            with tab_db:
                db_feeds = load_feeds_db()
                trusted_set = set(load_trusted_feeds())
                if not db_feeds:
                    st.info("Feed database is empty.")
                else:
                    for idx, feed in enumerate(db_feeds):
                        col_info, col_btn = st.columns([4, 1])
                        is_trusted = feed["url"] in trusted_set
                        with col_info:
                            label = f"{'[trusted] ' if is_trusted else ''}{feed.get('name', 'Unnamed')}"
                            cats = ", ".join(feed.get("categories", []))
                            st.markdown(f"**{label}**")
                            st.caption(f"{feed['url']}  \n_{feed.get('region', 'global')} - {cats}_")
                        with col_btn:
                            if st.button("Remove", key=f"rm_db_{idx}", help="Remove from database"):
                                remove_feed_from_db(feed["url"])
                                st.rerun()
