# SEC EDGAR API notes

All examples below were run against the live API and confirmed working.

## Required: User-Agent header

EDGAR blocks requests without a proper identifying `User-Agent` (returns `403`). It must look
like `AppName contact@email.com` — a generic `curl/8.0` or missing header both get rejected.

```bash
curl -A "sec-intelligence-mcp your.name@email.com" "https://data.sec.gov/submissions/CIK0000320193.json"
```

Confirmed: without a proper User-Agent, `data.sec.gov` returns `HTTP 403`.

## Rate limit

Max **10 requests/second**. Add `time.sleep(0.1)` between calls (or use a small async
semaphore) to stay under it — SEC will temporarily block your IP if you exceed it.

## 1. Ticker → CIK mapping

One static file with every ticker mapped to its CIK (Central Index Key, SEC's company ID):

```bash
curl -A "sec-intelligence-mcp you@email.com" "https://www.sec.gov/files/company_tickers.json"
```

Returns `{"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}, "1": {...}, ...}`
— a dict keyed by row index, not by ticker. Download once, build a `ticker -> cik` map, cache it
(see Issue 2.2). The CIK must be zero-padded to 10 digits for the other endpoints below
(`1045810` -> `0001045810`).

## 2. List a company's filings

```bash
curl -A "sec-intelligence-mcp you@email.com" "https://data.sec.gov/submissions/CIK0000320193.json"
```

Key field: `filings.recent`, a dict of parallel arrays (index `i` is the same filing across all
arrays) with `form`, `filingDate`, `accessionNumber`, `primaryDocument`, etc. Filter
`form == "10-K"` (or `"10-Q"`) to get annual/quarterly reports. Example row for Apple's latest
10-K:

```json
{"form": "10-K", "filingDate": "2025-10-31", "accessionNumber": "0000320193-25-000079",
 "primaryDocument": "aapl-20250927.htm"}
```

If a company has >1000 filings, older ones move to separate paginated files listed under
`filings.files` — not needed for "recent 10-Ks" use cases.

## 3. Build the actual filing document URL

```
https://www.sec.gov/Archives/edgar/data/{cik_no_leading_zeros}/{accession_no_dashes}/{primaryDocument}
```

- `cik_no_leading_zeros`: the CIK as a plain int (`320193`, not `0000320193`)
- `accession_no_dashes`: `accessionNumber` with the dashes stripped (`0000320193-25-000079` ->
  `000032019325000079`)

```bash
curl -A "sec-intelligence-mcp you@email.com" \
  "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm"
```

Confirmed: `HTTP 200`, ~1.5MB of HTML — the actual 10-K document.

There's also always a filing index page at the same path, useful when a filing has multiple
documents (exhibits, etc.) and you need to figure out which one is the primary 10-K:

```
https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{accession-with-dashes}-index.htm
```

## 4. Company facts (XBRL structured financial data)

Optional — gives structured numeric data (revenue, EPS, etc.) without parsing the filing text,
useful later if we want exact financial figures rather than text-based answers:

```bash
curl -A "sec-intelligence-mcp you@email.com" "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
```

## 5. Full-text search

Search across all filings' text (not limited to one company):

```bash
curl -A "sec-intelligence-mcp you@email.com" \
  "https://efts.sec.gov/LATEST/search-index?q=%22NVIDIA%22&forms=10-K&dateRange=custom&startdt=2024-01-01&enddt=2024-12-31"
```

`q` is URL-encoded query text; `forms` filters by filing type; `startdt`/`enddt` filter by date
(YYYY-MM-DD). Returns matching filings with `_id` in the form
`{accessionNumber}:{primaryDocument}`.
