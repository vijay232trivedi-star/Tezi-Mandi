import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

st.set_page_config(page_title="Market Data Explorer", page_icon="📊", layout="wide")

IST = "Asia/Kolkata"

POPULAR = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "RELIANCE": "RELIANCE.NS",
    "HDFC BANK": "HDFCBANK.NS",
    "ICICI BANK": "ICICIBANK.NS",
    "INFOSYS": "INFY.NS",
    "TCS": "TCS.NS",
    "SBIN": "SBIN.NS",
    "TATA MOTORS": "TATAMOTORS.NS",
    "Other (type symbol)": "",
}

# Free intraday data is only available for recent days.
INTERVAL_MAX_DAYS_BACK = {"1m": 7, "5m": 59, "15m": 59, "30m": 59, "60m": 700}


def normalize_symbol(text: str) -> str:
    s = text.strip().upper()
    if not s:
        return ""
    if s.startswith("^") or "." in s:
        return s
    return s + ".NS"


@st.cache_data(ttl=900, show_spinner=False)
def load_data(symbol: str, start: dt.date, end: dt.date, interval: str) -> pd.DataFrame:
    df = yf.download(
        symbol,
        start=start,
        end=end + dt.timedelta(days=1),  # end is exclusive
        interval=interval,
        progress=False,
        auto_adjust=False,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(IST)
    df.index.name = "Datetime (IST)"
    return df.round(2)


def show_summary(df: pd.DataFrame):
    o, c = df["Open"].iloc[0], df["Close"].iloc[-1]
    h, l = df["High"].max(), df["Low"].min()
    vol = df["Volume"].sum()
    chg = c - o
    chg_pct = chg / o * 100 if o else 0

    cols = st.columns(6)
    cols[0].metric("Open", f"{o:,.2f}")
    cols[1].metric("High", f"{h:,.2f}")
    cols[2].metric("Low", f"{l:,.2f}")
    cols[3].metric("Close", f"{c:,.2f}", f"{chg:+.2f} ({chg_pct:+.2f}%)")
    cols[4].metric("Range", f"{h - l:,.2f}")
    if vol > 0:
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        vwap = (tp * df["Volume"]).sum() / vol
        cols[5].metric("VWAP", f"{vwap:,.2f}")
        st.caption(f"Total volume: {int(vol):,}")
    else:
        cols[5].metric("Volume", "n/a (index)")


def show_chart(df: pd.DataFrame, title: str):
    has_volume = df["Volume"].sum() > 0
    rows = 2 if has_volume else 1
    fig = make_subplots(
        rows=rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.75, 0.25] if has_volume else [1],
    )
    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
        ),
        row=1,
        col=1,
    )
    if has_volume:
        fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume"), row=2, col=1)
    fig.update_layout(
        title=title,
        height=620,
        xaxis_rangeslider_visible=False,
        showlegend=False,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------- UI ----------------
st.title("📊 Market Data Explorer")
st.write("Pick a stock or index and a date to view and download historical market data.")

with st.sidebar:
    st.header("Choose data")
    choice = st.selectbox("Stock / Index", list(POPULAR.keys()))
    if POPULAR[choice]:
        symbol = POPULAR[choice]
    else:
        custom = st.text_input("NSE symbol (e.g. ITC, WIPRO) or Yahoo symbol", "ITC")
        symbol = normalize_symbol(custom)

    mode = st.radio("Mode", ["Single day (intraday)", "Date range (daily)"])
    today = dt.date.today()

    if mode == "Single day (intraday)":
        interval = st.selectbox("Candle size", list(INTERVAL_MAX_DAYS_BACK.keys()), index=1)
        min_date = today - dt.timedelta(days=INTERVAL_MAX_DAYS_BACK[interval])
        day = st.date_input("Date", value=today, min_value=min_date, max_value=today)
        start, end = day, day
        st.caption(
            f"Free {interval} data is available for roughly the last "
            f"{INTERVAL_MAX_DAYS_BACK[interval]} days only."
        )
    else:
        interval = "1d"
        start = st.date_input("From", value=today - dt.timedelta(days=90), max_value=today)
        end = st.date_input("To", value=today, max_value=today)

    go_btn = st.button("Get data", type="primary", use_container_width=True)

if go_btn:
    if not symbol:
        st.error("Please enter a symbol.")
    elif start > end:
        st.error("'From' date must be before 'To' date.")
    else:
        with st.spinner("Fetching data..."):
            try:
                data = load_data(symbol, start, end, interval)
            except Exception as e:  # network / rate limit / bad symbol
                data = pd.DataFrame()
                st.error(f"Could not fetch data: {e}")

        if data.empty:
            st.warning(
                "No data found. The market may have been closed (weekend/holiday), "
                "the symbol may be wrong, or the date is outside the free data window."
            )
        else:
            label = f"{choice if POPULAR[choice] else symbol} — {start}" + (
                f" to {end}" if start != end else ""
            )
            show_summary(data)
            show_chart(data, label)
            st.subheader("Data")
            st.dataframe(data, use_container_width=True)
            st.download_button(
                "⬇️ Download CSV",
                data=data.to_csv().encode("utf-8"),
                file_name=f"{symbol.replace('^', '')}_{start}_{end}_{interval}.csv",
                mime="text/csv",
            )
else:
    st.info("Choose a stock and date in the sidebar, then click **Get data**.")

st.divider()
st.caption(
    "Disclaimer: This tool shows historical market data for information and education only. "
    "It is not investment advice, a recommendation, or a research report. Data comes from a "
    "third-party source, may be delayed or inaccurate, and is not guaranteed. Trading in "
    "equities and F&O involves substantial risk of loss."
)
