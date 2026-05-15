"""OFM Hospitality MCP server.

Wraps an Open Data Hub Tourism API instance (South Tyrol by default; the
upstream base URL and human-readable region name are configurable via the
OFM_TOURISM_BASE_URL and OFM_REGION_NAME environment variables) as a set of
MCP tools an LLM can use to assemble a fully customized vacation plan for the
managed area: accommodations, activities, gastronomy, points of interest,
events, suggested tours, editorial inspiration, venues and weather forecasts.

Design: a curated set of planning-oriented tools plus a `raw_api_call` escape
hatch for any endpoint/filter not covered by the curated set.

Run (streamable HTTP):
    pip install -r requirements.txt
    python server.py
The endpoint is served at  http://MCP_HOST:MCP_PORT/MCP_PATH  (see .env.example).

Only public GET endpoints are used; no API credentials are required. Write
endpoints (POST/PUT/DELETE) are intentionally not exposed.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP

BASE_URL = os.environ.get(
    "OFM_TOURISM_BASE_URL", "https://tourism.api.opendatahub.com"
).rstrip("/")
DEFAULT_LANGUAGE = os.environ.get("OFM_DEFAULT_LANGUAGE", "en")
REGION_NAME = os.environ.get("OFM_REGION_NAME", "South Tyrol")

mcp = FastMCP(
    "ofm-hospitality",
    instructions=(
        f"Tools for planning a vacation in {REGION_NAME} using the Open Data "
        "Hub Tourism API. Typical flow: (1) call resolve_location to turn a "
        "place name into a locfilter token, (2) search accommodations / "
        "activities / events / trips constrained to that location and the "
        "travel dates, (3) call get_weather_forecast for the area, (4) call "
        "get_detail for full information on any item the traveller is "
        "interested in. Use list_filter_options to discover valid bitmask/type "
        "filter values. Use raw_api_call only for endpoints the curated tools "
        "do not cover."
    ),
)

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(30.0),
            headers={"Accept": "application/json"},
        )
    return _client


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    """Drop None values and normalize bools/lists for the query string."""
    out: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            if value:
                out[key] = ",".join(str(v) for v in value)
        else:
            out[key] = value
    return out


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    resp = await _http().get(path, params=_clean(params or {}))
    resp.raise_for_status()
    if not resp.content:
        return None
    return resp.json()


def _fields(default: str, override: str | None, lang: str) -> str | None:
    """Resolve a field projection. `override=""` means 'return all fields'."""
    if override == "":
        return None
    chosen = override if override else default
    return chosen.replace("{lang}", lang)


# --- curated default field projections (keep responses compact) -------------
F_ACCOMMODATION = (
    "Id,Shortname,AccoTypeId,AccoCategoryId,AccoDetail.{lang},LocationInfo,"
    "Latitude,Longitude,Altitude,HasRoom,HasApartment,TagIds,Source"
)
F_POI = (
    "Id,Shortname,Detail.{lang},LocationInfo,ContactInfos.{lang},GpsInfo,"
    "Highlight,DistanceInfo,Difficulty,Latitude,Longitude,Source"
)
F_EVENT = (
    "Id,Shortname,Detail.{lang},DateBegin,DateEnd,EventDate,LocationInfo,"
    "ContactInfos.{lang},Latitude,Longitude"
)
F_TRIP = "Id,Shortname,Agency,Route,Geo,StopTimes"
F_ARTICLE = "Id,Shortname,Detail.{lang},ArticleType,ContactInfos.{lang}"
F_VENUE = "Id,Shortname,Detail.{lang},LocationInfo,GpsInfo,RoomDetails"


# ---------------------------------------------------------------------------
# Location resolution
# ---------------------------------------------------------------------------
@mcp.tool
async def resolve_location(
    query: str,
    types: str = "reg,tvs,mun,mta,fra",
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Turn a place name into the `locfilter` token used by every search tool.

    The Tourism API filters by area using opaque IDs, not names. Call this
    first to map a human place name (e.g. "Val Gardena", "Bolzano") to one or
    more `locfilter_token` values, then pass those tokens as the `locfilter`
    argument of search_accommodations / search_activities_and_pois /
    search_events / etc.

    Args:
        query: Substring to match against location names (case-insensitive).
        types: Comma-separated location levels to include. mta=metaregion,
            reg=region, tvs=tourism association, mun=municipality,
            fra=fraction/hamlet.
        language: Content language (default: server default, usually "en").

    Returns:
        A list of {name, type, id, locfilter_token} dicts, best matches first.
    """
    lang = language or DEFAULT_LANGUAGE
    data = await _get(
        "/v1/Location", {"language": lang, "type": types, "showall": True}
    )
    needle = query.strip().lower()
    matches = [
        loc
        for loc in (data or [])
        if needle in str(loc.get("name", "")).lower()
    ]
    matches.sort(key=lambda loc: (str(loc.get("name", "")).lower() != needle,
                                  len(str(loc.get("name", "")))))
    return [
        {
            "name": loc.get("name"),
            "type": loc.get("typ"),
            "id": loc.get("id"),
            "locfilter_token": f"{loc.get('typ')}{loc.get('id')}",
        }
        for loc in matches[:25]
    ]


