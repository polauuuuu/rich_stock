# Stock Research Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a local interactive research dashboard with real-data ingestion, scanning, backtesting and chronological ML evaluation.

**Architecture:** FastAPI on 6001, React/TypeScript on 6002. One Docker container runs Uvicorn and Nginx with Supervisor; SQLite tracks background jobs and Parquet stores isolated demo/live datasets.

**Tech Stack:** Python, pandas, scikit-learn, FastAPI, React, Vite, Recharts, Docker.

**Spec:** ../specs/2026-11-04-stock-research-design.md (user approved by “great and go ahead”).

## Global Constraints

- Same container, backend 6001, frontend 6002, persistent /data volume.
- Secrets are backend environment variables only; no order execution.
- Demo and live data never mix. Current universe implies survivorship bias.
- Signal at close; first execution next session open. Chronological ML split purges overlapping labels.

## Review Focus

- Missing sessions must not become consecutive signals: validate expected trading sessions.
- Cancellation or restart must not produce a successful incomplete dataset: atomic per-symbol writes and durable job state.
- Cost and capital allocation must remain consistent on gaps and overlapping positions.
- Models must not fit preprocessing on validation/test dates or rank historical signals with future-trained models.
- Live authentication/network failure must remain visible and never trigger demo fallback.

## Task 1: Research engine

Files: backend/research.py, backend/demo.py, tests/test_research.py, requirements.txt.
Interfaces: features(frame, down_days, volume_days) returns per-symbol causal features and signals; backtest(frame, config, scores=None) returns equity, trades, metrics; train_model(frame, config) returns chronological metrics and test-only scores.
- [x] Write and run failing tests for four-close/three-volume semantics, missing sessions, next-open entries, gap stops, same-bar dual touches, capital constraints and purged splits.
- [x] Implement research functions, deterministic synthetic OHLCV and honest sample-size validation.
- [x] Run pytest tests/test_research.py and commit engine.

## Task 2: Data and API

Files: backend/store.py, backend/providers.py, backend/jobs.py, backend/main.py, tests/test_api.py, tests/test_providers.py.
Interfaces: /api/status, /api/scan, /api/bars/{symbol}, /api/jobs, /api/jobs/{id}, /api/jobs/{id}/cancel, /api/results/{id}, /api/export.
- [x] Write and run failing tests for pagination, filtering, no-key rejection, durable job interruption and scan contracts.
- [x] Implement Nasdaq universe snapshots, SIP daily batches with retries/limits, NYSE calendar filtering, atomic Parquet merge, SQLite jobs and single-worker cancellable execution.
- [x] Run full pytest suite and commit API.

## Task 3: Interactive frontend

Files: frontend/package.json, frontend/src/App.tsx, frontend/src/styles.css, frontend/src/main.tsx, frontend/index.html, frontend/vite.config.ts.
- [x] Build responsive Traditional Chinese dashboard: scan filters, sorting/search/pagination/export, selectable price/volume chart and date brush, backtest settings/curves/trades, ML experiments, data downloads/jobs.
- [x] Display source, coverage, bias limitations, loading, cancellation and actionable errors. Never invent model performance.
- [x] Run TypeScript and production build; verify live demo API/UI interactions and commit.

## Task 4: Packaging and verification

Files: Dockerfile, compose.yaml, deploy/nginx.conf, deploy/supervisord.conf, .env.example, .dockerignore, README.md.
- [x] Add non-root container runtime, two processes, healthcheck, local-only published ports and named volume.
- [x] Test API routes, full demo backtest/training, frontend build, compose configuration and Docker build/start if available.
- [x] Review full diff independently, fix material findings with regression tests, record verification limits and commit.

## Execution record

- Baseline: empty application, Git baseline 741267f. Docker CLI available but daemon initially stopped.
- Ruling: execute directly in user-selected checkout, using a feature branch rather than creating another worktree; preserves their Codex workspace and baseline without moving files. Cost: no second checkout isolation.
- Ruling: user already explicitly authorized implementation; proceed with native execution without another plan approval cycle. Cost: implementation choices remain reviewable in this plan and Git history.

- Task 1: complete — b3f848e; research tests passed.
- Task 2: complete — 817ae01; 18-test suite includes review regressions.
- Task 3: complete — React production build and two result-loading tests passed; browser interactions checked.
- Task 4: complete — Docker build/start healthy, both ML models completed via HTTP, restart persisted results. See docs/verification.md for evidence and limits.
- Final review: four material findings fixed with reproductions and green regression tests; no material finding deferred.
