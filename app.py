# ----------------------------------------------------------------------
# Celestial Post Generator - Flask App (app.py)
# ----------------------------------------------------------------------

import os
import json
import time
import logging
import traceback
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

# Import your modules
import s2
import build_index
import train_model
import generate_posts

# ----------------------------------------------------------------------
# Logging Setup
# ----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# ----------------------------------------------------------------------
# Flask App Initialization
# ----------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

CACHE_DIR = "cache"
CACHE_DURATION_HOURS = 24
os.makedirs(CACHE_DIR, exist_ok=True)
logging.info(f"Cache directory '{CACHE_DIR}' ready.")

# ----------------------------------------------------------------------
# Utility Functions
# ----------------------------------------------------------------------
def get_cache_path(profile_name: str) -> str:
    """Return safe cache filename for a profile."""
    safe_filename = "".join(c for c in profile_name if c.isalnum() or c in (' ', '_')).rstrip()
    return os.path.join(CACHE_DIR, f"{safe_filename.replace(' ', '_').lower()}.json")


def get_cache_age_hours(file_path: str):
    """Return cache age in hours."""
    if not os.path.exists(file_path):
        return None
    age_seconds = time.time() - os.path.getmtime(file_path)
    return age_seconds / 3600


def is_cache_valid(file_path: str):
    """Check if cache is still valid based on CACHE_DURATION_HOURS."""
    age = get_cache_age_hours(file_path)
    return age is not None and age < CACHE_DURATION_HOURS


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cache_duration_hours": CACHE_DURATION_HOURS
    })


@app.route("/api/cache-status", methods=["POST"])
def cache_status():
    try:
        data = request.get_json()
        profile_name = data.get("profileName", "").strip()
        if not profile_name:
            return jsonify({"success": False, "error": "Missing profile name"}), 400

        cache_file = get_cache_path(profile_name)
        age_hours = get_cache_age_hours(cache_file)
        return jsonify({
            "success": True,
            "cached": age_hours is not None,
            "cache_age_hours": age_hours
        })
    except Exception as e:
        logging.error(e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/clear-cache", methods=["POST"])
def clear_cache():
    try:
        data = request.get_json()
        profile_name = data.get("profileName", "").strip()
        cache_file = get_cache_path(profile_name)
        if os.path.exists(cache_file):
            os.remove(cache_file)
            return jsonify({"success": True, "message": "Cache cleared."})
        else:
            return jsonify({"success": False, "error": "No cache found."}), 404
    except Exception as e:
        logging.error(e)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/generate", methods=["POST"])
def generate():
    """Main endpoint to generate post text."""
    start = time.time()
    try:
        data = request.get_json()
        profile_url = data.get("profileUrl", "").strip()
        profile_name = data.get("profileName", "").strip()
        criteria = data.get("criteria", "").strip()
        force_refresh = data.get("forceRefresh", False)

        if not all([profile_url, profile_name, criteria]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        cache_file = get_cache_path(profile_name)
        used_cache = False

        # Use cache if valid
        if not force_refresh and is_cache_valid(cache_file):
            with open(cache_file, "r", encoding="utf-8") as f:
                trained_data = json.load(f)
            used_cache = True
        else:
            # ✅ Fixed function names
            posts = s2.scrape_profile_posts(profile_url)
            build_index.build_index(posts)  # changed from create_index() → build_index()
            trained_data = train_model.train(posts)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(trained_data, f, indent=4)

        # Generate post text
        post_text = generate_posts.create_post(criteria, trained_data)
        meta = {
            "used_cache": used_cache,
            "cache_age_hours": get_cache_age_hours(cache_file),
            "generation_time": round(time.time() - start, 2)
        }
        return jsonify({"success": True, "post": post_text, "meta": meta})

    except Exception as e:
        logging.error(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# ----------------------------------------------------------------------
# Factory Function (used by main.py)
# ----------------------------------------------------------------------
def create_app():
    """Return Flask app instance."""
    return app
