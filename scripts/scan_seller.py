#!/usr/bin/env python3
"""Fetch every currently-for-sale listing from a public Discogs seller inventory."""
import datetime as dt
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

SELLER = os.environ.get("DISCOGS_SELLER", "wgwstore")
OUTPUT = Path("data/sellers") / SELLER
HEADERS = {"User-Agent": "VinylDiggingInventoryResearch/1.0 (personal discovery)", "Accept": "application/vnd.discogs.v2.discogs+json"}
TOKEN = os.environ.get("DISCOGS_TOKEN", "").strip()
if TOKEN:
    HEADERS["Authorization"] = "Discogs token=" + TOKEN


def request_page(page):
    query = urllib.parse.urlencode({"per_page": 100, "page": page, "status": "For Sale"})
    url = f"https://api.discogs.com/users/{urllib.parse.quote(SELLER)}/inventory?{query}"
    for retry in range(7):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=40) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and retry < 6:
                try:
                    retry_after = int(exc.headers.get("Retry-After", "0"))
                except ValueError:
                    retry_after = 0
                delay = min(max(retry_after, 3 * 2**retry), 120)
                print(f"HTTP {exc.code}, waiting {delay}s")
                time.sleep(delay)
            else:
                raise
        except (urllib.error.URLError, TimeoutError):
            if retry == 6:
                raise
            time.sleep(min(3 * 2**retry, 120))
    raise RuntimeError("Discogs inventory request failed")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    listings = []
    page = 1
    while True:
        data = request_page(page)
        chunk = data.get("listings")
        if not isinstance(chunk, list):
            raise ValueError(f"Unexpected API response on page {page}")
        listings.extend(chunk)
        total_pages = data.get("pagination", {}).get("pages", page)
        print(f"Fetched page {page}/{total_pages}: {len(chunk)} listings")
        if page >= total_pages:
            break
        page += 1
        time.sleep(1.2)
    # Save compact, normalized data in small chunks so downstream report readers do not truncate JSON.
    normalized = []
    for item in listings:
        release = item.get("release") or {}
        price = item.get("price") or {}
        normalized.append({
            "listing_id": item.get("id"),
            "release_id": release.get("id"),
            "title": release.get("description", ""),
            "artist": release.get("artist", ""),
            "release_title": release.get("title", ""),
            "year": release.get("year"),
            "catalog_number": release.get("catalog_number", ""),
            "format": release.get("format", ""),
            "label": release.get("label", ""),
            "price": price.get("value"),
            "currency": price.get("currency"),
            "media_condition": item.get("condition"),
            "sleeve_condition": item.get("sleeve_condition"),
            "comments": item.get("comments"),
            "status": item.get("status"),
            "uri": item.get("uri"),
        })
    # Never publish a partial or empty scan if an API error occurred.
    chunksize = 100
    chunks = [normalized[i:i+chunksize] for i in range(0, len(normalized), chunksize)]
    if not chunks:
        chunks = [[]]
    for idx, chunk in enumerate(chunks, 1):
        (OUTPUT / f"page-{idx:04d}.json").write_text(json.dumps(chunk, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    # Remove old pages if inventory has shrunk.
    for old in OUTPUT.glob("page-*.json"):
        if int(old.stem.split("-")[-1]) > len(chunks):
            old.unlink()
    status = {"seller": SELLER, "last_sync": dt.datetime.now(dt.timezone.utc).isoformat(),
              "listing_count": len(normalized), "page_count": len(chunks),
              "pages": [f"page-{idx:04d}.json" for idx in range(1, len(chunks)+1)]}
    (OUTPUT / "index.json").write_text(json.dumps(status, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Complete: {len(normalized)} listings in {len(chunks)} JSON pages")


if __name__ == "__main__":
    main()
