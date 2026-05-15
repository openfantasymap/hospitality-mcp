# We Pointed the OFM Engine at South Tyrol. It Planned a Holiday.

### A 106-endpoint open tourism API, thirteen MCP tools, and one slightly unhinged thesis I'm taking to ODH Day 2026.

---

There is a sentence I have said out loud, in public, to actual humans:

> "Planning a trip to Val Gardena is structurally identical to planning a three-day trek through the Thay mountains."

You, reading this in the OFM publication, do not need me to explain what Thay is. That is the whole reason this article exists here and not somewhere else — because the punchline at the end only works if "Doskvol" and "the Sword Coast" land without footnotes.

I'm presenting the full story at **ODH Day 2026**, hosted by NOI Techpark up in Bolzano — the same people whose Open Data Hub I have been gleefully poking with an LLM for the last few weeks. Consider this article the spoiler.

---

## The detour: a 106-endpoint tourism API

NOI Techpark runs the [**South Tyrol Open Data Hub Tourism API**](https://tourism.api.opendatahub.com). It is glorious. It is enormous. It is, in the way of all sufficiently large APIs, slightly cursed.

The numbers:

- **106 endpoints**
- **44,000+ points of interest**
- Accommodations, activities, gastronomy, events, weather forecasts, suggested tours, editorial articles, venues, ski areas…
- Free, public, no API key, no booking surface (so nothing can charge your card while you debug)

And then the filter syntax. Bitmasks. Opaque region IDs. `locfilter=tvs/0F3...`. The kind of API where the docs are excellent and you still need three coffees to use them.

Now — *I* could plan a trip with this API. So could most of you. But OFM has never been about "make geospatial accessible to people who already understand geospatial." It's about:

> A traveller types *"plan 4 days near Val Gardena in June with my family"* — and gets a real itinerary.

The traveller does not want to know about bitmasks. The traveller wants Tuesday.

---

## The trick: don't make the AI smarter. Make the tools obvious.

There's a temptation, when you have a Big API and a Big Model, to just shove them at each other. *Here's 106 endpoints, here's Claude, godspeed.*

This works approximately as well as you'd guess.

The actual move is **Model Context Protocol** — the same MCP layer that already sits under the gaia_agent in OFM. You don't make the model learn an API; you write a server that exposes the API as *tools the model already knows how to call*.

So I built **[Hospitality MCP](https://github.com/openfantasymap/hospitality-mcp)**: a Python FastMCP server that turns those 106 cursed-but-glorious endpoints into **13 tools a language model can actually use**.

```
Traveller  →  Claude  →  Hospitality MCP server  →  Open Data Hub Tourism API
"plan my trip"          13 planning tools          tourism.api.opendatahub.com
```

The LLM does the reasoning. The MCP server does the *not making the LLM hallucinate API syntax*.

The toolkit, roughly:

- **`resolve_location`** — turn *"Val Gardena"* into the opaque token every search needs. The model never has to guess an ID. This is the single most important tool in the set.
- **`search_accommodations` / `search_activities_and_pois` / `search_events` / `search_trips` / `search_articles` / `search_venues`** — the offer, sliceable.
- **`get_weather_forecast`** — because June in the Dolomites is not always June in the Dolomites.
- **`check_accommodation_availability`** — live rooms and prices.
- **`get_detail` / `list_filter_options` / `list_tags`** — the connective tissue.
- **`raw_api_call`** — the escape hatch, for the rare case the curated tools don't fit. Coverage stays at 100%, because you don't take features away from your future self.

Two design decisions matter more than the rest:

**Curated, not raw.** A thin pass-through is easier to write and pushes all the burden onto the model. Curated tools encode the API's quirks — bitmask values, naming, defaults — *in the tool descriptions themselves*. The LLM picks a tool; it doesn't reverse-engineer an API. The escape hatch means we didn't trade away any coverage to get there.

**Built for an LLM consumer.** Responses use curated field projections and null-stripping by default. Smaller payloads → lower token cost → faster, sharper answers. When you need the long form, ask for it. The model is the user; design the API for it.

This is, of course, exactly the same shape as the MCP layer we run over Toril's POI database. Different schema, same architecture.

---

## Did it work?

End-to-end MCP client against the running Docker container, real network, live data:

- ✅ Resolved *Val Gardena* → region token
- ✅ **8** family-friendly hotels with half-board
- ✅ **62** gastronomy & activity POIs
- ✅ **17** events in the June window
- ✅ 3-municipality weather forecast
- ✅ **28** ski areas via the raw escape hatch
- ✅ **71** accommodation filter options discovered on demand

The model is the travel agent. The tools are its reference desk. The traveller types one sentence; everything else is the AI doing the boring part.

You can run it yourself in roughly the time it takes to make an espresso:

```bash
docker compose up -d --build
# server live at http://localhost:8750/mcp
```

Point Claude Desktop, Claude Code, or any MCP client at it. Done.

---

## So why is the fantasy-maps guy presenting at ODH Day?

Because this wasn't a side project. It was a **proving ground**.

The OFM thesis — *"turn a world's geospatial data into agent-queryable tools"* — has been on slides for a while. South Tyrol Open Data Hub is the hardest possible test case for it: not our own curated datasets, not a fictional world where we control the schema. Real open data. 106 endpoints. Opaque IDs. Bitmask filters. Multilingual content. The kind of mess no one designs on purpose — it happens because reality is messy.

If the OFM pattern survives that, it carries a fantasy realm with room to spare.

And the flow is **identical**. I mean that literally, not as a marketing line:

> *Resolve a place → search what's there → get detail → let an LLM weave it into a journey.*

Whether the place is **Val Gardena** or **the Cloak Wood**, the architecture doesn't care. A traveller asking for *"four days, family, June, easy hikes"* is a Dungeon Master asking for *"three days, party of five, late autumn, no fey crossings, end in Baldur's Gate."*

Same tools. Same model. Different world.

Doskvol, in 3D, with its canals and bridges and ghosts, is one MCP server. South Tyrol, with its 44,000 POIs and its perfectly engineered hospitality data, is another. The engine doesn't know the difference. The engine **shouldn't** know the difference. That has been the bet from the start; this is the receipt.

---

## What I'm bringing to ODH Day 2026

If you're in Bolzano for **ODH Day 2026**, come say hi. The talk is *"From Open Data to Agent-Queryable Worlds: Building a Hospitality Layer on top of Open Data Hub APIs."* Ten minutes, thirteen tools, one slightly unhinged thesis about fantasy maps and tourism APIs being the same thing.

I will:

- show the MCP server live against the actual Open Data Hub
- walk through the *"4 days near Val Gardena, family, June"* run
- explain why the curated-plus-escape-hatch design is the only sensible way to wrap a 106-endpoint API for a language model
- and then, in the last slide, take it back to Toril — because the whole point of building OFM is to discover that the fantasy part was a UX choice, not an architectural one

The code: **[`github.com/openfantasymap/hospitality-mcp`](https://github.com/openfantasymap/hospitality-mcp)**
The slides: **[`openfantasymap.github.io/hospitality-mcp`](https://openfantasymap.github.io/hospitality-mcp/)**

The data is from the [South Tyrol Open Data Hub](https://opendatahub.com) — run by [NOI Techpark](https://noi.bz.it), who deserve a quiet round of applause for shipping a tourism API this comprehensive in the first place. It's the kind of open data infrastructure that makes a project like this possible in an afternoon instead of a quarter.

For OFM, this is one more world on the shelf. It just happens to be the one you can actually book a hotel in.

See you in Bolzano.
