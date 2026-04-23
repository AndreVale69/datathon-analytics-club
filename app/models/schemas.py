from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

# ── Typed enumerations matching exact DB column values ───────────────────────

OfferType = Literal["RENT", "SALE"]

# Exact German strings stored in the object_category column.
# Sorted by frequency (from DB inspection).
ObjectCategory = Literal[
    # Apartments (Wohnungen)
    "Wohnung",            # 6146 — standard apartment
    "Möblierte Wohnung",  # 336  — furnished apartment
    "Dachwohnung",        # 156  — attic apartment
    "Maisonette",         # 112  — maisonette
    "Studio",             # 68   — studio
    "Attika",             # 57   — penthouse/attika
    "WG-Zimmer",          # 48   — flatshare room
    "Loft",               # 40   — loft
    "Einzelzimmer",       # 146  — single room
    "Terrassenwohnung",   # 3    — terrace apartment
    "Ferienwohnung",      # 2    — holiday apartment
    "Ferienimmobilie",    # 1    — holiday property
    # Houses (Häuser)
    "Haus",               # 268  — house (generic)
    "Villa",              # 26   — villa
    "Doppeleinfamilienhaus", # 19 — semi-detached
    "Reihenhaus",         # 8    — terraced house
    "Mehrfamilienhaus",   # 4    — multi-family house
    "Bauernhaus",         # 4    — farmhouse
    "Terrassenhaus",      # 1    — terrace house
    # Commercial / other
    "Gewerbeobjekt",      # 1913 — commercial property
    "Parkplatz, Garage",  # 402  — parking + garage
    "Parkplatz",          # 371  — parking spot
    "Tiefgarage",         # 313  — underground garage
    "Bastelraum",         # 202  — storage/hobby room
    "Einzelgarage",       # 80   — single garage
    "Diverses",           # 24   — miscellaneous
    "Wohnnebenraeume",    # 3    — ancillary rooms
    "Grundstück",         # 1    — plot/land
    "Gastgewerbe",        # 1    — gastronomy
]

# Exact keys from FEATURE_COLUMN_MAP in app/core/hard_filters.py.
# `temporary` excluded: 0 listings have it set to 1.
FeatureName = Literal[
    "balcony",               # 3072 listings
    "elevator",              # 3091 listings
    "parking",               # 2358 listings
    "garage",                # 1383 listings
    "pets_allowed",          # 1564 listings
    "private_laundry",       # 847  listings
    "wheelchair_accessible", # 788  listings
    "child_friendly",        # 675  listings
    "minergie_certified",    # 331  listings
    "fireplace",             # 260  listings
    "new_build",             # 221  listings
]

SortOrder = Literal["price_asc", "price_desc", "rooms_asc", "rooms_desc", "area_asc", "area_desc"]


class GeoTarget(BaseModel):
    label: str | None = None
    latitude: float
    longitude: float


# ── Hard filter schema ───────────────────────────────────────────────────────
# Single source of truth: LLM structured-output target AND DB query filter.
# Every field maps 1-to-1 to a filterable column in the listings SQLite table.

