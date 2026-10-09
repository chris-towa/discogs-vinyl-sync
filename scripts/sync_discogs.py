#!/usr/bin/env python3
"""Synchronize public Discogs collection and wantlist with change tracking."""
import datetime as dt
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

USERNAME = os.getenv("DISCOGS_USERNAME", "chris-towa")
BASE = "https://api.discogs.com"
DATA = Path("data")
HEADERS = {
    "User-Agent": "ChrisVinylDiggingSync/1.0 (GitHub Actions; personal collection backup)",
    "Accept": "application/vnd.discogs.v2.discogs+json",
}
TOKEN = os.getenv("DISCOGS_TOKEN", "").strip()
if TOKEN:
    HEADERS["Authorization"] = "Discogs token=" + TOKEN


def fetch_json(url):
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=35) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 5:
                delay = min(int(exc.headers.get("Retry-After", "0") or 0) or 2 ** attempt + 2, 120)
                print(f"HTTP {exc.code}; retrying in {delay}s")
                time.sleep(delay)
                continue
            raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == 5:
                raise
            time.sleep(2 ** attempt + 2)
    raise RuntimeError("Could not fetch Discogs API")


def fetch_all(path, key):
    page = 1
    records = []
    while True:
        query = urllib.parse.urlencode({"page": page, "per_page": 100})
        payload = fetch_json(f"{BASE}{path}?{query}")
        chunk = payload.get(key)
        if not isinstance(chunk, list):
            raise ValueError(f"Invalid Discogs response for {key} page {page}")
        records.extend(chunk)
        pages = payload.get("pagination", {}).get("pages", page)
        print(f"{key}: page {page}/{pages}, {len(chunk)} records")
        if page >= pages:
            break
        page += 1
        time.sleep(1.1)
    return records


def load_old(name):
    path = DATA / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def write_json(name, payload):
    (DATA / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def release_summary(item):
    release = item.get("basic_information") or {}
    artists = release.get("artists") or []
    artist = ", ".join(a.get("name", "") for a in artists)
    return {
        "release_id": item.get("id") or release.get("id"),
        "artist": artist,
        "title": release.get("title", ""),
        "label": ", ".join(l.get("name", "") for l in release.get("labels", [])),
        "year": release.get("year"),
        "added": item.get("date_added"),
    }


def collection_key(item):
    return str(item.get("instance_id") or item.get("id"))


def want_key(item):
    return str(item.get("id"))


def main():
    DATA.mkdir(exist_ok=True)
    collection = fetch_all(
        f"/users/{urllib.parse.quote(USERNAME)}/collection/folders/0/releases", "releases"
    )
    wants = fetch_all(f"/users/{urllib.parse.quote(USERNAME)}/wants", "wants")
    # A zero-length result can be valid, but an API failure is never saved as a snapshot.
    old_collection = load_old("collection.json")
    old_wants = load_old("wantlist.json")
    old_c = {collection_key(x): x for x in (old_collection or {}).get("releases", [])}
    old_w = {want_key(x): x for x in (old_wants or {}).get("wants", [])}
    new_c = {collection_key(x): x for x in collection}
    new_w = {want_key(x): x for x in wants}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    changes = {
        "generated_at": now,
        "username": USERNAME,
        "initial_sync": old_collection is None or old_wants is None,
        "collection_added": [release_summary(new_c[k]) for k in sorted(new_c.keys() - old_c.keys())] if old_collection else [],
        "collection_removed": [release_summary(old_c[k]) for k in sorted(old_c.keys() - new_c.keys())] if old_collection else [],
        "wantlist_added": [release_summary(new_w[k]) for k in sorted(new_w.keys() - old_w.keys())] if old_wants else [],
        "wantlist_removed": [release_summary(old_w[k]) for k in sorted(old_w.keys() - new_w.keys())] if old_wants else [],
    }
    write_json("collection.json", {"username": USERNAME, "releases": collection})
    write_json("wantlist.json", {"username": USERNAME, "wants": wants})
    write_json("changes.json", changes)
    write_json("status.json", {
        "username": USERNAME,
        "last_successful_sync": now,
        "collection_items": len(collection),
        "wantlist_items": len(wants),
    })
    print(f"Sync complete: {len(collection)} collection items, {len(wants)} wants")


if __name__ == "__main__":
    main()
