import { useEffect, useMemo, useRef, useState } from "react";
import RankedList from "./components/RankedList";
import ListingsMap from "./components/ListingsMap";

type ListingData = {
  id: string;
  title: string;
  city?: string | null;
  canton?: string | null;
  street?: string | null;
  latitude?: number | null;
  longitude?: number | null;
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

type ToolResultPayload = {
  query?: string;
  listings?: RankedListingResult[];
};

type ListingImagesPayload = {
  listing_id: string;
  image_urls: string[];
  hero_image_url?: string | null;
};

const API_BASE = "http://localhost:8000";

export default function App() {
  const [query, setQuery]       = useState("");
  const [results, setResults]   = useState<RankedListingResult[]>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [isOpen, setIsOpen]     = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId]   = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(10);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const requestedImageIdsRef = useRef<Set<string>>(new Set());

  function applyToolResult(payload: ToolResultPayload) {
    const listings = Array.isArray(payload.listings) ? payload.listings : [];
    requestedImageIdsRef.current = new Set();
    setQuery(typeof payload.query === "string" ? payload.query : "");
    setResults(listings);
    setError(null);
    setLoading(false);
    setIsOpen(true);
    setSelectedId(null);
    setHoveredId(null);
    setVisibleCount(10);
  }

  async function search() {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setIsOpen(true);
    setResults([]);
    setVisibleCount(10);
    requestedImageIdsRef.current = new Set();
    try {
      const res = await fetch(`${API_BASE}/listings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit: 500 }),
      });
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      const listings: RankedListingResult[] = data.listings ?? [];
      setResults(listings);
      setSelectedId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  const mappableResults = useMemo(
    () => results.filter(
      (r) => typeof r.listing.latitude === "number" && typeof r.listing.longitude === "number"
    ),
    [results],
  );

  const visibleResults = useMemo(
    () => mappableResults.slice(0, visibleCount),
    [mappableResults, visibleCount],
  );

  useEffect(() => {
    const listingIds = visibleResults
      .map((result) => result.listing_id)
      .filter((listingId) => {
        const listing = results.find((item) => item.listing_id === listingId)?.listing;
        if (!listing) return false;
        const hasImages = Boolean(listing.hero_image_url) || Boolean(listing.image_urls?.length);
        return !hasImages && !requestedImageIdsRef.current.has(listingId);
      });

    if (!listingIds.length) return;

    for (const listingId of listingIds) {
      requestedImageIdsRef.current.add(listingId);
    }

    let cancelled = false;

    async function loadVisibleImages() {
      try {
        const res = await fetch(`${API_BASE}/listings/images`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ listing_ids: listingIds }),
        });
        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        const data = await res.json();
        if (cancelled) return;

        const resolved = new Map<string, ListingImagesPayload>(
          (data.listings ?? []).map((item: ListingImagesPayload) => [item.listing_id, item]),
        );

        setResults((current) =>
          current.map((item) => {
            const images = resolved.get(item.listing_id);
            if (!images) return item;
            return {
              ...item,
              listing: {
                ...item.listing,
                image_urls: images.image_urls,
                hero_image_url: images.hero_image_url ?? null,
              },
            };
          }),
        );
      } catch {
        if (cancelled) return;
      }
    }

    void loadVisibleImages();

    return () => {
      cancelled = true;
    };
  }, [results, visibleResults]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "0px";
    const lineHeight = 24;
    const maxRows = 5;
    const maxHeight = lineHeight * maxRows;
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight);

    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [query]);

  useEffect(() => {
    function handleToolResult(event: Event) {
      const customEvent = event as CustomEvent<ToolResultPayload>;
      if (customEvent.detail) {
        applyToolResult(customEvent.detail);
      }
    }

    function handleMessage(event: MessageEvent<unknown>) {
      const data = event.data;
      if (!data || typeof data !== "object") return;

      const message = data as {
        type?: string;
        structuredContent?: ToolResultPayload;
        payload?: ToolResultPayload;
      };

      if (message.type !== "tool-result") return;

      const payload = message.structuredContent ?? message.payload;
      if (payload) {
        applyToolResult(payload);
      }
    }

    window.addEventListener("tool-result", handleToolResult as EventListener);
    window.addEventListener("message", handleMessage);
    return () => {
      window.removeEventListener("tool-result", handleToolResult as EventListener);
      window.removeEventListener("message", handleMessage);
    };
  }, []);

  return (
    <div className="app-shell">

      <main className={`map-panel ${isOpen ? "shrink" : "full"}`}>
        <ListingsMap
          results={visibleResults}
          selectedId={selectedId}
          hoveredId={hoveredId}
          onSelect={setSelectedId}
          onHover={setHoveredId}
        />
      </main>

      {isOpen && (
        <aside className="sidebar">
          <button
            className="close-sidebar"
            onClick={() => setIsOpen(false)}
            aria-label="Close"
          >
            ✕
          </button>

          <div className="sidebar-header">
            <p className="eyebrow">Listings</p>
            <h1>Ranked results</h1>
            <p className="muted">
              {loading
                ? ""
                : mappableResults.length
                  ? `${visibleResults.length} of ${mappableResults.length} result${mappableResults.length === 1 ? "" : "s"}`
                  : "No results"}
            </p>
          </div>

          {loading ? (
            <div className="skeleton-list">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="skeleton-card">
                  <div className="skeleton-image" />
                  <div className="skeleton-line w-80" />
                  <div className="skeleton-line w-50" />
                  <div className="skeleton-tags">
                    <div className="skeleton-tag" />
                    <div className="skeleton-tag" />
                    <div className="skeleton-tag" />
                  </div>
                  <div className="skeleton-reason" />
                </div>
              ))}
            </div>
          ) : visibleResults.length > 0 ? (<>
            <RankedList
              query={query}
              results={visibleResults}
              selectedId={selectedId}
              hoveredId={hoveredId}
              onSelect={setSelectedId}
              onHover={setHoveredId}
            />
            {visibleCount < mappableResults.length && (
              <div className="show-more-wrap">
                <button
                  className="show-more-btn"
                  onClick={() => setVisibleCount((c) => c + 10)}
                >
                  Show more ({mappableResults.length - visibleCount} remaining)
                </button>
              </div>
            )}
          </>) : null}
        </aside>
      )}

      <div className={`floating-search ${isOpen ? "open" : ""}`}>
        <textarea
          ref={textareaRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Tell Robin what you're looking for…"
          disabled={loading}
          rows={1}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void search();
            }
          }}
        />
        <button onClick={search} disabled={loading}>
          {loading ? <span className="btn-spinner" /> : "Search"}
        </button>
      </div>

      {error && <div className="search-error">{error}</div>}

    </div>
  );
}
