"""
ingestion/github_client.py

GitHub API client for searching repos and fetching metadata.
Uses contracts/schema.py for all config constants.
"""
# -- Imports ------------------------------------------------

# Allows for modern type annotation syntax in Python
# ex/ str | int
from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
import os

# Values from the contracts/schema file, should not be hardcorded here
from contracts.schema import (
    API_CALL_DELAY,
    API_MAX_RETRIES,
    DEFAULT_LANGUAGES,
    DEFAULT_REPO_LIMIT,
    Language,
    SearchTopic,
    language_query_value,
)

# -- ------------------------------------------------

# Read the .env file
load_dotenv(".env")

# Makes logging for this github_clients.py file
log = logging.getLogger(__name__)

# Use my GITHUB_TOKEN, else use defualt blank (works but lower limit)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
SEARCH_URL = "https://api.github.com/search/repositories"
PER_PAGE = 100  # GitHub max per page


# We need a header for our request, with auth for increased rate limits
def _headers() -> dict[
    str, str
]:  # internal function, returns dict with Key:string, value:string
    """Build HTTP headers for GitHub API requests.

    Returns headers with Accept field and, if GITHUB_TOKEN is set,
    an Authorization bearer token.

    Returns:
        dict[str, str]: Request headers dictionary.

    With no GITHUB_TOKEN:

    ```json
    {
    "Accept": "application/vnd.github+json"
    }
    ```
    With a token, the header should be:

    ```json
    {
    "Accept": "application/vnd.github+json",
    "Authorization": "Bearer YOUR_ACTUAL_TOKEN_HERE"
    }
    ```
    """

    h = {"Accept": "application/vnd.github+json"}  # ask github for json
    if GITHUB_TOKEN:  # If we have our token
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"  # Use our token for Authorization
    return h  # h is either the inital h variable or our new one with the GITHUB_TOKEN


# The actual get request for data, with the option to retry after rate limits
def _request_with_retry(url: str, params: dict | None = None) -> dict:
    """GET with simple retry on 403/429 rate-limit responses.

    Parameters:
     - url — the web address to request
     - params — query parameters (like ?q=topic:llm&sort=stars at the
           end of a URL). dict | None = None means "this can be a dictionary or nothing,
           and defaults to nothing."
    - timeout — If no response in 30 seconds, then end this

    403 vs 429
    - 403 - "Forbidden": Often used for rate limiting
    - 429 - "Too many requests": The standard for rate limiting
    """
    #
    for attempt in range(1, API_MAX_RETRIES + 1):
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)

        # put the response to json if everything is ok
        if resp.status_code == 200:
            return resp.json()

        # if something with rate limiting is wrong, retry and log
        if resp.status_code in (403, 429):
            # Check for Retry-After header, otherwise exponential backoff
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                wait = int(retry_after)
            else:
                wait = 2**attempt #exponential backoff, a nice thing to do
            log.warning(
                "Rate limited (HTTP %s), attempt %d/%d — sleeping %ds",
                resp.status_code,
                attempt,
                API_MAX_RETRIES,
                wait,
            )
            time.sleep(wait)
            continue

        resp.raise_for_status()

    # If all three attempts fail, throw an explicit error
    raise RuntimeError(
        f"GitHub API request failed after {API_MAX_RETRIES} retries: {url}"
    )


def search_repos(
    topic: str,
    language: str = Language.PYTHON.value,              # default set by contracts/schema
    limit: int = DEFAULT_REPO_LIMIT,                    # default set by contracts/schema
    created_after: str | None = None,                   # ISO date string e.g. "2026-03-30"
) -> list[dict]:
    """Search GitHub for repos matching a topic + language filter.

    Returns a list of raw repo dicts from the API (up to *limit* items).
    - Each dictionary is one repo

    """
    # Format our query like you would in GitHub. Multi-word languages such as
    # "jupyter notebook" must be quoted — language_query_value handles that.
    query = f"topic:{topic} language:{language_query_value(language)}"
    if created_after:
        query += f" created:>{created_after}"
    # Make an empty list for repositories
    collected: list[dict] = []
    # Start on page 1 of GitHubs pagenation
    page = 1

    # ensure we collect less then our limit set in contracts/schema
    while len(collected) < limit:
        params = {
            "q": query,                                         # the search query
            "sort": "stars",                                    # Sort by number of stars
            "order": "desc",                                    # in descending order
            "per_page": min(PER_PAGE, limit - len(collected)),  # only ask for number we want per page
            "page": page,                                       # page number
        }
        # Do the request with the retry
        data = _request_with_retry(SEARCH_URL, params)
        # github calls these things items, get them
        items = data.get("items", [])
        # break out of this if there are no results
        if not items:
            break

        # extend used to add all items from the page to our collected list
        #       (unlike append(), which would add itself as a single element
        collected.extend(items)
        # Go to the next page
        page += 1
        # Sleep a little to be polite to the servers
        time.sleep(API_CALL_DELAY)

    # only grab up to the limit, even if we got more than that from a page
    return collected[:limit]


