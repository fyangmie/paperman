param([string]$TargetId, [string]$RequestBase64)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
if ($TargetId -eq "browser") {
    $target = Invoke-RestMethod -Uri "http://127.0.0.1:9222/json/version" -TimeoutSec 10
} else {
    $targets = Invoke-RestMethod -Uri "http://127.0.0.1:9222/json/list" -TimeoutSec 10
    $target = $targets | Where-Object { $_.id -eq $TargetId } | Select-Object -First 1
}
if (-not $target) { throw "Requested page target no longer exists" }
$socket = New-Object System.Net.WebSockets.ClientWebSocket
$cancel = New-Object System.Threading.CancellationTokenSource
$cancel.CancelAfter(30000)
try {
    [void]$socket.ConnectAsync([uri]$target.webSocketDebuggerUrl, $cancel.Token).GetAwaiter().GetResult()
    $request = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($RequestBase64))
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($request)
    $segment = New-Object "System.ArraySegment[byte]" -ArgumentList (, $bytes)
    [void]$socket.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cancel.Token).GetAwaiter().GetResult()
    $buffer = New-Object byte[] 65536
    while ($true) {
        $stream = New-Object System.IO.MemoryStream
        do {
            $chunk = New-Object "System.ArraySegment[byte]" -ArgumentList (, $buffer)
            $received = $socket.ReceiveAsync($chunk, $cancel.Token).GetAwaiter().GetResult()
            $stream.Write($buffer, 0, $received.Count)
        } while (-not $received.EndOfMessage)
        $text = [System.Text.Encoding]::UTF8.GetString($stream.ToArray())
        $stream.Dispose()
        $response = $text | ConvertFrom-Json
        if ($response.id -eq 1) {
            Write-Output $text
            break
        }
    }
} finally {
    $socket.Dispose()
    $cancel.Dispose()
}
