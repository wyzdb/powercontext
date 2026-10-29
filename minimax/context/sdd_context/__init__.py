"""SDD context module for the MiniMax × OceanBase ecosystem challenge."""

def main() -> int:
    """Load service adapters only when invoking the CLI."""
    from sdd_context.cli import main as cli_main

    return cli_main()

__all__ = ["main"]
