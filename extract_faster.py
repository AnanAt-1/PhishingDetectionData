import asyncio
import aiohttp
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd
import ctypes

# Windows sleep-prevention flags
ES_CONTINUOUS       = 0x80000000
ES_DISPLAY_REQUIRED = 0x00000002

def prevent_sleep():
    """Prevent display from turning off."""
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_DISPLAY_REQUIRED
    )

def restore_sleep():
    """Restore normal sleep behavior."""
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

def normalize_url(u: str) -> str:
    """Ensure URL has a scheme; default to https:// if none."""
    p = urlparse(u.strip())
    if not p.scheme:
        return 'https://' + u
    return u

async def fetch_one(session: aiohttp.ClientSession, idx: int, raw_url: str, out_dir: Path):
    """Download a single URL and save to out_dir/idx.html, skipping if exists."""
    file_path = out_dir / f"{idx}.html"
    if file_path.exists():
        return True  # skip existing

    url = normalize_url(raw_url)
    try:
        async with session.get(url) as resp:
            if resp.status == 200 and 'text/html' in resp.headers.get('Content-Type',''):
                text = await resp.text()
                file_path.write_text(text, encoding='utf-8')
                return True
    except Exception:
        # fallback to HTTP if HTTPS failed
        if url.startswith('https://'):
            http_url = 'http://' + url[len('https://'):]
            try:
                async with session.get(http_url) as resp2:
                    if resp2.status == 200 and 'text/html' in resp2.headers.get('Content-Type',''):
                        text = await resp2.text()
                        file_path.write_text(text, encoding='utf-8')
                        return True
            except:
                pass
    return False

async def download_htmls_async(result_df, concurrency: int = 100):
    """Download up to 45k URLs concurrently using aiohttp."""
    # sample up to 45k
    sample_size = min(20000, len(result_df))
    sampled = result_df.sample(n=sample_size, random_state=42).reset_index()

    out_dir = Path('content/html/phishing')
    out_dir.mkdir(parents=True, exist_ok=True)

    # aiohttp connector with limited connections
    connector = aiohttp.TCPConnector(limit_per_host=concurrency, limit=concurrency)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    }
    timeout = aiohttp.ClientTimeout(total=15)

    successes = 0
    failures = []

    async with aiohttp.ClientSession(connector=connector,
                                     headers=headers,
                                     timeout=timeout) as session:
        sem = asyncio.Semaphore(concurrency)

        async def bound_fetch(idx, url):
            async with sem:
                ok = await fetch_one(session, idx, url, out_dir)
                return idx, url, ok

        tasks = [
            bound_fetch(row['phish_id'], row['url'])
            for _, row in sampled.iterrows()
        ]
        for future in asyncio.as_completed(tasks):
            idx, url, ok = await future
            if ok:
                successes += 1
            else:
                failures.append(url)

    print(f"Completed: {successes} succeeded, {len(failures)} failed")
    if failures:
        pd.Series(failures, name='url').to_csv('failed_urls_phish.csv', index=False)

def extract_data(csv_file=r"c:\Users\ASUS\Downloads\verified_online\verified_online.csv"):
    """Read CSV, filter rows where status == 1, return DataFrame with original index."""
    df = pd.read_csv(csv_file)
    
    return df

def main():
    prevent_sleep()
    try:
        df = extract_data()
        print(f"Total URLs to download: {len(df)}")
        asyncio.run(download_htmls_async(df))
    finally:
        restore_sleep()

if __name__ == "__main__":
    main()
