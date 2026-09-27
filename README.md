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
| Dashboard | `radar site` | Renders the latest month in `data/` into `site/index.html` | none |

`radar run` does all of it in order.

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

- `data/` holds the public outputs and is committed: `13f/<cik>/<period>.json`, plus `demand.json`, `supply.json`, `bottleneck.json` and `memo.md` for each month.
- `private/` holds anything about your account: positions, the order list and exposure. Git ignores it.
- `config/` holds the inputs you maintain by hand:
  - `assumptions.yaml` has every factor that turns dollars into physical units, each with a source. Entries marked `unverified` still need one.
  - `owners.yaml` lists which companies make each input. The model can only name companies from this list.
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

`radar site` renders one static page from `data/`: the monthly call, the four inputs, demand, supply and the fund's book, with a table view under every chart. Vercel serves `site/` as it is (see `vercel.json`), so there's no build step, and every push to `main` redeploys it. The page only reads `data/`, so account data can't reach it.

## Running it monthly

GitHub Actions runs the public stages on the 24th of each month, after Taiwan publishes its export orders (`.github/workflows/monthly.yml`). The workflow commits `data/` and `site/`, and Vercel redeploys from that commit. It needs a repository variable named `SEC_USER_AGENT`, plus an `ANTHROPIC_API_KEY` secret for the memo. You can also start it by hand from the Actions tab.

Stage 4 reads your brokerage account, so it never runs on GitHub, where Actions logs are public. `scripts/monthly.sh` pulls the refresh and runs it locally. This cron entry runs it two hours after the workflow:

```cron
0 16 24 * * /path/to/bottleneck-radar/scripts/monthly.sh >> /var/log/bottleneck-radar.log 2>&1
```

## Caveats

- A 13F shows US long positions 45 days after the quarter ends. Shorts, cash and leverage don't appear, so the clone copies one slice of the fund.
- Capex here is cash paid for property and equipment. It leaves out finance leases and includes spending that isn't AI data centers.
- The physical conversions are rough. Change the factors in `config/assumptions.yaml` and rerun.
- Taiwan's export orders measure demand for Taiwanese electronics. Leading-edge chips have no direct supply series yet.

## Tests

```bash
uv run pytest
```
