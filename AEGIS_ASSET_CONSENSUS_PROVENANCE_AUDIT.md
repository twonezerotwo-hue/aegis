# AEGIS Asset Consensus Provenance Audit

## Exact data path

Each asset consensus response flows through the following path:
1. Gateway (`/api/consensus`) — fetches Touche/Fundamental/News scores
2. Consensus engine (`/process`) — applies Sentinel + Quantum + CBR
3. `normalizeConsensus()` in `apiV2.ts` — merges both responses
4. `ConsensusModuleSources` — per-module provenance with `verified`, `fallback_used`, `data_status`, `timestamp`

## Module source provenance fields

Each `ConsensusModuleSource` carries:
- `module`: name of the module
- `service`: which service provided the data
- `source`: data origin identifier
- `source_data`: raw data type
- `timestamp`: when the data was generated
- `data_status`: LIVE | PARTIAL_FALLBACK | FALLBACK | MOCK | MISSING | UNKNOWN
- `fallback_used`: boolean
- `verified`: true only when all conditions (live status, no fallback, asset-specific, not shared) are met
- `warnings`: list of provenance warnings

## Remaining limitations

- Quantum module always returns a neutral default (0.5) — no rich data source connected
- Fundamental data uses simulated MVRV/NUPL from mock Glassnode until API is connected
- Shared scores (News/Sentinel) are not asset-specific — same value across all assets
- CBR edge depends on trade history; with empty history, defaults to neutral
