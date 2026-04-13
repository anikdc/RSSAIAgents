import os
import google.generativeai as genai
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

class SynthesisAgent:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not found. Synthesis will fail.")
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-3.1-flash-lite-preview') 

    def synthesize_briefing(self, articles_content, sources_meta=None):
        """
        Synthesizes a briefing from a list of article texts.
        articles_content: Dict {url: text}
        sources_meta: Optional list of article dicts with 'title', 'source', 'link' keys,
                      used to provide richer source labels for inline citations.
        """
        if not articles_content:
            return "No content to synthesize."

        # Build a lookup from URL to article metadata for richer labels
        meta_lookup = {}
        if sources_meta:
            for art in sources_meta:
                link = art.get("link", "")
                if link:
                    meta_lookup[link] = art

        # Prepare context with rich source labels
        context = ""
        for idx, (url, text) in enumerate(articles_content.items()):
            meta = meta_lookup.get(url, {})
            source_name = meta.get("source", "Unknown")
            title = meta.get("title", "Untitled")
            label = f'SOURCE {idx+1} ({source_name} — "{title}") [{url}]'
            context += f"--- {label} ---\n{text[:8000]}\n\n"

        # Load system prompt
        system_prompt = ""
        prompt_path = os.path.join(os.path.dirname(__file__), 'systemprompt.txt')
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                system_prompt = f.read()
        except Exception as e:
            logger.error(f"Could not load system prompt: {e}")
            system_prompt = (
                "You are an expert news analyst. "
                "Synthesize these articles into a single coherent narrative briefing. "
                "Highlight discrepancies between sources if any. "
                "Focus on the facts and the bigger picture. "
                "Format nicely in Markdown."
            )

        prompt = f"{system_prompt}\n\n### SOURCES TO SYNTHESIZE:\n\n{context}"

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error during synthesis: {e}")
            return "Error generating briefing."

if __name__ == "__main__":
    agent = SynthesisAgent()
    # Mock data would go here
