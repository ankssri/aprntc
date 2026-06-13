# aprntc — dashboard (React + Vite + Tailwind)

Modern web console for the apprentice loop: promotion review, lineage, trajectory
explorer, and the experience-memory (lessons) browser. Light/dark theme toggle.

## Prerequisites
- **Node 18+** (not installed on the build machine — `brew install node`)
- The backend API running (see below).

## Run (two terminals)

**1. Backend** (FastAPI, from the repo root):
```bash
pip install -e '.[web]'
uvicorn aprntc.web.app:app --reload          # serves http://127.0.0.1:8000
```
Generate data first if needed: `python scripts/demo_promotion.py` (writes
`review_bundle.json` + `lineage_demo.json` for the review/lineage screens).

**2. Frontend** (this folder):
```bash
cd web
npm install
npm run dev                                  # http://localhost:5173
```
The Vite dev server proxies `/api` → the FastAPI backend, so no CORS/setup needed.

## Build for production
```bash
npm run build       # → web/dist (static; serve behind the API or any static host)
```

## Layout
```
src/
  main.tsx, App.tsx        app shell + sidebar nav + routing
  lib/      api.ts (typed client), theme.tsx (light/dark), hooks.ts
  components/ ui.tsx (Card/Metric/Badge/Button…), icons.tsx
  screens/  Review, Lineage, Trajectories, Lessons
```

## Design
Theme tokens live in `src/index.css` (`:root` light, `.dark` dark) and are wired
into Tailwind via `tailwind.config.js`. Both modes work from one set of class
names; the toggle persists to `localStorage`.
