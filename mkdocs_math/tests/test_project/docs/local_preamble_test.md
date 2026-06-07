---
title: "Local Preamble Test"
math:
  preamble: |
    \newcommand{\MyCmd}{\text{MyCmd}}
---

# Local Preamble Test

This page tests that local preamble from frontmatter is correctly injected.

The local preamble defines $\MyCmd$ command that should be available in math mode.
