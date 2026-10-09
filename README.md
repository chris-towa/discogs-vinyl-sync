# Discogs Vinyl Sync

Daily automated sync of the public Discogs **Collection** and **Wantlist** for **chris-towa**.

## Start the first run
Open **Actions → Sync Discogs Collection and Wantlist → Run workflow** and check the result. On success the workflow commits these files:

- `data/collection.json`: complete Collection
- `data/wantlist.json`: complete Wantlist
- `data/changes.json`: additions and removals since the **previous daily sync**
- `data/status.json`: last successful sync and item counts

The workflow runs daily at 05:17 UTC (07:17 CEST / 06:17 CET). GitHub can delay scheduled runs.

## Data access
After the first successful run, the files are available at:

- https://raw.githubusercontent.com/chris-towa/discogs-vinyl-sync/main/data/collection.json
- https://raw.githubusercontent.com/chris-towa/discogs-vinyl-sync/main/data/wantlist.json
- https://raw.githubusercontent.com/chris-towa/discogs-vinyl-sync/main/data/status.json

**No token required** for public lists. If the public API becomes restricted, set the optional `DISCOGS_TOKEN` as a GitHub Actions repository secret, never in code or a chat message.

A new Collection entry is not necessarily a confirmed purchase, and a Wantlist removal is not necessarily a purchase. The snapshots are public in a public repository.

**Important:** The GitHub sync does not automatically feed data into ChatGPT scheduled reports. The Friday report must explicitly fetch the latest files and verify freshness and live shop stock.
