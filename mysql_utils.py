import os
import re
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}


def get_conn():
    """Return a new MySQL connection using DB_CONFIG."""
    return mysql.connector.connect(**DB_CONFIG)


def setup_table():
    """Create the posts table with all required columns."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        content TEXT NOT NULL,
        likes INT,
        comments INT,
        reposts INT,
        url VARCHAR(255),
        timestamp BIGINT,
        scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY unique_post (content(255))
    )
    """)
    conn.commit()
    conn.close()


def clean_post(text: str, profile_name: str = "") -> str:
    """Remove junk like duplicate names, LinkedIn UI text, etc."""
    if not text:
        return ""

    # Remove LinkedIn UI junk
    junk_patterns = [
        r"Like\s*Comment\s*Repost\s*Send",
        r"Follow",
        r"• \d+ (yr|mo|w|d) ago",
        r"\d+\s*comments?",
        r"\d+\s*reposts?",
        r"Activate to view larger image",
        r"Edited •",
        r"anyone on or off LinkedIn",
    ]
    for pattern in junk_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Split into lines, remove duplicates and profile names
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    filtered_lines = []
    for line in lines:
        if filtered_lines and line == filtered_lines[-1]:
            continue  # skip duplicates
        if profile_name and profile_name.lower() in line.lower():
            continue  # remove user name lines
        if "influencer" in line.lower():
            continue
        filtered_lines.append(line)

    cleaned = " ".join(filtered_lines)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def insert_posts_into_mysql(posts):
    """
    Insert posts into MySQL, skipping duplicates.
    Returns: (inserted_count, skipped_count)
    """
    conn = get_conn()
    cursor = conn.cursor()

    # Fetch existing post contents
    cursor.execute("SELECT content FROM posts")
    existing_posts = set(row[0] for row in cursor.fetchall())

    new_posts = []
    skipped_count = 0

    for post in posts:
        if post["content"] in existing_posts:
            skipped_count += 1
        else:
            new_posts.append(post)

    inserted_count = 0

    # Insert only new posts
    for post in new_posts:
        try:
            cursor.execute("""
                INSERT INTO posts (content, likes, comments, reposts, url, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                post["content"],
                post["likes"],
                post["comments"],
                post["reposts"],
                post["url"],
                post["timestamp"]
            ))
            inserted_count += 1
        except mysql.connector.errors.IntegrityError:
            skipped_count += 1
            continue

    conn.commit()
    conn.close()

    # Return accurate counts instead of printing directly
    return inserted_count, skipped_count


def debug_db():
    """Show all tables and describe the posts table."""
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SHOW TABLES")
    print("Tables:", cursor.fetchall())

    try:
        cursor.execute("DESCRIBE posts")
        print("Columns:", cursor.fetchall())
    except mysql.connector.errors.ProgrammingError:
        print("⚠️ Table 'posts' does not exist yet. Run setup_table().")

    conn.close()


if __name__ == "__main__":
    # Run this file directly to debug DB structure
    debug_db()
