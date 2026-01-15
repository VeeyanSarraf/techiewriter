import subprocess
from app import create_app

if __name__ == "__main__":
    print("🚀 Celestial Post Generator Launcher 🚀")
    print("=" * 80)
    print("✨ Celestial Post Generator Flask App Starting ✨")
    print("🌍 Visit http://192.168.31.92:8000/ in your browser")
    print("=" * 80)

    # Directly start Flask app without asking for input
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=True)
