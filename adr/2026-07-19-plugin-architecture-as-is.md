# ADR: mkdocs-math plugin architecture (as-is record)

Date: 2026-07-19. Status: ACCEPTED (retroactive record).

This ADR documents the architecture decisions already embodied in the
plugin, so far only implicit in the README and code. Elements semantics
are NOT specified here — they are owned by the math repo's ADRs
(`2026-07-18-elements-theory-tree`, `2026-07-19-mkdocs-math-elements-support`,
`2026-07-19-elements-validation`); this plugin implements them.

## Context

The plugin grew feature by feature (environments, preamble, citations,
outlines, article layout, export, Elements) without a recorded
architecture. Before making forward-looking decisions
(see `2026-07-19-plugin-site-boundary.md`) the status quo is fixed here.

## Decision (as-is)

### 1. Markdown-native syntax, no custom markup

All authoring syntax is plain markdown that degrades gracefully in any
renderer (Obsidian is the primary editing frontend):

- Environments: `**Name.**` / `**Name (Label).**` bold headers,
  terminated by two blank lines, the next environment header, a
  heading, or EOF. Any capitalized word is an environment name; proofs
  are unnumbered.
- Stable anchors: `{#custom-id}` on the first content line
  (environments) or `attr_list` syntax (headings).
- Cross-references: `[#id]` → numbered link, `[❌]` when unresolved.
- Citations: pandoc-style `[@key]` / `[@key; @key2]` against a BibTeX
  file; optional `citetag` bib field for visible tags.
- Metadata: standard YAML frontmatter only (`type: math-article`,
  `outline_*`, `math.preamble`, Elements node schema).

Rationale: files stay readable and editable outside the build pipeline;
no lock-in to plugin-specific markup.

### 2. Build pipeline: markdown-to-markdown transforms

`on_page_markdown` is a fixed sequence of text transforms; each step
consumes and produces markdown, so steps compose and can be tested in
isolation:

1. article listing expansion (`{{ARTICLES}}`, `{{FLAT_ARTICLES}}`)
2. heading-anchor registration
3. Elements header/backlinks injection (before citations, so
   `published_at` chips resolve as citations)
4. citation processing
5. outline injection
6. print/web target-block stripping
7. preamble injection (hidden MathJax `<div>`; no server-side LaTeX)
8. environment conversion (to `pymdownx.blocks` / raw HTML divs)
9. anchor-reference resolution
10. E-ID autolinking

Rendering delegates to standard extensions (`pymdownx.blocks`,
`attr_list`, `arithmatex`/MathJax); the plugin emits markdown they
understand rather than HTML wherever possible.

### 3. Registries as single sources of truth

- **Elements registry** (`id → node`), built in `on_files` by scanning
  the elements dir frontmatter. All E-ID resolution goes through it;
  duplicate IDs abort the build. Exported as `elements/index.json`
  (machine interface per the math repo ADR).
- **Anchor registry** (`anchor → title/number/type`), populated during
  page processing and persisted to `.cache/` so forward references
  survive page-ordering and serve rebuilds.
- **Citation registry**, backed by the configured bib file (vendored
  citation code under `citations/`).

### 4. Companion CLI shares the build parsers

`python -m mkdocs_math {lint, outline, export}` reuses
`environment_regex` and the Elements registry — the linter checks what
the build would do, not a parallel grammar. Lint covers article checks
(F/E/C/M/L/R codes) and, for Elements nodes, the E-* checks from the
math repo ADR. Export produces LaTeX/PDF via pandoc from the same
source files.

### 5. Templates

The plugin ships `templates/main.html` (article layout: title, byline,
abstract, outline, references) and registers its template dir with the
theme. Article pages are driven entirely by frontmatter; the body has
no H1.

## Consequences

- Any markdown processor can render the sources; the plugin only adds
  numbering, links, and layout.
- Transform ordering is load-bearing (e.g. Elements header before
  citations); changes to the sequence need tests.
- Registries make features orthogonal: autolinking, backlinks, badges,
  and `index.json` are views over the same data.

## Known deviations (recorded, not endorsed)

See `Reviews/2026-07-19-claude-fable-5.md` for the full list. The
significant ones: three URL builders instead of one, `.cache/` anchored
to CWD, preamble cache not invalidated on serve rebuilds, `pcre2`
dependency where stdlib `re` suffices, lint without error/warn
severities. Forward decisions on these live in
`2026-07-19-plugin-site-boundary.md`.
