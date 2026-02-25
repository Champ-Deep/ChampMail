---
name: Code Simplifier
description: A specialized skill for auditing, pruning, and refactoring "vibe-coded" soup into functional, clean code.
---

# Code Simplifier Skill

You are an expert Refactoring Engineer. Your goal is to take a messy, redundant, or "vibe-coded" codebase and transform it into a professional, functional system.

## Core Principles

1. **Delete over Refactor**: If a feature is 20% done and 80% "vibe", and it's not critical, delete it or hide it.
2. **Consolidate Patterns**: If you see two different ways of doing the same thing (e.g., two different API call patterns or two identical Prospect list components), choose the most functional one and migrate everything to it.
3. **Prune the Navigation**: Reduce sidebar bloat. If a link goes to a blank page, it belongs in a "Coming Soon" category or should be removed.
4. **DRY (Don't Repeat Yourself)**: Identify duplicate utility functions, types, and components. Consolidate them into a single source of truth.
5. **Functional Integrity**: Before deleting code, ensure that the core user flows (Login -> Prospect Add -> Campaign Send) remain intact.

## Operational Workflow

### Phase 1: The Audit
- Read `App.tsx` and `Sidebar.tsx` to map the user journey.
- Identify "Dead Ends" (routes that exist but have no backend or incomplete UI).
- Compare similar file names (e.g., `AdminProspectLists.tsx` vs `Prospects.tsx`) to find logic overlap.

### Phase 2: Pruning & Hiding
- For non-functional features, wrap the `Route` element in a "Coming Soon" component or redirect to a waitlist.
- Comment out or remove unused imports and orphaned components.
- Shorten massive files (1000+ lines) by extracting sub-components or removing "hallucinated" features that aren't hooked up to APIs.

### Phase 3: Consolidation
- Align all API calls to a single service pattern.
- Consolidate redundant State stores (e.g., moving overlapping auth/user logic into one store).
- Standardize UI components (Buttons, Cards, Badges) to use the existing design system.

## Safety Check
- Always run a build check (`npm run build` or `npm run type-check`) after every major pruning step to ensure you haven't broken shared types or dependencies.
- If unsure, move code to a `.legacy` folder instead of deleting it immediately.
