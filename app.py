"""Personal trading journal and the existing historical market data explorer."""

import datetime as dt
import sqlite3

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from journal_store import JournalStore, TRADE_COLUMNS, market_now
from market_explorer import show_market_explorer

st.set_page_config(page_title="Tezi Mandi · Trading Journal", page_icon="📒", layout="wide")

COLORS = {"BUY": "#16a34a", "SELL": "#e05252"}
LABELS = {
    "trade_date": "Date", "trade_time": "Time (IST)", "side": "Side",
    "symbol": "Stock Name / Symbol", "quantity": "Quantity", "price": "Price (₹)",
    "amount": "Trade Value (₹)", "notes": "Notes",
}


def trades_frame(trades):
    frame = pd.DataFrame(trades, columns=TRADE_COLUMNS)
    for column in ("quantity", "price"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["amount"] = (frame["quantity"] * frame["price"]).round(2)
    return frame


def display_trades(frame, *, include_side=True, key=None):
    if include_side:
        columns = ["trade_date", "trade_time", "side", "symbol"]
    else:
        columns = ["symbol", "trade_time"]
    columns += ["quantity", "price", "amount", "notes"]
    st.dataframe(
        frame[columns].rename(columns=LABELS), hide_index=True,
        width="stretch", key=key,
        column_config={
            "Stock Name / Symbol": st.column_config.TextColumn(width="medium"),
            "Quantity": st.column_config.NumberColumn(format="%d"),
            "Price (₹)": st.column_config.NumberColumn(format="₹%.2f"),
            "Trade Value (₹)": st.column_config.NumberColumn(format="₹%.2f"),
        },
    )


def csv_data(frame):
    return frame[["id", *LABELS]].rename(columns=LABELS).to_csv(index=False).encode("utf-8-sig")


def flash(message):
    st.session_state["journal_message"] = message
    st.rerun()


def entry_form(store, side, day):
    with st.form(f"add_{side}", clear_on_submit=True):
        symbol = st.text_input("Stock Name / Symbol", key=f"{side}_symbol",
                               placeholder="e.g. RELIANCE or HDFC Bank")
        with st.expander("Optional trade details"):
            left, right = st.columns(2)
            quantity = left.number_input("Quantity (optional)", min_value=1, value=None,
                                         step=1, key=f"{side}_quantity")
            price = right.number_input("Price per share (₹, optional)", min_value=0.01,
                                       value=None, step=0.01, format="%.2f", key=f"{side}_price")
            time = st.time_input("Trade time (IST)", value=market_now().time().replace(microsecond=0),
                                 key=f"{side}_time")
            notes = st.text_input("Notes (optional)", key=f"{side}_notes",
                                  placeholder="Setup, reason for entry, or lessons")
        submitted = st.form_submit_button(f"Add {side} trade", type="primary",
                                         width="stretch")
    if submitted:
        try:
            store.add_trade(trade_date=day, trade_time=time, side=side, symbol=symbol,
                            quantity=quantity, price=price, notes=notes)
        except (ValueError, sqlite3.Error) as error:
            st.error(str(error))
        else:
            flash(f"{side} trade saved for {day:%d %b %Y}.")


def manage_trades(store, frame, today):
    if frame.empty:
        return
    with st.expander("Edit or delete an entry"):
        records = {int(row["id"]): row for row in frame.to_dict("records")}
        trade_id = st.selectbox(
            "Choose an entry", list(records), key="manage_trade",
            format_func=lambda value: f"#{value} · {records[value]['trade_time']} · "
                                      f"{records[value]['side']} · {records[value]['symbol']}",
        )
        trade = records[trade_id]
        with st.form(f"edit_{trade_id}"):
            left, right = st.columns(2)
            symbol = left.text_input("Stock Name / Symbol", value=trade["symbol"])
            side = right.selectbox("Side", ["BUY", "SELL"], index=["BUY", "SELL"].index(trade["side"]))
            day = left.date_input("Trade date", value=dt.date.fromisoformat(trade["trade_date"]),
                                  max_value=today)
            time = right.time_input("Trade time (IST)", value=dt.time.fromisoformat(trade["trade_time"]))
            quantity = left.number_input("Quantity (optional)", min_value=1, step=1,
                                         value=None if pd.isna(trade["quantity"]) else int(trade["quantity"]))
            price = right.number_input("Price per share (₹, optional)", min_value=0.01,
                                       step=0.01, format="%.2f",
                                       value=None if pd.isna(trade["price"]) else float(trade["price"]))
            notes = st.text_input("Notes (optional)", value=trade["notes"])
            saved = st.form_submit_button("Save changes", type="primary")
        if saved:
            try:
                store.update_trade(trade_id, trade_date=day, trade_time=time, side=side,
                                   symbol=symbol, quantity=quantity, price=price, notes=notes)
            except (ValueError, sqlite3.Error) as error:
                st.error(str(error))
            else:
                flash("Trade updated.")
        confirmed = st.checkbox("Confirm deletion of this entry", key=f"confirm_delete_{trade_id}")
        if st.button("Delete entry", disabled=not confirmed, key=f"delete_{trade_id}"):
            try:
                store.delete_trade(trade_id)
            except (ValueError, sqlite3.Error) as error:
                st.error(str(error))
            else:
                flash("Trade deleted.")


def show_analysis(store, today):
    st.subheader("Trading activity analysis")
    left, right = st.columns(2)
    start = left.date_input("From", value=today - dt.timedelta(days=29),
                            max_value=today, key="analysis_start")
    end = right.date_input("To", value=today, max_value=today, key="analysis_end")
    if start > end:
        st.error("'From' date must be on or before 'To' date.")
        return
    frame = trades_frame(store.list_trades(start, end))
    if frame.empty:
        st.info("No trades recorded in this date range. Add an entry to start tracking your activity.")
        return
    cols = st.columns(4)
    cols[0].metric("BUY trades in range", int((frame["side"] == "BUY").sum()))
    cols[1].metric("SELL trades in range", int((frame["side"] == "SELL").sum()))
    cols[2].metric("Stocks traded", frame["symbol"].nunique())
    cols[3].metric("Active trading days", frame["trade_date"].nunique())
    daily = frame.groupby(["trade_date", "side"]).size().unstack(fill_value=0)
    daily = daily.reindex(pd.date_range(start, end).strftime("%Y-%m-%d"), fill_value=0)
    fig = go.Figure()
    for side in ("BUY", "SELL"):
        fig.add_bar(name=side, x=daily.index,
                    y=daily[side] if side in daily else [0] * len(daily),
                    marker_color=COLORS[side])
    fig.update_layout(barmode="group", height=320, margin=dict(l=10, r=10, t=20, b=10),
                      yaxis_title="Number of trades", xaxis_title="Trade date (IST)",
                      yaxis=dict(dtick=1), legend=dict(orientation="h"))
    st.plotly_chart(fig, width="stretch")
    activity = frame.groupby(["symbol", "side"]).size().unstack(fill_value=0)
    activity = activity.reindex(columns=["BUY", "SELL"], fill_value=0)
    activity["Total trades"] = activity.sum(axis=1)
    st.markdown("**Activity by stock**")
    st.dataframe(activity.rename_axis("Stock Name / Symbol").reset_index(),
                 hide_index=True, width="stretch")
    left, right = st.columns(2)
    for column, side in ((left, "BUY"), (right, "SELL")):
        values = frame.loc[frame["side"] == side, "amount"]
        column.metric(f"Recorded {side} value", f"₹{values.sum():,.2f}")
    st.caption("Recorded values include only entries with both quantity and price. "
               "BUY and SELL values exclude fees and taxes; they do not represent profit or loss.")
    with st.expander("All entries in this date range"):
        display_trades(frame, key="history_table")
    st.download_button("Download history CSV", data=csv_data(frame),
                       file_name=f"trading_journal_{start}_{end}.csv", mime="text/csv", on_click="ignore")


def show_journal():
    today = market_now().date()
    with st.sidebar:
        st.header("Trading day")
        day = st.date_input("Journal date", value=today, max_value=today, key="journal_day")
        st.caption("Dates and trade times use Asia/Kolkata (IST).")
        if st.button("Refresh journal", width="stretch"):
            st.rerun()
    try:
        store = JournalStore()
        todays_trades = trades_frame(store.list_trades(today, today))
        day_trades = todays_trades if day == today else trades_frame(store.list_trades(day, day))
    except (OSError, sqlite3.Error) as error:
        st.error(f"Could not open the journal: {error}")
        st.stop()

    st.title("📒 Daily Trading Journal")
    st.write("Record your trades, review your day, and build a clear picture of your trading activity.")
    if message := st.session_state.pop("journal_message", None):
        st.success(message)
    st.caption(f"Today · {today:%A, %d %B %Y} · IST")
    buy_total, sell_total = st.columns(2)
    buy_total.metric("Today's total BUY trades", int((todays_trades["side"] == "BUY").sum()))
    sell_total.metric("Today's total SELL trades", int((todays_trades["side"] == "SELL").sum()))
    st.caption("Totals count individual trade entries. You can record the same stock multiple times.")

    daily_tab, analysis_tab = st.tabs(["Daily BUY & SELL", "History & analysis"])
    with daily_tab:
        label = "Today's activity" if day == today else "Trading day"
        st.subheader(f"{label} · {day:%d %b %Y}")
        st.caption("Enter a stock name or symbol to save a trade. Quantity, price, and notes are optional.")
        buy_column, sell_column = st.columns(2, gap="large")
        for column, side, icon in ((buy_column, "BUY", "🟢"), (sell_column, "SELL", "🔴")):
            with column:
                with st.container(border=True):
                    section = day_trades[day_trades["side"] == side]
                    st.subheader(f"{icon} {side}")
                    st.caption(f"{len(section)} trade{'s' if len(section) != 1 else ''} recorded for this day")
                    entry_form(store, side, day)
                    st.markdown(f"**{side} trades**")
                    if section.empty:
                        st.info(f"No {side} trades recorded for this day.")
                    display_trades(section, include_side=False, key=f"{side}_table")
        if not day_trades.empty:
            st.download_button("Download this day's CSV", data=csv_data(day_trades),
                               file_name=f"trading_journal_{day}.csv", mime="text/csv", on_click="ignore")
        manage_trades(store, day_trades, today)
    with analysis_tab:
        try:
            show_analysis(store, today)
        except sqlite3.Error as error:
            st.error(f"Could not read journal history: {error}")
    st.divider()
    st.caption("Your journal is saved locally. Keep a backup of data/trading_journal.sqlite3 "
               "or export your entries as CSV.")


with st.sidebar:
    st.title("Tezi Mandi")
    page = st.radio("View", ["Trading Journal", "Market Data Explorer"])
    st.divider()

if page == "Trading Journal":
    show_journal()
else:
    show_market_explorer()
