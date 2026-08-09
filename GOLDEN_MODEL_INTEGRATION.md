# Golden Model integration

The forecast screen keeps its existing Streamlit layout. Only the workbook
boundary changes:

1. `read_workbook` validates the XLSX and inspects sheet aliases once.
2. Populated `STD_*` tables are preferred and aggregated by scenario/month.
3. When standard tables are empty, the approved `Data` sheet is projected into
   the dashboard's existing input-key contract.
4. Plan/Actual columns are separated using the scenario header, without asking
   users to duplicate values into the `STD_*` sheets.

`inspect_workbook` exposes the detected source path and warnings for future
upload/reconciliation UI. The analysis screen can later consume standardized
tables without coupling its calculations to Streamlit widgets.

Important: formula results in `Data` must have cached values. If a workbook was
generated without calculation, open it in Excel, calculate, and save once before
uploading. The adapter reports this as a warning instead of silently treating the
workbook as the old first-sheet upload format.
