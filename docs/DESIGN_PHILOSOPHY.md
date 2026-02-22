# Design philosophy

Core principles behind the LLM content pipeline.

## Local models are cheap but mediocre

- Local LLM models (Ollama, Apple Foundation Models) cost nearly nothing to run per invocation.
- A single draft from a local model is serviceable but rarely polished.
- The pipeline exploits this cost asymmetry: generate many drafts cheaply, then refine.

## Patience produces quality

- This pipeline is not real-time. No user is waiting for a response.
- We trade compute time for quality by generating multiple independent drafts and selecting or refining the best one.
- A run that takes ten minutes but produces a strong result beats a fast run with mediocre output.

## Caching enables resilience

- Each intermediate result (JSONL fetch, daily outline, repo shard, compiled outline, content draft) is cached independently on disk.
- Partial runs resume cleanly when something breaks: re-running a stage skips work that already succeeded.
- Continue mode (`--continue`) is the default across pipeline stages.

## The depth system

A `--depth` flag (1-4) controls how many independent drafts are generated and how they are refined:

- **depth 1**: Single draft, current baseline behavior. No comparison or polish step.
- **depth 2**: Two independent drafts. A polish LLM merges the two into a final output.
- **depth 3**: Three independent drafts. The polish step picks the strongest draft as a base and borrows the best elements from the others.
- **depth 4**: Four independent drafts. A referee tournament (draft 1 vs 2, draft 3 vs 4) selects two winners. The polish LLM merges the two winners into the final output.

Higher depth costs more compute but produces stronger results. Depth 1 is the fast path for development and testing.

## Referee pattern

Adapted from the `automated_radio_disc_jockey` repo.

- Two candidate drafts are compared by a referee LLM prompt.
- The referee outputs a `<winner>` tag indicating which candidate is stronger.
- Evaluation criteria are measurable and explicit (factual accuracy, completeness, clarity) rather than subjective style preferences.
- The referee never generates new content, only selects between existing candidates.

## Anti-hallucination guardrails

- Polish prompts include a hard rule: "do not add new facts."
- The polish step may rephrase, reorganize, and tighten, but must not introduce information absent from the source drafts.
- A quality check validates the polish output against the source material.
- If the quality check fails, the pipeline falls back to the best unpolished draft rather than shipping hallucinated content.
