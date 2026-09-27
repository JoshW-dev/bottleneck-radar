# bottleneck-radar

A monthly research pipeline for the AI data center buildout. It copies a hedge fund's 13F, turns hyperscaler capex into megawatts and memory, works out which physical input is tightest, and checks how much of your IBKR portfolio sits with the companies that make it.

The idea comes from a TikTok by [Angus the Nontechnical](https://www.tiktok.com/@angusthenontechnical), who ran these four steps as prompts. This version pulls the data in code so each month's numbers line up with the last, and uses a model only to make the call and write the memo.

It's for research. It doesn't give investment advice or place orders.

The dashboard is live at [bottleneck-radar-two.vercel.app](https://bottleneck-radar-two.vercel.app).

## The four stages

| Stage | Command | What it does | Model |
|---|---|---|---|
| 1. Clone the book | `radar clone` | Pulls Situational Awareness LP's latest 13F from EDGAR, maps CUSIPs to tickers, weights the long stock and sizes an order list against your account. The list is never sent. | none |
| 2. Demand | `radar demand` | Capex for Microsoft, Amazon, Alphabet, Meta and Oracle from SEC XBRL, converted into GW, GPUs, HBM, floor space and turbines | none |
| 3a. Supply | `radar supply` | Korean memory chip exports, Taiwan export orders, gas turbine backlogs and ERCOT's large-load queue | none |
| 3b. Bottleneck | `radar bottleneck` | Ranks the four inputs, picks one, names who owns it and what would prove the call wrong, and writes `memo.md` | Claude Sonnet |
| 4. Exposure | `radar ibkr`, `radar exposure` | Reads your positions through an IBKR Flex query and splits them into bottleneck owners, the consensus AI trade and everything else | none |
| Picks | `radar picks` | Freezes the call's owners as that month's picks at equal weight, with the consensus trade kept as the comparison. A month's picks are never rewritten. | none |
| Tracking | `radar performance` | Prices the picks, a point-in-time copy of the fund's 13F filings, the consensus basket and the S&P 500 for the year so far, in dollars | none |
| Predictions | `radar predict`, `radar predictions` | Freezes a set of dated predictions with a timestamp and a SHA-256, then checks each one against the data when it comes due | none |
| Dashboard | `radar site` | Renders the latest month in `data/` into `site/index.html` | none |

`radar run` does all of it in order. A month's call is made once: rerunning `radar bottleneck` keeps it unless you pass `--force`.

## Setup

You need [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
git clone https://github.com/JoshW-dev/bottleneck-radar
cd bottleneck-radar
uv sync
cp .env.example .env
```

Then fill in `.env`:

- `SEC_USER_AGENT` is your name and email. SEC blocks scripts that don't identify themselves.
- `ANTHROPIC_API_KEY` is for the Stage 3 memo. Without it, `radar bottleneck` saves its prompt to `data/<month>/bottleneck-prompt.md` and stops.
- `IBKR_FLEX_TOKEN` and `IBKR_FLEX_QUERY_ID` are for Stage 4. Setup is below.

### IBKR Flex setup

A Flex Web Service token can only download reports, so Stage 4 can't trade.

1. In IBKR's Client Portal, go to Performance & Reports, then Flex Queries.
2. Create an Activity Flex Query in XML format, period Last Business Day, with two sections:
   - Open Positions at Summary level of detail, with at least Asset Class, Symbol, Underlying Symbol, Description, Currency, FX Rate To Base, Listing Exchange, ISIN, Quantity, Mark Price and Position Value.
   - Net Asset Value (NAV) in Base, with Total.
3. Note the query ID.
4. Open Flex Web Service Configuration, turn it on and generate a token. If you can, restrict it to the IP address of the machine that runs the job.
5. Add both to `.env` and run `uv run radar ibkr`.

## Where things go

- `data/` holds the public outputs and is committed: `13f/<cik>/<period>.json`, `picks/<month>.json`, `performance.json`, `predictions/<set>.json`, `prediction-results.json`, plus `demand.json`, `supply.json`, `bottleneck.json` and `memo.md` for each month.
- `private/` holds anything about your account: positions, the order list and exposure. Git ignores it.
- `config/` holds the inputs you maintain by hand:
  - `assumptions.yaml` has every factor that turns dollars into physical units, each with a source. Entries marked `unverified` still need one.
  - `owners.yaml` lists which companies make each input, with the listing the tracker prices and a line on why each one is exposed. The model can only name companies from this list.
  - `cusip_overrides.yaml` fixes 13F rows that a fund filed under the wrong CUSIP. Each entry says how it was checked.
  - `manual.yaml` has figures copied from PDFs that don't have a parser yet: Siemens Energy and MHI turbine backlogs and ERCOT's large-load queue. The memo flags entries older than 120 days.

## Data sources

| Input | Source | Updated |
|---|---|---|
| 13F holdings | SEC EDGAR, with tickers from OpenFIGI | Quarterly, 45 days after quarter end |
| Hyperscaler capex | SEC XBRL company facts | With each 10-Q |
| Capex guidance | Earnings release exhibits on EDGAR. Meta is the only one that puts guidance there. | Quarterly |
| Korean memory exports and DRAM prices | Trade ministry (MOTIR) monthly release PDF | 1st of each month |
| Taiwan export orders | Ministry of Economic Affairs open data CSVs | Around the 20th |
| Gas turbine backlogs | GE Vernova's earnings release on EDGAR; Siemens Energy and MHI from `manual.yaml` | Quarterly |
| Grid connection queue | ERCOT's Batch Zero update, from `manual.yaml` | Monthly |
| Prices for the order list | Yahoo's chart API | Daily |

## Dashboard

`radar site` renders one static page from `data/`: the monthly call, the four inputs, demand, supply and the fund's book, with a table view and a copy-data button under every chart. Vercel serves `site/` as it is (see `vercel.json`), so there's no build step, and every push to `main` redeploys it. The page only reads `data/`, so account data can't reach it.

The design follows the two `/taste` studies in `docs/taste/`, of Stripe's homepage and Ramp's AI Index. Color is reserved for data, the four input figures light up one at a time, and the globe in the hero draws arcs from where each input is made to two US data center markets. The globe uses [globe.gl](https://github.com/vasturiano/globe.gl), and its land dots come from [Natural Earth](https://www.naturalearthdata.com/) (public domain). Motion switches off for readers who ask their system for reduced motion.

## Picks and tracking

Each month's call names the companies that own the bottleneck. `radar picks` saves them to `data/picks/<month>.json` at equal weight, and later runs leave that file alone, so the record can't be edited after the fact. `radar performance` then writes `data/performance.json` with four lines for the year so far:

- The picks, bought at the first close after the call is published and held until the next call replaces them.
- A 13F clone that buys each of the fund's filings at the first close after its filing date, starting from the book it had published before January. `radar clone` saves every filing the tracker needs.
- The consensus trade named in the call, at equal weight.
- The S&P 500, through SPY.

Prices are Yahoo Finance daily closes adjusted for dividends and splits. Listings in Seoul and Tokyo are converted to dollars at each day's exchange rate.

The dashboard shows the picks from January 1, even though September 2026 was the first call, so everything before the call date is hindsight. It draws that stretch dashed and marks the call. The 13F clone uses only filings that were public at the time, which makes it the fairer test of the year so far.

The September 2026 call was made before the pipeline had an API key: claude-opus-5-5 read the saved prompt outside the API run, and `radar bottleneck --import` put its answer through the same checks as an API call. The call records who made it.

## Predictions

Each prediction has a due date, a stated chance of coming true and a check the code can run by itself. A check reads one number: a figure from Korea's trade release or Taiwan's export orders, GE Vernova's backlog, the hyperscalers' quarterly capex, the fund's 13F, the next monthly call, or how one basket of stocks did against another. `radar predict --import FILE --made-by NAME` freezes a set into `data/predictions/<month>.json` with the UTC time it was made and a SHA-256 of the predictions, and it won't overwrite a set that already exists.

`radar predictions` checks every open prediction and writes `data/prediction-results.json`. It reads the committed data first and fetches what's missing once a prediction is due, so most results land within a day of the release. Each result records the value found, the day that value became public and the UTC time of the check. Once a prediction is settled its result stays put, even if the source later revises the figure. If there's still no data 30 days after the due date, the prediction is marked void and left out of the score.

The score compares how many came true with how many the stated chances say should have (the sum of the chances). The Brier score is the average squared gap between each chance and the outcome: 0 is perfect, and saying 50% every time scores 0.25. The checker recomputes each set's SHA-256 on every run, and the commit history on GitHub shows when each set was frozen.

The first set has 13 predictions due between October 2026 and February 2027. claude-opus-5-5 made them from the September data on Sep 27, 2026.

## Running it monthly

GitHub Actions runs the public stages on the 24th of each month, after Taiwan publishes its export orders (`.github/workflows/monthly.yml`). The workflow commits `data/` and `site/`, and Vercel redeploys from that commit. It needs a repository variable named `SEC_USER_AGENT`, plus an `ANTHROPIC_API_KEY` secret for the memo. You can also start it by hand from the Actions tab.

A second workflow (`.github/workflows/prices.yml`) updates the tracker, checks the open predictions and redraws the dashboard after each US trading day. It reads only public data, so it needs no secrets, though predictions that read SEC filings wait for `SEC_USER_AGENT`.

Stage 4 reads your brokerage account, so it never runs on GitHub, where Actions logs are public. `scripts/monthly.sh` pulls the refresh and runs it locally. This cron entry runs it two hours after the workflow:

```cron
0 16 24 * * /path/to/bottleneck-radar/scripts/monthly.sh >> /var/log/bottleneck-radar.log 2>&1
```

## Caveats

- A 13F shows US long positions 45 days after the quarter ends. Shorts, cash and leverage don't appear, so the clone copies one slice of the fund.
- Capex here is cash paid for property and equipment. It leaves out finance leases and includes spending that isn't AI data centers.
- The physical conversions are rough. Change the factors in `config/assumptions.yaml` and rerun.
- Taiwan's export orders measure demand for Taiwanese electronics. Leading-edge chips have no direct supply series yet.
- A pick's return for the year includes the months before the call that picked it. Judge the picks from the call date on.
- The picks rebalance only when a new call arrives, and the tracker ignores trading costs and taxes.
- Thirteen predictions are too few to judge calibration. The score means something after a few dozen.

## Tests

```bash
uv run pytest
```
