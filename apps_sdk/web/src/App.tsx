import { useEffect, useMemo, useState } from "react";
import RankedList from "./components/RankedList";
import ListingsMap from "./components/ListingsMap";
import FilterChips, { type FilterState, EMPTY_FILTERS } from "./components/FilterChips";

type ListingData = {
  id: string;
  title: string;
  city?: string | null;
  canton?: string | null;
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

type ToolOutput = {
  listings?: RankedListingResult[];
  meta?: Record<string, unknown>;
};

declare global {
  interface Window {
    openai?: { toolOutput?: ToolOutput };
  }
}

type UiToolResultMessage = {
  jsonrpc?: string;
  method?: string;
  params?: { structuredContent?: ToolOutput };
};

function readToolOutput(): ToolOutput {
  return window.openai?.toolOutput ?? {};
}

function readToolOutputFromMessage(message: unknown): ToolOutput | null {
  if (!message || typeof message !== "object") return null;
  const m = message as UiToolResultMessage;
  if (m.jsonrpc !== "2.0" || m.method !== "ui/notifications/tool-result") return null;
  return m.params?.structuredContent ?? {};
}

// ── Mock data (sostituire con backend reale) ──────────────────────────────────
const MOCK_RESULTS: RankedListingResult[] = [
  {
    listing_id: "1",
    score: 0.94,
    reason: "Very close to ETH Zurich, modern kitchen, bright rooms, excellent transport access.",
    listing: {
      id: "1",
      title: "Modern 3-room apartment near ETH Zurich",
      city: "Zurich", canton: "ZH",
      price_chf: 2750, rooms: 3,
      features: ["balcony", "bright", "close_to_transport"],
      hero_image_url: "https://picsum.photos/500/300",
      image_urls: ["https://picsum.photos/500/301", "https://picsum.photos/500/302"],
    },
  },
  {
    listing_id: "2",
    score: 0.81,
    reason: "Affordable option with good commute time to ETH, quiet area and decent lighting.",
    listing: {
      id: "2",
      title: "Bright student-friendly flat in Oerlikon",
      city: "Zurich", canton: "ZH",
      price_chf: 1950, rooms: 2,
      features: ["quiet", "bright", "parking"],
      hero_image_url: "https://picsum.photos/500/303",
      image_urls: ["https://picsum.photos/500/304"],
    },
  },
  {
    listing_id: "3",
    score: 0.72,
    reason: "Lower price but further from ETH, still good public transport connections.",
    listing: {
      id: "3",
      title: "Affordable 2-room apartment in Winterthur",
      city: "Winterthur", canton: "ZH",
      price_chf: 1600, rooms: 2,
      features: ["transport_access"],
      hero_image_url: "https://picsum.photos/500/305",
      image_urls: [],
    },
  },
  {
    listing_id: "4",
    score: 0.92,
    reason: "Great match for demo — spacious and well connected.",
    listing: {
      id: "4",
      title: "Modern apartment in Zurich",
      city: "Zurich", canton: "ZH",
      latitude: 47.37, longitude: 8.54,
      price_chf: 2500, rooms: 3,
      features: ["elevator", "balcony"],
    },
  },
];

export default function App() {
  const [toolOutput, setToolOutput] = useState<ToolOutput>(() => readToolOutput());
  const [selectedId, setSelectedId]   = useState<string | null>(null);
  const [query, setQuery]             = useState("");
  const [isOpen, setIsOpen]           = useState(false);
  const [filters, setFilters]         = useState<FilterState>(EMPTY_FILTERS);

  useEffect(() => {
    const onGlobals = (event: Event) => {
      const e = event as CustomEvent<{ globals?: { toolOutput?: ToolOutput } }>;
      setToolOutput(e.detail?.globals?.toolOutput ?? readToolOutput());
    };
    const onMessage = (event: MessageEvent) => {
      if (event.source !== window.parent) return;
      const next = readToolOutputFromMessage(event.data);
      if (next) setToolOutput(next);
    };
    window.addEventListener("openai:set_globals", onGlobals as EventListener);
    window.addEventListener("message", onMessage, { passive: true });
    return () => {
      window.removeEventListener("openai:set_globals", onGlobals as EventListener);
      window.removeEventListener("message", onMessage);
    };
  }, []);

  const results: RankedListingResult[] = toolOutput.listings ?? MOCK_RESULTS;

  // ── Client-side filtering (sostituire con query param al backend) ──────────
  const filteredResults = useMemo(() => {
    return results.filter(({ listing }) => {
      if (filters.offer_type) {
        // offer_type not in mock data — skip silently
      }
      if (filters.min_rooms != null && listing.rooms != null) {
        if (listing.rooms < filters.min_rooms) return false;
      }
      if (filters.max_price != null && listing.price_chf != null) {
        if (listing.price_chf > filters.max_price) return false;
      }
      if (filters.features.length > 0) {
        const feats = listing.features ?? [];
        if (!filters.features.every((f) => feats.includes(f))) return false;
      }
      return true;
    });
  }, [results, filters]);

  useEffect(() => {
    if (!filteredResults.length) { setSelectedId(null); return; }
    setSelectedId((cur) =>
      cur && filteredResults.some((r) => r.listing_id === cur)
        ? cur
        : filteredResults[0].listing_id,
    );
  }, [filteredResults]);

  const selectedListing = useMemo(
    () => filteredResults.find((r) => r.listing_id === selectedId) ?? null,
    [filteredResults, selectedId],
  );

  return (
    <div className="app-shell">

      {/* MAPPA */}
      <main className={`map-panel ${isOpen ? "shrink" : "full"}`}>
        <ListingsMap
          results={filteredResults}
          selectedId={selectedId}
          selectedListing={selectedListing}
          onSelect={setSelectedId}
          mode={isOpen ? "results" : "overview"}
        />
      </main>

      {/* SIDEBAR */}
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
              {filteredResults.length
                ? `${filteredResults.length} of ${results.length} result${results.length === 1 ? "" : "s"}`
                : "No results"}
            </p>
          </div>

          <FilterChips
            filters={filters}
            onChange={setFilters}
            activeCount={filteredResults.length}
          />

          <RankedList
            results={filteredResults}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </aside>
      )}

      {/* FLOATING SEARCH */}
      <div className={`floating-search ${isOpen ? "open" : ""}`}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search apartments in Zurich..."
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setIsOpen(true);
              console.log("query:", query);
            }
          }}
        />
        <button onClick={() => setIsOpen(true)}>Search</button>
      </div>

    </div>
  );
}
