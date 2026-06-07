"""
Shared pytest fixtures for mkdocs-math plugin tests.

Provides a module-level build fixture that builds the test project once
and makes the build artifacts available to all tests.
"""

import subprocess
from pathlib import Path
import shutil
import pytest


TEST_PROJECT_DIR = Path(__file__).parent / "test_project"
BUILD_OUTPUT_DIR = Path(__file__).parent / "test_project" / "build"


@pytest.fixture(scope="session")
def build_test_project():
    """Build the test project once for all tests in the session.

    This fixture:
    1. Cleans the build directory
    2. Runs mkdocs build
    3. Provides the build output directory to all tests
    4. Cleans up after all tests in the session

    Returns:
        Path: The build output directory
    """
    # Clean build directory
    if BUILD_OUTPUT_DIR.exists():
        shutil.rmtree(BUILD_OUTPUT_DIR)

    # Build the project
    result = subprocess.run(
        ["uv", "run", "mkdocs", "build", "-f", str(TEST_PROJECT_DIR / "mkdocs.yml")],
        cwd=TEST_PROJECT_DIR.parent.parent.parent,  # Run from project root (math/)
        capture_output=True,
        text=True
    )

    # Fail early if build doesn't work - all subsequent tests depend on this
    if result.returncode != 0:
        raise RuntimeError(f"Build failed:\n{result.stderr}")

    if not BUILD_OUTPUT_DIR.exists():
        raise RuntimeError("Build output directory not created")

    yield BUILD_OUTPUT_DIR

    # Build artifacts are preserved for manual inspection
    # Run 'just clean' to remove the build directory manually


def assert_environment_rendered(html_content: str, env_name: str, label: str = None):
    """Assert that an environment is present in the rendered HTML.

    Args:
        html_content: The HTML content to search
        env_name: Environment name (e.g., "Definition", "Theorem")
        label: Optional label text to verify (e.g., "Pythagorean")

    Raises:
        AssertionError: If environment is not found
    """
    # Check environment name appears in HTML
    assert env_name in html_content, \
        f"Environment '{env_name}' not found in rendered HTML"

    # If label provided, verify it's in the HTML too
    if label:
        assert label in html_content, \
            f"Label '{label}' not found for environment '{env_name}'"


def assert_environment_not_rendered(html_content: str, env_name: str):
    """Assert that an environment is NOT present in the rendered HTML.

    Args:
        html_content: The HTML content to search
        env_name: Environment name (e.g., "Definition")

    Raises:
        AssertionError: If environment is found
    """
    assert env_name not in html_content, \
        f"Environment '{env_name}' unexpectedly found in rendered HTML"
