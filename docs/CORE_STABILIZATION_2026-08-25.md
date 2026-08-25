# VCMS Core Stabilization — 25/08/2026

## Completed

- Backend infrastructure separated into settings, database transport, authentication, storage signing, roles and error handling modules.
- Global frontend source separated into nine focused modules and built into one production bundle to preserve fast mobile loading.
- Shared UI utilities added for loading buttons, accessible status toasts, consistent API errors and JSON requests.
- Retired worker-card, certificate and training-matrix pages and APIs removed.
- Disabled notification, Web Push and reminder code, dependency and workflow removed.
- Service-worker cache advanced and now caches the new core bundle and shared UI module.
- Playwright regression suite added for mobile Safari and desktop Chromium.
- CI now checks the generated frontend bundle and runs browser regression tests.

## Verification

- 73 applicable automated backend/contract tests pass.
- The intentionally deferred Scheduling/Progress contract remains excluded until Scheduling is released.
- Python modules compile successfully.
- Frontend asset-reference scan reports no missing local scripts.
- Local browser smoke check: login rendered without horizontal overflow or console errors.

## Rollback

- Backend module extraction checkpoint: `08258aa`.
- The stabilization changes following that checkpoint should be released as one commit after CI passes.
