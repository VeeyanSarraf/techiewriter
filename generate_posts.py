"""
LinkedIn Post Generator - ML-Enhanced with Gemini
Pipeline: scraper -> DB -> build_index -> train_model -> generate_posts
Outputs ONLY the final post text (no JSON, no extra metadata)
"""

import os
import time
import random
import threading
import argparse
import pickle
import sys
import mysql_utils
import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core.exceptions import ResourceExhausted, TooManyRequests
from serpapi import GoogleSearch
import json

# ----------------- Load Keys -----------------
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SERP_API_KEY = os.getenv("SERPAPI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ Error: GEMINI_API_KEY missing in .env")
    sys.exit(1)

genai.configure(api_key=GEMINI_API_KEY)

# ----------------- Config -----------------
PRIMARY_MODEL = "models/gemini-2.0-flash-exp"
FALLBACK_MODEL = "models/gemini-1.5-pro"
GEN_CFG = {
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "max_output_tokens": 1000,
}

# ----------------- Load Trained ML Models -----------------
class MLModelLoader:
    def __init__(self):
        self.patterns = None
        self.stats = None
        self.vectorizer = None
        self.load_models()
    
    def load_models(self):
        """Load trained models if available"""
        try:
            with open('models/patterns.json', 'r', encoding='utf-8') as f:
                self.patterns = json.load(f)
            with open('models/stats.json', 'r', encoding='utf-8') as f:
                self.stats = json.load(f)
            with open('models/tfidf_vectorizer.pkl', 'rb') as f:
                self.vectorizer = pickle.load(f)
            print("✅ ML models loaded", file=sys.stderr)
        except FileNotFoundError:
            print("⚠️  ML models not found (run train_model.py)", file=sys.stderr)

ml_models = MLModelLoader()

# ----------------- Prompt Builder -----------------
def build_enhanced_prompt(user_idea, db_context, web_context, founder=None, company=None):
    """Builds a context-aware prompt"""
    base_prompt = f"""You are an expert LinkedIn content creator.

Write a professional, natural LinkedIn post for the following topic:

**Topic:** {user_idea}

Guidelines:
- Start with a strong hook.
- Add storytelling or founder journey if available.
- Keep it human-like and engaging.
- Avoid robotic tone and repetition.
- End with a question or reflection.
- Use only relevant hashtags (based on topic or industry).
- Avoid adding names, random people, or irrelevant hashtags.

Database Context: {db_context}
Web Context: {web_context}
"""
    if founder:
        base_prompt += f"Founder: {founder}\n"
    if company:
        base_prompt += f"Company: {company}\n"
    return base_prompt

# ----------------- Rate Limiter -----------------
class RateLimiter:
    def __init__(self, rps: float, burst: int):
        self.rate, self.capacity, self.tokens = rps, burst, burst
        self.lock, self.last = threading.Lock(), time.time()

    def acquire(self):
        with self.lock:
            now = time.time()
            elapsed = now - self.last
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last = now
            if self.tokens < 1:
                time.sleep((1 - self.tokens) / self.rate)
                self.tokens = 0
            else:
                self.tokens -= 1

limiter = RateLimiter(1.0, 3)

# ----------------- Helpers -----------------
def safe_response_to_text(response):
    """Extract clean text from Gemini API response"""
    if not response or not hasattr(response, "candidates"):
        return ""
    for c in response.candidates:
        if hasattr(c, "content") and hasattr(c.content, "parts"):
            parts = [p.text for p in c.content.parts if hasattr(p, "text")]
            if parts:
                return " ".join(parts).strip()
    return ""

def deduplicate_text(text: str) -> str:
    """Remove duplicate lines/sentences"""
    lines, seen = [], set()
    for line in text.splitlines():
        clean = line.strip()
        if clean and clean not in seen:
            lines.append(clean)
            seen.add(clean)
    return "\n".join(lines).strip()

def fetch_db_context(limit=3):
    """Fetch recent posts for context"""
    try:
        conn = mysql_utils.get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT content FROM posts ORDER BY scraped_at DESC LIMIT %s", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return " | ".join([r["content"] for r in rows if r["content"]]) if rows else "None"
    except Exception:
        return "None"

def fetch_web_context(query):
    """Fetch web snippets"""
    if not SERP_API_KEY:
        return "None"
    try:
        search = GoogleSearch({"q": query, "api_key": SERP_API_KEY})
        results = search.get_dict()
        snippets = [r["snippet"] for r in results.get("organic_results", []) if "snippet" in r]
        return " | ".join(snippets[:5]) if snippets else "None"
    except Exception:
        return "None"

def _generate_with_retries(model_name, prompt, max_retries=4):
    limiter.acquire()
    model = genai.GenerativeModel(model_name=model_name, generation_config=GEN_CFG)
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except (ResourceExhausted, TooManyRequests):
            time.sleep(2**attempt + random.random())
        except Exception as e:
            print(f"[error] {model_name} failed: {e}", file=sys.stderr)
            break
    return None

# ----------------- Post Processing -----------------
def apply_post_processing(post: str, idea: str) -> str:
    """Clean hashtags and refine post"""
    if not post:
        return post
    post = "\n".join([line for line in post.splitlines() if not line.strip().startswith("#")])
    keywords = [w for w in idea.split() if len(w) > 3][:3]
    hashtags = " ".join([f"#{w.capitalize()}" for w in keywords])
    if hashtags:
        post += "\n\n" + hashtags
    if "?" not in post:
        post += "\n\nWhat do you think?"
    return post.strip()

# ----------------- Main -----------------
def generate_linkedin_post(idea, founder=None, company=None):
    if not idea.strip():
        return "Error: Empty idea provided."
    db_context = fetch_db_context()
    web_context = fetch_web_context(f"{founder or ''} {company or ''}".strip() or idea)
    prompt = build_enhanced_prompt(idea, db_context, web_context, founder, company)
    response = _generate_with_retries(PRIMARY_MODEL, prompt)
    post = safe_response_to_text(response)
    if not post:
        response = _generate_with_retries(FALLBACK_MODEL, prompt)
        post = safe_response_to_text(response)
    if not post:
        post = f"Here's a quick thought on {idea}: every journey begins with a spark of vision."
    post = deduplicate_text(post)
    post = apply_post_processing(post, idea)
    return post

# ----------------- CLI -----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a clean LinkedIn post (no JSON output).")
    parser.add_argument("idea", type=str, help="Topic or idea for the LinkedIn post")
    parser.add_argument("--founder", type=str, default=None)
    parser.add_argument("--company", type=str, default=None)
    args = parser.parse_args()

    try:
        final_post = generate_linkedin_post(args.idea, founder=args.founder, company=args.company)
        print(final_post)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