# ---------------------------------------------------------------------------
# Accommodations
# ---------------------------------------------------------------------------
@mcp.tool
async def search_accommodations(
    locfilter: str | None = None,
    searchfilter: str | None = None,
    typefilter: str | None = None,
    categoryfilter: str | None = None,
    boardfilter: str | None = None,
    themefilter: str | None = None,
    featurefilter: str | None = None,
    badgefilter: str | None = None,
    altitudefilter: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius: int | None = None,
    odhtagfilter: str | None = None,
    bookable_only: bool | None = None,
    pagenumber: int = 1,
    pagesize: int = 10,
    language: str | None = None,
    fields: str | None = None,
) -> Any:
    """Search lodging (hotels, B&Bs, farms, apartments, campsites, huts).

    All *filter args are BITMASK strings unless noted; sum the values you want.
        typefilter:     1=HotelPension 2=BedBreakfast 4=Farm 8=Camping
                        16=Youth 32=Mountain 64=Apartment 128=NotDefined
        categoryfilter: stars/flowers/suns, e.g. 32768=5stars, 2048=4stars,
                        128=3stars (call list_filter_options('accommodation_types')
                        for the full table).
        boardfilter:    1=without board 2=breakfast 4=half board 8=full board
                        16=all inclusive
        themefilter:    1=Gourmet 2=At altitude 16=With family 32=Hiking
                        64=In the vineyards 256=At the ski resort 2048=Alpine
                        4096=Small and charming 8192=Huts and mountain inns ...
        featurefilter:  1=Group-friendly 4=Swimming pool ... (see list_filter_options)
        badgefilter:    1=Belvita Wellness 2=Familyhotel ...

    Args:
        locfilter: locfilter token(s) from resolve_location, comma-separated.
        searchfilter: free-text match on the title in all languages.
        altitudefilter: "min,max" metres, e.g. "800,1500".
        latitude/longitude/radius: geo search around a point (radius in metres).
        bookable_only: if true, only accommodations bookable online.
        fields: comma-separated field projection; pass "" to return all fields.

    Returns the paginated API response ({TotalResults, Items, ...}).
    """
    lang = language or DEFAULT_LANGUAGE
    return await _get(
        "/v1/Accommodation",
        {
            "locfilter": locfilter,
            "searchfilter": searchfilter,
            "typefilter": typefilter,
            "categoryfilter": categoryfilter,
            "boardfilter": boardfilter,
            "themefilter": themefilter,
            "featurefilter": featurefilter,
            "badgefilter": badgefilter,
            "altitudefilter": altitudefilter,
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius,
            "odhtagfilter": odhtagfilter,
            "bookablefilter": bookable_only,
            "pagenumber": pagenumber,
            "pagesize": pagesize,
            "language": lang,
            "fields": _fields(F_ACCOMMODATION, fields, lang),
            "removenullvalues": True,
        },
    )


@mcp.tool
async def check_accommodation_availability(
    arrival: str,
    departure: str,
    roominfo: str,
    accommodation_ids: str | None = None,
    locfilter: str | None = None,
    boardfilter: str | None = None,
    bokfilter: str = "hgv",
    detail: bool = False,
    language: str | None = None,
) -> Any:
    """Check live room availability and prices for given dates.

    Args:
        arrival: check-in date, "yyyy-MM-dd".
        departure: check-out date, "yyyy-MM-dd".
        roominfo: room/guest spec. Rooms separated by "|", guest ages within a
            room by ",". Example "0|30,30" = one room for two adults (age 30);
            "0|30,30|0|8" = a second room for one child age 8. Age 0 also works
            as a generic adult.
        accommodation_ids: comma-separated Accommodation IDs to check. Provide
            either this or `locfilter` to bound the search.
        locfilter: locfilter token(s) from resolve_location (alternative to ids).
        boardfilter: board bitmask (see search_accommodations).
        bokfilter: booking channel(s). "hgv"=Booking Südtirol, "lts"=LTS,
            "htl"=hotel.it; comma-separate to combine.
        detail: include full offer/price details when true.

    Returns accommodations annotated with availability/offer information.
    """
    lang = language or DEFAULT_LANGUAGE
    return await _get(
        "/v1/Accommodation",
        {
            "availabilitycheck": True,
            "arrival": arrival,
            "departure": departure,
            "roominfo": roominfo,
            "idfilter": accommodation_ids,
            "locfilter": locfilter,
            "boardfilter": boardfilter,
            "bokfilter": bokfilter,
            "detail": "1" if detail else "0",
            "availabilitychecklanguage": lang,
            "language": lang,
            "fields": _fields(F_ACCOMMODATION, None, lang),
            "removenullvalues": True,
        },
    )


