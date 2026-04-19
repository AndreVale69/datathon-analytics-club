from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.harness.search_service import query_from_filters, query_from_text, resolve_listing_images
from app.models.schemas import (
    HealthResponse,
    ListingExplanationRequest,
    ListingExplanationResponse,
    ListingImagesPayload,
    ListingImagesRequest,
    ListingImagesResponse,
    ListingsQueryRequest,
    ListingsResponse,
    ListingsSearchRequest,
)
from app.participant.explanations import explain_listing_match

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/listings", response_model=ListingsResponse)
def listings(request: ListingsQueryRequest) -> ListingsResponse:
    settings = get_settings()
    return query_from_text(
        db_path=settings.db_path,
        query=request.query,
        limit=request.limit,
        offset=request.offset,
    )


@router.post("/listings/search/filter", response_model=ListingsResponse)
def listings_search(request: ListingsSearchRequest) -> ListingsResponse:
    settings = get_settings()
    return query_from_filters(
        db_path=settings.db_path,
        hard_facts=request.hard_filters,
    )


@router.post("/listings/images", response_model=ListingImagesResponse)
def listing_images(request: ListingImagesRequest) -> ListingImagesResponse:
    settings = get_settings()
    return ListingImagesResponse(
        listings=[
            ListingImagesPayload(**item)
            for item in resolve_listing_images(
                db_path=settings.db_path,
                listing_ids=request.listing_ids,
            )
        ]
    )


@router.post("/listings/explain", response_model=ListingExplanationResponse)
def explain_listing(request: ListingExplanationRequest) -> ListingExplanationResponse:
    settings = get_settings()
    explanation = explain_listing_match(
        db_path=settings.db_path,
        query=request.query,
        listing_id=request.listing_id,
    )
    return ListingExplanationResponse(
        listing_id=request.listing_id,
        explanation=explanation,
    )
