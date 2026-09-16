# Mandatory Agent Guidelines: Modular Logging Protocol

This repository adheres to a strict, modular change-tracking and logging standard.
All AI agents (Antigravity, Gemini, Claude, etc.) and automated tools working on this codebase **MUST** comply with these instructions.

---

## 1. Mandatory Logging Rules

Any task that modifies code, configuration, database schemas, documentation, or assets **MUST** record its actions in the `logs/` directory:

1. **`logs/ACTIVITY_LOG.md` (Session Log)**:
   - Append a new entry at the top of the activity log at the conclusion of every work session or task execution.
   - Include: timestamp, agent/role, session goal, specific actions taken, files created/modified, and verification results.
2. **`logs/DECISION_LOG.md` (Decision Records - ADR)**:
   - If the session introduces, changes, or deprecates an architectural pattern, library dependency, database model, API contract, or significant project strategy, document it as a new `[DEC-xxx]` entry.
   - Include: date, status, context, decision made, rationale/alternatives considered, and affected components.
3. **`logs/CHANGELOG.md` (Version & Release History)**:
   - For user-facing feature additions, bug fixes, breaking changes, or version bumps, update the changelog following the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) standard.
4. **Git Inclusion**:
   - Always stage and commit all updated files in `logs/` alongside the primary changes in the same atomic commit.

---

## 2. Engineering & Operational Invariants

- **Understand Before Touching**: Trace real call paths and read relevant docs before proposing edits.
- **Root Cause over Symptom**: Fix shared utilities and underlying root causes rather than patching one-off symptoms.
- **Verify Every Change**: Every non-trivial change must leave behind a runnable verification check (test suite, verification script, or assertion check).
- **Preserve Documentation Integrity**: Do not delete unrelated comments, docstrings, or architectural notes without explicit instructions.\n