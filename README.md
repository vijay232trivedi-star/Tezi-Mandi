# Tezi Mandi

A personal Streamlit trading journal with the existing Market Data Explorer.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens on **Trading Journal**. Select **Market Data Explorer** in the sidebar
to use the historical charts and market-data CSV downloads.

## Journal

- Today's BUY and SELL totals count individual entries using the India time zone
  (`Asia/Kolkata`), even while reviewing another date.
- The independent BUY and SELL columns each have their own form and table. Only
  **Stock Name / Symbol** is required. Repeated entries for the same stock are allowed.
- Quantity (whole shares), price per share in INR, trade time, and notes can be
  recorded. Leave quantity or price blank when you only want to log a stock.
- Use **Journal date** to review or add earlier trades. Future dates are blocked.
- Use **Edit or delete an entry** to correct a trade. Deletion requires checking
  the confirmation box for the selected entry.
- **History & analysis** provides date-range totals, daily activity, counts by
  stock, recorded BUY/SELL values, and a CSV export. Values exclude entries missing
  quantity or price and exclude fees and taxes; they are not realized profit or loss.

Symbols and names are trimmed and stored in uppercase. Use the same name or symbol
consistently to group stock activity accurately. The journal does not require market
data or a network connection to save entries.

## Storage and backups

Entries persist across Streamlit reruns and server restarts in
`data/trading_journal.sqlite3` (created automatically and excluded from Git).
Keep this file on persistent local storage and back it up while the app is stopped,
or export entries as CSV. Deleting the database removes the journal.

To choose another database location, set `TRADING_JOURNAL_DB` before starting:

```bash
TRADING_JOURNAL_DB=/path/to/trading_journal.sqlite3 streamlit run app.py
```

This is a local personal app without authentication. For hosting, use persistent
storage and restrict access to your own account.

## Verification

```bash
python -m unittest discover -s tests -v
```

Tests use temporary databases and do not touch your personal entries.
