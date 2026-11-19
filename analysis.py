"""Was 2024 unusually hot in Nakhon Pathom? Station 451301, 2024 vs 2025 vs 2021-2023.

Reads data/nakhon_pathom_451301_daily.csv (built by prepare_data.py) and writes
results/monthly_stats.csv, results/daily_anomalies.csv and charts in figures/.

Run from the repository root:  python analysis.py
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
FIG, RES = ROOT / "figures", ROOT / "results"
FIG.mkdir(exist_ok=True)
RES.mkdir(exist_ok=True)
MONTHS = list(range(1, 13))
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
C24, C25 = "#1f5f80", "#f0a30a"

daily = pd.read_csv(ROOT / "data" / "nakhon_pathom_451301_daily.csv", parse_dates=["date"], index_col="date")
t = daily["avg"]  # TMD daily mean of the 8 three-hourly readings
d24, d25, base = t.loc["2024"], t.loc["2025"], t.loc["2021":"2023"]
assert (len(d24), len(d25), len(base)) == (366, 365, 1095)


def monthly(s: pd.Series) -> pd.DataFrame:
    g = s.groupby(s.index.month)
    return pd.DataFrame({"mean": g.mean(), "sd": g.std(ddof=0), "sd_sample": g.std(ddof=1), "n": g.size()})


def effective_n(x: np.ndarray) -> float:
    """Shrink n for lag-1 autocorrelation: consecutive days are not independent."""
    r = max(np.corrcoef(x[:-1], x[1:])[0, 1], 0.0)
    return max(len(x) * (1 - r) / (1 + r), 2.0)


def welch_p(a: np.ndarray, b: np.ndarray, adjust: bool) -> float:
    na, nb = (effective_n(a), effective_n(b)) if adjust else (len(a), len(b))
    va, vb = a.var(ddof=1) / na, b.var(ddof=1) / nb
    tstat = (a.mean() - b.mean()) / np.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (na - 1) + vb ** 2 / (nb - 1))
    return 2 * stats.t.sf(abs(tstat), df)


m24, m25 = monthly(d24), monthly(d25)
by_year = base.groupby([base.index.year, base.index.month]).mean().unstack(0)  # month x year
table = pd.DataFrame({
    "month": MONTHS,
    "mean_2024": m24["mean"].values, "sd_2024": m24["sd"].values,
    "mean_2025": m25["mean"].values, "sd_2025": m25["sd"].values,
    "diff_2024_minus_2025": (m24["mean"] - m25["mean"]).values,
    "base_2021_23_mean": by_year.mean(axis=1).values,
    "base_lowest_year": by_year.min(axis=1).values,
    "base_highest_year": by_year.max(axis=1).values,
})
table["anom_2024"] = table["mean_2024"] - table["base_2021_23_mean"]
table["anom_2025"] = table["mean_2025"] - table["base_2021_23_mean"]
table["2024_above_all_base_years"] = table["mean_2024"] > table["base_highest_year"]
table["2025_above_all_base_years"] = table["mean_2025"] > table["base_highest_year"]
a_by_m = [(d24[d24.index.month == k].values, d25[d25.index.month == k].values) for k in MONTHS]
table["welch_p_naive"] = [welch_p(a, b, adjust=False) for a, b in a_by_m]
table["welch_p_autocorr_adjusted"] = [welch_p(a, b, adjust=True) for a, b in a_by_m]
table = table.round(3)
table.to_csv(RES / "monthly_stats.csv", index=False)

print(table[["month", "mean_2024", "sd_2024", "mean_2025", "sd_2025", "base_lowest_year", "base_highest_year",
             "2024_above_all_base_years", "welch_p_autocorr_adjusted"]].to_string(index=False))
print(f"\nMonths where 2024 beat every year of 2021-2023: {int(table['2024_above_all_base_years'].sum())}/12")
print(f"Months where 2025 beat every year of 2021-2023: {int(table['2025_above_all_base_years'].sum())}/12")
print("Annual mean: " + ", ".join(f"{k} {v.mean():.2f} °C" for k, v in
                                    {"2021-23": base, "2024": d24, "2025": d25}.items()))
for name, s in {"2024": d24, "2025": d25}.items():
    print(f"{name}: hottest day {s.idxmax().date()} ({s.max()} °C), coolest day {s.idxmin().date()} ({s.min()} °C)")


# ---- daily anomaly vs the 2021-2023 average for the same calendar day (29 Feb folded into 28 Feb) ----
def day_key(ix: pd.DatetimeIndex) -> pd.Index:
    return pd.Index([f"{d.month:02d}-{min(d.day, 28) if d.month == 2 else d.day:02d}" for d in ix])


normal = base.groupby(day_key(base.index)).mean()
anoms = pd.concat({name: pd.Series(s.values - normal.loc[day_key(s.index)].values, index=s.index)
                   for name, s in {"2024": d24, "2025": d25}.items()}, axis=1).round(2)
anoms.to_csv(RES / "daily_anomalies.csv", index_label="date")


# ---- charts ----
def style(ax, title, ylabel="Temperature (°C)"):
    ax.set_title(title, fontsize=13)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#dddddd")
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def save(fig, name, note):
    fig.text(0.01, 0.01, note, fontsize=7.5, color="#55554f")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(FIG / name, dpi=140)
    plt.close(fig)


SRC = "Source: Thai Meteorological Department, station 451301 Nakhon Pathom, 3-hourly dry-bulb temperature"

fig, ax = plt.subplots(figsize=(10, 5))
for m, c, lab, dx in [(m24, C24, "2024", -0.08), (m25, C25, "2025", 0.08)]:
    ax.errorbar(np.array(MONTHS) + dx, m["mean"], yerr=m["sd"], color=c, lw=2.2, marker="o",
                ms=6, capsize=4, elinewidth=1.2, label=lab)
ax.fill_between(MONTHS, table["base_lowest_year"], table["base_highest_year"], color="#cccccc",
                alpha=0.5, label="2021-2023 range of monthly means")
ax.set_xticks(MONTHS, MONTH_LABELS)
ax.set_ylim(20, 34)
ax.legend(frameon=False, loc="lower center", ncol=3)
style(ax, "Nakhon Pathom monthly mean temperature (± SD of daily means)")
save(fig, "monthly_mean_2024_vs_2025.png", SRC)

fig, ax = plt.subplots(figsize=(10, 5))
w = 0.38
ax.axhline(0, color="#555", lw=1)
ax.bar(np.array(MONTHS) - w / 2, table["anom_2024"], w, color=C24, label="2024")
ax.bar(np.array(MONTHS) + w / 2, table["anom_2025"], w, color=C25, label="2025")
ax.set_xticks(MONTHS, MONTH_LABELS)
ax.legend(frameon=False)
style(ax, "Monthly mean minus the 2021-2023 average", "Difference (°C)")
save(fig, "anomaly_vs_2021_2023.png", SRC + " · baseline is only 3 years, not a 30-year normal")

fig, ax = plt.subplots(figsize=(12, 5))
for s, c, lab in [(d24, C24, "2024"), (d25, C25, "2025")]:
    # place both years on a 2025 calendar so dates line up; 29 Feb 2024 sits between 28 Feb and 1 Mar
    x = [pd.Timestamp(2025, d.month, 28 if (d.month, d.day) == (2, 29) else d.day).dayofyear
         + (0.5 if (d.month, d.day) == (2, 29) else 0) for d in s.index]
    ax.plot(x, s.values, color=c, lw=1.1, label=lab)
ax.set_xticks(pd.date_range("2025-01-01", periods=12, freq="MS").dayofyear, MONTH_LABELS)
for (yr, m, d, txt, dx, dy) in [(2024, 5, 1, "1 May 2024: 33.4 °C\n(regional heat wave)", 25, 0.2),
                                (2025, 1, 13, "13 Jan 2025: 19.3 °C\n(cold surge)", 25, 1.2),
                                (2025, 11, 29, "29 Nov 2025: 19.2 °C\n(cold surge)", -95, 1.2)]:
    x0, y0 = pd.Timestamp(2025, m, d).dayofyear, t.loc[f"{yr}-{m:02d}-{d:02d}"]
    ax.annotate(txt, (x0, y0), xytext=(x0 + dx, y0 + dy), fontsize=9,
                arrowprops=dict(arrowstyle="->", color="#555", lw=1))
ax.set_ylim(18, 35)
ax.legend(frameon=False)
style(ax, "Nakhon Pathom daily mean temperature: 2024 vs 2025", "Daily mean (°C)")
save(fig, "daily_2024_vs_2025.png", SRC)
print(f"\nWrote {RES / 'monthly_stats.csv'}, {RES / 'daily_anomalies.csv'} and 3 charts in {FIG}")
