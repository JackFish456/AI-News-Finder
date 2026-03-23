# Example: run once and write reports to outputs/
# Schedule with Windows Task Scheduler for 8:00 AM local time.
Set-Location $PSScriptRoot\..
if (Test-Path .\.venv\Scripts\python.exe) {
  .\.venv\Scripts\python.exe -m news_agent.cli run
} else {
  python -m news_agent.cli run
}
