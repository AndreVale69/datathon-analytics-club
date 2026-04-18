import { useRef, useState } from "react";

type ListingData = {
  id: string;
  title: string;
  city?: string | null;
  canton?: string | null;
  image_urls?: string[] | null;
  hero_image_url?: string | null;
  price_chf?: number | null;
  rooms?: number | null;
  features?: string[];
};

type RankedListingResult = {
  listing_id: string;
  score: number;
  reason: string;
  listing: ListingData;
};

type RankedListProps = {
  results: RankedListingResult[];
  selectedId: string | null;
  hoveredId: string | null;
  onSelect: (listingId: string) => void;
  onHover: (listingId: string | null) => void;
};

function formatPrice(price?: number | null): string {
  if (price == null) return "Price n/a";

  return new Intl.NumberFormat("de-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(price);
}

function getImageUrls(listing: ListingData): string[] {
  const candidates = [
    listing.hero_image_url,
    ...(listing.image_urls ?? []),
  ].filter((v): v is string => Boolean(v));

  return Array.from(new Set(candidates));
}

export default function RankedList({
  results,
  selectedId,
  hoveredId,
  onSelect,
  onHover,
}: RankedListProps) {
  const [imageIndexes, setImageIndexes] = useState<Record<string, number>>({});
  const touchStartXRef = useRef<Record<string, number>>({});

  return (
    <div className="ranked-list">
      {results.map((result, index) => {
        const listing = result.listing;
        const features = (listing.features ?? []).slice(0, 3);
        const imageUrls = getImageUrls(listing);

        const activeImageIndex =
          imageIndexes[result.listing_id] ?? 0;

        const activeImageUrl =
          imageUrls[
            (activeImageIndex + imageUrls.length) %
              Math.max(imageUrls.length, 1)
          ];

        const advanceImage = (delta: number) => {
          onSelect(result.listing_id);

          if (imageUrls.length <= 1) return;

          setImageIndexes((current) => {
            const currentIndex =
              current[result.listing_id] ?? 0;

            const nextIndex =
              (currentIndex + delta + imageUrls.length) %
              imageUrls.length;

            return {
              ...current,
              [result.listing_id]: nextIndex,
            };
          });
        };

        const score = result.score;

        return (
          <div
            key={result.listing_id}
            className={`listing-card ${
              hoveredId === result.listing_id || selectedId === result.listing_id ? "selected" : ""
            }`}
            onClick={() => onSelect(result.listing_id)}
            onMouseEnter={() => onHover(result.listing_id)}
            onMouseLeave={() => onHover(null)}
            role="button"
            tabIndex={0}
          >
            {/* IMAGE SECTION */}
            {activeImageUrl && (
              <div className="listing-image-wrap">

                {/* OVERLAY */}
                <div className="image-overlay">
                  <div className="price-badge">
                    {formatPrice(listing.price_chf)}
                  </div>

                  <div
                    className={`score-badge ${
                      score > 0.8
                        ? "high"
                        : score > 0.5
                        ? "mid"
                        : "low"
                    }`}
                  >
                    {Math.round(score * 100)}%
                  </div>
                </div>

                {/* NAV BUTTONS */}
                {imageUrls.length > 1 && (
                  <>
                    <button
                      className="listing-image-button listing-image-button-prev"
                      onClick={(e) => {
                        e.stopPropagation();
                        advanceImage(-1);
                      }}
                      type="button"
                    >
                      ‹
                    </button>

                    <button
                      className="listing-image-button listing-image-button-next"
                      onClick={(e) => {
                        e.stopPropagation();
                        advanceImage(1);
                      }}
                      type="button"
                    >
                      ›
                    </button>
                  </>
                )}

                <img
                  className="listing-image"
                  src={activeImageUrl}
                  alt={listing.title}
                  loading="lazy"
                />
              </div>
            )}

            {/* HEADER */}
            <div className="listing-card-header">
              <span className="listing-rank">#{index + 1}</span>
            </div>

            {/* CONTENT */}
            <h2 className="listing-title">{listing.title}</h2>

            <p className="listing-meta">
              {[listing.city, listing.canton]
                .filter(Boolean)
                .join(", ")}
              {" · "}
              {listing.rooms ?? "?"} rooms
            </p>

            {/* FEATURES */}
            {!!features.length && (
              <div className="feature-row">
                {features.map((f) => (
                  <span key={f} className="feature-badge">
                    {f.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
            )}

            {/* AI REASON */}
            <div className="ai-reason">
              <span className="ai-label">💡 Why this match</span>
              <p>{result.reason}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}