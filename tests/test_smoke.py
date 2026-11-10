"""Smoke tests for ecommerce_agent package."""

import json
import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestImports:
    """Test that all modules can be imported."""
    
    def test_import_package(self):
        import ecommerce_agent
        assert hasattr(ecommerce_agent, "__version__")
    
    def test_import_config(self):
        from ecommerce_agent.config import config
        assert config is not None
    
    def test_import_logger(self):
        from ecommerce_agent.logger import log
        assert log is not None
    
    def test_import_pipeline(self):
        from ecommerce_agent.pipeline import run_pipeline
        assert callable(run_pipeline)


class TestExtraction:
    """Test field extraction logic."""
    
    def test_extract_fields(self):
        from ecommerce_agent.extract import extract_fields
        
        sample = {
            "name": "TestProduct",
            "description": "A tool for developers to automate tasks",
            "url": "https://test.com",
            "integrations": ["Slack"],
            "location": "Test City",
        }
        
        result = extract_fields(sample)
        
        assert "product_one_liner" in result
        assert "target_user" in result
        assert "tasks_covered" in result
        assert "can_execute" in result
        assert "multi_agent" in result
        assert "integrations" in result
        assert result["integrations"] == ["Slack"]
        assert result["can_execute"] is True  # "automate" in description


class TestPipeline:
    """Test the full pipeline."""
    
    def test_demo_pipeline(self, tmp_path):
        from ecommerce_agent.pipeline import run_pipeline
        
        # Use fixture and write to temp output
        fixtures_dir = Path(__file__).parent.parent / "fixtures"
        input_file = fixtures_dir / "sample_input.json"
        output_file = tmp_path / "test_output.json"
        
        # Run pipeline
        result_path = run_pipeline(
            input_path=input_file,
            output_path=output_file,
        )
        
        # Verify output
        assert result_path.exists()
        
        with open(result_path) as f:
            report = json.load(f)
        
        assert "meta" in report
        assert "products" in report
        assert "summary" in report
        assert report["meta"]["product_count"] == 2
        assert len(report["products"]) == 2


class TestCLI:
    """Test CLI argument parsing."""
    
    def test_help_runs(self):
        from ecommerce_agent.cli import main
        
        # --help should return 0 (captured by argparse)
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
    
    def test_no_args_shows_help(self):
        from ecommerce_agent.cli import main
        
        # No args should return 0 and show help
        result = main([])
        assert result == 0
