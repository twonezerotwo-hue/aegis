Set-Location "C:\Users\twone\Desktop\aegis_clean_v7.1"

$BASE = "http://localhost:8502"
$SYMBOL = "BTC/USDT"
$CAPITAL = 10000

$PERIODS = @(
  @{Name="1M"; Start=(Get-Date).AddMonths(-1).ToString("yyyy-MM-dd"); End=(Get-Date).ToString("yyyy-MM-dd")},
  @{Name="3M"; Start=(Get-Date).AddMonths(-3).ToString("yyyy-MM-dd"); End=(Get-Date).ToString("yyyy-MM-dd")},
  @{Name="6M"; Start=(Get-Date).AddMonths(-6).ToString("yyyy-MM-dd"); End=(Get-Date).ToString("yyyy-MM-dd")},
  @{Name="12M"; Start=(Get-Date).AddMonths(-12).ToString("yyyy-MM-dd"); End=(Get-Date).ToString("yyyy-MM-dd")}
)
$TIMEFRAMES = @("1h","4h","1d")
$Z_THRESHOLDS = @(0.5, 0.7, 0.9, 1.1, 1.3)
$KELLY_CAPS = @(0.10, 0.15, 0.20, 0.25)
$RSI_BOUNDS = @("30/70","35/65","40/60")

$REPORT_DIR = "backtest_reports/GRID_SEARCH_FAST_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $REPORT_DIR -Force | Out-Null
$LOG_FILE = Join-Path $REPORT_DIR "run.log"

$TASKS = @()
foreach ($p in $PERIODS) {
  foreach ($tf in $TIMEFRAMES) {
    foreach ($z in $Z_THRESHOLDS) {
      foreach ($kc in $KELLY_CAPS) {
        foreach ($rsi in $RSI_BOUNDS) {
          $TASKS += [PSCustomObject]@{
            PeriodName = $p.Name
            StartDate = $p.Start
            EndDate = $p.End
            TF = $tf
            Z = [double]$z
            Kelly = [double]$kc
            RSI = $rsi
          }
        }
      }
    }
  }
}

$TOTAL = $TASKS.Count
$MAX_JOBS = 8
$chunkSize = [math]::Ceiling($TOTAL / $MAX_JOBS)
$chunks = @()
for ($i = 0; $i -lt $TOTAL; $i += $chunkSize) {
  $end = [math]::Min($i + $chunkSize - 1, $TOTAL - 1)
  $chunks += ,($TASKS[$i..$end])
}

Write-Output ("START_TOTAL=" + $TOTAL)
Add-Content -Path $LOG_FILE -Value ("START_TOTAL=" + $TOTAL)

$jobs = @()
for ($idx = 0; $idx -lt $chunks.Count; $idx++) {
  $chunk = $chunks[$idx]
  $jobs += Start-Job -ArgumentList $chunk, $BASE, $SYMBOL, $CAPITAL, ($idx + 1) -ScriptBlock {
    param($taskChunk, $baseUrl, $symbol, $capital, $workerId)
    $results = @()
    $processed = 0

    foreach ($t in $taskChunk) {
      $processed++
      $rsiLow = [int]($t.RSI -split '/')[0]
      $rsiHigh = [int]($t.RSI -split '/')[1]
      $body = @{
        symbol = $symbol
        timeframe = $t.TF
        start_date = $t.StartDate
        end_date = $t.EndDate
        initial_capital = $capital
        risk_per_trade = 0.02
        use_live_data = $true
        include_fees = $true
        z_threshold = $t.Z
        kelly_cap = $t.Kelly
        rsi_lower = $rsiLow
        rsi_upper = $rsiHigh
      } | ConvertTo-Json -Depth 5

      try {
        $run = Invoke-RestMethod -Method Post -Uri "$baseUrl/backtest/run" -ContentType "application/json" -Body $body -TimeoutSec 120
        $results += [PSCustomObject]@{
          Period = $t.PeriodName
          TF = $t.TF
          Z = [double]$t.Z
          Kelly = [double]$t.Kelly
          RSI = $t.RSI
          PnL = [double]$run.metrics.pnl.total_pnl_pct
          WR = [double]$run.metrics.win_loss.win_rate
          Trades = [int]$run.metrics.pnl.num_trades
          Sharpe = [math]::Round([double]$run.metrics.sharpe_ratio, 2)
          Worker = $workerId
          Ok = $true
        }
      }
      catch {
        $results += [PSCustomObject]@{
          Period = $t.PeriodName
          TF = $t.TF
          Z = [double]$t.Z
          Kelly = [double]$t.Kelly
          RSI = $t.RSI
          PnL = 0.0
          WR = 0.0
          Trades = 0
          Sharpe = 0.0
          Worker = $workerId
          Ok = $false
        }
      }
    }

    return $results
  }
}

$all = @()
foreach ($job in $jobs) {
  $jobResult = Receive-Job -Job (Wait-Job -Job $job)
  if ($jobResult) {
    $all += $jobResult
  }
  Remove-Job -Job $job -Force | Out-Null
  $done = $all.Count
  Write-Output ("PROGRESS=" + $done + "/" + $TOTAL)
  Add-Content -Path $LOG_FILE -Value ("PROGRESS=" + $done + "/" + $TOTAL)
}

$winners = $all | Where-Object { $_.Ok -eq $true -and $_.PnL -gt 0 -and $_.WR -ge 51 }

$winners | ConvertTo-Json -Depth 6 | Out-File "$REPORT_DIR/winning_configs.json" -Encoding UTF8
$winners | Sort-Object -Property PnL -Descending | Format-Table Period,TF,Z,Kelly,RSI,PnL,WR,Trades,Sharpe,Worker -AutoSize | Out-File "$REPORT_DIR/summary.txt" -Encoding UTF8
$all | ConvertTo-Json -Depth 6 | Out-File "$REPORT_DIR/all_runs.json" -Encoding UTF8

Write-Output ("DONE_TOTAL=" + $TOTAL)
Write-Output ("DONE_WINNERS=" + $winners.Count)
Add-Content -Path $LOG_FILE -Value ("DONE_TOTAL=" + $TOTAL)
Add-Content -Path $LOG_FILE -Value ("DONE_WINNERS=" + $winners.Count)
if ($winners.Count -gt 0) {
  $best = $winners | Sort-Object -Property PnL -Descending | Select-Object -First 1
  Write-Output ("BEST=" + ($best | ConvertTo-Json -Compress))
  Add-Content -Path $LOG_FILE -Value ("BEST=" + ($best | ConvertTo-Json -Compress))
}
Write-Output ("REPORT_DIR=" + $REPORT_DIR)
Add-Content -Path $LOG_FILE -Value ("REPORT_DIR=" + $REPORT_DIR)
