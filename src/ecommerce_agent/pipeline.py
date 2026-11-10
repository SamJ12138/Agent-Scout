"""Main pipeline orchestrating fetch → extract → report."""

import json
from pathlib import Path
from typing import Any
from .config import config
from .logger import log
from .extract import extract_fields
from .report import generate_report, write_report


def load_input(input_path: Path) -> list[dict[str, Any]]:
    """Load input data from JSON file."""
    log.info(f"Loading input from: {input_path}")
    
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Handle both single object and list
    if isinstance(data, dict):
        products = data.get("products", [data])
    else:
        products = data
    
    log.info(f"Loaded {len(products)} product(s)")
    return products


def fetch_product_data(product: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch/enrich product data.
    
    In production, this would make real HTTP requests.
    For demo, we pass through with mock enrichment.
    """
    url = product.get("url", "")
    log.info(f"Fetching: {url or 'inline data'}")
    
    # Mock fetch - in production this would crawl the URL
    enriched = {
        **product,
        "fetched": True,
        "fetch_timestamp": "2024-01-01T00:00:00Z",
    }
    
    return enriched


def run_pipeline(
    input_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """
    Run the full pipeline: load → fetch → extract → report.
    
    Returns the path to the output file.
    """
    log.info("=" * 40)
    log.info("Starting ecommerce agent pipeline")
    log.info("=" * 40)
    
    # Resolve paths
    if input_path is None:
        input_path = config.fixtures_dir / "sample_input.json"
    if output_path is None:
        output_path = config.ensure_output_dir() / "output.json"
    
    # Step 1: Load input
    products = load_input(input_path)
    
    # Step 2: Fetch (mock)
    log.info("Step: Fetch product data")
    fetched = [fetch_product_data(p) for p in products]
    
    # Step 3: Extract structured fields
    log.info("Step: Extract structured fields")
    extracted = [extract_fields(p) for p in fetched]
    
    # Step 4: Generate and write report
    log.info("Step: Generate report")
    report = generate_report(extracted)
    output_file = write_report(report, output_path)
    
    log.info("=" * 40)
    log.info(f"Pipeline complete! Output: {output_file}")
    log.info("=" * 40)
    
    return output_file
