import os
import json
import logging
import google.generativeai as genai
from dotenv import load_dotenv

try:
    import groq
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

load_dotenv()
logger = logging.getLogger(__name__)

class SearchAgent:
    def __init__(self, db_path="feeds_db.json"):
        self.db_path = db_path
        self.feeds_db = self._load_db()
        
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        
        if self.provider == "groq":
            self.api_key = os.getenv("GROQ_API_KEY")
            if not self.api_key:
                logger.warning("GROQ_API_KEY not found. Query parsing will fail.")
            
            if GROQ_AVAILABLE:
                self.client = Groq(api_key=self.api_key)
                # Using a faster, smaller model for simple JSON extraction
                self.groq_model = os.getenv("GROQ_MODEL", "llama3-8b-8192")
            else:
                logger.error("groq package not installed but LLM_PROVIDER is groq.")
                
        else: # Default to gemini
            self.api_key = os.getenv("GEMINI_API_KEY")
            if not self.api_key:
                logger.warning("GEMINI_API_KEY not found. Query parsing will fail.")
            else:
                genai.configure(api_key=self.api_key)
                gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
                self.model = genai.GenerativeModel(gemini_model)

    def _load_db(self):
        try:
            with open(self.db_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Could not load {self.db_path}: {e}")
            return []

    def parse_query(self, user_query):
        """
        Uses an LLM to extract topics, time window, and region from a natural language query.
        Returns a dictionary with these parsed fields.
        """
        system_prompt = """
        You are a search query parser for a news aggregator.
        Extract the topics, time window, region, and filter keywords from the user's query.
        
        Time Rules:
        - Convert any time references into hours as an integer (e.g., "last week" = 168, "yesterday" = 48, "today" = 24, "last 3 days" = 72, "last month" = 720).
        - If no time is specified, output null for time_filter_hours.
        
        Region Rules:
        - If a specific country/region is mentioned (e.g., "ukraine", "us", "uk", "europe", "india", "middle-east"), extract it.
        - Otherwise, output null for region.
        
        Topics Rules:
        - Extract the core topics or categories (e.g., "technology", "ai", "politics", "science").
        - Output them as a list of lowercase strings.
        
        Filter Keywords Rules:
        - Generate a comprehensive list of keywords, synonyms, related terms, key people, cities, and alternate spellings that a news article about this topic would likely contain.
        - For example, if the topic is "ukraine", filter_keywords should include: ["ukraine", "ukrainian", "kyiv", "kiev", "zelenskyy", "zelensky", "donbas", "crimea", "kherson", "bakhmut", "zaporizhzhia"].
        - If the topic is "technology", filter_keywords should include: ["tech", "technology", "software", "hardware", "startup", "silicon valley", "computing"].
        - Include at least 5-15 filter keywords for thorough coverage.
        
        Output strictly in JSON format:
        {
          "topics": ["topic1", "topic2"],
          "time_filter_hours": 168,
          "region": "europe",
          "filter_keywords": ["keyword1", "keyword2", "keyword3"]
        }
        Return ONLY the JSON object, no markdown blocks or extra text.
        """
        
        try:
            if self.provider == "groq" and GROQ_AVAILABLE:
                response = self.client.chat.completions.create(
                    model=self.groq_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_query}
                    ],
                    response_format={"type": "json_object"}
                )
                output = response.choices[0].message.content
            else:
                # Gemini doesn't strictly enforce JSON object return without schema,
                # but standard prompting works well with flash
                response = self.model.generate_content(
                    f"{system_prompt}\n\nUser Query: {user_query}",
                    generation_config={"response_mime_type": "application/json"}
                )
                output = response.text
                
            return json.loads(output)
            
        except Exception as e:
            logger.error(f"Error parsing query: {e}")
            # Fallback
            return {
                "topics": [w.lower() for w in user_query.split() if len(w) > 3],
                "time_filter_hours": None,
                "region": None
            }

    def find_feeds(self, parsed_query, max_feeds=10):
        """
        Scores feeds in the database against the parsed query and returns the top matches.
        """
        topics = parsed_query.get("topics", [])
        region = parsed_query.get("region")
        
        if not topics and not region:
             # If completely empty query, return top general feeds
             return [f["url"] for f in self.feeds_db[:max_feeds]]

        scored_feeds = []
        
        for feed in self.feeds_db:
            score = 0
            feed_categories = feed.get("categories", [])
            feed_region = feed.get("region", "global")
            feed_name = feed.get("name", "").lower()
            
            # Score topics (matches against category list or name)
            for topic in topics:
                if topic in feed_categories:
                    score += 3
                elif topic in feed_name:
                    score += 2
                    
            # Score region
            if region:
                if feed_region == region.lower() or region.lower() in feed_categories:
                    score += 5
                elif region.lower() in feed_name:
                    score += 3
                    
            # Intelligent fallback for regional/country searches:
            # If the user is searching for a specific region or a country-like topic, 
            # give a slight boost to general "world", "conflict", or "politics" feeds 
            # so they get included as secondary (or primary) sources.
            is_regional_query = region is not None or any(t in ["ukraine", "russia", "china", "israel", "gaza", "middle-east", "europe", "us", "uk", "india"] for t in topics)
            
            if is_regional_query and ("world" in feed_categories or "conflict" in feed_categories or "politics" in feed_categories):
                score += 2
                    
            if score > 0:
                scored_feeds.append((score, feed["url"]))
                
        # Sort by score descending
        scored_feeds.sort(key=lambda x: x[0], reverse=True)
        
        # If we found nothing, fallback to some default feeds
        if not scored_feeds:
            logger.info("No exact feed matches found, falling back to general feeds.")
            return [f["url"] for f in self.feeds_db[:max_feeds] if "global" in f.get("region", "")]

        return [url for score, url in scored_feeds[:max_feeds]]

    def search(self, user_query):
        """
        Main entry point. Parses query, finds feeds, returns parameters for orchestrator.
        """
        logger.info(f"Processing search query: '{user_query}'")
        parsed = self.parse_query(user_query)
        logger.info(f"Parsed query: {parsed}")
        
        feeds = self.find_feeds(parsed)
        logger.info(f"Found {len(feeds)} matching feeds.")
        
        # Default to 24 hours if no time filter specified
        time_window = parsed.get("time_filter_hours")
        if time_window is None or time_window <= 0:
            time_window = 24.0
            
        return {
            "feeds": feeds,
            "time_window_hours": float(time_window),
            "parsed_intent": parsed
        }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = SearchAgent()
    print("Testing 'news related to technology'")
    print(agent.search("news related to technology"))
    print("\nTesting 'news related to ukraine in the last week'")
    print(agent.search("news related to ukraine in the last week"))
