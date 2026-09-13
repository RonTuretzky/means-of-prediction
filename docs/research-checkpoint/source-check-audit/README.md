# Archived source-check audit code

Exact source copies from the completed private September 13 source-check audit.
`source-manifest.json` records their original SHA-256 values. These are source
archives, not new experiment entry points. They require the original private
run directory and pinned local dependencies; do not execute them here, where
relative output paths would be wrong. No emails, raw responses or credentials
are included.

`audit.py` independently reconstructs all paired decisions, execution failures,
token/runtime checks and baseline replay agreement. `paired_review.py` records
post-hoc semantic review of discordances; it is not a blinded evaluation.
See ../../QWEN-SOURCE-CHECK-V1.md for the public findings and artifact hashes.
