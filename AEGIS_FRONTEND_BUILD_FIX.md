# AEGIS Frontend Build Fix

## Root cause

Two separate issues were present:

1. The `build` script depended on shell wrapper resolution for `tsc`.
   - `npm run build` originally failed at the TypeScript stage because the local wrapper/invocation path was unreliable in this environment.
   - Direct invocation of the compiler entrypoint worked:
     - `node ./node_modules/typescript/lib/tsc.js --noEmit`

2. The remaining blocker is Vite/esbuild process spawning in the current sandboxed environment.
   - After fixing the `tsc` invocation path, `npm run build` now reaches Vite.
   - Vite then fails while loading `vite.config.ts` with:
     - `Error: spawn EPERM`
   - The failing path is `esbuild` being spawned from Node's `child_process` API.
   - This is an environment/process-permission blocker, not a dashboard business-logic or TypeScript-source blocker.

## Files changed

- [dashboard_react/frontend/package.json](/C:/Users/twone/Desktop/aegis_codex/dashboard_react/frontend/package.json)
  - changed the `build` script to use explicit local Node entrypoints:
    - `node ./node_modules/typescript/lib/tsc.js`
    - `node ./node_modules/vite/bin/vite.js build`
- [AEGIS_FRONTEND_BUILD_FIX.md](/C:/Users/twone/Desktop/aegis_codex/AEGIS_FRONTEND_BUILD_FIX.md)

No dependency versions were changed.
No dashboard business logic was changed.
No backend logic was changed.

## Commands run

From `C:\Users\twone\Desktop\aegis_codex\dashboard_react\frontend`:

1. `npm install`
2. `npm run build`
3. `node ./node_modules/typescript/lib/tsc.js --noEmit`
4. `node ./node_modules/vite/bin/vite.js build`

Additional environment checks:

- `& 'C:\Users\twone\Desktop\aegis_codex\dashboard_react\frontend\node_modules\@esbuild\win32-x64\esbuild.exe' --version`

## Build result

- `npm install`: passed
- `node ./node_modules/typescript/lib/tsc.js --noEmit`: passed
- `npm run build`: still blocked
- `node ./node_modules/vite/bin/vite.js build`: same blocker as `npm run build`

Current failing error:

```text
failed to load config from ...\dashboard_react\frontend\vite.config.ts
error during build:
Error: spawn EPERM
```

## Interpretation

- The frontend source tree type-checks with the recent dashboard stabilization patch in place.
- The stale/fallback/mock freshness work did not introduce a TypeScript compile error.
- The remaining failure occurs when Vite/esbuild tries to spawn its helper process from Node.
- Because the standalone `esbuild.exe --version` command succeeds, the repo install itself is present.
- The blocker is specifically Node-driven process spawn under the current execution environment.

## Remaining warnings

- Full `vite build` could not be completed inside this environment because of the `spawn EPERM` process-permission failure.
- `vite.config.ts` is valid enough to be discovered, but Vite cannot complete config loading because it uses esbuild under the hood.
- No frontend test harness exists in `dashboard_react/frontend/package.json`, so there is still no automated UI/unit test layer.

## Manual verification steps for localhost:3001

If the frontend dev server is already running, reuse it.
If not, run the dev server in a normal local shell outside this sandboxed build environment.

1. Open [http://localhost:3001](http://localhost:3001)
2. Open [http://localhost:3001/v2](http://localhost:3001/v2)
3. On `/`, confirm:
   - the header shows browser time separately from data status
   - metric, consensus, and system cards still show freshness/status badges
   - stale/fallback/mock data is still visibly labeled
4. On `/v2`, confirm:
   - the `Data Source Binding` banner is visible
   - macro and asset cards still show source/timestamp status badges
   - switching horizon updates the displayed timeframe context
5. Trigger a data-source failure if possible and confirm:
   - `FALLBACK DATA`, `MISSING DATA`, or `UNKNOWN DATA` labels remain visible
   - no card generates a fake fresh timestamp

## Confirmation on stale/fallback/mock labels

The dashboard stabilization changes were preserved:

- `dataFreshness.ts` remains in place
- freshness/status badges remain in place
- stale/fallback/mock labeling was not removed
- fake fresh timestamps were not reintroduced

## Precise blocker

The repo-level fix is applied for the TypeScript invocation path, but full `npm run build` is still blocked by a Vite/esbuild `spawn EPERM` failure in the current environment. The next required action is to run the build in a shell/environment where Node child-process spawning is allowed for Vite/esbuild, or to approve an unsandboxed build run if that becomes available.
