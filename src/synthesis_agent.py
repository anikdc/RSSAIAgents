import os
from google import genai
import logging
from dotenv import load_dotenv

try:
    import groq
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

load_dotenv()
logger = logging.getLogger(__name__)

class SynthesisAgent:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        
        if self.provider == "groq":
            self.api_key = os.getenv("GROQ_API_KEY")
            if not self.api_key:
                logger.warning("GROQ_API_KEY not found. Synthesis will fail.")
            
            if GROQ_AVAILABLE:
                self.client = Groq(api_key=self.api_key)
                self.groq_model = os.getenv("GROQ_MODEL", "groq/compound-mini")
            else:
                logger.error("groq package not installed but LLM_PROVIDER is groq. Run `uv sync --extra groq`.")
                
        else: # Default to gemini
            self.api_key = os.getenv("GEMINI_API_KEY")
            if not self.api_key:
                logger.warning("GEMINI_API_KEY not found. Synthesis will fail.")
                self.client = None
            else:
                self.client = genai.Client(api_key=self.api_key)
                self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

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
            if self.provider == "groq":
                response = self.client.chat.completions.create(
                    model=self.groq_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"### SOURCES TO SYNTHESIZE:\n\n{context}"}
                    ]
                )
                return response.choices[0].message.content
            else:
                if not self.client:
                    return "Error generating briefing."
                response = self.client.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt,
                )
                return response.text
                
        except Exception as e:
            logger.error(f"Error during synthesis: {e}")
            return "Error generating briefing."

if __name__ == "__main__":
    agent = SynthesisAgent()
    # Mock data would go here
