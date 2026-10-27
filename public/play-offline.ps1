$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8088
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
try {
    $listener.Start()
} catch {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
}

$mimeMap = @{
    '.html' = 'text/html; charset=utf-8'
    '.js'   = 'application/javascript; charset=utf-8'
    '.mjs'  = 'application/javascript; charset=utf-8'
    '.css'  = 'text/css; charset=utf-8'
    '.json' = 'application/json; charset=utf-8'
    '.wasm' = 'application/wasm'
    '.glb'  = 'model/gltf-binary'
    '.png'  = 'image/png'
    '.jpg'  = 'image/jpeg'
    '.jpeg' = 'image/jpeg'
    '.svg'  = 'image/svg+xml'
    '.ico'  = 'image/x-icon'
}

$url = "http://127.0.0.1:$port/"
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  Desk Racer · 曙光云立体密算版 (离线便携试玩服务)" -ForegroundColor Cyan
Write-Host "  游戏地址: $url" -ForegroundColor Green
Write-Host "  关闭此窗口即可停止服务。" -ForegroundColor DarkGray
Write-Host "======================================================" -ForegroundColor Cyan
Start-Process $url

while ($true) {
    $client = $listener.AcceptTcpClient()
    try {
        $stream = $client.GetStream()
        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::ASCII, $false, 4096, $true)
        $reqLine = $reader.ReadLine()
        while ($line = $reader.ReadLine()) { if ($line -eq '') { break } }
        if ($reqLine) {
            $rawPath = ($reqLine -split ' ')[1]
            $cleanPath = [System.Uri]::UnescapeDataString(($rawPath -split '\?')[0]).TrimStart('/')
            if ([string]::IsNullOrWhiteSpace($cleanPath)) { $cleanPath = 'index.html' }
            $fullPath = Join-Path $root $cleanPath
            if (Test-Path $fullPath -PathType Leaf) {
                $ext = [System.IO.Path]::GetExtension($fullPath).ToLowerInvariant()
                $mime = if ($mimeMap.ContainsKey($ext)) { $mimeMap[$ext] } else { 'application/octet-stream' }
                $bytes = [System.IO.File]::ReadAllBytes($fullPath)
                $header = "HTTP/1.1 200 OK`r`nContent-Type: $mime`r`nContent-Length: $($bytes.Length)`r`nCache-Control: no-cache`r`nConnection: close`r`n`r`n"
                $hBytes = [System.Text.Encoding]::ASCII.GetBytes($header)
                $stream.Write($hBytes, 0, $hBytes.Length)
                $stream.Write($bytes, 0, $bytes.Length)
            } else {
                $msg = [System.Text.Encoding]::UTF8.GetBytes("404 Not Found")
                $header = "HTTP/1.1 404 Not Found`r`nContent-Length: $($msg.Length)`r`nConnection: close`r`n`r`n"
                $hBytes = [System.Text.Encoding]::ASCII.GetBytes($header)
                $stream.Write($hBytes, 0, $hBytes.Length)
                $stream.Write($msg, 0, $msg.Length)
            }
        }
    } catch {} finally {
        $client.Close()
    }
}
