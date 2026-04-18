import { useEffect, useRef } from "react";
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
  selectedListing: RankedListingResult | null;
  onSelect: (listingId: string) => void;
  mode: "overview" | "results";
};

const ZOOM_THRESHOLD = 8.5;

const CANTON_COLORS: Record<string, string> = {
  ZH: "#4361ee", BE: "#7209b7", LU: "#f72585", UR: "#3a0ca3",
  SZ: "#4cc9f0", OW: "#480ca8", NW: "#b5179e", GL: "#560bad",
  ZG: "#f3722c", FR: "#f8961e", SO: "#43aa8b", BS: "#277da1",
  BL: "#4d908e", SH: "#577590", AR: "#e63946", AI: "#2a9d8f",
  SG: "#264653", GR: "#e9c46a", AG: "#f4a261", TG: "#90be6d",
  TI: "#023047", VD: "#219ebc", VS: "#8ecae6", NE: "#ffb703",
  GE: "#fb8500", JU: "#606c38",
};

const CANTON_CENTROIDS: Record<string, [number, number]> = {
  ZH: [8.65, 47.42], BE: [7.45, 46.95], LU: [8.30, 47.05],
  UR: [8.63, 46.77], SZ: [8.65, 47.02], OW: [8.25, 46.88],
  NW: [8.38, 46.92], GL: [9.07, 47.04], ZG: [8.52, 47.17],
  FR: [7.15, 46.80], SO: [7.53, 47.33], BS: [7.59, 47.56],
  BL: [7.72, 47.48], SH: [8.63, 47.70], AR: [9.41, 47.37],
  AI: [9.41, 47.32], SG: [9.37, 47.23], GR: [9.53, 46.66],
  AG: [8.07, 47.39], TG: [9.07, 47.55], TI: [8.95, 46.33],
  VD: [6.53, 46.57], VS: [7.60, 46.23], NE: [6.93, 47.00],
  GE: [6.15, 46.22], JU: [7.34, 47.36],
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

export default function ListingsMap({
  results,
  selectedId,
  selectedListing,
  onSelect,
  mode,
}: ListingsMapProps) {
  const mapRef       = useRef<maplibregl.Map | null>(null);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);

  // DOM elements for show/hide without recreating markers
  const cantonElsRef  = useRef<HTMLElement[]>([]);
  const listingElsRef = useRef<HTMLElement[]>([]);

  // Marker instances (for cleanup)
  const cantonMarkersRef  = useRef<maplibregl.Marker[]>([]);
  const listingMarkersRef = useRef<maplibregl.Marker[]>([]);

  // Stable ref so zoom listener always sees current mode
  const modeRef = useRef(mode);
  useEffect(() => { modeRef.current = mode; }, [mode]);

  const coordinateResults = results.filter(
    (r) =>
      typeof r.listing.latitude === "number" &&
      typeof r.listing.longitude === "number",
  );

  // Update DOM visibility without touching React state (called imperatively)
  function applyVisibility(zoom: number, currentMode: string) {
    const showCantons = currentMode === "overview" && zoom < ZOOM_THRESHOLD;
    const showListings = currentMode === "results" || zoom >= ZOOM_THRESHOLD;
    cantonElsRef.current.forEach(
      (el) => (el.style.display = showCantons ? "flex" : "none"),
    );
    listingElsRef.current.forEach(
      (el) => (el.style.display = showListings ? "flex" : "none"),
    );
  }

  // Init map once
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

    // Zoom-based clustering: update visibility on every zoom tick
    map.on("zoom", () => {
      applyVisibility(map.getZoom(), modeRef.current);
    });

    return () => {
      cantonMarkersRef.current.forEach((m) => m.remove());
      listingMarkersRef.current.forEach((m) => m.remove());
      cantonMarkersRef.current  = [];
      listingMarkersRef.current = [];
      cantonElsRef.current  = [];
      listingElsRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Canton cluster markers — recreated when results change
  useEffect(() => {
    cantonMarkersRef.current.forEach((m) => m.remove());
    cantonMarkersRef.current = [];
    cantonElsRef.current = [];

    const map = mapRef.current;
    if (!map) return;

    // Group by canton
    const cantonCounts: Record<string, number> = {};
    results.forEach((r) => {
      const c = r.listing.canton?.toUpperCase();
      if (c) cantonCounts[c] = (cantonCounts[c] ?? 0) + 1;
    });

    Object.entries(cantonCounts).forEach(([canton, count]) => {
      const coords = CANTON_CENTROIDS[canton];
      if (!coords) return;

      const color = CANTON_COLORS[canton] ?? "#5c5ce0";

      const el = document.createElement("div");
      el.style.cssText = `
        background: ${color};
        color: white;
        border-radius: 999px;
        padding: 5px 11px 5px 9px;
        font-size: 0.75rem;
        font-weight: 700;
        white-space: nowrap;
        box-shadow: 0 4px 18px ${color}80;
        cursor: pointer;
        border: 2.5px solid white;
        display: flex;
        align-items: center;
        gap: 6px;
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        transition: transform 0.15s ease;
      `;
      el.innerHTML = `
        <span>${canton}</span>
        <span style="
          background: rgba(255,255,255,0.28);
          border-radius: 999px;
          padding: 1px 8px;
          font-size: 0.8rem;
        ">${count}</span>
      `;

      el.onmouseenter = () => (el.style.transform = "scale(1.08)");
      el.onmouseleave = () => (el.style.transform = "scale(1)");

      // Click → zoom into canton
      el.onclick = () => {
        map.easeTo({ center: coords, zoom: ZOOM_THRESHOLD + 0.5, duration: 700 });
      };

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat(coords)
        .addTo(map);

      cantonMarkersRef.current.push(marker);
      cantonElsRef.current.push(el);
    });

    applyVisibility(map.getZoom(), mode);

    if (mode === "overview") {
      map.easeTo({ center: [8.23, 46.8], zoom: 7.2, duration: 600 });
    }
  }, [results, mode]);

  // Individual listing markers — recreated when results or selection change
  useEffect(() => {
    listingMarkersRef.current.forEach((m) => m.remove());
    listingMarkersRef.current = [];
    listingElsRef.current = [];

    const map = mapRef.current;
    if (!map) return;

    coordinateResults.forEach((result, index) => {
      const score = result.score;
      let color = "#999";
      if (score > 0.8)      color = "#22c55e";
      else if (score > 0.5) color = "#f5a040";
      else                  color = "#ef4444";

      const isSelected = selectedId === result.listing_id;

      const el = document.createElement("button");
      el.type = "button";
      el.style.cssText = `
        background: ${color};
        width: 32px;
        height: 32px;
        border-radius: 50%;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.82rem;
        border: ${isSelected ? "3px solid #5c5ce0" : "2px solid white"};
        box-shadow: 0 4px 12px rgba(0,0,0,0.22);
        cursor: pointer;
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      `;
      el.textContent = String(index + 1);
      el.onclick      = () => onSelect(result.listing_id);
      el.onmouseenter = () => onSelect(result.listing_id);

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([result.listing.longitude!, result.listing.latitude!])
        .setPopup(
          new maplibregl.Popup({ offset: 12 }).setHTML(
            `<strong>${result.listing.title}</strong><br/>${result.listing.city ?? ""}`,
          ),
        )
        .addTo(map);

      listingMarkersRef.current.push(marker);
      listingElsRef.current.push(el);
    });

    applyVisibility(map.getZoom(), mode);

    if (mode === "results" && coordinateResults.length) {
      const top = coordinateResults[0];
      if (top?.listing.latitude && top?.listing.longitude) {
        map.easeTo({
          center: [top.listing.longitude, top.listing.latitude],
          zoom: 12,
          duration: 800,
        });
      }
    }
  }, [coordinateResults, onSelect, selectedId, mode]);

  // Pan to selected listing in results mode
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !selectedListing || mode !== "results") return;
    if (
      typeof selectedListing.listing.latitude  === "number" &&
      typeof selectedListing.listing.longitude === "number"
    ) {
      map.easeTo({
        center: [selectedListing.listing.longitude, selectedListing.listing.latitude],
        zoom: Math.max(map.getZoom(), 12),
        duration: 500,
      });
    }
  }, [selectedListing, mode]);

  return <div ref={mapContainerRef} className="map-container" />;
}
