"""Turn the TMD web-page exports in raw/ into one tidy daily CSV for station 451301.

The Thai Meteorological Department (TMD) data service exports 3-hourly dry-bulb
temperature as saved web pages (.mhtml, Thai cp874 encoding). The raw files are
not committed; data/nakhon_pathom_451301_daily.csv is the output of this script.

Run from the repository root:  python prepare_data.py
"""
import email
import re
from pathlib import Path

import pandas as pd
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
OUT = ROOT / "data" / "nakhon_pathom_451301_daily.csv"
STATION = "451301"
HOURS = ["t01", "t04", "t07", "t10", "t13", "t16", "t19", "t22"]
COLUMNS = ["no", "station", "date", *HOURS, "avg"]


def load(path: Path) -> pd.DataFrame:
    """Parse every table row that looks like <no, station, dd/mm/yyyy, 8 readings, avg>."""
    with open(path, "rb") as fh:
        msg = email.message_from_binary_file(fh)
    html = next(
        part.get_payload(decode=True).decode("cp874", errors="replace")
        for part in msg.walk()
        if part.get_content_type() == "text/html"
    )
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        cells = [re.sub(r"<[^>]+>|&nbsp;", "", c).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if len(cells) >= 12 and re.match(r"\d+/\d+/\d{4}$", cells[2]):
            rows.append(cells[:12])
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y")
    for c in [*HOURS, "avg"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[df["station"].str.startswith(STATION)]
    return df.set_index("date").sort_index()[[*HOURS, "avg"]]


def raw_file(suffix: str) -> Path:
    matches = sorted(RAW.glob(f"dryBT-3hr-*{suffix}"))
    if not matches:
        raise SystemExit(f"Missing raw file *{suffix} in {RAW}. See README for how to download it.")
    return matches[0]


def main() -> None:
    f_2021_2024 = load(raw_file("2021-30-8-2024.mhtml"))
    f_aug_dec_2024 = load(raw_file("8-12-2024.mhtml"))
    f_2025 = load(raw_file("2025.mhtml"))

    # The first export stops part-way through 30 Aug 2024, so Aug-Dec 2024 comes from the second file.
    daily = pd.concat([
        f_2021_2024.loc["2021-01-01":"2024-07-31"],
        f_aug_dec_2024.loc["2024-08-01":"2024-12-31"],
        f_2025.loc["2025-01-01":"2025-12-31"],
    ])

    # Quality checks: one row per calendar day, no gaps, no missing readings,
    # and TMD's daily average equals the mean of the 8 readings (to rounding).
    assert daily.index.is_unique, "duplicate dates"
    expected = pd.date_range("2021-01-01", "2025-12-31", freq="D")
    missing_days = expected.difference(daily.index)
    assert missing_days.empty, f"missing days: {list(missing_days[:5])}"
    assert daily["avg"].notna().all(), "missing daily average"
    incomplete = daily[daily[HOURS].isna().any(axis=1)]
    complete = daily.drop(incomplete.index)
    gap = (complete[HOURS].mean(axis=1) - complete["avg"]).abs().max()
    assert gap <= 0.051, f"TMD avg differs from mean of 8 readings by {gap:.2f}"
    for day, row in incomplete.iterrows():
        print(f"note: {day.date()} has {row[HOURS].isna().sum()} missing 3-hourly readings; "
              f"TMD's daily average ({row['avg']}) is kept")

    OUT.parent.mkdir(exist_ok=True)
    daily.reset_index().to_csv(OUT, index=False, date_format="%Y-%m-%d")
    print(f"{len(daily):,} days ({daily.index.min().date()} to {daily.index.max().date()}) -> {OUT}")
    print(f"max |TMD avg - mean of 8 readings| = {gap:.3f} °C")


if __name__ == "__main__":
    main()
