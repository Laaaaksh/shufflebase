# Recording the README demo

`make demo` (or `scripts/record-demo/run.sh` directly) re-records
`docs/assets/demo.mp4` / `docs/assets/demo.gif` from scratch:

1. Starts a throwaway Postgres container (`shufflebase-demo-pg`, port 5540)
   and loads `examples/demo/seed.sql` (a `customers` / `orders` /
   `order_items` schema with real foreign keys) into a `proddb` database,
   plus an empty `staging` database as the mask target.
2. Installs shufflebase into `.venv` (if not already) and starts
   `shufflebase serve` on port 8642.
3. Runs `record.js` — a Playwright script that drives a real Chromium
   browser against the running app: connects to `proddb`, reviews the
   suggested masking strategies (including hand-correcting one the
   name-pattern heuristic gets wrong), runs a mask into `staging`, and
   captures real `psql` output from both databases before and after so the
   recording proves referential integrity survived the run rather than just
   asserting it.
4. Converts the raw `.webm` recording to `docs/assets/demo.mp4` (H.264,
   1280px wide) and `docs/assets/demo.gif` (960px wide, ~12fps) via
   `convert.sh`, then tears down the container and the `shufflebase serve`
   process.

Requirements: Docker, and `ffmpeg`/`ffprobe` on `PATH` (`brew install
ffmpeg`). Playwright and its Chromium binary are installed into this
directory's own `node_modules` on first run — nothing is installed globally.

Everything here is dev-only tooling for producing the README asset; it is
not part of the shufflebase package itself.

To tweak the walkthrough (pacing, which columns get corrected, etc.), edit
`record.js` directly — it's the single source of truth for what the
recording shows, so a re-run always reproduces the same real flow.
