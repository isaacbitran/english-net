# English Net study page

A Next.js page with three figures: score a prompt and read every neuron, compare against a single question, and add one
English sentence as a neuron to watch verdicts flip. Plain CSS in `app/globals.css`; Newsreader and Inter are bundled in
`app/fonts/` (SIL OFL 1.1).

## Run

```sh
npm install
npm run dev            # http://localhost:3000; no key needed for the preset texts
npm run build && npm start
```

`python -m englishnet.export_web` (from the repo root) regenerates `data/network.json`, `data/network_patched.json` and
`data/replay.json` from the model files and the Jev answer cache.

## Modes

| Mode | When | What it does |
|---|---|---|
| Cached (default) | `TYPESAFE_API_KEY` is not set | Preset texts and the shipped sentence use real Jev answers saved in `data/replay.json`. Any other text is refused with HTTP 503. No network calls, 0 USD. |
| Live | `TYPESAFE_API_KEY` is set in `.env.local` | Any text is sent to Jev (about 2e-5 USD per text); you can try your own patch sentence and queue missed attacks. |
| Stand-in | `MOCK=1` | Local UI work only: keyword-based fake answers, labelled "stand-in answers, not Jev". |

Create `.env.local` from the repo's `.env` without printing the key: `grep '^TYPESAFE_API_KEY=' ../.env > .env.local`.

## Deploy on Vercel

Import the repository and set **Root Directory = `web`** (`web/vercel.json` sets the framework and build commands). Do not
add `TYPESAFE_API_KEY`: without it the deployment runs in cached mode and never calls Jev. The attack queue writes to the
local file system, so it is off on serverless hosts.

## API

- `GET /api/score` returns `{live, mock, standIn}`.
- `POST /api/score` `{"text": "...", "patched": false}` returns `{p_attack, label, threshold, logit, intercept, ms, tokens, usd, model, mock, replay, contributions[]}`.
  Same normalization and forward pass as `englishnet/forward.py`. Max 6,000 characters, 30 requests per minute per IP,
  identical texts answered from an in-memory cache. `"patched": true` scores with `data/network_patched.json`.
- `POST /api/patch` `{"question": "..."}` adds the question as a neuron with the weight rule from `englishnet/patch.py` and
  rescores the 12 demo rows: `{weight, threshold, shipped, rows: [{id, p_before, p_patch, p_after}]}`. Only the shipped
  sentence works in cached mode.
- `POST /api/break` `{"text": "...", "submit": true}` (live mode only) appends a text the network missed to
  `data/submissions.jsonl`, the queue the next adversarial round reads.