# ---------------------------------------------------------------------------
# Activities, gastronomy & points of interest
# ---------------------------------------------------------------------------
@mcp.tool
async def search_activities_and_pois(
    type: str | None = None,
    locfilter: str | None = None,
    searchfilter: str | None = None,
    odhtagfilter: str | None = None,
    difficultyfilter: str | None = None,
    durationfilter: str | None = None,
    altitudefilter: str | None = None,
    distancefilter: str | None = None,
    highlights_only: bool | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius: int | None = None,
    pagenumber: int = 1,
    pagesize: int = 10,
    language: str | None = None,
    fields: str | None = None,
) -> Any:
    """Search activities, hikes, gastronomy and points of interest.

    `type` is a BITMASK (sum to combine, default = all):
        1=Wellness 2=Winter 4=Summer 8=Culture 16=Other
        32=Gastronomy (restaurants, huts, bars) 64=Mobility 128=Shops & services

    Args:
        type: type bitmask above. Use 32 for restaurants/gastronomy.
        locfilter: locfilter token(s) from resolve_location.
        searchfilter: free-text title search.
        difficultyfilter: "1"=easy "2"=medium "3"=difficult.
        durationfilter: "min,max" hours, e.g. "1,3".
        altitudefilter: "min,max" metres.
        distancefilter: "min,max" kilometres (route length).
        highlights_only: if true, only items flagged as highlights.
        latitude/longitude/radius: geo search around a point (radius in metres).
        fields: field projection; pass "" for all fields.

    Returns the paginated API response.
    """
    lang = language or DEFAULT_LANGUAGE
    return await _get(
        "/v1/ODHActivityPoi",
        {
            "type": type,
            "locfilter": locfilter,
            "searchfilter": searchfilter,
            "odhtagfilter": odhtagfilter,
            "difficultyfilter": difficultyfilter,
            "durationfilter": durationfilter,
            "altitudefilter": altitudefilter,
            "distancefilter": distancefilter,
            "highlight": highlights_only,
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius,
            "pagenumber": pagenumber,
            "pagesize": pagesize,
            "language": lang,
            "langfilter": lang,
            "fields": _fields(F_POI, fields, lang),
            "removenullvalues": True,
        },
    )


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@mcp.tool
async def search_events(
    begindate: str | None = None,
    enddate: str | None = None,
    locfilter: str | None = None,
    searchfilter: str | None = None,
    topicfilter: str | None = None,
    odhtagfilter: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius: int | None = None,
    sort: str = "asc",
    pagenumber: int = 1,
    pagesize: int = 10,
    language: str | None = None,
    fields: str | None = None,
) -> Any:
    """Search events happening in the area, optionally within a date window.

    Args:
        begindate: only events ending on/after this date, "yyyy-MM-dd".
            Set this to the traveller's arrival date.
        enddate: only events beginning on/before this date, "yyyy-MM-dd".
            Set this to the traveller's departure date.
        locfilter: locfilter token(s) from resolve_location.
        searchfilter: free-text title search.
        topicfilter: topic ID bitmask; call list_filter_options('event_topics').
        sort: "asc" or "desc" by next begin date.
        latitude/longitude/radius: geo search around a point (radius in metres).
        fields: field projection; pass "" for all fields.

    Returns the paginated API response.
    """
    lang = language or DEFAULT_LANGUAGE
    return await _get(
        "/v1/Event",
        {
            "begindate": begindate,
            "enddate": enddate,
            "locfilter": locfilter,
            "searchfilter": searchfilter,
            "topicfilter": topicfilter,
            "odhtagfilter": odhtagfilter,
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius,
            "sort": sort,
            "pagenumber": pagenumber,
            "pagesize": pagesize,
            "language": lang,
            "langfilter": lang,
            "fields": _fields(F_EVENT, fields, lang),
            "removenullvalues": True,
        },
    )


