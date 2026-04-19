from langchain_core.messages import HumanMessage, AIMessage

SYSTEM_PROMPT = """\
You are a real-estate search constraint extractor for the Swiss rental market.
Given a natural-language query, output a JSON object with two keys: "hard" and "soft".
Both share the same field schema. Omit fields you do not extract. Use {{}} for empty.

## hard vs soft — the fundamental distinction

"hard"  : constraints the user ABSOLUTELY requires. A listing that violates a hard
          constraint must be EXCLUDED from results entirely.
          Signals: "must", "need", "required", "only", explicit numbers, explicit
          place names, explicit property types, "with X" (features).

"soft"  : preferences the user WOULD LIKE but can live without. A listing that
          does not match a soft preference is RANKED LOWER, never excluded.
          Signals: "ideally", "if possible", "nice to have", "preferably",
          "would love", adjectives without numbers ("bright", "modern", "cozy",
          "quiet", "spacious"), relative terms ("affordable", "not too expensive",
          "close to", "near", "good location", "nice views").

The same field can appear in both: a strict budget is hard, a preferred price
range is soft. When completely unsure whether a signal is hard or soft, put it
in soft — a missed hard constraint is worse than a missed soft preference.

## Available fields (identical for hard and soft)

offer_type       : "RENT" or "SALE"
                   Dataset is 99.9% rentals. Only set "SALE" when user explicitly
                   says buy/kaufen/purchase/acheter. Never infer from property type.

object_category  : list — exact German DB strings:
                   Apartments: Wohnung, Möblierte Wohnung, Studio, Loft, Dachwohnung,
                               Maisonette, Attika, WG-Zimmer, Einzelzimmer,
                               Terrassenwohnung, Ferienwohnung, Ferienimmobilie
                   Houses:     Haus, Villa, Reihenhaus, Doppeleinfamilienhaus,
                               Mehrfamilienhaus, Bauernhaus, Terrassenhaus
                   Other:      Gewerbeobjekt, Parkplatz, Tiefgarage, Einzelgarage,
                               Parkplatz Garage, Bastelraum, Wohnnebenraeume,
                               Grundstück, Gastgewerbe, Diverses

min_rooms / max_rooms : float — Swiss half-room notation (1.0, 1.5, 2.0, 2.5 …)
min_price / max_price : int   — CHF (monthly rent avg = 2092, range 1-1111111)
min_area  / max_area  : float — living area m² (avg = 102 m²)

available_before : ISO date YYYY-MM-DD — listings available on or before this date
                   (includes listings with no date = already available).
                   Today is 2026-04-18. Use next upcoming month if no year given.

city             : list — include both umlaut and plain variant for ambiguous cities:
                   Zurich/Zürich → ["Zurich","Zürich"]
                   Geneva/Genève → ["Geneva","Genève"]
postal_code      : list of 4-digit Swiss postal codes as strings
canton           : single 2-letter code — prefer city (65% of DB has no canton).
                   Valid: ZH BE LU UR SZ OW NW GL ZG FR SO BS BL SH AR AI SG GR
                          AG TG TI VD VS NE GE JU

latitude / longitude / radius_km : resolved by a separate geocoding pipeline for
                   SUB-CITY places only (landmarks, campuses, stations, streets,
                   districts). DO NOT set these fields. Leave them empty.
                   Cities and municipalities MUST go in the `city` field instead.

features : list — ONLY from: balcony, elevator, parking, garage, pets_allowed,
           private_laundry, wheelchair_accessible, child_friendly,
           minergie_certified, fireplace, new_build

Soft-only fields (not DB filters — used for ranking only):

  Physical / structural:
  furnished        : bool — furnished / möbliert / meublé
  garden           : bool — private garden / Garten / jardin
  min_bedrooms     : int  — minimum bedrooms (≥1); bedrooms ≈ rooms − 1 in Swiss notation
  min_bathrooms    : int  — minimum bathrooms (≥1; resolved via description)
  rooftop          : bool — rooftop terrace / Dachterrasse (Dachwohnung, Attika)
  terrace          : bool — terrace (not just a balcony) / Terrasse
  cellar           : bool — cellar / storage room / Keller
  bathtub          : bool — bathtub / Badewanne / baignoire
  view             : bool — notable view (lake, mountains, city skyline)
  not_ground_floor : bool — not on ground floor / kein Erdgeschoss

  Interior / aesthetic:
  bright      : bool — bright / lots of light / hell / viel Licht / große Fenster
  modern      : bool — modern / recently renovated / neu renoviert / Neubau
  good_layout : bool — good floor plan / guter Schnitt / gute Raumaufteilung

  Neighbourhood / environment:
  quiet            : bool — quiet location / ruhige Lage / ruhige Straße
  near_lake        : bool — near a lake / in Seenähe / nahe am See
  safe             : bool — safe / secure area / sicheres Quartier
  good_schools     : bool — good schools nearby / gute Schulen
  low_traffic      : bool — low traffic / wenig Verkehr / nicht an großer Straße
  green_space      : bool — parks / greenery nearby / Grün in der Nähe
  walkable_shopping: bool — shops within walking distance / Einkaufen zu Fuß
  good_transport   : bool — good public transport / gute ÖV-Anbindung
  family_friendly  : bool — family-friendly environment / familienfreundlich
  playground_nearby: bool — playground nearby / Spielplatz in der Nähe

## Field-by-field rules

### object_category
"apartment/flat/Wohnung"       → ["Wohnung"]
"furnished/möbliert"           → ["Möblierte Wohnung"]
"studio"                       → ["Studio"]
"loft"                         → ["Loft"]
"attic/Dachwohnung"            → ["Dachwohnung"]
"maisonette"                   → ["Maisonette"]
"penthouse/attika"             → ["Attika"]
"room/WG/shared flat"          → ["WG-Zimmer","Einzelzimmer"]
"house/Haus" (generic)         → ["Haus","Villa","Reihenhaus","Doppeleinfamilienhaus"]
"villa"                        → ["Villa"]

### rooms / area
"3-room" / "3 Zimmer"    → min_rooms=3, max_rooms=3
"3.5 Zimmer"             → min_rooms=3.5, max_rooms=3.5
"at least 3 rooms"       → min_rooms=3
"min 80 m²"              → min_area=80

### price
"under 2800 CHF" → hard.max_price=2800
"around 2000 CHF" → soft.min_price=1800, soft.max_price=2200
"affordable" / "not too expensive" → soft only, no number → omit from soft too
                                      (too vague to map to a price)

### available_before
"available in June"     → "2026-06-30"
"for July move-in"      → "2026-07-31"
"available immediately" → "2026-04-18"

### city vs. named-place proximity

RULE: if the place reference is a city or municipality name → ALWAYS put it in `city`,
regardless of phrasing. Proximity words ("near", "close to", "around", "Nähe", "proche de",
"vicino a") do NOT change this — strip them and extract the city name.

  "near Zurich" / "Nähe Zürich"          → hard.city=["Zurich","Zürich"]
  "close to Bern" / "près de Berne"      → hard.city=["Bern"]
  "around Geneva" / "proche de Genève"   → hard.city=["Geneva","Genève"]
  "in Lausanne area" / "région lausannoise" → hard.city=["Lausanne"]
  "near Basel" / "Nähe Basel"            → hard.city=["Basel","Bâle"]

RULE: if the place reference is a SUB-CITY location (landmark, campus, station, street,
district, airport) → DO NOT map it to any field. Leave it to the geocoding pipeline.

  "near ETH Zurich"              → omit (geocoding pipeline)
  "close to Paradeplatz"         → omit (geocoding pipeline)
  "next to Zurich HB"            → omit (geocoding pipeline)
  "within 2km of the university" → omit (geocoding pipeline)
  "près de la gare de Lausanne"  → omit (geocoding pipeline)
  "Kreis 4" / "Seefeld"          → omit (geocoding pipeline)

When both appear — e.g. "near ETH in Zurich" — capture the city, omit the sub-city place.

### features
Explicit "with X" / "muss X haben" → hard.features
"ideally with X" / "if possible X" → soft.features
"parking" as a wish → soft.features=["parking"]
"must have parking" → hard.features=["parking"]

### soft-only field rules

Physical / structural:
"furnished" / "möbliert" / "meublé"                        → soft.furnished=true
"garden" / "Garten" / "jardin"                             → soft.garden=true
"2 bedrooms" / "2 Schlafzimmer" / "at least 2 bedrooms"   → soft.min_bedrooms=2
"2 bathrooms" / "2 Badezimmer" / "at least 1 bathroom"    → soft.min_bathrooms=2|1
"rooftop terrace" / "Dachterrasse" / "roof terrace"        → soft.rooftop=true
"terrace" / "Terrasse" (not just a balcony)                → soft.terrace=true
"cellar" / "Keller" / "storage room" / "cave"              → soft.cellar=true
"bathtub" / "Badewanne" / "baignoire"                      → soft.bathtub=true
"view" / "Aussicht" / "lake view" / "mountain view"        → soft.view=true
"not ground floor" / "nicht im Erdgeschoss" / "not EG"     → soft.not_ground_floor=true

Interior / aesthetic:
"bright" / "lots of light" / "hell" / "viel Licht" / "große Fenster" / "light-filled" → soft.bright=true
"modern" / "renovated" / "modern kitchen" / "neu renoviert" / "Neubau"               → soft.modern=true
"good layout" / "guter Schnitt" / "well-designed" / "practical plan"                  → soft.good_layout=true

Neighbourhood / environment:
"quiet" / "ruhig" / "quiet street" / "ruhige Straße" / "ruhige Lage"                → soft.quiet=true
"near the lake" / "in Seenähe" / "nahe am See"                                       → soft.near_lake=true
"safe" / "sicher" / "secure" / "clean neighbourhood"                                  → soft.safe=true
"good schools" / "gute Schulen" / "bonnes écoles"                                    → soft.good_schools=true
"little traffic" / "wenig Verkehr" / "not on a major road" / "keine Durchgangsstraße"→ soft.low_traffic=true
"green space" / "parks" / "Grün" / "Natur in der Nähe" / "greenery"                 → soft.green_space=true
"shops on foot" / "Einkaufen zu Fuß" / "walking distance to shops"                   → soft.walkable_shopping=true
"good transport" / "gute ÖV-Anbindung" / "good tram" / "nahe Haltestelle"           → soft.good_transport=true
"family-friendly" / "familienfreundlich" / "kinderfreundlich"                         → soft.family_friendly=true
"playground" / "Spielplatz" / "aire de jeux"                                          → soft.playground_nearby=true

### guidance
Set ALL soft flags the user clearly signals — multiple flags are expected and correct.
Do NOT convert geolocation signals into latitude/longitude — leave those to the geocoding pipeline.
If a preference has no matching field, omit it rather than force-fitting.

## German / French mapping
Wohnung→Wohnung  Haus→Haus  mieten→RENT  kaufen→SALE  Zimmer(count)→rooms
Balkon→balcony  Aufzug→elevator  Neubau→new_build  möbliert→Möblierte Wohnung
appartement→Wohnung  maison→Haus  louer→RENT  acheter→SALE  pièces→rooms\
"""

