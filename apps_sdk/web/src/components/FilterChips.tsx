export type FilterState = {
  offer_type: "RENT" | "SALE" | null;
  min_rooms: number | null;
  max_price: number | null;
  features: string[];
};

export const EMPTY_FILTERS: FilterState = {
  offer_type: null,
  min_rooms: null,
  max_price: null,
  features: [],
};

const FEATURE_LABELS: [string, string][] = [
  ["balcony",              "🌿 Balcony"],
  ["parking",              "🚗 Parking"],
  ["elevator",             "🛗 Elevator"],
  ["pets_allowed",         "🐾 Pets"],
  ["new_build",            "✨ New build"],
  ["child_friendly",       "👶 Family"],
  ["garage",               "🏠 Garage"],
  ["minergie_certified",   "🌱 Minergie"],
];

const PRICE_OPTIONS: [number, string][] = [
  [1500, "≤ 1.5k"],
  [2000, "≤ 2k"],
  [2500, "≤ 2.5k"],
  [3000, "≤ 3k"],
];

const ROOM_OPTIONS = [1, 2, 3, 4];

type Props = {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  activeCount: number;
};

export default function FilterChips({ filters, onChange, activeCount }: Props) {
  function toggleScalar<K extends "offer_type" | "min_rooms" | "max_price">(
    key: K,
    value: FilterState[K],
  ) {
    onChange({ ...filters, [key]: filters[key] === value ? null : value });
  }

  function toggleFeature(feat: string) {
    const next = filters.features.includes(feat)
      ? filters.features.filter((f) => f !== feat)
      : [...filters.features, feat];
    onChange({ ...filters, features: next });
  }

  const anyActive =
    filters.offer_type !== null ||
    filters.min_rooms !== null ||
    filters.max_price !== null ||
    filters.features.length > 0;

  return (
    <div className="filter-chips">
      <div className="filter-chip-scroll">

        {/* Offer type */}
        {(["RENT", "SALE"] as const).map((type) => (
          <button
            key={type}
            className={`filter-chip ${filters.offer_type === type ? "active" : ""}`}
            onClick={() => toggleScalar("offer_type", type)}
          >
            {type === "RENT" ? "🏠 Rent" : "💰 Sale"}
          </button>
        ))}

        <span className="filter-chip-divider" />

        {/* Min rooms */}
        {ROOM_OPTIONS.map((r) => (
          <button
            key={r}
            className={`filter-chip ${filters.min_rooms === r ? "active" : ""}`}
            onClick={() => toggleScalar("min_rooms", r)}
          >
            {r === 4 ? "4+ rooms" : `${r}+ rooms`}
          </button>
        ))}

        <span className="filter-chip-divider" />

        {/* Max price */}
        {PRICE_OPTIONS.map(([price, label]) => (
          <button
            key={price}
            className={`filter-chip ${filters.max_price === price ? "active" : ""}`}
            onClick={() => toggleScalar("max_price", price)}
          >
            CHF {label}
          </button>
        ))}

        <span className="filter-chip-divider" />

        {/* Features */}
        {FEATURE_LABELS.map(([feat, label]) => (
          <button
            key={feat}
            className={`filter-chip ${filters.features.includes(feat) ? "active" : ""}`}
            onClick={() => toggleFeature(feat)}
          >
            {label}
          </button>
        ))}

        {/* Clear all */}
        {anyActive && (
          <>
            <span className="filter-chip-divider" />
            <button
              className="filter-chip filter-chip-clear"
              onClick={() => onChange(EMPTY_FILTERS)}
            >
              ✕ Clear
            </button>
          </>
        )}
      </div>

      {anyActive && (
        <p className="filter-result-count">
          {activeCount} result{activeCount !== 1 ? "s" : ""} after filters
        </p>
      )}
    </div>
  );
}
