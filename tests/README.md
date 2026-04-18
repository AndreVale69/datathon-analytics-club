# Tests

This directory contains both the existing harness tests and the new geocoding coverage for place resolution.

## Geocoding Tests

The geocoding-specific tests live in [test_geocoding.py](../tests/test_geocoding.py).

They cover:

- parsing the Swiss GeoAdmin API response in `app/core/geocoding.py`
- resolving explicit place phrases such as `near Zurich HB`
- preserving explicit radii such as `within 1.5 km of Lausanne station`
- end-to-end filtering through the `/listings` API after a place is geocoded

These tests do not call the live GeoAdmin service. They mock the HTTP response or patch the geocoding helper directly, so they are deterministic and do not require network access.

## Why The Tests Are Structured This Way

The repository currently has broader bootstrap/import tests that depend on the local raw dataset. Those tests are separate from the geocoding work.

The geocoding tests use a tiny self-contained SQLite fixture instead of the full raw-data import path. That keeps the tests focused on:

- query parsing for place phrases
- geocoding result handling
- geographic filtering integration

and avoids unrelated dataset/bootstrap failures.

## Running The Tests

Run only the geocoding coverage:

```bash
uv run pytest tests/test_geocoding.py
```

Run the geocoding tests plus the lightweight pipeline smoke test:

```bash
uv run pytest tests/test_geocoding.py tests/test_pipeline.py
```

If `pytest` is not directly available in the shell, prefer `uv run pytest ...`, because this project documents `uv` as the supported runner.

## Behavior Without OpenAI Configuration

`app/participant/hard_fact_extraction.py` is now a thin orchestrator.

The LLM-backed pieces are split into separate modules:

- `app/participant/constraint_extractor/` for normal hard filters
- `app/participant/geolocation_extractor.py` for place-resolution intent

If any of these happen:

- `langchain-core` is not installed
- `langchain-openai` is not installed
- `OPENAI_API_KEY` is missing
- the OpenAI client or extractor initialization fails for another reason

then `extract_constraints(...)` falls back to:
then the LLM-backed extractor modules fall back to empty structured outputs:

```python
HardFilters()
```

or, for place intent:

```python
GeolocationIntent()
```

This means:

- import-time failures should not break `tests/test_geocoding.py`
- basic pipeline tests can still run without OpenAI credentials
- the application degrades cleanly instead of crashing during import or startup

What you lose in that fallback mode:

- LLM-extracted city / price / room / feature constraints from free text

What still works:

- explicit structured filter requests
- local geocoding enrichment when the geolocation extractor is available and returns a place query
- downstream search and ranking on the resulting hard filters

## Behavior Without Geocoding Access

The production geocoding helper calls the Swiss GeoAdmin search endpoint configured by:

- `GEOCODING_API_BASE_URL`
- `GEOCODING_TIMEOUT_SECONDS`

If the geocoding request fails, returns no result, or the payload is malformed, the code falls back to the existing hard filters without adding `latitude`, `longitude`, or `radius_km`.

So the search still works, but place-resolution-based geographic filtering will not be applied for that query.
