"""
2s10s Treasury CURVE CARRY/ROLL backtest  —  starter version
=============================================================

WHAT THIS DOES (the 7-step arc, in code):
  1. Load Treasury yields for several tenors (FRED, no API key needed).
  2. For each month, compute the CARRY + ROLL of a 2s10s curve trade.
  3. Take the trade the carry favors (steepener if carry+roll > 0, else flattener),
     sized DV01-neutral so it's a pure bet on the curve's SHAPE.
  4. Let the next month actually happen and compute the realized P&L.
  5. Subtract a bid-offer cost whenever the position flips.
  6. Plot the equity curve and print total return / max drawdown / Sharpe.
  7. Eyeball where it breaks (look at 2022-2023).

SIMPLIFICATIONS (say these out loud in an interview — naming them shows maturity):
  * Constant-maturity (CMT) yields are treated as tradeable. They aren't; a real
    desk trades futures (ZT/ZF/ZN/ZB) or specific bonds. This is the biggest one.
  * DV01 per $1 face is approximated as (maturity * 1e-4), i.e. duration ~= maturity.
    Real bonds have duration a bit BELOW maturity. Easy first upgrade.
  * P&L is in "per $1-of-DV01-per-leg" units. The absolute scale is arbitrary; the
    SHAPE of the equity curve and the Sharpe ratio are what matter.

Run it, read the printout, then start changing things. That's the point.
"""

import numpy as np
import pandas as pd

# ------------------------------- Parameters --------------------------------- #
# FRED series id -> tenor in years. These are the curve points we pull.
TENORS = {"DGS3MO": 0.25, "DGS1": 1.0, "DGS2": 2.0, "DGS3": 3.0,
          "DGS5": 5.0, "DGS7": 7.0, "DGS10": 10.0}
SHORT_TENOR = 0.25      # 3-month bill used as the funding (repo) proxy
T_SHORT, T_LONG = 2.0, 10.0   # the two legs of the 2s10s trade
H = 1.0 / 12.0          # holding horizon = 1 month
TC_BP = 0.5             # bid-offer cost per leg, in bp of yield, charged on a flip
START = "2015-01-01"    # history start date


# ------------------------------- Data loading ------------------------------- #
def load_yields():
    """Pull real yields from FRED (keyless). If offline, fall back to synthetic
    demo data so the script always runs and you can see the output shape."""
    try:
        from pandas_datareader import data as pdr
        raw = pdr.DataReader(list(TENORS.keys()), "fred", START)
        df = raw.rename(columns=TENORS).sort_index()
        df = df.resample("ME").last().dropna()          # month-end snapshots
        print(f"Loaded REAL FRED data: {df.index.min().date()} -> {df.index.max().date()}"
              f"  ({len(df)} months)\n")
        return df
    except Exception as e:
        print(f"FRED unavailable ({type(e).__name__}) -> using SYNTHETIC demo data.")
        print("Install real data with:  pip install pandas-datareader\n")
        return _synthetic_yields()


def _synthetic_yields():
    """A plausible fake history: normal upward curve -> inverts (2022-style) ->
    re-steepens. ONLY for seeing the code work offline. Not a real result."""
    dates = pd.date_range("2015-01-31", periods=120, freq="ME")
    t = np.arange(len(dates))
    # short rate: low, ramps up (hikes), then eases
    short = 0.5 + 4.5 / (1 + np.exp(-(t - 70) / 6)) - 1.5 / (1 + np.exp(-(t - 100) / 6))
    # term spread: starts +2%, goes negative (inversion), then back positive
    slope = 2.0 - 3.0 / (1 + np.exp(-(t - 72) / 5)) + 1.8 / (1 + np.exp(-(t - 102) / 6))
    cols = {}
    for key, tau in TENORS.items():
        frac = np.log(tau / 0.25) / np.log(10 / 0.25)         # 0 at 3mo, 1 at 10y
        noise = np.random.default_rng(int(tau * 100)).normal(0, 0.03, len(dates))
        cols[key] = short + slope * frac + noise
    return pd.DataFrame(cols, index=dates).rename(columns=TENORS)


# ------------------------------- Backtest ----------------------------------- #
def curve_yield(curve, tau):
    """Linear-interpolate the yield at any maturity from the pulled tenor grid.
    Needed for roll-down: a 10y today becomes a ~9.9y next month."""
    xs = np.array(sorted(curve.index))
    ys = curve.reindex(xs).values.astype(float)
    return float(np.interp(tau, xs, ys))


