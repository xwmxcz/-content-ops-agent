---
name: frontend-page-pattern
description: Implement and refactor frontend pages in this content-ops-agent Vue 3 plus TypeScript plus Pinia plus Element Plus project using the existing API/store/router conventions. Use when creating new views, wiring frontend/src/api clients, updating Pinia stores, or adding routes under frontend/src/router/index.ts. Trigger for edits in frontend/src/views/**, frontend/src/api/**, frontend/src/stores/**, frontend/src/router/index.ts, and related style updates.
---

# Frontend Page Pattern

Build or modify pages by reusing existing project patterns instead of inventing new structure.

## Follow This Sequence

1. Confirm route intent and page path under `frontend/src/views/`.
2. Implement or extend API client in `frontend/src/api/`.
3. Implement or extend Pinia store in `frontend/src/stores/` when shared state is needed.
4. Build the Vue SFC page with existing Element Plus interaction style.
5. Register route in `frontend/src/router/index.ts`.
6. Run frontend build gate.

## Conventions To Reuse

- Keep axios access through `frontend/src/api/index.ts` (`api` instance and `ApiError`).
- Keep API files small and typed: export request/response interfaces and thin functions.
- Use Pinia for cross-view state; keep one store focused on one domain.
- Use route-level lazy loading in router:
  - `component: () => import('../views/YourPage.vue')`
- Preserve current TypeScript style:
  - single quotes
  - explicit exported types for API payloads

## Page Delivery Checklist

- API contract wired in `frontend/src/api/*.ts`.
- Store added/updated only if state is reused.
- Page uses loading and error states.
- Route is registered and reachable.
- `npm run build` passes.

## Fast Scaffold

Generate a starter page and optional API/store files:

```powershell
python .codex/skills/frontend-page-pattern/scripts/scaffold_page.py --name Trends --route /trends --with-api --with-store
```

Then customize generated placeholders and align payload types with backend schemas.

## Report Format

When finishing a frontend task, report:

- Files created/changed.
- Route path and route name.
- API methods added.
- Store actions added.
- Build result.