"""Install or verify the dependencies listed in the repository requirements file."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the Python dependencies required by CostAware."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check that dependencies are installed without changing the environment.",
    )
    args = parser.parse_args()

    if not REQUIREMENTS.exists():
        raise FileNotFoundError(f"Requirements file not found: {REQUIREMENTS}")

    if args.check:
        command = [sys.executable, "-m", "pip", "check"]
    else:
        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(REQUIREMENTS),
        ]

    print(f"Using Python: {sys.executable}")
    print(f"Requirements: {REQUIREMENTS}")
    subprocess.run(command, cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
