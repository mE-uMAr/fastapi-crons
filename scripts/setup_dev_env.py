#!/usr/bin/env python3
"""
Setup development environment for fastapi-crons
Installs all dependencies and pre-commit hooks
"""

import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a shell command and handle errors"""
    print(f"\n📦 {description}...")
    try:
        subprocess.run(cmd, shell=True, check=True)
        print(f"✅ {description} completed!")
        return True
    except subprocess.CalledProcessError:
        print(f"❌ {description} failed!")
        return False

def main():
    """Main setup function"""
    print("🚀 Setting up fastapi-crons development environment...\n")

    # Get project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Install dependencies
    if not run_command(
        "pip install -e '.[dev]'",
        "Installing dependencies"
    ):
        sys.exit(1)

    # Make scripts executable
    scripts_dir = project_root / "scripts"
    for script in scripts_dir.glob("*.sh"):
        script.chmod(0o755)
        print(f"✅ Made {script.name} executable")

    # Setup pre-commit hook
    pre_commit_hook = project_root / ".git" / "hooks" / "pre-commit"
    if (project_root / ".git").exists():
        pre_commit_content = f"""#!/bin/bash
{project_root}/scripts/pre-commit.sh
"""
        pre_commit_hook.parent.mkdir(parents=True, exist_ok=True)
        pre_commit_hook.write_text(pre_commit_content)
        pre_commit_hook.chmod(0o755)
        print("✅ Pre-commit hook installed!")

    print("\n✨ Development environment setup complete!")
    print("\n📚 Available commands:")
    print("  ./scripts/test.sh          - Run tests with coverage")
    print("  ./scripts/lint.sh          - Run linting checks")
    print("  ./scripts/format.sh        - Format code")
    print("  ./scripts/type-check.sh    - Run type checking")
    print("  ./scripts/dev.sh           - Start development server")
    print("  ./scripts/build.sh         - Build package")
    print("  ./scripts/clean.sh         - Clean build artifacts")
    print("  ./scripts/ci.sh            - Run full CI pipeline")

if __name__ == "__main__":
    main()
