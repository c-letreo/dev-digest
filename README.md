# dev-digest

A CLI tool that generates a local HTML digest of AI-summarized blog posts and YouTube videos from your curated sources. Runs on demand and opens the result in your browser.

## How it works

1. Fetches recent posts from RSS feeds and YouTube channels defined in `sources.yaml`
2. Retrieves YouTube transcripts when available for richer summaries
3. Summarizes each item using Claude (Haiku) via the Anthropic API
4. Renders everything into a single self-contained HTML file and opens it

Items already seen in previous runs are skipped (tracked in `.seen_items.json`).

## Requirements

- Python 3.10+
- An **Anthropic API key** (required)
- A **Google API key** (optional — improves YouTube video discovery)

### Python dependencies

```
pip3 install anthropic pyyaml youtube-transcript-api
```

## API keys

### Anthropic API key (required)

Used to summarize blog posts and YouTube videos via Claude.

1. Sign up or log in at [console.anthropic.com](https://console.anthropic.com)
2. Go to **API Keys** and create a new key
3. Export it in your shell:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Google API key (recommended)

Used to query the YouTube Data API v3 for more reliable video discovery. Without it, the tool falls back to YouTube's public RSS feeds (which is less stable and often faces down-times).

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a project (or select an existing one)
3. Navigate to **APIs & Services → Library** and enable **YouTube Data API v3**
4. Go to **APIs & Services → Credentials** and click **Create Credentials → API key**
5. Export it in your shell:

```bash
export GOOGLE_API_KEY="AIza..."
```

## Usage

```bash
python3 digest.py
```

### Options

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to sources config (default: `sources.yaml`) |
| `--profile PATH` | Path to tech stack profile (default: `tech-stack.yml` next to config) |
| `--output FILE` | Override the output filename |
| `--force` | Re-summarize items that were already seen |
| `--no-cache` | Dry run — don't update the seen-items cache |

## Configuration

### Tech stack

Edit `tech-stack.yml` to describe your tech stack and interests. This is used to tailor summaries and decide what content is relevant:

```yaml
stack:
  - Angular
  - TypeScript
  - Tailwind

interests:
  - AI/LLM developments (models, tools, agents, APIs, research)
  - general software engineering (new tools, infra, paradigms, security)
```

A custom profile path can be passed with `--profile path/to/tech-stack.yml`.

### Sources

Edit `sources.yaml` to add or remove sources:

```yaml
blogs:
  - name: "Angular Blog"
    rss: "https://blog.angular.io/feed"
  - name: "My Blog"
    rss: "https://example.com/feed.xml"
    max_items: 2          # override per-source (optional)

youtube_channels:
  - name: "Fireship"
    channel_id: "fireship"   # YouTube handle without the @

settings:
  max_items_per_source: 3   # default items fetched per source
  max_age_days: 14          # skip items older than this
  summary_sentences: "5 to 10"
```

Channel IDs can be a YouTube handle (e.g. `fireship`) or a raw channel ID starting with `UC`.

## Output

HTML digests are written to the `output/` directory and opened automatically in your default browser. Each file is timestamped, so previous digests are preserved.