# AI News Trend Agent

This project is a Python-based system that polls RSS feeds, detects trending topics using vector clustering, and uses Google Gemini to synthesize a briefing from the clustered articles. It provides a Streamlit interface to view the generated briefing and the latest raw news feed.

## Prerequisites

- Python 3.8 or higher
- A Google Gemini API Key

## Installation

1. Clone this repository.

2. Create a virtual environment:
   python -m venv venv

3. Activate the virtual environment:
   - Windows: .\venv\Scripts\activate
   - Linux/Mac: source venv/bin/activate

4. Install dependencies:
   pip install -r requirements.txt

5. Configure Environment Variables:
   - Rename .env.example to .env
   - Open .env and set your GEMINI_API_KEY.

## Usage

### Running the System
You can run the agent and the UI independently, or trigger the agent directly from the UI.

To start the UI (which includes a button to trigger the agent):
streamlit run app.py

If running in a headless environment (like WSL or a server), use:
streamlit run app.py --server.headless true

### Running the Agent Manually
To run the news collection and synthesis pipeline manually from the command line:
python src/orchestrator.py

## File Description

### Root Directory
- app.py: The Streamlit web application. It displays the briefing and provides controls to trigger the agent.
- feeds.json: A JSON list of RSS feed URLs to poll. You can edit this file to add or remove sources.
- requirements.txt: List of Python dependencies.
- .env: Configuration file for API keys (not committed to git).

### src/ Directory
- src/orchestrator.py: The main controller. It coordinates fetching feeds, detecting trends, scraping content, and synthesis.
- src/rss_poller.py: Handles fetching and parsing of RSS feeds.
- src/trend_detector.py: Uses embeddings and clustering (DBSCAN) to group similar articles into trends.
- src/scraper_agent.py: Fetches the full text of articles from their URLs.
- src/synthesis_agent.py: Interfaces with the Gemini API to summarize the clustered articles into a coherent narrative.