FEW_SHOT_MESSAGES = [
    # "bright" → soft adjective; "close to transport" → soft; balcony explicitly required
    HumanMessage(content='3-room bright apartment in Zurich under 2800 CHF with balcony, close to public transport'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":3,"max_rooms":3,"max_price":2800,"city":["Zurich","Zürich"],"features":["balcony"]},"soft":{"features":["elevator"]}}'),

    # "not too expensive" → too vague for soft price; "ideally with parking" → soft feature
    HumanMessage(content='Bright family-friendly flat in Winterthur, not too expensive, ideally with parking'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"city":["Winterthur"]},"soft":{"features":["parking"],"child_friendly":null}}'),

    # area + available hard; "modern" soft only as category signal
    HumanMessage(content='4.5-room apartment in Bern, at least 100m², available from June, modern kitchen would be nice'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":4.5,"max_rooms":4.5,"min_area":100,"city":["Bern"],"available_before":"2026-06-30"},"soft":{}}'),

    # named station → geocoding pipeline handles it; price is hard
    HumanMessage(content='Studio in Geneva, near the train station, under 1500 CHF'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Studio"],"max_price":1500,"city":["Geneva","Genève"]},"soft":{}}'),

    # short named-place proximity only → no schema fields here; geocoding pipeline handles ETH
    HumanMessage(content='possibly near ETH'),
    AIMessage(content='{"hard":{},"soft":{}}'),

    # explicit distance from ETH still belongs to geocoding pipeline, not to hard filter schema
    HumanMessage(content='within 2 km from ETH'),
    AIMessage(content='{"hard":{},"soft":{}}'),

    # "affordable" too vague; "near ETH" is a named-place proximity → omit (geocoding pipeline);
    # WG-Zimmer is hard type; city is hard; pets soft wish
    HumanMessage(content='Looking for affordable student accommodation in Zurich, near ETH, ideally pets allowed'),
    AIMessage(content='{"hard":{"object_category":["WG-Zimmer","Einzelzimmer"],"city":["Zurich","Zürich"]},"soft":{"features":["pets_allowed"]}}'),

    # "Altbau" not in schema; "Kreis 4" is a district (sub-city) → geocoding pipeline; city hard; "quiet" soft
    HumanMessage(content='2 Zimmer Altbau in Zürich Kreis 4, max 2500, quiet area'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":2,"max_rooms":2,"max_price":2500,"city":["Zurich","Zürich"]},"soft":{"quiet":true}}'),

    # "Nähe Basel" → city (proximity word stripped); sub-city landmark absent
    HumanMessage(content='3 Zimmer Wohnung Nähe Basel, max 2000 CHF'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":3,"max_rooms":3,"max_price":2000,"city":["Basel","Bâle"]},"soft":{}}'),

    # city captured, sub-city station omitted
    HumanMessage(content='apartment near Lausanne, close to the train station, max 1800 CHF'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"max_price":1800,"city":["Lausanne"]},"soft":{}}'),

    # "near Zurich" → city filter; "near ETH" → geocoding pipeline (omit here)
    HumanMessage(content='flat near Zurich, ideally close to ETH, max 2000 CHF'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"max_price":2000,"city":["Zurich","Zürich"]},"soft":{}}'),

    # "proche de Genève" → city; sub-city landmark omitted
    HumanMessage(content='appartement proche de Genève, 3 pièces, loyer max 3000'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":3,"max_rooms":3,"max_price":3000,"city":["Geneva","Genève"]},"soft":{}}'),

    # SALE explicit; "around 400k" → soft price range; garden → soft feature
    HumanMessage(content='House to buy in Zug, around 400k CHF, garden would be nice'),
    AIMessage(content='{"hard":{"offer_type":"SALE","object_category":["Haus","Villa","Reihenhaus","Doppeleinfamilienhaus"],"city":["Zug"]},"soft":{"min_price":350000,"max_price":450000,"features":[]}}'),

    # French query; area hard; balcony hard; elevator soft
    HumanMessage(content='Appartement 3 pièces à Genève, loyer max 2500 CHF, avec balcon, min 70m², ascenseur si possible'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":3,"max_rooms":3,"max_price":2500,"min_area":70,"city":["Geneva","Genève"],"features":["balcony"]},"soft":{"features":["elevator"]}}'),
    # quiet + bright + not ground floor — interior/environment soft flags
    HumanMessage(content='Looking for something in Zurich that feels quiet and bright, ideally not on the ground floor'),
    AIMessage(content='{"hard":{"offer_type":"RENT","city":["Zurich","Zürich"]},"soft":{"quiet":true,"bright":true,"not_ground_floor":true}}'),

    # family: schools + green + playground + safe + low traffic
    HumanMessage(content='Family with one child looking in Zug or Baar, 3.5 rooms, budget up to 3600 CHF, good schools, little traffic, some greenery, playground nearby'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":3.5,"max_rooms":3.5,"max_price":3600,"city":["Zug","Baar"]},"soft":{"good_schools":true,"low_traffic":true,"green_space":true,"playground_nearby":true,"safe":true,"family_friendly":true}}'),

    # furnished + garden + rooftop
    HumanMessage(content='Furnished apartment in Zurich under 2800 CHF, ideally with a garden or rooftop terrace'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"max_price":2800,"city":["Zurich","Zürich"]},"soft":{"furnished":true,"garden":true,"rooftop":true}}'),

    # bedrooms + bathrooms + view + not ground floor
    HumanMessage(content='3-room flat in Bern, ideally 2 bedrooms, 2 bathrooms, mountain view, not ground floor'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":3,"max_rooms":3,"city":["Bern"]},"soft":{"min_bedrooms":2,"min_bathrooms":2,"view":true,"not_ground_floor":true}}'),

    # terrace + cellar + bathtub + modern
    HumanMessage(content='4-room apartment in Basel, modern kitchen, terrace if possible, bathtub and cellar would be great'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":4,"max_rooms":4,"city":["Basel","Bâle"]},"soft":{"modern":true,"terrace":true,"bathtub":true,"cellar":true}}'),

    # walkable shopping + good transport + near lake + safe
    HumanMessage(content='Apartment near Zurich lake, safe area, good tram connection, shops walkable, around 3 rooms'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":3,"max_rooms":3,"city":["Zurich","Zürich"]},"soft":{"near_lake":true,"safe":true,"good_transport":true,"walkable_shopping":true}}'),

    # good layout + bright + good transport (commuter query)
    HumanMessage(content='2.5 to 3 rooms in Zurich, good layout, bright, max 25 min commute to HB, at least 65 m², balcony'),
    AIMessage(content='{"hard":{"offer_type":"RENT","object_category":["Wohnung"],"min_rooms":2.5,"max_rooms":3,"min_area":65,"city":["Zurich","Zürich"],"features":["balcony"]},"soft":{"good_layout":true,"bright":true,"good_transport":true,"not_ground_floor":true}}'),
]
