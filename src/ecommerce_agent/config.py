"""Configuration management via environment variables."""

import os
from pathlib import Path

# Try to load .env file if it exists (optional dependency)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    """Application configuration from environment variables."""
    
    def __init__(self):
        self.api_key: str = os.getenv("API_KEY", "")
        self.output_dir: Path = Path(os.getenv("OUTPUT_DIR", "output"))
        self.fixtures_dir: Path = Path(os.getenv("FIXTURES_DIR", "fixtures"))
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    def ensure_output_dir(self) -> Path:
        """Create output directory if it doesn't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir


# Global config instance
config = Config()