class HardFilters(BaseModel):

    # ── Location ─────────────────────────────────────────────────────────────
    # city: case+umlaut-normalized IN match. 48.7% of listings have a city.
    city: list[str] | None = None
    postal_code: list[str] | None = None
    # canton: 65% of listings have NULL canton — prefer city when possible.
    canton: str | None = None

    # ── Price ─────────────────────────────────────────────────────────────────
    # INTEGER column `price`. Monthly CHF rent. avg=2092, range=1..1111111.
    # Dataset is 99.9% RENT — only set offer_type=SALE when explicitly stated.
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)

    # ── Size ──────────────────────────────────────────────────────────────────
    # REAL column `rooms`. Swiss half-room notation (1.0, 1.5, 2.0, 2.5 …).
    min_rooms: float | None = Field(default=None, ge=0)
    max_rooms: float | None = Field(default=None, ge=0)
    # REAL column `area` in m². avg=102 m², range=1..12500. 81.4% non-null.
    min_area: float | None = Field(default=None, ge=0)
    max_area: float | None = Field(default=None, ge=0)

    # ── Availability ──────────────────────────────────────────────────────────
    # TEXT column `available_from` in ISO format YYYY-MM-DD. 30.1% non-null.
    # available_before: keep listings where available_from IS NULL (already
    # available) OR available_from <= this date.
    available_before: str | None = None   # ISO date string e.g. "2026-06-30"

    # ── Geo radius ────────────────────────────────────────────────────────────
    # Haversine applied in-memory after SQL fetch. 92.8% of listings have coords.
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = Field(default=None, ge=0)
    geo_targets: list[GeoTarget] | None = None

    # ── Boolean feature columns (feature_* INTEGER 0/1, AND semantics) ───────
    features: list[FeatureName] | None = None

    # ── Categorical columns ───────────────────────────────────────────────────
    offer_type: OfferType | None = None
    object_category: list[ObjectCategory] | None = None

    # ── Pagination & sorting (not constraints — not exposed to the LLM) ──────
    limit: int = Field(default=20, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort_by: SortOrder | None = None


# ── Unified query constraints (hard + soft, same shape) ─────────────────────

class QueryConstraints(BaseModel):
    """
    Single LLM extraction result.
    hard: constraints that MUST be satisfied — violations exclude a listing.
    soft: preferences that SHOULD influence ranking — violations do not exclude.
    Both use identical fields; interpretation differs in the pipeline.
    """
    hard: HardFilters = Field(default_factory=HardFilters)

    # Soft preferences extend the hard filters with attributes that are
    # not (necessarily) direct DB filters but are useful ranking hints for
    # the pipeline / LLM output.
    class SoftFilters(HardFilters):
        # ── Physical / structural ────────────────────────────────────────────
        furnished: bool | None = None       # furnished / möbliert / meublé
        garden: bool | None = None          # private garden / Garten
        min_bedrooms: int | None = Field(default=None, ge=1)   # min bedrooms
        min_bathrooms: int | None = Field(default=None, ge=1)  # min bathrooms
        rooftop: bool | None = None         # rooftop terrace / Dachterrasse
        terrace: bool | None = None         # terrace (not just balcony)
        cellar: bool | None = None          # cellar / Keller / storage room
        bathtub: bool | None = None         # bathtub / Badewanne
        view: bool | None = None            # notable view (lake, mountains, city)
        not_ground_floor: bool | None = None  # not on ground floor / kein Erdgeschoss
        # ── Interior / aesthetic ─────────────────────────────────────────────
        bright: bool | None = None          # bright / lots of light / hell / viel Licht
        modern: bool | None = None          # modern / renovated / neu renoviert
        good_layout: bool | None = None     # good floor plan / guter Schnitt
        # ── Neighbourhood / environment ──────────────────────────────────────
        quiet: bool | None = None           # quiet environment / ruhige Lage
        near_lake: bool | None = None       # near a lake / in Seenähe
        safe: bool | None = None            # safe area / sichere Gegend
        good_schools: bool | None = None    # good schools nearby / gute Schulen
        low_traffic: bool | None = None     # low traffic / wenig Verkehr
        green_space: bool | None = None     # parks / greenery nearby / Grün
        walkable_shopping: bool | None = None  # shops within walking distance
        good_transport: bool | None = None  # good public transport / gute ÖV-Anbindung
        family_friendly: bool | None = None # family-friendly environment
        playground_nearby: bool | None = None  # playground nearby / Spielplatz

    soft: SoftFilters = Field(default_factory=SoftFilters)


# ── Rest of API schemas ──────────────────────────────────────────────────────

class ListingsQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ListingsSearchRequest(BaseModel):
    hard_filters: HardFilters | None = None



class ListingExplanationRequest(BaseModel):
    query: str = Field(min_length=1)
    listing_id: str = Field(min_length=1)


class ListingExplanationResponse(BaseModel):
    listing_id: str
    explanation: str


class ListingData(BaseModel):
    id: str
    title: str
    description: str | None = None
    street: str | None = None
    city: str | None = None
    postal_code: str | None = None
    canton: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    price_chf: int | None = None
    rooms: float | None = None
    living_area_sqm: float | None = None
    available_from: str | None = None
    image_urls: list[str] | None = None
    hero_image_url: str | None = None
    original_listing_url: str | None = None
    features: list[str] = Field(default_factory=list)
    offer_type: str | None = None
    object_category: str | None = None
    object_type: str | None = None
    distance_public_transport: int | None = None
    distance_shop: int | None = None


class RankedListingResult(BaseModel):
    listing_id: str
    score: float
    reason: str
    listing: ListingData
    matched_soft_features: list[str] = Field(default_factory=list)


class ListingsResponse(BaseModel):
    listings: list[RankedListingResult]
    meta: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
