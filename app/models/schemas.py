from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

# ── Typed enumerations matching exact DB column values ───────────────────────

OfferType = Literal["RENT", "SALE"]

# Exact German strings stored in the object_category column.
# Sorted by frequency (from DB inspection).
ObjectCategory = Literal[
    # Apartments (Wohnungen) — 7118 total
    "Wohnung",           # 6146 — standard apartment
    "Möblierte Wohnung", # 336  — furnished apartment
    "Dachwohnung",       # 156  — attic apartment
    "Maisonette",        # 112  — maisonette
    "Studio",            # 68   — studio
    "Attika",            # 57   — penthouse/attika
    "WG-Zimmer",         # 48   — flatshare room
    "Loft",              # 40   — loft
    "Einzelzimmer",      # 146  — single room
    "Terrassenwohnung",  # 3    — terrace apartment
    "Ferienwohnung",     # 2    — holiday apartment
    "Ferienimmobilie",   # 1    — holiday property
    # Houses (Häuser) — 329 total
    "Haus",              # 268  — house (generic)
    "Villa",             # 26   — villa
    "Doppeleinfamilienhaus", # 19 — semi-detached
    "Reihenhaus",        # 8    — terraced house
    "Mehrfamilienhaus",  # 4    — multi-family house
    "Bauernhaus",        # 4    — farmhouse
    "Terrassenhaus",     # 1    — terrace house
    # Commercial / other
    "Gewerbeobjekt",     # 1913 — commercial property
    "Parkplatz, Garage", # 402  — parking + garage
    "Parkplatz",         # 371  — parking spot
    "Tiefgarage",        # 313  — underground garage
    "Bastelraum",        # 202  — storage/hobby room
    "Einzelgarage",      # 80   — single garage
    "Diverses",          # 24   — miscellaneous
    "Wohnnebenraeume",   # 3    — ancillary rooms
    "Grundstück",        # 1    — plot/land
    "Gastgewerbe",       # 1    — gastronomy
]

# Exact keys from FEATURE_COLUMN_MAP in app/core/hard_filters.py.
# Each maps to a feature_* INTEGER (0/1) column. `temporary` excluded (0 listings with value=1).
FeatureName = Literal[
    "balcony",            # 3072 listings
    "elevator",           # 3091 listings
    "parking",            # 2358 listings
    "garage",             # 1383 listings
    "pets_allowed",       # 1564 listings
    "private_laundry",    # 847  listings
    "wheelchair_accessible", # 788 listings
    "child_friendly",     # 675  listings
    "minergie_certified", # 331  listings
    "fireplace",          # 260  listings
    "new_build",          # 221  listings
]

SortOrder = Literal["price_asc", "price_desc", "rooms_asc", "rooms_desc"]

# ── Hard filter schema ───────────────────────────────────────────────────────
# Single source of truth: LLM structured-output target AND DB query filter.
# Every filterable field maps 1-to-1 to an indexed column in the listings table.

class HardFilters(BaseModel):
    # Location — indexed columns
    # NOTE: city uses case-insensitive + umlaut-normalized matching in the DB layer.
    # DB stores both "Zürich" (877) and "Zurich" (71) — output the user's spelling,
    # the query layer handles normalization.
    city: list[str] | None = None
    postal_code: list[str] | None = None
    canton: str | None = None  # single 2-letter Swiss canton code; 14874/22819 listings have None

    # Price — INTEGER column `price` (monthly CHF rent; avg=2092, range=1..1111111)
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)

    # Size — REAL column `rooms` (Swiss half-room notation: 1.0, 1.5, 2.0, 2.5 … 10.0+)
    min_rooms: float | None = Field(default=None, ge=0)
    max_rooms: float | None = Field(default=None, ge=0)

    # Geo radius — Haversine applied in-memory after SQL fetch
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = Field(default=None, ge=0)

    # Boolean feature columns (feature_* INTEGER 0/1) — AND semantics
    features: list[FeatureName] | None = None

    # Categorical columns
    offer_type: OfferType | None = None           # dataset: 21785 RENT, 1 SALE
    object_category: list[ObjectCategory] | None = None  # 12064/22819 listings have None

    # Pagination & sorting — not constraints, not exposed to the LLM
    limit: int = Field(default=20, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort_by: SortOrder | None = None


# ── Rest of API schemas ──────────────────────────────────────────────────────

class ListingsQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ListingsSearchRequest(BaseModel):
    hard_filters: HardFilters | None = None


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
    living_area_sqm: int | None = None
    available_from: str | None = None
    image_urls: list[str] | None = None
    hero_image_url: str | None = None
    original_listing_url: str | None = None
    features: list[str] = Field(default_factory=list)
    offer_type: str | None = None
    object_category: str | None = None
    object_type: str | None = None


class RankedListingResult(BaseModel):
    listing_id: str
    score: float
    reason: str
    listing: ListingData


class ListingsResponse(BaseModel):
    listings: list[RankedListingResult]
    meta: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
