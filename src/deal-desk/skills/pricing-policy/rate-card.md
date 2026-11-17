# Pricing policy and rate card

> Illustrative planning record; decisions are internal to this Deal System and do not submit a customer order or external offer.

## Standard rate card (retail pharmacy and mass channel)

| Term | Standard | Notes |
|---|---|---|
| Volume rebate | **8 %** of list revenue | paid quarterly in arrears as a credit; **contra-revenue** |
| Payment terms | **Net-45** | |
| Price protection | **12 months** from contract start | after that, Caldova may pass component cost increases through as price adjustments |
| Co-marketing (MDF) | **1 % of TCV** | **contra-revenue**, never opex; prefer sell-through-tied MDF |
| Contract length | 1-3 years | multi-year deals must be priced with the component cost forecast |

## Concessions

A concession is anything more generous to the customer than the rate card. Measure the size of a
package as **concession $ = deal margin at the rate card - deal margin at the package**. This is
deal-life and includes cost-forecast effects. The pricing engine returns it as `concession_usd`.

Typical concession levers, ordered from most to least cost-effective for Caldova:

1. **Growth kicker.** Extra rebate (<= 2 %) on all volume in a contract year where volume is >= 110 % of commit. It pays only if the customer grows.
2. **CPI cap after the protection period.** Price adjustments limited to CPI (3 %/yr). Customers value price certainty highly. It costs Caldova little when the forecast pass-through is close to CPI.
3. **Sell-through-tied MDF.** Caldova pays only on verified sell-through (historical claim rate about 80 %).
4. Payment terms up to Net-60.
5. Base rebate points.
6. **Price protection beyond 12 months.** This is the most expensive lever when a component cost increase is forecast, because Caldova cannot pass the increase through. See `margin-floor.md`.

## Component cost forecast (FY2027-2029)

Supply-chain planning forecasts a **sensor-component cost increase** starting in contract year 2
(2028). It is about 5.0 % of list price for the standard home-diagnostics mix, plus a further step to
5.5 % in year 3. Contracts recover this through post-protection price adjustments. Every
multi-year deal must be priced against this forecast (`data/generated/cost_forecast.json` in the sample repo).
