
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("start", "stop", "status")]
    [string]$Action
)

switch ($Action) {
    "start" {
        docker info *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Docker Desktop is not running. Start it and wait for 'Engine running'."
            exit 1
        }

        # XAMPP Apache can conflict with the cluster's port 80.
        $apache = Get-Process httpd -ErrorAction SilentlyContinue
        if ($apache) {
            Write-Host "Apache (httpd) is running. Stop XAMPP Apache, then retry."
            exit 1
        }

        k3d cluster start urumi
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Could not start cluster urumi."
            exit 1
        }

        $ready = $false
        for ($i = 0; $i -lt 30; $i++) {
            kubectl get nodes *> $null
            if ($LASTEXITCODE -eq 0) {
                $ready = $true
                break
            }
            Start-Sleep -Seconds 5
        }

        if (-not $ready) {
            Write-Host "Kubernetes API did not become reachable in time."
            exit 1
        }

        kubectl wait --for=condition=Ready pod/mariadb-0 -n store --timeout=300s
        if ($LASTEXITCODE -ne 0) { exit 1 }

        kubectl wait --for=condition=Available deployment --all -n store --timeout=300s
        if ($LASTEXITCODE -ne 0) { exit 1 }

        kubectl wait --for=condition=Available deployment --all -n mcp-servers --timeout=300s
        if ($LASTEXITCODE -ne 0) { exit 1 }

        kubectl wait --for=condition=Available deployment --all -n gateway --timeout=300s
        if ($LASTEXITCODE -ne 0) { exit 1 }

        kubectl get pods -A
        Write-Host "Store:   http://store.localtest.me"
        Write-Host "Gateway: http://gateway.localtest.me"
    }

    "stop" {
        Get-Process kubectl -ErrorAction SilentlyContinue | Stop-Process
        k3d cluster stop urumi
    }

    "status" {
        k3d cluster list
        kubectl get pods -A
    }
}