# ---------------------------------------------------------------------------
# Suggested tours / trips
# ---------------------------------------------------------------------------
@mcp.tool
async def search_trips(
    searchfilter: str | None = None,
    begin: str | None = None,
    end: str | None = None,
    tagfilter: str | None = None,
    pagenumber: int = 1,
    pagesize: int = 10,
    language: str | None = None,
    fields: str | None = None,
) -> Any:
    """Search ready-made suggested tours / itineraries ("Trips").

    Args:
        searchfilter: free-text title search.
        begin: RFC3339 timestamp; only trips intersecting on/after this.
        end: RFC3339 timestamp; only trips intersecting on/before this.
        tagfilter: tag expression, e.g. "or(tagid1,tagid2)".
        fields: field projection; pass "" for all fields.

    Returns the paginated API response.
    """
    lang = language or DEFAULT_LANGUAGE
    return await _get(
        "/v1/Trip",
        {
            "searchfilter": searchfilter,
            "begin": begin,
            "end": end,
            "tagfilter": tagfilter,
            "pagenumber": pagenumber,
            "pagesize": pagesize,
            "language": lang,
            "langfilter": lang,
            "fields": _fields(F_TRIP, fields, lang),
            "removenullvalues": True,
        },
    )


# ---------------------------------------------------------------------------
# Editorial inspiration
# ---------------------------------------------------------------------------
@mcp.tool
async def search_articles(
    searchfilter: str | None = None,
    articletype: str | None = None,
    odhtagfilter: str | None = None,
    pagenumber: int = 1,
    pagesize: int = 10,
    language: str | None = None,
    fields: str | None = None,
) -> Any:
    """Search editorial articles: travel tips, recipes, stories, inspiration.

    Args:
        searchfilter: free-text title search.
        articletype: type bitmask, e.g. 4=contentarticle 32=recipe
            8=eventarticle 64=touroperator (default = all).
        fields: field projection; pass "" for all fields.

    Returns the paginated API response.
    """
    lang = language or DEFAULT_LANGUAGE
    return await _get(
        "/v1/Article",
        {
            "searchfilter": searchfilter,
            "articletype": articletype,
            "odhtagfilter": odhtagfilter,
            "pagenumber": pagenumber,
            "pagesize": pagesize,
            "language": lang,
            "langfilter": lang,
            "fields": _fields(F_ARTICLE, fields, lang),
            "removenullvalues": True,
        },
    )


# ---------------------------------------------------------------------------
# Venues
# ---------------------------------------------------------------------------
@mcp.tool
async def search_venues(
    locfilter: str | None = None,
    searchfilter: str | None = None,
    categoryfilter: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius: int | None = None,
    pagenumber: int = 1,
    pagesize: int = 10,
    language: str | None = None,
    fields: str | None = None,
) -> Any:
    """Search venues (event/meeting locations, halls, conference spaces).

    Args:
        locfilter: locfilter token(s) from resolve_location.
        searchfilter: free-text title search.
        categoryfilter: venue category bitmask (see list_filter_options).
        latitude/longitude/radius: geo search around a point (radius in metres).
        fields: field projection; pass "" for all fields.

    Returns the paginated API response.
    """
    lang = language or DEFAULT_LANGUAGE
    return await _get(
        "/v1/Venue",
        {
            "locfilter": locfilter,
            "searchfilter": searchfilter,
            "categoryfilter": categoryfilter,
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius,
            "pagenumber": pagenumber,
            "pagesize": pagesize,
            "language": lang,
            "langfilter": lang,
            "fields": _fields(F_VENUE, fields, lang),
            "removenullvalues": True,
        },
    )


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------
@mcp.tool
async def get_weather_forecast(
    locfilter: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius: int | None = None,
    language: str | None = None,
) -> Any:
    """Get the municipality-level weather forecast for an area.

    Args:
        locfilter: a REGION token only — i.e. a resolve_location result whose
            type is "reg" (e.g. "regD2633A1E..."). Tourism-association ("tvs")
            or municipality ("mun") tokens are NOT supported here and return an
            empty list; pass a "reg" token or use a geo query instead.
        latitude/longitude/radius: geo search around a point (radius in metres).

    With no arguments, returns the forecast for all municipalities. Returns
    daily and 3-hour-interval forecast data.
    """
    lang = language or DEFAULT_LANGUAGE
    return await _get(
        "/v1/Weather/Forecast",
        {
            "locfilter": locfilter,
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius,
            "language": lang,
        },
    )


