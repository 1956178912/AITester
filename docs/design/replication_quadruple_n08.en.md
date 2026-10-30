# Replication Environment Quadruple (N08, frozen 2026-10-30)

Every new batch's replication claim must pin the quadruple — any missing component is
fail-closed, and batches across quadruples must not be pooled:

- **seed**: explicit value (e.g. `--seed 42`); never reaches the LLM API — the same seed
  guarantees only task sampling and execution order;
- **model**: alias + `system_fingerprint` (response header), both recorded; an alias
  resolving to a different snapshot is a different model (S29 drift clause);
- **temperature**: `TEMPERATURE=0.0` mandatory for measurement batches; exploration
  batches exempt but disclosed;
- **dataset version**: name + subset + task count + content fingerprint (sha256 over the
  sorted task set — dataset files regenerate on download, paths/line numbers unreliable).

Server-side snapshot drift follows the E8/B2 disclosure caliber (readings carry a
snapshot label). Registration side is carried by batch provenance in
`docs/reports/data/experiment_register.json`; automated gating to be wired later.
