---
title: Documentation Metadata Standard
doc_type: standard
status: active
audience:
  - human
  - ai-agent
canonicality: canonical
subsystem: documentation
purpose: Define lightweight frontmatter and traceability conventions for repository docs.
related_docs:
  - ../README.md
  - README.md
  - ../python/AI_PROMPT_GUIDE.md
verified_on: 2026-03-22
---

# Documentation Metadata Standard

## Goal

This file defines a lightweight metadata standard for markdown documents in this repository.

The goal is to make docs easier for:

- humans to navigate
- AI coding agents to classify and route
- future tooling to validate and lint

## Why this helps AI

Frontmatter gives an AI model and future automation explicit signals about:

- what a document is
- whether it is canonical or supporting
- which subsystem it belongs to
- who it is for
- what related docs should be read next

Without metadata, those signals must be inferred from prose. Inference works, but metadata is cleaner and more reliable.

## Required frontmatter fields for key docs

Important repo entry points and canonical docs should include these fields:

- `title`
- `doc_type`
- `status`
- `audience`
- `canonicality`
- `subsystem`
- `purpose`
- `related_docs`
- `verified_on`

## Field definitions

### `title`

Human-readable document title.

### `doc_type`

What kind of document this is.

Suggested values:

- `guide`
- `index`
- `reference`
- `design`
- `prompt-guide`
- `prompt-templates`
- `standard`
- `testing-guide`
- `legacy-reference`
- `proposal`

### `status`

Lifecycle state.

Suggested values:

- `active`
- `draft`
- `legacy`
- `historical`

### `audience`

List of intended audiences.

Suggested values:

- `human`
- `ai-agent`
- `developer`
- `operator`
- `tester`

### `canonicality`

How authoritative the document is.

Suggested values:

- `canonical`
- `supporting`
- `legacy`
- `draft`

### `subsystem`

Primary area of the repo the document describes.

Suggested values:

- `repository`
- `documentation`
- `firmware`
- `spi`
- `msp`
- `esc-passthrough`
- `python`
- `imgui-esc-config`

### `purpose`

One sentence describing how the document should be used.

### `related_docs`

Relative-path list of the most relevant companion docs.

### `verified_on`

Date this doc structure/content was last deliberately reviewed.

## Optional fields

These are useful when a doc becomes more rigorous later:

- `related_files`
- `implements`
- `supersedes`
- `superseded_by`
- `tags`
- `verification_confidence`

## Example

```yaml
---
title: Python Directory AI Prompt Guide
doc_type: prompt-guide
status: active
audience:
  - human
  - ai-agent
canonicality: canonical
subsystem: python
purpose: Route humans and AI agents to the correct Python subtree and prompt context.
related_docs:
  - ../README.md
  - imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md
verified_on: 2026-03-22
---
```

## Scope for this first pass

This first pass applies the standard to the most important repo entry documents:

- `README.md`
- `PROMPTS.md`
- `docs/README.md`
- `python/AI_PROMPT_GUIDE.md`
- `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`

The same scheme can be expanded later to the rest of the markdown files.

## Notes

- Keep metadata lightweight; do not turn every file into a bureaucratic form.
- Prefer accuracy over completeness.
- If frontmatter and document body disagree, update the document.
