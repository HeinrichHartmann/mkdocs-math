# MkDocs Math - Outline Feature

Automatic table of contents generation for mathematical articles.

## Setup

1. Copy `mkdocs_math/templates/main.html` to your project's `overrides/` directory
2. Configure MkDocs theme:

```yaml
theme:
  name: material
  custom_dir: overrides
```

## Article Pages

Mark pages as articles by adding `type: math-article` to frontmatter:

```markdown
---
type: math-article
title: "My Mathematics Article"
author: "Your Name"
date: "2025-12-04"
place: "Location"
abstract: |
  Brief description of your article...
---

## Introduction

Your content here...
```

## Outline Configuration

The outline is automatically generated from document headings.

### 1. Global Configuration (mkdocs.yml)

Configure outline behavior in plugin settings:

```yaml
plugins:
  - my-mkdocs-math:
      outline_enabled: true      # Enable/disable outlines (default: true)
      outline_depth: 2           # Include h2 and h3 (default: 2)
```

### 2. Per-Article Override

Override settings in individual article frontmatter:

```markdown
---
type: math-article
title: "My Article"
outline_enabled: true      # true/false to enable/disable
outline_depth: 3           # 1-6 to include h2, h3, h4, etc.
---
```

### 3. Heading Levels

- `outline_depth: 1` → Include h2 only
- `outline_depth: 2` → Include h2, h3 (default)
- `outline_depth: 3` → Include h2, h3, h4
- etc. (up to h6)

## Features

1. **Automatic generation** - Outline extracted from document headings
2. **Anchor links** - Outline items link directly to sections
3. **Math support** - Full LaTeX math notation in headings
4. **Configurable depth** - Control which heading levels appear
5. **Per-file control** - Enable/disable outline per article
