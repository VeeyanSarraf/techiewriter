"""
LinkedIn Post ML Training Pipeline
Integrates with pipeline: s2.py -> DB -> build_index -> train_model -> generate_posts
Compatible with Flask app (app.py)
"""

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import pickle
import json
import os
import re
import sys
from collections import Counter

# Import your existing utilities
import mysql_utils

class PostTrainer:
    def __init__(self):
        self.vectorizer = None
        self.patterns = {}
        self.stats = {}
        
    def load_posts_from_db(self):
        """Load posts from your existing database - auto-detects table structure"""
        try:
            conn = mysql_utils.get_conn()
            cursor = conn.cursor(dictionary=True)
            
            # Auto-detect table and columns
            print("🔍 Detecting database structure...")
            
            # Get all tables
            cursor.execute("SHOW TABLES")
            tables = [list(row.values())[0] for row in cursor.fetchall()]
            print(f"   Found tables: {tables}")
            
            # Try to find the posts table
            post_table = None
            for table in tables:
                if 'post' in table.lower():
                    post_table = table
                    break
            
            if not post_table and tables:
                post_table = tables[0]  # Use first table as fallback
            
            if not post_table:
                raise ValueError("No tables found in database")
            
            print(f"   Using table: {post_table}")
            
            # Get table columns
            cursor.execute(f"DESCRIBE {post_table}")
            columns = [row['Field'] for row in cursor.fetchall()]
            print(f"   Columns: {columns}")
            
            # Find content column
            content_col = None
            for col in columns:
                if 'content' in col.lower() or 'text' in col.lower() or 'post' in col.lower():
                    content_col = col
                    break
            
            if not content_col:
                raise ValueError(f"No content column found in {post_table}. Available: {columns}")
            
            # Find timestamp column for ordering
            time_col = None
            for col in columns:
                if any(t in col.lower() for t in ['time', 'date', 'created', 'scraped']):
                    time_col = col
                    break
            
            # Build query
            order_by = f"ORDER BY {time_col} DESC" if time_col else "ORDER BY id DESC" if 'id' in columns else ""
            query = f"SELECT * FROM {post_table} WHERE {content_col} IS NOT NULL AND {content_col} != '' {order_by}"
            
            print(f"   Query: {query[:100]}...")
            
            cursor.execute(query)
            posts = cursor.fetchall()
            cursor.close()
            conn.close()
            
            if not posts:
                raise ValueError(f"No posts found in {post_table}")
            
            df = pd.DataFrame(posts)
            
            # Ensure 'content' column exists for processing
            if content_col != 'content':
                df['content'] = df[content_col]
            
            print(f"   ✓ Loaded {len(df)} posts successfully")
            return df
            
        except Exception as e:
            print(f"\n❌ Database error: {e}")
            print("\n💡 Troubleshooting:")
            print("   1. Check mysql_utils.py has get_conn() function")
            print("   2. Verify database connection settings")
            print("   3. Ensure table exists and has data")
            print("   4. Run: python s2.py [profile_url] [profile_name]")
            sys.exit(1)
    
    def analyze_patterns(self, df):
        """Extract patterns from successful posts"""
        all_posts = df['content'].tolist()
        
        patterns = {
            'openings': [],
            'closings': [],
            'phrases': [],
            'hashtags': [],
            'structures': []
        }
        
        for content in all_posts:
            if not content or not isinstance(content, str):
                continue
                
            lines = [l.strip() for l in content.split('\n') if l.strip()]
            
            # Opening lines (first 2 lines)
            if lines:
                patterns['openings'].append(lines[0])
                if len(lines) > 1:
                    patterns['openings'].append(lines[1])
            
            # Closing lines (last line)
            if lines:
                patterns['closings'].append(lines[-1])
            
            # Extract hashtags
            hashtags = re.findall(r'#\w+', content)
            patterns['hashtags'].extend(hashtags)
            
            # Extract 2-4 word phrases
            words = content.lower().split()
            for i in range(len(words) - 2):
                patterns['phrases'].append(' '.join(words[i:i+3]))
            
            # Analyze structure
            structure = {
                'has_list': bool(re.search(r'(\d+[.)\-:]|[•\-]\s)', content)),
                'has_question': '?' in content,
                'has_emojis': bool(re.findall(r'[^\w\s,.]', content)),
                'line_count': len(lines),
                'word_count': len(words)
            }
            patterns['structures'].append(structure)
        
        # Get top patterns
        self.patterns = {
            'top_openings': [x[0] for x in Counter(patterns['openings']).most_common(30)],
            'top_closings': [x[0] for x in Counter(patterns['closings']).most_common(20)],
            'common_phrases': [x[0] for x in Counter(patterns['phrases']).most_common(100)],
            'popular_hashtags': [x[0] for x in Counter(patterns['hashtags']).most_common(50)],
        }
        
        # Calculate average stats
        structures = patterns['structures']
        self.stats = {
            'avg_line_count': np.mean([s['line_count'] for s in structures]),
            'avg_word_count': np.mean([s['word_count'] for s in structures]),
            'list_usage': sum(s['has_list'] for s in structures) / len(structures),
            'question_usage': sum(s['has_question'] for s in structures) / len(structures),
            'emoji_usage': sum(s['has_emojis'] for s in structures) / len(structures),
        }
        
        return self.patterns, self.stats
    
    def train_vectorizer(self, texts):
        """Train TF-IDF vectorizer on post contents"""
        self.vectorizer = TfidfVectorizer(
            max_features=300,
            ngram_range=(1, 2),
            stop_words='english',
            min_df=2,
            max_df=0.8
        )
        
        self.vectorizer.fit(texts)
        return self.vectorizer
    
    def save_trained_data(self):
        """Save all trained models and patterns"""
        os.makedirs('models', exist_ok=True)
        
        # Save vectorizer
        with open('models/tfidf_vectorizer.pkl', 'wb') as f:
            pickle.dump(self.vectorizer, f)
        
        # Save patterns
        with open('models/patterns.json', 'w', encoding='utf-8') as f:
            json.dump(self.patterns, f, indent=2, ensure_ascii=False)
        
        # Save stats
        with open('models/stats.json', 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, indent=2)
        
        print("\n✅ Saved trained models:")
        print("   📄 models/tfidf_vectorizer.pkl")
        print("   📄 models/patterns.json")
        print("   📄 models/stats.json")
    
    def train_pipeline(self):
        """Main training pipeline"""
        print("="*60)
        print("🚀 LinkedIn Post ML Training Pipeline")
        print("="*60)
        
        # Step 1: Load data from DB
        print("\n[1/4] 📊 Loading posts from database...")
        df = self.load_posts_from_db()
        print(f"      ✓ Loaded {len(df)} posts")
        
        if len(df) == 0:
            print("      ❌ No posts found! Run s2.py first.")
            return
        
        # Step 2: Analyze patterns
        print("\n[2/4] 🔍 Analyzing post patterns...")
        patterns, stats = self.analyze_patterns(df)
        print(f"      ✓ Found {len(patterns['top_openings'])} opening patterns")
        print(f"      ✓ Found {len(patterns['popular_hashtags'])} hashtags")
        print(f"      ✓ Extracted {len(patterns['common_phrases'])} phrases")
        
        # Step 3: Train vectorizer
        print("\n[3/4] 🤖 Training ML vectorizer...")
        self.train_vectorizer(df['content'].tolist())
        print(f"      ✓ Vectorizer trained on {len(df)} posts")
        
        # Step 4: Save everything
        print("\n[4/4] 💾 Saving trained models...")
        self.save_trained_data()
        
        # Print summary
        self.print_summary()
        
        print("\n" + "="*60)
        print("✅ Training Complete!")
        print("="*60 + "\n")
    
    def print_summary(self):
        """Print training summary"""
        print("\n" + "="*60)
        print("📈 TRAINING SUMMARY")
        print("="*60)
        
        print(f"\n📊 Post Statistics:")
        print(f"   • Average words: {self.stats['avg_word_count']:.0f}")
        print(f"   • Average lines: {self.stats['avg_line_count']:.0f}")
        print(f"   • Posts with lists: {self.stats['list_usage']*100:.0f}%")
        print(f"   • Posts with questions: {self.stats['question_usage']*100:.0f}%")
        
        print(f"\n💬 Top Opening Lines:")
        for i, opening in enumerate(self.patterns['top_openings'][:3], 1):
            print(f"   {i}. {opening[:60]}...")
        
        print(f"\n🔥 Popular Hashtags:")
        print(f"   {' '.join(self.patterns['popular_hashtags'][:10])}")


def main():
    """Run the training pipeline"""
    trainer = PostTrainer()
    trainer.train_pipeline()


if __name__ == "__main__":
    main()