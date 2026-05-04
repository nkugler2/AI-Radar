"""
main.py

Orchestrates the full AI Radar pipeline:
1. Ingestion: Fetch repos from GitHub, write raw_repos
2. Transform: Clean data and compute metrics, write repos
3. Dashboard: Ready to launch with streamlit run dashboard/app.py
"""

import logging
import sys

from ingestion.runner import run_ingestion
from transform.metrics import run as run_transform

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)


def main():
    """Run the full pipeline: ingestion → transform → ready for dashboard."""
    log.info("=" * 70)
    log.info("AI Radar Pipeline Started")
    log.info("=" * 70)

    # Step 1: Ingestion
    log.info("")
    log.info("STEP 1: Running ingestion...")
    log.info("-" * 70)
    ingestion_count = run_ingestion()
    log.info("Ingestion complete: %d repos fetched and written to raw_repos.", ingestion_count)

    # Step 2: Transform
    log.info("")
    log.info("STEP 2: Running transform...")
    log.info("-" * 70)
    transform_count = run_transform()
    log.info("Transform complete: %d repos cleaned, scored, and written to repos.", transform_count)

    # Summary and next steps
    log.info("")
    log.info("=" * 70)
    log.info("Pipeline Complete!")
    log.info("=" * 70)
    log.info("")
    log.info("Next: Launch the dashboard with:")
    log.info("  uv run streamlit run dashboard/app.py")
    log.info("")


if __name__ == "__main__":
    main()
    sys.exit(0)
