# Ecommerce Agent

A minimal CLI tool for automated product research: crawl/fetch → extract structured fields → output report.

## Quick Start (Windows PowerShell)

### 1. Create and activate virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Install the package

```powershell
pip install -e .
```

### 4. (Optional) Configure environment

```powershell
Copy-Item .env.example .env
# Edit .env with your settings
```

### 5. Run demo

```powershell
python -m ecommerce_agent demo
```

### 6. Run tests

```powershell
pytest tests/ -v
```

## Usage

```powershell
# Show help
python -m ecommerce_agent --help

# Run demo with default sample input
python -m ecommerce_agent demo

# Run with custom input/output
python -m ecommerce_agent demo -i path/to/input.json -o path/to/output.json

# Run pipeline on specific file
python -m ecommerce_agent run input.json -o results.json
```

## Project Structure

```
├── README.md
├── .gitignore
├── .env.example
├── requirements.txt
├── src/
│   └── ecommerce_agent/
│       ├── __init__.py      # Package metadata
│       ├── __main__.py      # Entry point for -m
│       ├── cli.py           # Argument parsing
│       ├── config.py        # Environment config
│       ├── logger.py        # Logging setup
│       ├── pipeline.py      # Main orchestration
│       ├── extract.py       # Field extraction
│       └── report.py        # Report generation
├── tests/
│   └── test_smoke.py        # Smoke tests
├── fixtures/
│   └── sample_input.json    # Demo input
└── output/                  # Generated reports (gitignored)
```

## Input Format

```json
{
  "products": [
    {
      "name": "Product Name",
      "url": "https://example.com/product",
      "category": "tool type",
      "description": "Product description text...",
      "tasks": ["task1", "task2"],
      "integrations": ["App1", "App2"],
      "location": "City, State"
    }
  ]
}
```

## Output Fields

Each product is analyzed to extract:

| Field | Type | Description |
|-------|------|-------------|
| `product_one_liner` | string | Brief summary |
| `target_user` | string | Inferred target audience |
| `tasks_covered` | list | Capabilities/tasks |
| `can_execute` | bool | Can perform actions |
| `multi_agent` | bool | Multi-agent support |
| `integrations` | list | Connected services |
| `evidence_sources` | list | Source URLs |
| `location` | string | Company location |

## Development

```powershell
# Run tests with coverage
pytest tests/ -v --tb=short

# Run specific test
pytest tests/test_smoke.py::TestPipeline -v
```

## Verification

```powershell
python -m ecommerce_agent demo
pytest -q
```

## License

MIT
