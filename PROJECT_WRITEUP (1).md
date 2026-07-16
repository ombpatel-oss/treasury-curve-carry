# 2s10s Treasury Curve Carry/Roll Strategy

*A systematic rates strategy that trades the shape of the U.S. Treasury curve — and a case study in why naive carry loses money.*

## The idea

Instead of betting on the *direction* of interest rates, this strategy bets on the *shape* of the yield curve — specifically the **2s10s**, the gap between the 2-year and 10-year Treasury yields. Each month it computes the **carry + roll-down** of a 2s10s curve trade and puts on whichever side the carry favors: a **steepener** when carry is positive, a **flattener** when it's negative. Both legs are sized **DV01-neutral**, so the position is a pure bet on the curve's shape, not on the level of rates.

## Method

- **Data:** FRED constant-maturity Treasury yields (3M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y), 2015–2026, month-end.
- **Signal:** carry (yield earned minus funding cost at the 3-month rate) plus roll-down (price drift as each bond ages down a static curve).
- **Sizing:** DV01-neutral — hold more face of the 2Y, less of the 10Y, so each leg has equal sensitivity to a rate move.
- **Costs:** a bid-offer charge is applied every time the position flips.

## Result: it loses money — and that's the point

| Metric | Value |
|---|---|
| Months traded | 138 (~11.5 years) |
| Time in steepener | 50% |
| Total P&L* | −122 |
| Max drawdown* | 258 |
| Annualized Sharpe | **−0.23** |
| Monthly hit rate | 50% |
| Worst month | **March 2023 (−30)** |

\*P&L is in "per \$1-of-DV01-per-leg" units; the absolute scale is arbitrary. What matters is the shape of the equity curve and the Sharpe ratio.

The strategy posts a **negative Sharpe** and loses money overall. Notice that the max drawdown (258) is *larger* than the final loss (−122): the strategy was profitable through the calm 2015–2021 years and then gave it all back — and more — in 2022–2023.

## The key finding: carry in rates has negative skew

The strategy doesn't lose because carry is a bad idea. It loses because **carry trades have negative skew** — they collect small, steady gains for months, then take one catastrophic loss when the regime shifts. On a desk this is called *picking up pennies in front of a steamroller*. The naive signal captures the pennies but is blind to the steamroller.

## The blow-up: March 2023 (Silicon Valley Bank)

The single worst month was March 2023, and it's a textbook illustration.

Through 2022 the Fed hiked aggressively and the curve inverted deeply — the 2Y yield rose *above* the 10Y. On an inverted curve the carry math flips, which pushed the signal into **flatteners**: the strategy was effectively betting the curve would stay inverted. Then SVB collapsed:

- The **2-year yield fell ~100bp in three days** — its largest such move since the 1987 Black Monday crash — as investors slashed Fed-hike expectations and fled to the safety of government debt.
- The **10-year fell only ~17bp**, because the shock was about the Fed's near-term path, not long-run growth.
- The 2s10s inversion narrowed from roughly **−107bp to −47bp** — a violent **bull-steepening**.

A steepener would have profited enormously that month. The strategy's flattener got run over. This one month is the clearest evidence of the negative-skew problem baked into the naive signal.

## What I'd fix

- **Regime filter / trend overlay** — don't carry a flattener into a steepening regime; stop fighting the Fed at turning points.
- **Risk controls** — a stop-loss or volatility-scaled position sizing to cap the tail loss.
- **Tradeable instruments** — replace constant-maturity yields (not tradeable) with Treasury futures (ZT/ZF/ZN/ZB).
- **Better DV01** — use actual par-bond duration instead of the duration ≈ maturity approximation.

## Honest simplifications

Constant-maturity yields are treated as tradeable (a real desk trades futures or specific bonds); DV01 is approximated as duration ≈ maturity. Both are flagged in the code and would be the first upgrades. Naming these is deliberate — knowing where the model departs from reality is the point.

---

## Two-minute interview version

> I built a systematic 2s10s curve strategy that trades carry and roll, DV01-neutral. It loses money — negative Sharpe — and that's the interesting part. Carry in rates has negative skew: you collect small gains for months, then get steamrolled at a regime shift. My worst month was March 2023: the curve was deeply inverted, so my carry signal had me in a flattener; then SVB collapsed, the 2-year crashed 100bp in three days, the curve bull-steepened, and the flattener blew up. The takeaway is that a naive carry signal needs a regime filter or a risk overlay so it isn't fighting the Fed at a turning point.
