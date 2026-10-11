# ConstellaLab — Day 1 Baseline

**One-sentence:** Software-only crash-test lab for autonomous satellite swarms — Day 1: runnable code baseline + portable .exe application.

## Quick Start

| Action | Command |
|---|---|
| Run Python core status | `npm run status` |
| Start dev mode (core + Vite) | `npm run dev` |
| Build frontend | `npm run build` |
| Fetch embedded Python | `npm run fetch-python` |
| Build .exe (portable) | `npm run dist:win` |

## .exe Application

**`dist-electron\win-unpacked\ConstellaLab.exe`** — 180MB portable Windows executable.

- Native desktop app (no browser, no internet required after install)
- Embedded Python 3.14.1 service (autofetched via `npm run fetch-python`)
- Double-click to launch; opens the ConstellaLab orbital test lab window

## Day 1 Features

- **Python core** — stdlib-only simulation service with HTTP API (`/api/status`, `/api/health`, `/api/config/validate`)
- **Frontend** — Vite + React + TS empty scene placeholder (rendering starts Day 3 per the 14-week plan)
- **Config validation** — rejects unknown operational fields with field-path diagnostics (per handbook rule 5)
- **Smoke tests** — 11/11 pass (`npm test`)

## Folder Structure (minimal)

```
constellab/
  package.json     npm + electron-builder config
  .gitignore       standard ignores
  vite.config.ts   Vite + React config
  pyproject.toml   Python package metadata
  core/            Python constellab_core package
  frontend/        Vite + React + TS source
  electron/        Electron main + scripts
  scripts/         dev/fetch-python/test helpers
  dist-electron/   build output → ConstellaLab.exe (gitignored)
  node_modules/    (gitignored)
```

## Development Commands

```bash
npm run test      # Python smoke tests + Vite build check
npm run dev       # Start core + Vite dev server
npm run status    # Print core status as JSON
npm run fetch-python  # Download embedded Python for .exe
npm run dist:win  # Build portable .exe application
```

## Day 1 Goal Achieved

✅ Runnable code baseline established  
✅ Portable .exe application built  
✅ No web apps — standalone desktop .exe  
✅ Minimal folder structure (no generated data blobs)  
✅ Ready for Day 3: Three.js orbital simulator