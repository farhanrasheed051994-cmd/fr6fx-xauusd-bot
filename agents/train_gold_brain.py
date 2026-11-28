import os
import glob
import time
import requests
from google import genai
from google.genai import types
from pypdf import PdfReader

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
KNOWLEDGE_DIR = "knowledge"


def extract_text_from_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        reader = PdfReader(filepath)
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    elif ext in (".txt", ".md", ".json"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""


def chunk_text(text, chunk_size=1100, overlap=180):
    clean = " ".join(text.split())
    chunks = []
    start = 0
    while start < len(clean):
        end = start + chunk_size
        chunks.append(clean[start:end])
        start += chunk_size - overlap
    return [c.strip() for c in chunks if len(c.strip()) > 60]


def get_gemini_embedding(client, text):
    res = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=768),
    )
    return res.embeddings[0].values


def store_chunk_in_supabase(title, content, embedding):
    url = f"{SUPABASE_URL}/rest/v1/gold_knowledge"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = requests.post(
        url,
        headers=headers,
        json={"title": title, "content": content, "embedding": embedding},
        timeout=20,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Supabase insert failed ({resp.status_code}): {resp.text[:200]}")


def clear_existing_by_title(title):
    url = f"{SUPABASE_URL}/rest/v1/gold_knowledge?title=eq.{requests.utils.quote(title)}"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    requests.delete(url, headers=headers, timeout=15)


def train_from_knowledge_folder():
    if not SUPABASE_URL or not SUPABASE_KEY or not GEMINI_API_KEY:
        print("⚠️ Missing SUPABASE_URL, SUPABASE_KEY, or GEMINI_API_KEY. Skipping training.")
        return

    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    files = []
    for pattern in ("*.txt", "*.md", "*.pdf"):
        files.extend(glob.glob(os.path.join(KNOWLEDGE_DIR, pattern)))

    if not files:
        print("ℹ️ No files found in knowledge/ folder yet.")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    total_chunks = 0

    for fp in sorted(files):
        fname = os.path.basename(fp)
        raw_text = extract_text_from_file(fp)
        chunks = chunk_text(raw_text)
        if not chunks:
            continue

        clear_existing_by_title(fname)
        for ch in chunks:
            emb = get_gemini_embedding(client, ch)
            store_chunk_in_supabase(fname, ch, emb)
            total_chunks += 1
            time.sleep(0.25)

        print(f"✅ Trained GoldBrain on '{fname}' ({len(chunks)} chunks)")

    print(f"🧠 Total knowledge chunks synced to Supabase: {total_chunks}")


if __name__ == "__main__":
    train_from_knowledge_folder()
