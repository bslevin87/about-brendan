"""
Environment variable loader with file reference support.

This module automatically resolves 'file:' references in environment variables
when imported. It must be imported before any code that reads environment variables.
"""

import os
from pathlib import Path
from typing import Optional


def resolve_file_references() -> None:
    """
    Resolve file: references in environment variables.

    Scans all environment variables and resolves any that start with 'file:'.
    Updates os.environ with the resolved values in place.

    Example:
        If COINBASE_API_SECRET=file:config/private.key, this will read
        config/private.key and replace the environment variable with its contents.
    """
    project_root = Path(__file__).parent.parent.parent

    for key, value in list(os.environ.items()):
        if isinstance(value, str) and value.startswith('file:'):
            file_path_str = value[5:]  # Remove 'file:' prefix

            # Make relative paths relative to project root
            file_path = Path(file_path_str)
            if not file_path.is_absolute():
                file_path = project_root / file_path_str

            if not file_path.exists():
                raise FileNotFoundError(
                    f"Environment variable {key} references non-existent file: {file_path}"
                )

            try:
                # Read file contents and update environment
                with open(file_path, 'r') as f:
                    contents = f.read()

                os.environ[key] = contents

            except Exception as e:
                raise RuntimeError(
                    f"Failed to read file for environment variable {key}: {file_path}"
                ) from e


def load_environment() -> None:
    """
    Load .env file and resolve any file references.

    This should be called once at application startup before any
    other modules that depend on environment variables.

    Process:
    1. Load .env file manually (to ensure consistent behavior)
    2. Resolve any file: references in environment variables
    """
    # Load .env file manually to avoid dotenv issues
    project_root = Path(__file__).parent.parent.parent
    env_file = project_root / '.env'

    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse key=value pairs
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # Remove surrounding quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]

                    # Only set if not already in environment (don't override system env vars)
                    if key not in os.environ:
                        os.environ[key] = value

    # Resolve file references
    resolve_file_references()


# Auto-load on import
# This ensures file references are resolved before any other code runs
load_environment()
