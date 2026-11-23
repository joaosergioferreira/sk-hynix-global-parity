# SK hynix — Global Parity Monitor

**Self-updating dashboard** comparing Korea ordinary 000660.KS, Frankfurt GDR HY9H.F, Nasdaq ADR SKHY, and SK Square 402340.KS.

## Start

No Python dependencies beyond Python 3.10+: 

```bash
python app.py
```

Open http://localhost:8501. The browser refreshes automatically every 60 seconds while open; the backend caches requests for 75 seconds. No ChatGPT API, paid subscription, or scheduled ChatGPT automation is required.

## Put online

- Push the contents of this directory to a private or public GitHub repository.
- In Render, choose **New > Blueprint** and connect that repository; `render.yaml` contains the service configuration.
- Or deploy on any Python hosting platform with command `python app.py` and `PORT` supplied by host. The app listens on 0.0.0.0.
- Free-tier hosting may sleep when unused. A provider with always-on uptime is required for 24/7 operation.

## Feed limitations

The backend uses public **Yahoo Finance Chart** endpoints, best-effort and **unofficial**, with no SLA and possible regional blocking or rate limiting. Price updates may be delayed and exchanges do not trade simultaneously. The dashboard shows each original venue timestamp and never labels a cached close as a true simultaneous executable price. This is a refreshing dashboard, not a professional real-time exchange market-data entitlement.

If data is unavailable, the dashboard retains the clearly dated sample for inspection and offers manual price overrides. For low-latency trading, replace `retrieve_chart()` with your licensed multi-exchange provider and provide bid/ask spreads, FX bid/ask, execution costs, corporate-action and settlement adjustments.

## Market-model settings

The NAV model follows SK Square's official 20 Nov 2026 disclosures: 146,100,000 Hynix shares; 131,923,998 SK Square shares; KRW 4.69tn in other assets net of liabilities (total NAV 167.3tn less Hynix stake 162.61tn). These inputs are **not** self-updating; review and update in `app.py` following corporate actions, stake changes, and new SK Square NAV disclosures. UI shows the official basis date.

Calculations:

- `HY9H_GDR_premium = HY9H_EUR * EURKRW / 000660_KRW - 1`
- `SKHY_ADR_premium = SKHY_USD * 10 * USDKRW / 000660_KRW - 1`
- `SKHY_vs_HY9H = SKHY_USD * 10 * USDKRW / (HY9H_EUR * EURKRW) - 1`
- `SK_Square_NAV = Hynix_share_count * Hynix_price + other_assets_net`
- `SK_Square_NAV_discount = 1 - Square_market_cap / Square_NAV`
- `Square_lookthrough_price_per_Hynix = (Square_market_cap - other_assets_net)/Hynix_share_count`

**Important:** A visible price gap is not an executable arbitrage. SKHY ADR new issuance and conversion is constrained; venue time zones, depositary fees, price availability, borrow constraints and settlement risk matter. SK Square has holding-company risk, taxes and uncertain NAV convergence.

## Reference links

- Citi SKHY program: https://depositaryreceipts.citi.com/adr/guides/pgm_d.aspx?cusip=78392B206&pageId=15&subpageid=105
- Citi HY9H/HYXS program: https://depositaryreceipts.citi.com/adr/guides/dsfann.aspx?cusip=78392B107&recdate=20250307
- SK Square official NAV: https://www.sksquare.com/eng/ir/nav.do
- SK Square 13G: https://www.sec.gov/Archives/edgar/data/2120882/000119312526459140/xslSCHEDULE_13G_X02/primary_doc.xml

This software is educational and not investment or execution advice.
