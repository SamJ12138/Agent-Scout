"""Command-line interface for ecommerce agent."""

import argparse
import sys
from pathlib import Path
from . import __version__


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="ecommerce_agent",
        description="Ecommerce Agent - Auto researcher CLI tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Demo command
    demo_parser = subparsers.add_parser(
        "demo",
        help="Run demo pipeline with sample input",
    )
    demo_parser.add_argument(
        "-i", "--input",
        type=Path,
        help="Custom input file (default: fixtures/sample_input.json)",
    )
    demo_parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Custom output file (default: output/output.json)",
    )
    
    # Run command (alias for demo with custom input)
    run_parser = subparsers.add_parser(
        "run",
        help="Run pipeline with specified input",
    )
    run_parser.add_argument(
        "input",
        type=Path,
        help="Input JSON file",
    )
    run_parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file path",
    )
    
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)
    
    if args.command is None:
        parser.print_help()
        return 0
    
    # Import here to avoid circular imports and speed up --help
    from .pipeline import run_pipeline
    
    if args.command == "demo":
        output = run_pipeline(
            input_path=args.input,
            output_path=args.output,
        )
        print(f"\n[OK] Demo complete! Output saved to: {output}")
        return 0
    
    if args.command == "run":
        output = run_pipeline(
            input_path=args.input,
            output_path=args.output,
        )
        print(f"\n[OK] Pipeline complete! Output saved to: {output}")
        return 0
    
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
