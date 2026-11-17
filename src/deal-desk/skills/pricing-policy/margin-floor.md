# Margin floor and P&L method

> Illustrative planning record; decisions are internal to this Deal System and do not submit a customer order or external offer.

This explains the method so you can describe results. Never run this math yourself: the Deal Economics
agent and `evaluate_deal` compute every number.

## The floor

**Deal-life gross margin must be >= 32 %.** The agent cannot approve anything below it, and below
28 % only the CFO can approve.

## How deal-life GM is computed (the waterfall)

```
  List revenue (TCV, contract-start prices)
- Rebates incl. earned growth kicker              (contra-revenue)
- MDF (sell-through MDF at expected claim rate)   (contra-revenue, NOT opex)
+ Cost pass-through recovery after protection     (capped at CPI if a CPI cap applies)
= Net revenue
- COGS incl. forecast sensor-component increase (years 2-3)
- Payment-terms financing cost (TCV x 7 % WACC x days/365)
= Deal margin;   GM % = deal margin / net revenue
```

## The two classic mistakes (seen in our historical reviews)

1. **Multi-year price protection without the cost forecast.** Protection longer than 12 months
   overlaps the year-2 sensor-component increase. Caldova pays the increase but cannot pass it through.
   If you ignore the forecast, you overstate GM by 1-3 points and approve deals that are below the floor.
   Price-protection cost is zero at 12 months and material at 18-24 months.
2. **MDF treated as opex.** MDF is a payment to the customer, so it is **contra-revenue**. If you put
   it "below the line", net revenue and GM % are overstated.

## Northwind example (expected values; always report the tool's actual numbers)

| | Ask | Recommended counter |
|---|---|---|
| Terms | 18 % · Net-90 · 24 mo · $1.2M MDF | 12 % + 2 % kicker · Net-60 · 12 mo + CPI cap · $900K sell-through MDF |
| Deal-life GM | **26.4 %** (below floor) | **33.1 %** |
| Price-protection cost | $0.80M | $0.32M |
| Customer value vs. ask | 100 % | 85 % |
