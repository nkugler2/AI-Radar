"""
contracts/schema.py

AI Radar — Single Source of Truth
===================================
This file is the shared contract between all agents (ingestion, transform, dashboard).
Every agent MUST read this file before writing any code. No agent should hardcode table
names, column names, DB paths, or category logic — it all lives here.

Rules:
  - Ingestion agent WRITES to raw tables, READS nothing else.
  - Transform agent READS raw tables, WRITES to clean/analytical tables.
  - Dashboard agent READS clean/analytical tables, WRITES nothing.
  - If you need a new column or table, add it HERE first. Never in agent code.

Schema version is tracked so future migrations can be handled gracefully.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(PROJECT_ROOT / "data" / "ai_radar.duckdb")


# ---------------------------------------------------------------------------
# Table names — every SQL reference should use these constants
# ---------------------------------------------------------------------------
RAW_REPOS_TABLE = "raw_repos"
RAW_CONTRIBUTORS_TABLE = "raw_contributors"
RAW_RELEASES_TABLE = "raw_releases"

REPOS_TABLE = "repos"                # cleaned + scored
SNAPSHOTS_TABLE = "repo_snapshots"   # daily snapshots for time-series


# ---------------------------------------------------------------------------
# Ingestion config
# ---------------------------------------------------------------------------
class Language(str, Enum):
    """Supported languages for repo discovery. Add new languages here to
    expand coverage — the ingestion agent reads this list dynamically."""
    PYTHON = "python"
    # Future:
    # JAVASCRIPT = "javascript"
    # TYPESCRIPT = "typescript"
    # RUST = "rust"


# gives my code easy to use names for the strings that GitHub wants
class SearchTopic(str, Enum):
    """GitHub topic tags used as seed queries. Adding a value here
    automatically includes it in the next ingestion run."""
    LLM = "llm"
    RAG = "rag"
    AGENTS = "agents"
    COMPUTER_VISION = "computer-vision"
    NLP = "nlp"
    MACHINE_LEARNING = "machine-learning"
    DEEP_LEARNING = "deep-learning"
    TRANSFORMERS = "transformers"
    GENERATIVE_AI = "generative-ai"
    STABLE_DIFFUSION = "stable-diffusion"
    LANGCHAIN = "langchain"


# How many repos to pull per search query (GitHub caps at 1000 total results)
DEFAULT_REPO_LIMIT = 150

# Rate-limit safety: pause (seconds) between paginated API calls
API_CALL_DELAY = 0.75

# Maximum retries on 403 / rate-limit responses before giving up
API_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# AI category mapping — used by the transform agent
# ---------------------------------------------------------------------------
class AICategory(str, Enum):
    """High-level categories assigned to repos based on their topic tags.
    The transform agent maps raw topics → one of these. Dashboard reads them."""
    LLM = "LLM / Language Models"
    RAG = "RAG / Retrieval"
    AGENTS = "AI Agents"
    COMPUTER_VISION = "Computer Vision"
    NLP = "NLP"
    ML_FRAMEWORK = "ML Framework"
    IMAGE_GEN = "Image Generation"
    DATA_TOOLS = "Data / ML Ops"
    OTHER = "Other AI"


# Map from GitHub topic tags → AICategory.  Transform agent uses this
# to assign each repo a single primary category.  First match wins,
# so order matters (more specific topics should come first).
TOPIC_TO_CATEGORY: dict[str, AICategory] = {
    "rag": AICategory.RAG,
    "retrieval-augmented-generation": AICategory.RAG,
    "agents": AICategory.AGENTS,
    "ai-agents": AICategory.AGENTS,
    "langchain": AICategory.AGENTS,
    "autogen": AICategory.AGENTS,
    "llm": AICategory.LLM,
    "large-language-model": AICategory.LLM,
    "gpt": AICategory.LLM,
    "chatgpt": AICategory.LLM,
    "transformers": AICategory.LLM,
    "stable-diffusion": AICategory.IMAGE_GEN,
    "diffusion": AICategory.IMAGE_GEN,
    "text-to-image": AICategory.IMAGE_GEN,
    "computer-vision": AICategory.COMPUTER_VISION,
    "object-detection": AICategory.COMPUTER_VISION,
    "image-classification": AICategory.COMPUTER_VISION,
    "yolo": AICategory.COMPUTER_VISION,
    "nlp": AICategory.NLP,
    "natural-language-processing": AICategory.NLP,
    "text-classification": AICategory.NLP,
    "sentiment-analysis": AICategory.NLP,
    "machine-learning": AICategory.ML_FRAMEWORK,
    "deep-learning": AICategory.ML_FRAMEWORK,
    "pytorch": AICategory.ML_FRAMEWORK,
    "tensorflow": AICategory.ML_FRAMEWORK,
    "jax": AICategory.ML_FRAMEWORK,
    "mlops": AICategory.DATA_TOOLS,
    "data-pipeline": AICategory.DATA_TOOLS,
    "feature-store": AICategory.DATA_TOOLS,
}


# ---------------------------------------------------------------------------
# Scoring weights — used by the transform agent
# ---------------------------------------------------------------------------
# Momentum score = weighted combination of recent signals
MOMENTUM_WEIGHTS = {
    "stars_per_day": 0.40,       # stars / repo_age_days
    "recent_push_bonus": 0.30,   # inverse of days_since_push, capped
    "fork_ratio": 0.15,          # forks / stars  (engagement depth)
    "issue_activity": 0.15,      # open_issues as activity proxy
}

# Maintenance score = signals of active upkeep
MAINTENANCE_WEIGHTS = {
    "days_since_push": 0.50,     # lower is better
    "has_recent_release": 0.30,  # boolean bonus if release < 90 days
    "issue_close_ratio": 0.20,   # closed / (open + closed)
}


# ---------------------------------------------------------------------------
# Raw table schemas (Ingestion agent creates these)
# ---------------------------------------------------------------------------
RAW_REPOS_COLUMNS = [
    "id", "full_name", "owner", "name", "description", "language",
    "stars", "forks", "open_issues", "watchers", "size_kb",
    "created_at", "updated_at", "pushed_at", "fetched_at",
    "topics", "license", "homepage", "default_branch",
    "is_fork", "is_archived",
]

RAW_REPOS_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {RAW_REPOS_TABLE} (
    id                  BIGINT PRIMARY KEY,
    full_name           VARCHAR NOT NULL,
    owner               VARCHAR,
    name                VARCHAR,
    description         VARCHAR,
    language            VARCHAR,
    stars               INTEGER DEFAULT 0,
    forks               INTEGER DEFAULT 0,
    open_issues         INTEGER DEFAULT 0,
    watchers            INTEGER DEFAULT 0,
    size_kb             INTEGER DEFAULT 0,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    pushed_at           TIMESTAMP,
    fetched_at          TIMESTAMP NOT NULL,
    topics              VARCHAR[],
    license             VARCHAR,
    homepage            VARCHAR,
    default_branch      VARCHAR,
    is_fork             BOOLEAN DEFAULT FALSE,
    is_archived         BOOLEAN DEFAULT FALSE
);
"""

