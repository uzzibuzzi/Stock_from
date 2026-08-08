# Stock workflow implementation plan

## Findings
- The project already uses local CSV files in the save folder for historical stock data.
- The project already generates charts in the pics folder, and those plots should preserve the existing price-limit and trend-following style.
- There is no single entry point that combines incremental Yahoo Finance updates, local persistence, and chart generation in one flow.
- The current scripts are split across multiple files, which makes the workflow harder to run and maintain.

## Proposed plan
1. Create a new main entry point that processes a ticker list.
2. For each ticker, load the existing local CSV if present.
3. Download only the missing rows from the last stored date to today.
4. Merge the new rows with the existing data, remove duplicates, and save back to the same local CSV.
5. Generate a chart for each ticker and save it in the pics folder.
6. Keep the plot style close to the existing project by adding:
   - a candlestick-like price panel,
   - 20-day and 100-day moving averages,
   - green/red limit lines based on the 100-day moving-average range,
   - a trend indicator in the title.
7. Add simple validation steps so the flow can be checked quickly after each change.

## Test steps
- Test 1: Run the script once for one ticker and verify that a CSV file is created in save and a PNG file is created in pics.
- Test 2: Run the script again for the same ticker and verify that no duplicate rows are added and the chart is regenerated.
- Test 3: Run the script for a small ticker list and verify that each ticker is processed without errors.
- Test 4: Verify that the generated chart contains the moving averages, limit lines, and trend label.

## Suggested GitHub issues
- Implement the incremental Yahoo Finance workflow in main.py.
- Add chart generation with trend and limit indicators.
- Add smoke tests for CSV persistence and chart output.
- Document how to run the workflow locally.
