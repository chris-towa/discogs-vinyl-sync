#!/usr/bin/env python3
"""Incremental, rate-limit-respecting public Discogs seller inventory scanner.

One workflow invocation reads at most PAGES_PER_RUN pages. Progress is committed
by the workflow, so subsequent invocations resume from the next page.
"""
import datetime as dt
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

SELLER = os.getenv("DISCOGS_SELLER", "wgwstore")
PAGES_PER_RUN = max(1, min(int(os.getenv("PAGES_PER_RUN", "15")), 30))
DELAY = max(float(os.getenv("DISCOGS_REQUEST_DELAY", "3.5")), 2.0)
OUT = Path("data/sellers") / SELLER
HEADERS = {"User-Agent": "VinylDiggingResearch/1.1 (personal record discovery; github.com/chris-towa/discogs-vinyl-sync)", "Accept": "application/vnd.discogs.v2.discogs+json"}
TOKEN = os.getenv("DISCOGS_TOKEN", "").strip()
if TOKEN:
    HEADERS["Authorization"] = "Discogs token=" + TOKEN


def fetch(page):
    params = urllib.parse.urlencode({"per_page": 100, "page": page, "status": "For Sale"})
    url = f"https://api.discogs.com/users/{urllib.parse.quote(SELLER)}/inventory?{params}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                print(f"Discogs returned HTTP 403 at page {page}. Stop without retrying a denied request.")
                return None
            if exc.code in (429, 500, 502, 503, 504):
                wait = min(max(int(exc.headers.get("Retry-After", "0") or 0), 15 * (attempt + 1)), 180)
                print(f"HTTP {exc.code} at page {page}, cooling down {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == 3:
                raise
            time.sleep(15 * (attempt + 1))
    print(f"Request failed repeatedly on page {page}; preserving earlier progress.")
    return None


def normalize(item):
    r = item.get("release") or {}
    p = item.get("price") or {}
    return {"listing_id": item.get("id"), "release_id": r.get("id"),
            "title": r.get("description", ""), "artist": r.get("artist", ""),
            "release_title": r.get("title", ""), "year": r.get("year"),
            "catalog_number": r.get("catalog_number", ""), "format": r.get("format", ""),
            "label": r.get("label", ""), "price": p.get("value"), "currency": p.get("currency"),
            "media_condition": item.get("condition"), "sleeve_condition": item.get("sleeve_condition"),
            "comments": item.get("comments"), "status": item.get("status"), "uri": item.get("uri")}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    start = int(index.get("next_page", 1))
    pages_total = index.get("total_pages")
    stopped_reason = None
    completed = 0
    for page in range(start, start + PAGES_PER_RUN):
        if pages_total is not None and page > int(pages_total):
            break
        data = fetch(page)
        if data is None:
            stopped_reason = "Discogs API access denied or throttled"
            break
        chunk = data.get("listings")
        if not isinstance(chunk, list):
            raise ValueError(f"Unexpected response at page {page}")
        pages_total = int(data.get("pagination", {}).get("pages", page))
        page_path = OUT / f"page-{page:04d}.json"
        page_path.write_text(json.dumps([normalize(x) for x in chunk], ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
        completed += 1
        index["next_page"] = page + 1
        index["total_pages"] = pages_total
        print(f"Saved page {page}/{pages_total}: {len(chunk)} listings", flush=True)
        if page >= pages_total:
            break
        time.sleep(DELAY)
    # Never claim complete coverage unless every expected page is stored.
    saved = len(list(OUT.glob("page-*.json")))
    index.update({"seller": SELLER, "last_scan_attempt": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "saved_pages": saved, "listing_count_estimate": saved * 100,
                  "complete": bool(pages_total and saved >= pages_total),
                  "last_run_pages": completed, "stopped_reason": stopped_reason,
                  "next_page": index.get("next_page", start)})
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(f"Progress saved: {saved}/{pages_total or '?'} pages; complete={index['complete']}", flush=True)


if __name__ == "__main__":
    main()