def backtest(df):
    tenors = sorted(TENORS.values())

    # DV01 per $1 face (duration ~= maturity approximation), and the face amount
    # of each leg that gives exactly $1 of DV01 per basis point.
    dv01_short = T_SHORT * 1e-4
    dv01_long = T_LONG * 1e-4
    face_short = 1.0 / dv01_short          # more face of the 2y  (~5000)
    face_long = 1.0 / dv01_long            # less face of the 10y (~1000)

    rows = []
    prev_pos = 0.0
    dates = df.index
    for i in range(len(dates) - 1):
        d, d_next = dates[i], dates[i + 1]
        curve = pd.Series({tau: df.loc[d, tau] / 100.0 for tau in tenors})  # -> decimals
        y2, y10, r = curve[T_SHORT], curve[T_LONG], curve[SHORT_TENOR]

        # ---- SIGNAL: carry + roll of the STEEPENER (long 2y, short 10y) over H ----
        # Carry = coupon income - funding on the net-long notional.
        income = (y2 * face_short - y10 * face_long) * H
        funding = r * (face_short - face_long) * H
        carry = income - funding

        # Roll = price drift as each bond ages down a static curve (in bp * legDV01,
        # and legDV01 = $1/bp by construction). Long leg gains; short leg loses.
        roll_2 = (y2 - curve_yield(curve, T_SHORT - H)) * 1e4
        roll_10 = (y10 - curve_yield(curve, T_LONG - H)) * 1e4
        roll = roll_2 - roll_10

        signal = carry + roll                       # steepener's expected static return
        position = 1.0 if signal > 0 else -1.0      # +1 = steepener, -1 = flattener

        # ---- REALIZED P&L over the next month ----
        y2n = df.loc[d_next, T_SHORT] / 100.0
        y10n = df.loc[d_next, T_LONG] / 100.0
        d_spread_bp = ((y10n - y2n) - (y10 - y2)) * 1e4   # steepener gains if spread widens
        pnl_directional = position * d_spread_bp          # legDV01 = $1/bp
        pnl_carry_roll = position * signal
        cost = TC_BP * 2.0 if position != prev_pos else 0.0   # two legs traded on a flip
        pnl = pnl_directional + pnl_carry_roll - cost

        rows.append({"date": d_next, "position": position, "signal": signal,
                     "pnl_dir": pnl_directional, "pnl_cr": pnl_carry_roll,
                     "cost": cost, "pnl": pnl, "spread_bp": (y10 - y2) * 1e4})
        prev_pos = position

    return pd.DataFrame(rows).set_index("date")


# ------------------------------- Reporting ---------------------------------- #
def report(bt):
    eq = bt["pnl"].cumsum()
    total = eq.iloc[-1]
    dd = (eq.cummax() - eq).max()
    sharpe = bt["pnl"].mean() / bt["pnl"].std() * np.sqrt(12)
    hit = (bt["pnl"] > 0).mean()
    pct_steep = (bt["position"] > 0).mean()

    print("=" * 56)
    print("RESULTS  (P&L in per-$1-DV01-per-leg units; scale is arbitrary)")
    print("=" * 56)
    print(f"  Months traded ......... {len(bt)}")
    print(f"  % of time in steepener  {pct_steep:6.1%}")
    print(f"  Total P&L ............. {total:8.2f}")
    print(f"  Max drawdown ......... {dd:8.2f}")
    print(f"  Annualized Sharpe .... {sharpe:8.2f}")
    print(f"  Monthly hit rate ..... {hit:6.1%}")
    print("=" * 56)

    worst = bt["pnl"].idxmin()
    print(f"  Worst single month: {worst.date()}  (P&L {bt['pnl'].min():.2f})")
    print("  ^ Look at what the curve was doing then -- that's your interview story.")

    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                               gridspec_kw={"height_ratios": [2, 1]})
        ax[0].plot(eq.index, eq.values, lw=1.6)
        ax[0].set_title("2s10s carry/roll strategy — cumulative P&L")
        ax[0].axhline(0, color="grey", lw=0.7)
        ax[1].plot(bt.index, bt["spread_bp"], lw=1.2, color="tab:orange")
        ax[1].axhline(0, color="grey", lw=0.7, ls="--")
        ax[1].set_title("2s10s spread (bp)  —  negative = inverted")
        fig.tight_layout()
        fig.savefig("equity_curve.png", dpi=110)
        print("\n  Saved chart -> equity_curve.png")
    except Exception as e:
        print(f"\n  (Plot skipped: {type(e).__name__}. `pip install matplotlib` to get the chart.)")


if __name__ == "__main__":
    df = load_yields()
    bt = backtest(df)
    report(bt)
