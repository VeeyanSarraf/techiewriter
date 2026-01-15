# search_similar.py
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import pickle
import os

MODEL_NAME = "all-MiniLM-L6-v2"
FAISS_INDEX_PATH = "faiss_index/linkedin_index.faiss"
ID_MAP_PATH = "faiss_index/id_map.pkl"

model = SentenceTransformer(MODEL_NAME)

def search_similar_posts(query: str, top_k: int = 3):
    if not os.path.exists(FAISS_INDEX_PATH):
        raise FileNotFoundError("FAISS index missing. Run build_index.py first.")

    if not query.strip():
        return []

    q_emb = model.encode([query], convert_to_numpy=True)
    q_emb = q_emb / (np.linalg.norm(q_emb, axis=1, keepdims=True) + 1e-12)

    index = faiss.read_index(FAISS_INDEX_PATH)
    with open(ID_MAP_PATH, "rb") as f:
        data = pickle.load(f)

    distances, indices = index.search(q_emb.astype("float32"), top_k)
    return [data["texts"][i] for i in indices[0] if 0 <= i < len(data["texts"])]
