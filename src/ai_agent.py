import os
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

class GeminiAgent:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            logger.warning("No Gemini API key provided. AI features will fail if not mocked.")
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro')

    def generate_response(self, prompt, context_history=None):
        """
        Generates a response from Gemini.
        
        Args:
            prompt (str): The user's input or system prompt.
            context_history (list): List of dicts [{'role': 'user'/'model', 'parts': ['text']}]
        
        Returns:
            str: The generated text response.
        """
        if not hasattr(self, 'model'):
            return "AI Service Unavailable (Missing API Key)."

        try:
            chat = self.model.start_chat(history=context_history or [])
            response = chat.send_message(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            return "I'm having trouble connecting to my knowledge base right now."

    def generate_reading_plan(self, profile):
        """Generates a reading plan based on user profile."""
        prompt = (
            f"Generate a customized daily Bible reading plan for a user with the following preferences:\n"
            f"{profile}\n\n"
            "Create a plan for the first 7 days. "
            "Format the output as a Markdown list with 'Day X: Book Chapter:Verse'."
        )
        return self.generate_response(prompt)

    def get_bible_text(self, reference, translation="ESV"):
        """Fetches/Quotes Bible text."""
        prompt = f"Please provide the full text of {reference} in the {translation} translation."
        return self.generate_response(prompt)

    def discuss_reading(self, user_input, history, reading_context, profile=None):
        """Engages in deep-dive discussion with personalization."""
        
        # Build persona context from profile
        persona_context = ""
        if profile:
            persona_context = (
                f"User Profile:\n"
                f"- Denomination/Background: {profile.get('denomination', 'General')}\n"
                f"- Communication Style: {profile.get('style', 'Empathetic')}\n"
                f"- Translation: {profile.get('translation', 'ESV')}\n"
            )

        full_prompt = (
            f"Context: User is reading {reading_context}.\n"
            f"{persona_context}\n"
            f"User says: {user_input}\n"
            "Respond as a knowledgeable, empathetic Bible companion, tailoring your response to the user's background and style."
        )
        return self.generate_response(full_prompt, context_history=history)
