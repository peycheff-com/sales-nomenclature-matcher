# Sales Nomenclature Matcher Frontend

This is the React Single Page Application (SPA) for the Sales Nomenclature Matcher tool.

## Tech Stack

- **Framework:** React 19 + TypeScript 5.9
- **Build Tool:** Vite 8
- **Styling:** Tailwind CSS 4 + shadcn/ui components
- **Routing:** TanStack Router
- **Data Fetching:** TanStack Query + `ky`
- **Tables:** TanStack Table v8

## Project Structure

- `src/api/` — Typed API clients mapping to the backend endpoints (Auth, Match, Review, Suppliers, Users, Catalog, Metrics)
- `src/components/` — Reusable UI components (shadcn/ui, layout, tables, forms)
- `src/pages/` — Main application views (Dashboard, Match Requests, Result Review, Catalog, Settings, Suppliers, Users)
- `src/lib/` — Utilities, auth store, theme context
- `src/router.tsx` — TanStack Router configuration and route definitions

## Development

```bash
npm ci                     # Install dependencies cleanly
npm run dev                # Start dev server on :5173 (proxies /api to backend)
npm run lint               # Run ESLint
npm run build              # Type-check and build production bundle
npx tsc --noEmit           # Type checking only
```

Ensure the backend API is running on `http://localhost:8000` to properly proxy requests during development.

