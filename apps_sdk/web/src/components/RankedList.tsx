import { useEffect, useRef, useState } from "react";

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
  matched_soft_features?: string[];
};

type RankedListProps = {
  query: string;
  results: RankedListingResult[];
  selectedId: string | null;
  hoveredId: string | null;
  onSelect: (listingId: string) => void;
  onHover: (listingId: string | null) => void;
};

const SOFT_FEATURE_LABELS: Record<string, string> = {
  furnished: "Furnished",
  garden: "Garden",
  rooftop: "Rooftop terrace",
  terrace: "Terrace",
  cellar: "Cellar",
  bathtub: "Bathtub",
  view: "Scenic view",
  not_ground_floor: "Not ground floor",
  bright: "Bright",
  modern: "Modern",
  good_layout: "Good layout",
  quiet: "Quiet",
  near_lake: "Near lake",
  safe: "Safe area",
  good_schools: "Good schools",
  low_traffic: "Low traffic",
  green_space: "Green space",
  walkable_shopping: "Shops nearby",
  good_transport: "Good transport",
  family_friendly: "Family friendly",
  playground_nearby: "Playground nearby",
  min_bedrooms: "Bedrooms",
  min_bathrooms: "Bathrooms",
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

type InlineToken =
  | { type: "text"; value: string }
  | { type: "strong"; value: string }
  | { type: "code"; value: string };

function parseInlineMarkdown(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;

  for (const match of text.matchAll(pattern)) {
    const full = match[0];
    const index = match.index ?? 0;

    if (index > lastIndex) {
      tokens.push({ type: "text", value: text.slice(lastIndex, index) });
    }

    if (full.startsWith("**") && full.endsWith("**")) {
      tokens.push({ type: "strong", value: full.slice(2, -2) });
    } else if (full.startsWith("`") && full.endsWith("`")) {
      tokens.push({ type: "code", value: full.slice(1, -1) });
    } else {
      tokens.push({ type: "text", value: full });
    }

    lastIndex = index + full.length;
  }

  if (lastIndex < text.length) {
    tokens.push({ type: "text", value: text.slice(lastIndex) });
  }

  return tokens;
}

function renderInlineMarkdown(text: string) {
  return parseInlineMarkdown(text).map((token, index) => {
    if (token.type === "strong") {
      return <strong key={index}>{token.value}</strong>;
    }
    if (token.type === "code") {
      return <code key={index}>{token.value}</code>;
    }
    return <span key={index}>{token.value}</span>;
  });
}

function MarkdownExplanation({ content }: { content: string }) {
  const blocks = content
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  return (
    <div className="markdown-block">
      {blocks.map((block, blockIndex) => {
        const lines = block
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean);

        const isBulletList = lines.every((line) => /^[-*]\s+/.test(line));
        if (isBulletList) {
          return (
            <ul key={blockIndex}>
              {lines.map((line, lineIndex) => (
                <li key={lineIndex}>{renderInlineMarkdown(line.replace(/^[-*]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }

        return <p key={blockIndex}>{renderInlineMarkdown(block)}</p>;
      })}
    </div>
  );
}

export default function RankedList({
  query,
  results,
  selectedId,
  hoveredId,
  onSelect,
  onHover,
}: RankedListProps) {
  const [imageIndexes, setImageIndexes] = useState<Record<string, number>>({});
  const [explanations, setExplanations] = useState<Record<string, string>>({});
  const [loadingExplanations, setLoadingExplanations] = useState<Record<string, boolean>>({});
  const touchStartXRef = useRef<Record<string, number>>({});
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const API_BASE = "http://localhost:8000";

  useEffect(() => {
    if (!selectedId) return;
    cardRefs.current[selectedId]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selectedId]);

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
        const explanation = explanations[result.listing_id];
        const explanationLoading = loadingExplanations[result.listing_id] ?? false;

        const requestExplanation = async () => {
          onSelect(result.listing_id);
          if (explanation || explanationLoading || !query.trim()) return;

          setLoadingExplanations((current) => ({
            ...current,
            [result.listing_id]: true,
          }));

          try {
            const res = await fetch(`${API_BASE}/listings/explain`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                query,
                listing_id: result.listing_id,
              }),
            });
            if (!res.ok) throw new Error(`Server error: ${res.status}`);
            const data = await res.json();
            setExplanations((current) => ({
              ...current,
              [result.listing_id]: data.explanation ?? result.reason,
            }));
          } catch {
            setExplanations((current) => ({
              ...current,
              [result.listing_id]: result.reason,
            }));
          } finally {
            setLoadingExplanations((current) => ({
              ...current,
              [result.listing_id]: false,
            }));
          }
        };

        return (
          <div
            key={result.listing_id}
            className={`listing-card ${
              hoveredId === result.listing_id || selectedId === result.listing_id ? "selected" : ""
            }`}
            ref={(el) => { cardRefs.current[result.listing_id] = el; }}
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

            {/* DESCRIPTION-MATCHED SOFT FEATURES */}
            {!!(result.matched_soft_features?.length) && (
              <div className="feature-row">
                {result.matched_soft_features.map((f) => (
                  <span key={f} className="soft-match-badge">
                    ✓ {SOFT_FEATURE_LABELS[f] ?? f.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
            )}
            <div className="ai-reason">
              <span className="ai-label">💡 Why it ranked here</span>
              <p>{result.reason}</p>
            </div>

            <div className="explain-wrap">
              <button
                className="explain-button"
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  void requestExplanation();
                }}
              >
                <span className="explain-button-icon" aria-hidden="true">
                  <svg viewBox="0 0 16 16" focusable="false">
                    <path
                      d="M8 1.5a5.5 5.5 0 1 0 3.49 9.75l2.63 2.63a.75.75 0 1 0 1.06-1.06l-2.63-2.63A5.5 5.5 0 0 0 8 1.5Zm0 1.5a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm-.75 1.75a.75.75 0 0 0 0 1.5h.5v2.5a.75.75 0 0 0 1.5 0v-3a.75.75 0 0 0-.75-.75h-1.25Zm.75 5.5a.88.88 0 1 0 0 1.76.88.88 0 0 0 0-1.76Z"
                      fill="currentColor"
                    />
                  </svg>
                </span>
                {explanationLoading ? "Preparing explanation..." : "Explain this score"}
              </button>

              {explanation && (
                <div className="llm-explanation">
                  <span className="llm-label">Detailed explanation</span>
                  <MarkdownExplanation content={explanation} />
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
