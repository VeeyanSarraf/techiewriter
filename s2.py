import os
import time
import argparse
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException
from mysql_utils import insert_posts_into_mysql, clean_post, setup_table

load_dotenv()

LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")


def login_linkedin(driver):
    driver.get("https://www.linkedin.com/login")
    time.sleep(2)
    driver.find_element(By.ID, "username").send_keys(LINKEDIN_EMAIL)
    driver.find_element(By.ID, "password").send_keys(LINKEDIN_PASSWORD)
    driver.find_element(By.XPATH, '//button[@type="submit"]').click()
    time.sleep(3)

    if "checkpoint/challenge" in driver.current_url or "captcha" in driver.page_source.lower():
        print("[WARNING] CAPTCHA detected. Solve it manually...", flush=True)
        while "feed" not in driver.current_url:
            time.sleep(5)
        print("[INFO] CAPTCHA solved. Proceeding...", flush=True)


def expand_all_buttons(driver):
    """Expand all 'see more' and '...more' buttons in LinkedIn posts."""
    try:
        buttons = driver.find_elements(
            By.XPATH,
            "//button[contains(@class,'see-more') or contains(@class,'inline-show-more-text__button')]"
        )

        for btn in buttons:
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)
            except Exception as e:
                print(f"[WARNING] Could not click button: {e}", flush=True)

    except Exception as e:
        print(f"[WARNING] Error expanding buttons: {e}", flush=True)


def scrape_profile_posts(profile_url, max_posts=100, profile_name=""):
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=chrome_options)

    try:
        login_linkedin(driver)
    except Exception as e:
        print(f"[ERROR] Login failed: {e}", flush=True)
        driver.quit()
        return []

    if "/recent-activity/" not in profile_url:
        profile_url = profile_url.rstrip("/") + "/recent-activity/"

    driver.get(profile_url)
    time.sleep(5)

    try:
        posts_tab = driver.find_element(By.XPATH, '//a[contains(@href, "recent-activity/posts")]')
        driver.execute_script("arguments[0].click();", posts_tab)
        print("[INFO] Clicked on 'Posts' tab.", flush=True)
        time.sleep(5)
    except NoSuchElementException:
        print("[WARNING] 'Posts' tab not found — scraping default activity feed.", flush=True)

    posts_data, scrolls, max_scrolls = [], 0, 10

    while len(posts_data) < max_posts and scrolls < max_scrolls:
        print(f"[INFO] Scroll {scrolls + 1} / {max_scrolls}...", flush=True)
        expand_all_buttons(driver)

        cards = driver.find_elements(By.CLASS_NAME, "feed-shared-update-v2")

        for card in cards:
            try:
                try:
                    content_elem = card.find_element(By.CLASS_NAME, "feed-shared-update-v2__description")
                    raw_text = content_elem.text.strip()
                except:
                    raw_text = card.text.strip()

                post_content = clean_post(raw_text, profile_name)

                if not post_content or len(post_content) < 10:
                    continue

                likes = comments = reposts = 0
                try:
                    like_element = card.find_element(
                        By.XPATH, ".//li[contains(@class,'social-details-social-counts__reactions')]"
                    )
                    digits = "".join(filter(str.isdigit, like_element.text))
                    likes = int(digits) if digits else 0
                except:
                    pass

                try:
                    engagement_section = card.find_element(By.CLASS_NAME, "social-details-social-counts")
                    spans = engagement_section.find_elements(By.TAG_NAME, "span")
                    for span in spans:
                        txt = span.text.lower()
                        digits = "".join(filter(str.isdigit, txt))
                        if "comment" in txt and digits:
                            comments = int(digits)
                        elif ("repost" in txt or "share" in txt) and digits:
                            reposts = int(digits)
                except:
                    pass

                posts_data.append({
                    "content": post_content,
                    "likes": likes,
                    "comments": comments,
                    "reposts": reposts,
                    "url": profile_url,
                    "timestamp": time.time()
                })
            except:
                continue

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(4)
        scrolls += 1

    print(f"[INFO] Scraping complete. Total raw posts collected: {len(posts_data)}", flush=True)
    driver.quit()
    return posts_data


def main():
    parser = argparse.ArgumentParser(description="Scrape LinkedIn profile posts.")
    parser.add_argument("profile_url", help="LinkedIn profile URL to scrape")
    parser.add_argument("profile_name", help="Profile name for filtering repeated text")
    args = parser.parse_args()

    setup_table()  # ensure DB table exists

    posts = scrape_profile_posts(args.profile_url, profile_name=args.profile_name)
    if not posts:
        print("[ERROR] No posts scraped. Exiting.", flush=True)
        return

    # ✅ Get insert summary from the DB utility
    inserted_count, skipped_count = insert_posts_into_mysql(posts)

    print(f"[INFO] Scraping finished for {args.profile_name}")
    print(f"       → Total posts scraped: {len(posts)}")
    print(f"       → Newly added posts: {inserted_count}")
    print(f"       → Already existing posts skipped: {skipped_count}")
    print(f"[INFO] Database update complete.", flush=True)


if __name__ == "__main__":
    main()