# ---------------------------------------------------------------------------
# Detail lookup
# ---------------------------------------------------------------------------
_DETAIL_ENDPOINTS = {
    "accommodation": "/v1/Accommodation",
    "activitypoi": "/v1/ODHActivityPoi",
    "poi": "/v1/ODHActivityPoi",
    "event": "/v1/Event",
    "trip": "/v1/Trip",
    "article": "/v1/Article",
    "venue": "/v1/Venue",
    "region": "/v1/Region",
    "municipality": "/v1/Municipality",
    "district": "/v1/District",
    "skiarea": "/v1/SkiArea",
}


@mcp.tool
async def get_detail(
    entity_type: str,
    id: str,
    language: str | None = None,
    fields: str = "",
) -> Any:
    """Fetch the full record for a single item by its ID.

    Args:
        entity_type: one of accommodation, activitypoi (alias: poi), event,
            trip, article, venue, region, municipality, district, skiarea.
        id: the item's ID, as returned by a search tool.
        language: content language.
        fields: field projection; default "" returns the complete record.

    Returns the full entity record.
    """
    key = entity_type.strip().lower()
    if key not in _DETAIL_ENDPOINTS:
        raise ValueError(
            f"Unknown entity_type '{entity_type}'. "
            f"Valid: {', '.join(sorted(_DETAIL_ENDPOINTS))}"
        )
    lang = language or DEFAULT_LANGUAGE
    return await _get(
        f"{_DETAIL_ENDPOINTS[key]}/{id}",
        {
            "language": lang,
            "fields": fields or None,
            "removenullvalues": True,
        },
    )


# ---------------------------------------------------------------------------
# Filter-option discovery
# ---------------------------------------------------------------------------
_FILTER_OPTION_ENDPOINTS = {
    "accommodation_types": "/v1/AccommodationTypes",
    "accommodation_features": "/v1/AccommodationFeatures",
    "activitypoi_types": "/v1/ODHActivityPoiTypes",
    "event_topics": "/v1/EventTopics",
    "eventshort_types": "/v1/EventShortTypes",
    "article_types": "/v1/ArticleTypes",
    "venue_types": "/v1/VenueTypes",
}


@mcp.tool
async def list_filter_options(kind: str, language: str | None = None) -> Any:
    """List valid values for the type/category/topic filters used by searches.

    Args:
        kind: one of accommodation_types, accommodation_features,
            activitypoi_types, event_topics, eventshort_types, article_types,
            venue_types.
        language: content language.

    Returns the list of available filter options with their IDs/bitmask values.
    """
    key = kind.strip().lower()
    if key not in _FILTER_OPTION_ENDPOINTS:
        raise ValueError(
            f"Unknown kind '{kind}'. "
            f"Valid: {', '.join(sorted(_FILTER_OPTION_ENDPOINTS))}"
        )
    return await _get(
        _FILTER_OPTION_ENDPOINTS[key],
        {"language": language or DEFAULT_LANGUAGE, "removenullvalues": True},
    )


@mcp.tool
async def list_tags(
    validforentity: str | None = None,
    searchfilter: str | None = None,
    language: str | None = None,
    pagesize: int = 50,
) -> Any:
    """List ODH tags usable in the `odhtagfilter` argument of search tools.

    Args:
        validforentity: restrict to tags valid for an entity type, e.g.
            "accommodation", "odhactivitypoi", "event".
        searchfilter: free-text match on the tag name.
        pagesize: max tags to return.

    Returns the list of tags.
    """
    return await _get(
        "/v1/ODHTag",
        {
            "validforentity": validforentity,
            "searchfilter": searchfilter,
            "language": language or DEFAULT_LANGUAGE,
            "pagesize": pagesize,
            "removenullvalues": True,
        },
    )


# ---------------------------------------------------------------------------
# Raw escape hatch
# ---------------------------------------------------------------------------
@mcp.tool
async def raw_api_call(path: str, params: dict[str, Any] | None = None) -> Any:
    """Call any Open Data Hub Tourism API GET endpoint not covered above.

    Use this only when the curated tools cannot express the query. See the
    full API at https://tourism.api.opendatahub.com/swagger/v1/swagger.json

    Args:
        path: API path beginning with "/v1/", e.g. "/v1/SkiArea" or
            "/v1/Weather/Realtime". Only GET endpoints are allowed.
        params: query parameters as a dict. Booleans and lists are normalized
            automatically; None values are dropped.

    Returns the raw JSON response.
    """
    if not path.startswith("/v1/"):
        raise ValueError("path must start with '/v1/'")
    return await _get(path, params or {})


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host=os.environ.get("MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("MCP_PORT", "8750")),
        path=os.environ.get("MCP_PATH", "/mcp"),
    )
