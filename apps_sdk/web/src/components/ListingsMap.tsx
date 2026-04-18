import { useEffect, useMemo, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type ListingData = {
  id: string;
  title: string;
  city?: string | null;
  canton?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  price_chf?: number | null;
};

type RankedListingResult = {
  listing_id: string;
  score: number;
  listing: ListingData;
};

type ListingsMapProps = {
  results: RankedListingResult[];
  selectedId: string | null;
  hoveredId: string | null;
  onSelect: (listingId: string) => void;
  onHover: (listingId: string | null) => void;
};

const MAP_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    "carto-voyager": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
        "https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; CARTO',
    },
  },
  layers: [
    {
      id: "carto-voyager-layer",
      type: "raster",
      source: "carto-voyager",
      minzoom: 0,
      maxzoom: 22,
    },
  ],
};

function makePinSvg(color: string, rank: number): string {
  return `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 52" width="36" height="46">
      <path d="M20 2C11.16 2 4 9.16 4 18c0 11.25 16 32 16 32S36 29.25 36 18C36 9.16 28.84 2 20 2z"
            fill="${color}" stroke="white" stroke-width="2.5"/>
      <circle cx="20" cy="18" r="9" fill="white"/>
      <text x="20" y="18" text-anchor="middle" dominant-baseline="central"
            font-size="11" font-weight="700" fill="${color}"
            font-family="IBM Plex Sans, Segoe UI, sans-serif">${rank}</text>
    </svg>
  `;
}

function scoreColor(score: number): string {
  if (score > 0.8) return "#22c55e";
  if (score > 0.5) return "#f5a040";
  return "#ef4444";
}

function applyPinStyle(el: HTMLElement, isHovered: boolean) {
  el.style.transform = isHovered ? "scale(1.5) translateY(-6px)" : "scale(1)";
  el.style.filter = isHovered
    ? "drop-shadow(0 6px 14px rgba(92,92,224,0.65))"
    : "drop-shadow(0 2px 6px rgba(0,0,0,0.28))";
  el.style.zIndex = isHovered ? "10" : "1";
}

const FOCUS_MIN_ZOOM = 13;

export default function ListingsMap({
  results,
  selectedId,
  hoveredId,
  onSelect,
  onHover,
}: ListingsMapProps) {
  const mapRef          = useRef<maplibregl.Map | null>(null);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const pinElsRef       = useRef<Record<string, HTMLElement>>({});
  const markersRef      = useRef<maplibregl.Marker[]>([]);

  const coordinateResults = useMemo(
    () =>
      results.filter(
        (r) =>
          typeof r.listing.latitude === "number" &&
          typeof r.listing.longitude === "number",
      ),
    [results],
  );

  // Init map centered on Switzerland
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: MAP_STYLE,
      center: [8.23, 46.8],
      zoom: 7.2,
      attributionControl: false,
    });
    mapRef.current = map;
    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right",
    );

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      pinElsRef.current = {};
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Recreate pins when results change
  useEffect(() => {
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    pinElsRef.current = {};

    const map = mapRef.current;
    if (!map) return;

    coordinateResults.forEach((result, index) => {
      const color = scoreColor(result.score);

      // Outer div: MapLibre owns its transform for positioning
      const wrapper = document.createElement("div");
      wrapper.style.cssText = "cursor: pointer; line-height: 0;";
      wrapper.onclick      = () => onSelect(result.listing_id);
      wrapper.onmouseenter = () => onHover(result.listing_id);
      wrapper.onmouseleave = () => onHover(null);

      // Inner div: we own the transform for hover animation
      const inner = document.createElement("div");
      inner.style.cssText = `
        transform-origin: bottom center;
        transition: transform 0.2s cubic-bezier(0.34,1.56,0.64,1), filter 0.2s ease;
        line-height: 0;
      `;
      inner.innerHTML = makePinSvg(color, index + 1);
      wrapper.appendChild(inner);

      applyPinStyle(inner, hoveredId === result.listing_id);

      const marker = new maplibregl.Marker({ element: wrapper, anchor: "bottom" })
        .setLngLat([result.listing.longitude!, result.listing.latitude!])
        .setPopup(
          new maplibregl.Popup({ offset: 12 }).setHTML(
            `<strong>${result.listing.title}</strong><br/>${result.listing.city ?? ""}`,
          ),
        )
        .addTo(map);

      markersRef.current.push(marker);
      pinElsRef.current[result.listing_id] = inner;
    });

    // Fit all pins in view
    if (coordinateResults.length > 1) {
      const bounds = new maplibregl.LngLatBounds();
      coordinateResults.forEach((r) =>
        bounds.extend([r.listing.longitude!, r.listing.latitude!]),
      );
      map.fitBounds(bounds, { padding: 80, maxZoom: 13, duration: 800 });
    } else if (coordinateResults.length === 1) {
      const r = coordinateResults[0];
      map.easeTo({ center: [r.listing.longitude!, r.listing.latitude!], zoom: 12, duration: 800 });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coordinateResults, onSelect, onHover]);

  // Style-only update on hover — no marker recreation
  useEffect(() => {
    Object.entries(pinElsRef.current).forEach(([id, el]) => {
      applyPinStyle(el, id === hoveredId);
    });
  }, [hoveredId]);

  // Pan + zoom to selected listing
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedId) return;
    const result = results.find((r) => r.listing_id === selectedId);
    if (!result) return;
    const { latitude: lat, longitude: lng } = result.listing;
    if (lat == null || lng == null) return;
    const currentZoom = map.getZoom();
    map.easeTo({
      center: [lng, lat],
      zoom: Math.max(currentZoom, FOCUS_MIN_ZOOM),
      duration: 600,
    });
  }, [selectedId, results]);


  return <div ref={mapContainerRef} className="map-container" />;
}
