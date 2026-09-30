# Build and verification record

Completed on 2026-09-23.

- Analyzed 579,023 source records: 541,909 retail lines, 17,379 bike hours, and 19,735 energy intervals.
- Seven full-data reconciliation gates passed.
- Sixteen unit tests passed, including upload profiling and truncation, temporal leakage, units, missing-hour handling, model-name normalization, API error guidance, malformed AI reviews, and failed-rerun isolation.
- The desktop window passed a smoke test covering sample loading, background local preview and mocked five-agent response rendering.
- Dashboard was rendered and visually inspected.
- Live OpenAI API requests were not executed. Agent handoffs were tested with mocks. No API key was supplied or required for deterministic analysis.

## Actual build-time agent contributions

Two Codex subagents contributed completed project reviews during development. These are separate from the five-worker API workflow shipped in agents.py.

- Analytics evidence reviewer: researched source definitions and reviewed completed aggregate evidence. No numerical discrepancy was found between the inspected tables and report. This review did not independently reload all raw source data.
- Portfolio documentation reviewer: clarified role descriptions, reproducibility requirements, and limits on resume claims.

The coordinating agent reviewed orchestration reliability and output-state handling and added regression tests. A separately requested code-review subtask did not complete and is not counted as independent verification.

The evidence review reconciled retail net value, row partitions, bike rentals, energy totals and complete-day averages. It confirmed that repeat-purchase share is 2,845 of 4,338 identified purchasing customers. Repeat purchasing here means more than one qualifying invoice during the observed period, not a retention estimate.

## Scope qualifications

Retail retains 5,268 exact duplicate rows and excludes 2,517 adjustment/sign-mismatch rows from scoped transaction-value metrics. Their signed value is -22,124.12 GBP. Bike has 165 absent hours, not assumed zero. Energy describes one dwelling. Baseline errors are holdout results, not demonstrated business savings.

## Environment note

The bundled Python downloader encountered an expired certificate during this build. Windows Invoke-WebRequest successfully downloaded the same HTTPS archives without disabling certificate checks. If you encounter that issue, use download-windows.ps1, then run pipeline.py --download.
