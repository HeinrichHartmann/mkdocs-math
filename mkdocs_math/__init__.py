"""
mkdocs-math: A MkDocs plugin for mathematical typesetting and semantic environments.

Provides support for:
- Mathematical theorem and proof environments
- Semantic LaTeX macros and preambles
- Math-specific document metadata
- Proof state management and rendering
"""

from .plugin import Plugin

__version__ = "0.1.0"
__all__ = ["Plugin"]
