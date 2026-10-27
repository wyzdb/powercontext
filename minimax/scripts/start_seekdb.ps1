param(
    [string]$Name = "seekdb",
    [int]$Port = 2881,
    [string]$Image = "quay.io/oceanbase/seekdb:latest"
)

$ErrorActionPreference = "Stop"
$existing = docker ps -a --filter "name=^$Name$" --format "{{.Names}}"
if ($existing -eq $Name) {
    $running = docker ps --filter "name=^$Name$" --format "{{.Names}}"
    if ($running -eq $Name) {
        Write-Host "seekdb container '$Name' already running on port $Port"
    } else {
        docker start $Name | Out-Null
        Write-Host "started existing container '$Name'"
    }
} else {
    docker run -d --name $Name -p "${Port}:2881" --restart unless-stopped $Image | Out-Null
    Write-Host "created container '$Name' from $Image on port $Port"
}

Write-Host "waiting for port $Port ..."
for ($i = 0; $i -lt 60; $i++) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect("127.0.0.1", $Port)
        $client.Close()
        Write-Host "seekdb is accepting connections on 127.0.0.1:$Port"
        exit 0
    } catch {
        Start-Sleep -Seconds 2
    } finally {
        $client.Dispose()
    }
}
Write-Error "seekdb did not open port $Port in time"
exit 1
