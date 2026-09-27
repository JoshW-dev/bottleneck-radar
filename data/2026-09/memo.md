# AI supply bottleneck, September 2026

## The call: Memory chips (HBM, DRAM, NAND)

Contract prices for DRAM and NAND are almost nine times what they were a year ago.

Korea exported $40.9B of memory chips in August, up 290% from $10.5B a year earlier, while its system chip exports grew 24%. Most of the memory jump is price. The DDR5 16Gb contract price was $46.50, up 786%, and the NAND contract price was $30.48, up 793%. Hyperscaler capex grew 84% to $586.4B over the last four quarters, so the value of memory exports is growing more than three times as fast as the buildout behind it. Prices move this far only when buyers can't get the volume they ordered, and a new memory fab takes more than a year to add supply.

## Ranking

| Input | Tightness | Demand | Supply |
|---|---:|---|---|
| Memory chips (HBM, DRAM, NAND) | 5/5 | Korean memory exports were $40.9B in August, up 290% y/y, against 24% growth for system chips. | DDR5 16Gb contract $46.50 (+786% y/y) and NAND contract $30.48 (+793%). Prices are doing the adjusting because volume can't. |
| Large gas turbines | 4/5 | The last four quarters of capex equal about 36 GE 7HA.03 turbines, 16 more than the year before, on assumed conversion factors. | GE Vernova holds 116 GW of backlog and slot reservations, 9.7 years at the 3 GW it shipped in Q2. Siemens Energy holds 95 GW, about 4 years, entered by hand as of June 30. |
| Grid connections (transformers, switchgear, transmission, on-site power) | 3/5 | ERCOT has qualified 66.4 GW of large loads as base load and 127.9 GW more as studied load (Sep 11 update). | The data has no rate at which connections get built. An Aug 3 directive added an audit step with an unknown effect on the timeline. |
| Leading-edge chips and packaging | 3/5 | Taiwan's electronics export orders were $45.8B in August, up 84% y/y. ICT orders rose 101%. | No direct supply series. Orders measure demand, and they're growing about as fast as capex (+84%), so the data shows no shortfall. |

## Who owns it

SK Hynix (000660), Micron Technology (MU), Sandisk (SNDK), Samsung Electronics (005930), Kioxia (285A)

## The consensus trade

Nvidia (NVDA), Broadcom (AVGO), Microsoft (MSFT), Alphabet (GOOGL/GOOG), Amazon (AMZN), Meta Platforms (META)

## What would prove this wrong

| Figure | Threshold | Why |
|---|---|---|
| Korean memory chip exports for September, due from MOTIR on Oct 1 | Under +100% y/y | A drop from +290% to under +100% in one month would mean prices or volumes are easing faster than a shortage allows. |
| DDR5 16Gb contract price in the same release | Below $46.50, August's level | A falling contract price means supply has caught up with orders. |
| NAND contract price in the same release | Below $30.48 | The same test for flash, which is most of what Sandisk and Kioxia sell. |
| Hyperscaler capex over the last four quarters, once the Q3 10-Qs are in | Growth under +50% y/y | The memory orders come from this buildout, so a sharp slowdown in capex would ease the shortage. |

## Since last month

This is the first note.

## Data gaps

- Siemens Energy and MHI turbine figures were entered by hand from June 30 results decks, 88 days old.
- ERCOT's Batch Zero figures were entered by hand as of Sep 11, and the Aug 3 directive's effect on its timeline is unknown.
- MHI doesn't report shipments in GW, so it has no years-of-backlog figure.
- Leading-edge chips have no supply series. Taiwan's export orders measure demand for Taiwanese electronics.
- Four conversion factors are unverified: data center share of capex, IT power share, kW per GPU and floor space per MW.
- Only Meta states capex guidance in its filings. The others guide on earnings calls, which this data doesn't include.

## The numbers

| Figure | Value | As of | Source |
|---|---|---|---|
| Hyperscaler capex, trailing 4 quarters | $586B (+84% y/y) | to 2026-08-31 | SEC XBRL |
| Same capex in physical terms | 15.5 GW, 6.5M GPUs, 1.88B GB of HBM, 36 turbine-equivalents |  | config/assumptions.yaml |
| Korea memory chip exports | $40.9B (+290% y/y) | 2026-08 | [MOTIR](https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/172145/view?mno=&pageIndex=1) |
| DDR5 16Gb contract price | $46.50 (+786% y/y) | 2026-08 | [MOTIR](https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/172145/view?mno=&pageIndex=1) |
| Taiwan export orders, electronics | $45.8B (+84% y/y) | 2026-08 | [MOEA](https://service.moea.gov.tw/EE520/opendata/經濟部統計處_外銷訂單_電子產品.csv) |
| GE Vernova gas backlog + slot reservations | 116 GW, 9.7 years of shipments | 2026-Q2 | [parsed](https://www.sec.gov/Archives/edgar/data/1996810/000199681026000147/gevpressrelease2q26.htm) |
| Siemens Energy gas backlog + slot reservations | 95 GW, 4.0 years of shipments | 2026-06-30 | [manual](https://assets.siemens-energy.com/dam/3e846440-66dd-4a56-be75-b49d004e6741/2026-08-05_Q3_Analyst_presentation-pdf_Original%20file.pdf) |
| Mitsubishi Heavy Industries gas backlog + slot reservations | 35 GW | 2026-06-30 | [manual](https://www.mhi.com/finance/library/result/pdf/fy20261q/presentation.pdf) |
| ERCOT large loads qualified for Batch Zero | 66.4 GW base + 127.9 GW studied | 2026-09-11 | [manual](https://www.ercot.com/files/docs/2026/09/11/14-Batch-Zero-Update.pdf) |

---

Generated 2026-09-27 by bottleneck-radar from a call claude-opus-5-5 made on the saved evidence packet, outside the API run. Research notes only. Nothing here is investment advice.
