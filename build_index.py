# build_index.py
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import pickle
import os
import mysql_utils

def build_index(posts=None):
    """
    Build a FAISS index from posts. If posts are not provided, fetch from MySQL.
    
    Args:
        posts (list[dict], optional): List of dicts with 'id' and 'content'.
    """
    # Fetch posts from MySQL if not provided
    if posts is None:
        print("🚚 Fetching posts from MySQL database...")
        conn = mysql_utils.get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, content FROM posts WHERE content IS NOT NULL AND content != ''")
        posts = cursor.fetchall()
        conn.close()

    if not posts:
        print("❌ No posts found. Build failed.")
        return False

    texts = [p["content"] for p in posts]
    ids = [p["id"] for p in posts]

    print("🧠 Loading sentence embedding model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    emb = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-12)

    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb.astype("float32"))

    os.makedirs("faiss_index", exist_ok=True)
    faiss.write_index(index, "faiss_index/linkedin_index.faiss")
    with open("faiss_index/id_map.pkl", "wb") as f:
        pickle.dump({"ids": ids, "texts": texts}, f)

    print(f"\n✅ Indexed {len(texts)} posts successfully!")
    return True

# Optional: allow running directly
if __name__ == "__main__":
    build_index()
