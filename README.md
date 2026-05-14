# Hospitality MCP

> A [Model Context Protocol](https://modelcontextprotocol.io) server that lets an
> LLM plan a fully customized **South Tyrol vacation** — accommodations, activities,
> gastronomy, events, weather and suggested tours — on top of the
> [Open Data Hub Tourism API](https://tourism.api.opendatahub.com).

Built by [Open Fantasy Maps](https://www.fantasymaps.org) as a real-world proving
ground for the OFM pattern: *turn a world's geospatial data into agent-queryable
tools.* South Tyrol is just another "world" — real, large, and gloriously messy
open data.

```
Traveller  →  Claude  →  Hospitality MCP server  →  Open Data Hub Tourism API
   "plan my trip"        13 planning tools          tourism.api.opendatahub.com
```

The LLM does the reasoning and synthesis; the MCP server gives it safe,
well-described, ready-to-use tools.

## What it does

The [South Tyrol Open Data Hub Tourism API](https://tourism.api.opendatahub.com)
(run by [NOI Techpark](https://noi.bz.it)) exposes **106 endpoints** and **44,000+**
points of interest — but with a filter syntax no traveller wants to learn. This
server wraps it as **13 curated planning tools** plus a raw escape hatch, so an
MCP client (Claude Desktop, Claude Code, …) can query and plan over it directly.

**Read-only by design:** only public `GET` endpoints are exposed — no credentials,
no write/booking endpoints, nothing that can charge a card.

## Quick start

```bash
cp .env.example .env          # optional — tweak language / port
docker compose up -d --build
# server live at http://localhost:8750/mcp
```

Point any MCP client at `http://<host>:8750/mcp` (streamable HTTP transport).

### Run without Docker

Requires Python 3.10+.

```bash
pip install -r requirements.txt
python server.py
```

## Connecting an MCP client

Claude Code:

```bash
claude mcp add --transport http hospitality http://localhost:8750/mcp
```

Or in an MCP client config file:

```json
{
  "mcpServers": {
    "hospitality": { "url": "http://localhost:8750/mcp" }
  }
}
```

## Tools

| Tool | Purpose |
|------|---------|
| `resolve_location` | Turn a place name (*"Val Gardena"*) into the `locfilter` token every search tool needs |
| `search_accommodations` | Lodging — hotels, B&Bs, farms, apartments, campsites, huts — with type/category/board/theme filters |
| `check_accommodation_availability` | Live room availability & pricing for given dates and room/guest specs |
| `search_activities_and_pois` | Activities, hikes, gastronomy and points of interest, with difficulty/duration/altitude filters |
| `search_events` | Events in the area, optionally within a date window |
| `search_trips` | Ready-made suggested tours / itineraries |
| `search_articles` | Editorial inspiration — travel tips, recipes, stories |
| `search_venues` | Event/meeting venues |
| `get_weather_forecast` | Municipality-level weather forecast (daily + 3-hour intervals) |
| `get_detail` | Full record for a single item by ID |
| `list_filter_options` | Discover valid type/category/topic filter values |
| `list_tags` | List ODH tags usable in `odhtagfilter` |
| `raw_api_call` | Escape hatch — any other `/v1/` GET endpoint the curated tools don't cover |

### Design notes

- **Curated, not a thin proxy.** The 13 tools encode the API's bitmask filters and
  quirks *in the tool descriptions*, so the LLM picks a tool instead of
  reverse-engineering an API. `raw_api_call` keeps 100% endpoint coverage.
- **Built for an LLM consumer.** `resolve_location` exists because the API filters
  by opaque IDs, not names — the model never has to guess an identifier. Responses
  use curated field projections + null-stripping to stay compact (lower token cost,
  less noise).

## Configuration

All optional — see `.env.example`. Set via environment or a `.env` file.

| Variable | Default | Description |
|----------|---------|-------------|
| `OFM_TOURISM_BASE_URL` | `https://tourism.api.opendatahub.com` | Tourism API base URL |
| `OFM_DEFAULT_LANGUAGE` | `en` | Default content language (`de`, `it`, `en`, `nl`, `cs`, `pl`, `fr`, `ru`) |
| `MCP_HOST` | `0.0.0.0` | Bind address |
| `MCP_PORT` | `8750` | Bind port |
| `MCP_PATH` | `/mcp` | Path the streamable-HTTP endpoint is mounted on |

For Docker, `MCP_HOST_PORT` sets the host-side published port (container stays on `8750`).

## Architecture

| Layer | Choice |
|-------|--------|
| Framework | [FastMCP](https://gofastmcp.com) (Python) |
| Transport | Streamable HTTP — hostable as a shared remote server |
| Runtime | Docker (`python:3.12-slim`) |
| API client | `httpx` async, single pooled connection |

## Presentation

`presentation/slides.md` is a [Marp](https://marp.app) deck — *"From Open Data to
Agent-Queryable Worlds"* — with the OFM theme in `presentation/ofm.css`. Render it:

```bash
cd presentation
docker run --rm -v "$PWD:/home/marp/app" marpteam/marp-cli \
  slides.md --theme-set ofm.css --pdf --html --allow-local-files
```

## Data & attribution

Tourism content is provided by the [Open Data Hub](https://opendatahub.com) /
NOI Techpark. This project only reads public endpoints; see the Open Data Hub
site for data licensing and terms.