def parse_repo(raw: dict) -> dict:
    """Extract the fields we care about from a GitHub API repo object,
    matching our raw_repos schema exactly."""
    # Grab the current time so we know when we donwloaded it
    now = datetime.now(timezone.utc)
    # fallback to empty dictionary if there is no license
    license_info = raw.get("license") or {}
    return {
        "id": raw["id"], # Required, so we dont use get()
        "full_name": raw["full_name"], # Required, so we dont use get()
        "owner": raw.get("owner", {}).get("login"), # way to navigate nested data
        "name": raw.get("name"),
        "description": (raw.get("description") or "")[:4000], # truncate to 4000 characters of desctiption
        "language": raw.get("language"),
        "stars": raw.get("stargazers_count", 0), # deafults stars to 0 if missing
        "forks": raw.get("forks_count", 0),
        "open_issues": raw.get("open_issues_count", 0),
        "watchers": raw.get("watchers_count", 0),
        "size_kb": raw.get("size", 0),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "pushed_at": raw.get("pushed_at"),
        "fetched_at": now.isoformat(),
        "topics": raw.get("topics", []), # a list of strings
        "license": license_info.get("spdx_id"), # helped by our license_info above
        "homepage": raw.get("homepage"),
        "default_branch": raw.get("default_branch"),
        "is_fork": raw.get("fork", False),
        "is_archived": raw.get("archived", False),
    }

def fetch_readme(full_name: str) -> str:
    """Fetch and decode the README for a repo. Returns "" on any error."""
    url = f"https://api.github.com/repos/{full_name}/readme"
    try:
        data = _request_with_retry(url)
        raw_content = data.get("content", "")
        decoded = base64.b64decode(raw_content).decode("utf-8", errors="replace")
        return decoded[:50_000]
    except Exception:
        return ""
    finally:
        time.sleep(API_CALL_DELAY)


def fetch_readmes(repos: list[dict]) -> list[dict]:
    """Inject readme_content into each repo dict by calling the GitHub API."""
    total = len(repos)
    for i, repo in enumerate(repos, start=1):
        print(f"Fetching READMEs: {i}/{total}", flush=True)
        repo["readme_content"] = fetch_readme(repo["full_name"])
    return repos


# Searches GitHub for each (language, topic) combination that we want
def fetch_all_topics(
    languages: list[str] | None = None,
    limit: int = DEFAULT_REPO_LIMIT,
) -> list[dict]:
    """Iterate over every language × SearchTopic combination, search GitHub,
    parse results, and return deduplicated parsed repo rows.

    Parameters:
      - languages — list of GitHub language names to search. When None, every
        language configured in ``DEFAULT_LANGUAGES`` (contracts/schema.py) is used.
      - limit — max repos to pull per (language, topic) query.

    Deduplication is global across all languages and topics: a repo is only
    returned once even if it matches several queries (its own ``language`` field
    from the API still reflects GitHub's primary language for that repo).
    """
    # Default to the full configured language set when none is provided
    languages = languages or DEFAULT_LANGUAGES

    # a set that includes unique repo ID's we have seen, stopping duplication
    seen_ids: set[int] = set()
    # our final list of parsed repos
    results: list[dict] = []

    # for each language, then each topic from our topics in contracts/schema
    for language in languages:
        for topic in SearchTopic:
            # log what we are going to do
            log.info(
                "Searching topic=%s language=%s limit=%d", topic.value, language, limit
            )
            # Call search repos to get raw data
            raw_items = search_repos(topic.value, language=language, limit=limit)
            # for each repo from GitHub
            for item in raw_items:
                # use the parse_repo function to parse it down to our cleaned set
                repo = parse_repo(item)
                # Check to see if we have the id already, to stop duplicates
                if repo["id"] not in seen_ids:
                    # If not, add to out set of seen ids
                    seen_ids.add(repo["id"])
                    # And then append our cleaned data into our list that is returned
                    results.append(repo)

    # Final logging information
    log.info(
        "Fetched %d unique repos across %d languages × %d topics",
        len(results),
        len(languages),
        len(SearchTopic),
    )
    # return our completed list of repository data
    return results
