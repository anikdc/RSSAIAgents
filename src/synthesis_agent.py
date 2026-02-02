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
            self.model = genai.GenerativeModel('gemini-2.5-flash') # Standard model

    def synthesize_briefing(self, articles_content):
        """
        Synthesizes a briefing from a list of article texts.
        articles_content: List of strings (article texts) or Dict {source: text}
        """
        if not articles_content:
            return "No content to synthesize."

        # Prepare context
        context = ""
        for idx, (url, text) in enumerate(articles_content.items()):
            context += f"--- SOURCE {idx+1} ({url}) ---\n{text[:8000]}\n\n"

        prompt = (
            "You are an expert news analyst. "
            "Synthesize these articles into a single coherent narrative briefing. "
            "Highlight discrepancies between sources if any. "
            "Focus on the facts and the bigger picture. "
            "Format nicely in Markdown."
            "\n\n"
            f"{context}"
        )

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error during synthesis: {e}")
            return "Error generating briefing."

if __name__ == "__main__":
    agent = SynthesisAgent()
    # Mock data would go here
