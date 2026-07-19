# ADR: Plugin/site boundary and consolidation decisions

Date: 2026-07-19. Status: PROPOSED.

Companion to `2026-07-19-plugin-architecture-as-is.md` (status quo) and
the math repo's `2026-07-19-mkdocs-math-elements-support.md` (Elements
semantics). This ADR fixes the forward-looking core decisions: who owns
templates and CSS, how URLs are computed, and the consolidation targets
the implementation must converge on.

## Context

The 2026-07-19 review (`Reviews/2026-07-19-claude-fable-5.md`) found
the plugin and the consuming site (math repo) mixed together:
`partials/toc.html` exists byte-identical in both repos, the kind-badge
color palette is defined in three places, plugin templates shadow the
site's `custom_dir`, and three independent URL builders disagree on
`use_directory_urls`. The Elements ADR scoped visual design out; nobody
scoped it *in* anywhere, so presentation drifted into both codebases.

## Decision

### 1. Ownership boundary: plugin = semantics + defaults, site = theming

- The **plugin** owns semantic markup (classes like `.el-kind-*`,
  `.elements-metadata`, `.el-sidebar-*`), default templates, and one
  default stylesheet. Everything it ships is overridable.
- The **site** owns theming only: it may override any template via
  `custom_dir` and restyle via `extra.css`, but must not duplicate
  plugin templates or markup.
- Consequence for today's state: `overrides/partials/toc.html` in the
  math repo is DELETED; the plugin copy is canonical.

### 2. Template precedence: site > plugin > theme

Plugin template dirs are registered AFTER the theme's `custom_dir`,
never before. A site override always wins. (Fixes the current
`theme.dirs.insert(0, …)`; the redundant `on_env` ChoiceLoader is
removed.)

### 3. CSS ships as one plugin asset, themed by variables

The plugin ships a single stylesheet (added to the build via
`on_files` + `extra_css`), defining the palette once as CSS custom
properties (`--el-kind-theorem-bg`, …). The Elements metadata header,
sidebar, and any future component consume the variables. Sites re-theme
by overriding variables in `extra.css`. No inline `<style>` blocks in
templates; the math repo's `.el-kind-*` color rules migrate here.

### 4. One URL authority

All URL generation goes through MkDocs' `File.url` +
`mkdocs.utils.get_relative_url`. This applies to the Elements sidebar,
`_element_link`, autolinking, article listings, and
`elements/index.json`. Hand-rolled `relpath`/strip-`.md` computation is
forbidden — it is the source of the `use_directory_urls` bugs.

### 4b. Elements permalinks: `/<elements_dir>/<ID>/` (to be expanded)

Element node pages are published at ID-based URLs
(`/Elements/E0001/`), decoupled from file location and title — the
theory-tree ADR's "permanent counted tag" applied to URLs
(Stacks-style `/tag/`). Implemented by remapping `File.dest_uri` in
`on_files`; `elements/index.json` carries the same URLs. Filesystem
layout (`<ID> - Title.md`, section directories) is unchanged and never
leaks into the URL. NO backwards compatibility: old title-based URLs
are not redirected (internal site). To be expanded: release-pinned
URLs (`E0042@v...`) build on this scheme.

### 5. Lint distinguishes errors from warnings

Severities follow the math repo ADR's E-* table: errors fail the build
and CI (exit 1); warnings report but pass (exit 0, or a flag-gated
strict mode). Article checks get severities on the same scale. A single
duplicate ID reports and continues instead of aborting all output.

### 6. Consolidation targets (implementation roadmap)

- One frontmatter parser (`elements.parse_node_frontmatter` becomes the
  shared one; `lint.parse_frontmatter` and the inline copy in the
  article listing go away).
- One slugify, mirroring Python-Markdown's `toc` slugify so generated
  outline anchors cannot drift from rendered heading IDs.
- Drop the `pcre2` dependency; the label grammar has one fixed nesting
  level and compiles under stdlib `re`.
- `.cache/` is anchored to the mkdocs config directory, not CWD.
- The preamble cache is invalidated in `on_config` (per rebuild), not
  `on_startup` (per process), and lives on the plugin instance.
- `plugin.py` splits along the feature seams already visible in the
  pipeline: environments, citations, articles (layout + listing),
  elements, preamble/outline. `elements.py` is the model to follow.

### 7. ADR homes

Plugin-internal decisions (this file's scope: templates, CSS, URLs,
caching, dependencies, module layout) live in THIS repo's `adr/`.
Content semantics (node schema, lint rule set, validation model,
publication gates) stay in the math repo's `adr/`. When a math repo ADR
changes plugin-visible semantics, the plugin references it rather than
restating it.

## Consequences

- Editing presentation happens in exactly one place per concern:
  markup/template in the plugin, colors/theming in the site.
- Sidebar and `index.json` URLs become correct under both
  `use_directory_urls` modes; tests must cover both.
- CI can gate on lint errors while tolerating warnings.
- The math repo sheds `overrides/partials/toc.html` and its
  `.el-kind-*` palette rules; its `extra.css` shrinks to theming.

## Out of scope

- Visual design itself (colors, spacing) — theming, decided in the
  site.
- Elements semantics — math repo ADRs.
- Release pinning / compatibility diffing — post first release tag.