RAW_CONTRIBUTORS_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {RAW_CONTRIBUTORS_TABLE} (
    repo_id             BIGINT NOT NULL,
    login               VARCHAR NOT NULL,
    contributions       INTEGER DEFAULT 0,
    fetched_at          TIMESTAMP NOT NULL,
    PRIMARY KEY (repo_id, login)
);
"""

RAW_RELEASES_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {RAW_RELEASES_TABLE} (
    id                  BIGINT PRIMARY KEY,
    repo_id             BIGINT NOT NULL,
    tag_name            VARCHAR,
    name                VARCHAR,
    published_at        TIMESTAMP,
    is_prerelease       BOOLEAN DEFAULT FALSE,
    fetched_at          TIMESTAMP NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Clean / analytical table schemas (Transform agent creates these)
# ---------------------------------------------------------------------------
REPOS_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {REPOS_TABLE} (
    id                      BIGINT PRIMARY KEY,
    full_name               VARCHAR NOT NULL,
    owner                   VARCHAR,
    name                    VARCHAR,
    description             VARCHAR,
    language                VARCHAR,
    stars                   INTEGER,
    forks                   INTEGER,
    open_issues             INTEGER,
    watchers                INTEGER,
    topics                  VARCHAR[],
    license                 VARCHAR,
    homepage                VARCHAR,
    created_at              TIMESTAMP,
    pushed_at               TIMESTAMP,
    fetched_at              TIMESTAMP,

    -- Computed by transform agent
    repo_age_days           INTEGER,
    days_since_push         INTEGER,
    stars_per_day           FLOAT,
    fork_to_star_ratio      FLOAT,
    contributor_count       INTEGER,
    release_count           INTEGER,
    latest_release_date     TIMESTAMP,
    days_since_release      INTEGER,

    -- Scores
    momentum_score          FLOAT,
    maintenance_score       FLOAT,

    -- Classification
    category                VARCHAR,

    -- Flags
    is_archived             BOOLEAN DEFAULT FALSE
);
"""

SNAPSHOTS_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {SNAPSHOTS_TABLE} (
    repo_id             BIGINT NOT NULL,
    snapshot_date       DATE NOT NULL,
    stars               INTEGER,
    forks               INTEGER,
    open_issues         INTEGER,
    momentum_score      FLOAT,
    maintenance_score   FLOAT,
    PRIMARY KEY (repo_id, snapshot_date)
);
"""


# ---------------------------------------------------------------------------
# All schemas in execution order — used by a setup / migration script
# ---------------------------------------------------------------------------
ALL_SCHEMAS = [
    RAW_REPOS_SCHEMA,
    RAW_CONTRIBUTORS_SCHEMA,
    RAW_RELEASES_SCHEMA,
    REPOS_SCHEMA,
    SNAPSHOTS_SCHEMA,
]


# ---------------------------------------------------------------------------
# Helper: initialize the database with all tables
# ---------------------------------------------------------------------------
def init_db(db_path: str | None = None) -> None:
    """Create the DuckDB file and all tables if they don't exist.
    Safe to call repeatedly — every statement uses IF NOT EXISTS."""
    import duckdb

    path = db_path or DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(path)
    try:
        # Store schema version as a pragma-style metadata table
        con.execute("""
            CREATE TABLE IF NOT EXISTS _meta (
                key     VARCHAR PRIMARY KEY,
                value   VARCHAR
            )
        """)
        con.execute("""
            INSERT OR REPLACE INTO _meta (key, value)
            VALUES ('schema_version', ?)
        """, [SCHEMA_VERSION])

        for ddl in ALL_SCHEMAS:
            con.execute(ddl)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Helper: get a DuckDB connection (agents should use this)
# ---------------------------------------------------------------------------
def get_connection(db_path: str | None = None, read_only: bool = False):
    """Return a duckdb connection.  Dashboard agent should pass read_only=True."""
    import duckdb

    path = db_path or DB_PATH
    return duckdb.connect(path, read_only=read_only)
