import sys
import os
import requests
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

def normalize_url(u):
    """Ensure URL has a scheme; default to https:// if none."""
    p = urlparse(u)
    if not p.scheme:
        return 'https://' + u
    return u

def fetch_and_save(idx, raw_url, out_dir, session):
    """Worker: download a single URL and save to out_dir/idx.html, skipping if exists."""
    file_path = out_dir / f"{idx}.html"
    if file_path.exists():
        return (idx, raw_url, True, "skipped")

    url = normalize_url(raw_url.strip())
    try:
        r = session.get(url, timeout=10)
    except requests.exceptions.RequestException:
        # fallback to HTTP
        if url.startswith('https://'):
            try:
                r = session.get('http://' + url[len('https://'):], timeout=10)
            except requests.exceptions.RequestException:
                return (idx, raw_url, False, "fail_dns")
        else:
            return (idx, raw_url, False, "fail")

    ct = r.headers.get('Content-Type', '')
    if r.status_code == 200 and 'text/html' in ct:
        file_path.write_text(r.text, encoding='utf-8')
        return (idx, raw_url, True, "ok")
    return (idx, raw_url, False, f"bad_status_{r.status_code}")

def download_htmls(result_df, max_workers=20):
    """Download up to 45k URLs in parallel, skipping already-downloaded files."""
    # prepare session with retries and headers
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    })

    # sample dataframe
    sample_size = min(45000, len(result_df))
    sampled = result_df.sample(n=sample_size, random_state=42).reset_index()

    out_dir = Path('content/html/legitimate')
    out_dir.mkdir(parents=True, exist_ok=True)

    failures = []
    tasks = [
        (row['index'], row['url'])
        for _, row in sampled.iterrows()
    ]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_and_save, idx, url, out_dir, session): (idx, url)
            for idx, url in tasks
        }
        for future in as_completed(futures):
            idx, raw_url = futures[future]
            try:
                _, _, success, note = future.result()
                if not success:
                    failures.append((raw_url, note))
            except Exception:
                failures.append((raw_url, "exception"))

    print(f"Completed: {len(tasks)-len(failures)} succeeded, {len(failures)} failed")
    if failures:
        df_fail = pd.DataFrame(failures, columns=['url','reason'])
        df_fail.to_csv('failed_urls.csv', index=False)

def extract_data(csv_file=r"c:\Users\ASUS\Downloads\archive\new_data_urls.csv"):
    """Read CSV, filter rows where status == 1, return DataFrame with original index."""
    df = pd.read_csv(csv_file)
    result_df = df[df['status'] == 1].copy()
    result_df.reset_index(inplace=True)  # original index in 'index' column
    return result_df

def main():
    df = extract_data()
    print(f"Total URLs to download: {len(df)}")
    download_htmls(df)

if __name__ == "__main__":
    main()
