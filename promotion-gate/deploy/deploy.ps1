#Requires -Version 7
<#
.SYNOPSIS
  Despliega el gate de promoción completo en Fabric: orquestador de carga, gate y Fabric App (Rayfin).

.DESCRIPTION
  Idempotente: se puede repetir para actualizar. Pasos (por defecto, todos):
    orchestrator  Fabric Load Test Orchestrator en el workspace de herramientas (notebooks y pipelines).
    gate          Notebooks NB_Gate_*, pipeline PL_PromotionGate, wheel y gate.yaml en el mismo workspace.
    app           Registro SPA de Entra, .env de la app y `rayfin up` (build, hosting estático y tabla del historial).
  Con -SuccessCase añade el caso de éxito Ventas Retail (lakehouse, modelo Direct Lake, informe y escenario) en
  -SuccessCaseWorkspace, mejor en otra capacidad que la del gate (por defecto, el workspace de herramientas).
  El orquestador se instala desde el repo que contiene el gate (promotion-gate/ dentro de fabric-load-test-orchestrator);
  si el gate está en otro sitio, indica el clon con -OrchestratorRepo.

  Identidad: usa Azure CLI. Con -Subscription o -Tenant pide los tokens para esa suscripción o tenant sin cambiar la
  cuenta por defecto de `az`. Necesita: Contributor en ambos workspaces y permiso para crear registros de aplicación
  en Entra (o pasar -SpaClientId de uno existente).

.EXAMPLE
  pwsh deploy/deploy.ps1 -ToolsWorkspace "[PoC] Promotion Gate" -AppWorkspace "[PoC] Promotion Gate App" `
       -CapacityMetricsWorkspace "Microsoft Fabric Capacity Metrics" -WhatIf
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string]$ToolsWorkspace,
  [string]$AppWorkspace,
  [string]$CapacityMetricsWorkspace = '',
  [string]$LakehouseName = 'lh_gate',
  [string]$AppItemName = 'PromotionGateApp',
  [string]$SpaClientId,
  [string]$SpaDisplayName = 'promotion-gate-app',
  [ValidateSet('orchestrator', 'gate', 'app')] [string[]]$Steps = @('orchestrator', 'gate', 'app'),
  [switch]$SuccessCase,
  [string]$SuccessCaseWorkspace,
  [string]$OrchestratorRepo,
  [string]$Subscription,
  [string]$Tenant,
  [switch]$WhatIf
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$App = Join-Path $Root 'app'
$FabricApi = 'https://api.fabric.microsoft.com/v1'
$GraphApi = 'https://graph.microsoft.com/v1.0'
$IsWin = $IsWindows -or $env:OS -eq 'Windows_NT'

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Info($text) { Write-Host "   $text" }
function Plan($text) { Write-Host "   [WhatIf] $text" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------------------------- identidad y tokens
$AzScope = if ($Subscription) { @('--subscription', $Subscription) } elseif ($Tenant) { @('--tenant', $Tenant) } else { @() }
$TokenCache = @{}
function Get-Token([string]$Resource) {
  if (-not $TokenCache[$Resource]) {
    $sel = if ($Resource -eq 'graph') { @('--resource-type', 'ms-graph') } else { @('--resource', $Resource) }
    $t = az account get-access-token @sel @AzScope --query accessToken -o tsv 2>$null
    if (-not $t) { throw "Sin token de Azure CLI para $Resource. Ejecuta az login (con --tenant si la cuenta está en varios)." }
    $TokenCache[$Resource] = $t
  }
  $TokenCache[$Resource]
}
function Get-Claims([string]$Jwt) {
  $p = $Jwt.Split('.')[1].Replace('-', '+').Replace('_', '/')
  $p += '=' * ((4 - $p.Length % 4) % 4)
  [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($p)) | ConvertFrom-Json
}
function Invoke-Fabric([string]$Method, [string]$Path, $Body) {
  $h = @{ Authorization = "Bearer $(Get-Token 'https://api.fabric.microsoft.com')" }
  $p = @{ Method = $Method; Uri = "$FabricApi/$Path"; Headers = $h; SkipHttpErrorCheck = $true }
  if ($null -ne $Body) { $p.Body = ($Body | ConvertTo-Json -Depth 10); $p.ContentType = 'application/json' }
  for ($try = 0; ; $try++) {
    $r = Invoke-WebRequest @p
    if ($r.StatusCode -ne 429 -or $try -ge 5) { break }
    Start-Sleep 20
  }
  if ($r.StatusCode -eq 202 -and $r.Headers.Location) {
    $loc = "$($r.Headers.Location)"
    do { Start-Sleep 3; $s = Invoke-RestMethod -Uri $loc -Headers $h } while ($s.status -notin 'Succeeded', 'Failed')
    if ($s.status -eq 'Failed') { throw "Fabric $Method $Path falló: $($s.error | ConvertTo-Json -Compress)" }
    return (Invoke-RestMethod -Uri "$loc/result" -Headers $h -SkipHttpErrorCheck)
  }
  if ($r.StatusCode -ge 400) { throw "Fabric $Method $Path -> $($r.StatusCode): $($r.Content)" }
  if ($r.Content) { $r.Content | ConvertFrom-Json } else { $null }
}
function Invoke-Graph([string]$Method, [string]$Path, $Body) {
  $p = @{ Method = $Method; Uri = "$GraphApi/$Path"; Headers = @{ Authorization = "Bearer $(Get-Token 'graph')" } }
  if ($null -ne $Body) { $p.Body = ($Body | ConvertTo-Json -Depth 10); $p.ContentType = 'application/json' }
  Invoke-RestMethod @p
}

# ---------------------------------------------------------------------------------------------- Fabric
$script:Workspaces = $null
function Get-Workspaces {
  if (-not $script:Workspaces) {
    $all = @(); $url = 'workspaces'
    while ($url) {
      $page = Invoke-Fabric GET $url
      $all += $page.value
      $url = if ($page.continuationToken) { "workspaces?continuationToken=$([uri]::EscapeDataString($page.continuationToken))" } else { $null }
    }
    $script:Workspaces = $all
  }
  $script:Workspaces
}
function Resolve-Workspace([string]$NameOrId) {
  $ws = Get-Workspaces | Where-Object { $_.id -eq $NameOrId -or $_.displayName -eq $NameOrId } | Select-Object -First 1
  if (-not $ws) { throw "No encuentro el workspace '$NameOrId' (¿existe y tienes acceso con esta identidad?)." }
  if (-not $ws.capacityId) { throw "El workspace '$($ws.displayName)' no tiene capacidad asignada." }
  $cap = (Invoke-Fabric GET 'capacities').value | Where-Object id -eq $ws.capacityId
  if ($cap -and $cap.state -ne 'Active') { throw "La capacidad de '$($ws.displayName)' está $($cap.state): reanúdala antes de desplegar." }
  [pscustomobject]@{ id = $ws.id; displayName = $ws.displayName; sku = $cap.sku; region = $cap.region }
}
function Ensure-Lakehouse($Ws) {
  $lh = (Invoke-Fabric GET "workspaces/$($Ws.id)/lakehouses").value | Where-Object displayName -eq $LakehouseName
  if ($lh) { Info "lakehouse $LakehouseName ya existe"; return $lh.id }
  if ($WhatIf) { Plan "crear lakehouse $LakehouseName en $($Ws.displayName)"; return '<nuevo-lakehouse>' }
  $r = Invoke-Fabric POST "workspaces/$($Ws.id)/lakehouses" @{ displayName = $LakehouseName; description = 'Gate de promoción y Fabric Load Test Orchestrator' }
  $id = if ($r.id) { $r.id } else { ((Invoke-Fabric GET "workspaces/$($Ws.id)/lakehouses").value | Where-Object displayName -eq $LakehouseName).id }
  Info "lakehouse $LakehouseName creado"
  $id
}

# ---------------------------------------------------------------------------------------------- Python (gate)
function Get-GatePython {
  $venv = Join-Path $Root '.venv'
  $py = if ($IsWin) { Join-Path $venv 'Scripts' 'python.exe' } else { Join-Path $venv 'bin' 'python' }
  if (-not (Test-Path $py)) {
    Info 'creando .venv del gate'
    python -m venv $venv
    if ($LASTEXITCODE) { throw 'No se pudo crear el entorno de Python (hace falta Python 3.10 o posterior en el PATH).' }
  }
  & $py -m pip install -q --disable-pip-version-check -e "$Root[cli]"
  if ($LASTEXITCODE) { throw 'pip install del gate falló.' }
  $py
}
function Invoke-Smgate([string]$Py, [string[]]$Arguments) {
  if ($Subscription) { $env:SMGATE_AZ_SUBSCRIPTION = $Subscription } elseif ($Tenant) { $env:SMGATE_AZ_TENANT = $Tenant }
  & $Py -m promotion_gate.cli @Arguments
  if ($LASTEXITCODE) { throw "smgate $($Arguments[0]) terminó con código $LASTEXITCODE" }
}

# ---------------------------------------------------------------------------------------------- Entra (SPA)
function Ensure-Spa([string[]]$RedirectUris) {
  $filter = if ($SpaClientId) { "appId eq '$SpaClientId'" } else { "displayName eq '$SpaDisplayName'" }
  $app = (Invoke-Graph GET "applications?`$filter=$([uri]::EscapeDataString($filter))").value | Select-Object -First 1
  if (-not $app -and $SpaClientId) { throw "No encuentro el registro de aplicación $SpaClientId en el tenant." }
  if (-not $app) {
    if ($WhatIf) { Plan "crear registro SPA '$SpaDisplayName' con redirect URIs $($RedirectUris -join ', ')"; return '<nuevo-cliente-spa>' }
    $app = Invoke-Graph POST 'applications' @{ displayName = $SpaDisplayName; signInAudience = 'AzureADMyOrg'; spa = @{ redirectUris = $RedirectUris } }
    Info "registro SPA '$SpaDisplayName' creado ($($app.appId))"
  } else {
    Info "registro SPA '$($app.displayName)' ($($app.appId))"
  }
  $current = @($app.spa.redirectUris)
  $missing = @($RedirectUris | Where-Object { $_ -and $_ -notin $current })
  if ($missing) {
    if ($WhatIf) { Plan "añadir redirect URIs al SPA: $($missing -join ', ')" }
    else { Invoke-Graph PATCH "applications/$($app.id)" @{ spa = @{ redirectUris = @($current + $missing) } } | Out-Null; Info "redirect URIs añadidas: $($missing -join ', ')" }
  }
  if (-not $WhatIf -and -not (Invoke-Graph GET "servicePrincipals?`$filter=$([uri]::EscapeDataString("appId eq '$($app.appId)'"))").value) {
    Invoke-Graph POST 'servicePrincipals' @{ appId = $app.appId } | Out-Null
  }
  $app.appId
}

# ---------------------------------------------------------------------------------------------- Rayfin (app)
function Get-Port {
  $f = Join-Path $App 'rayfin' '.env'
  $line = if (Test-Path $f) { Get-Content $f | Where-Object { $_ -match '^RAYFIN_PUBLIC_FRONTEND_PORT=' } }
  if ($line) { [int]($line -split '=', 2)[1] } else { 5173 }
}
function Invoke-Rayfin([string[]]$Arguments) {
  $env:RAYFIN_TOKEN = Get-Token 'https://api.fabric.microsoft.com'
  $env:RAYFIN_TENANT_ID = (Get-Claims $env:RAYFIN_TOKEN).tid
  Push-Location $App
  try {
    npx rayfin @Arguments
    if ($LASTEXITCODE) { throw "rayfin $($Arguments -join ' ') terminó con código $LASTEXITCODE" }
  } finally { Pop-Location }
}
function Write-AppEnv([System.Collections.IDictionary]$Values) {
  $lines = @('# Generado por deploy/deploy.ps1. Ids públicos, sin secretos. Rayfin escribe su parte en .env.local.')
  $lines += $Values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }
  Set-Content (Join-Path $App '.env') $lines -Encoding utf8
}

# ================================================================================================ ejecución
Step 'Comprobaciones'
foreach ($tool in @('az', 'python') + $(if ('app' -in $Steps) { @('node', 'npm') } else { @() })) {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Falta '$tool' en el PATH." }
}
if ('app' -in $Steps -and -not $AppWorkspace) { throw 'El paso app necesita -AppWorkspace (o quita app de -Steps).' }
$claims = Get-Claims (Get-Token 'https://api.fabric.microsoft.com')
$who = if ($claims.upn) { $claims.upn } elseif ($claims.unique_name) { $claims.unique_name } else { $claims.appid }
Info "identidad: $who (tenant $($claims.tid))"
$tools = Resolve-Workspace $ToolsWorkspace
Info "workspace de herramientas: $($tools.displayName) ($($tools.sku), $($tools.region))"
$appWs = $null
if ('app' -in $Steps) {
  $appWs = Resolve-Workspace $AppWorkspace
  Info "workspace de la app: $($appWs.displayName) ($($appWs.sku), $($appWs.region))"
}
if ($CapacityMetricsWorkspace -and -not (Get-Workspaces | Where-Object displayName -eq $CapacityMetricsWorkspace)) {
  Write-Warning "No veo el workspace '$CapacityMetricsWorkspace' de Capacity Metrics: la fase de capacidad fallará sin acceso."
}
$lakehouseId = Ensure-Lakehouse $tools

$py = $null
if (-not $WhatIf -and ('orchestrator' -in $Steps -or 'gate' -in $Steps)) { $py = Get-GatePython }
if ('orchestrator' -in $Steps) {
  Step 'Fabric Load Test Orchestrator'
  if ($WhatIf) { Plan "instalar notebooks y pipelines del orquestador en $($tools.displayName)/$LakehouseName" }
  else {
    $repoArg = if ($OrchestratorRepo) { @('--repo', $OrchestratorRepo) } else { @() }
    Invoke-Smgate $py (@('install-orchestrator', '--workspace-id', $tools.id, '--lakehouse-id', $lakehouseId, '--overwrite') + $repoArg)
  }
}
if ('gate' -in $Steps) {
  Step 'Gate de promoción'
  if ($WhatIf) { Plan "construir el wheel y desplegar NB_Gate_*, PL_PromotionGate y gate.yaml en $($tools.displayName)" }
  else {
    Get-ChildItem (Join-Path $Root 'dist') -Filter 'promotion_gate-*.whl' -ErrorAction SilentlyContinue | Remove-Item
    & $py -m pip wheel $Root -w (Join-Path $Root 'dist') --no-deps -q --disable-pip-version-check
    if ($LASTEXITCODE) { throw 'No se pudo construir el wheel del gate.' }
    Invoke-Smgate $py @('deploy', '--workspace-id', $tools.id, '--lakehouse-id', $lakehouseId, '--overwrite')
  }
}

$deployment = $null
if ('app' -in $Steps) {
  Step 'Fabric App (Rayfin)'
  $port = Get-Port
  $client = Ensure-Spa @("http://localhost:$port/blank.html")
  $envValues = [ordered]@{
    VITE_MSAL_CLIENT_ID = $client; VITE_MSAL_TENANT_ID = $claims.tid
    VITE_GATE_WORKSPACE_ID = $tools.id; VITE_GATE_LAKEHOUSE_ID = $lakehouseId
    VITE_CAPACITY_METRICS_WORKSPACE = $CapacityMetricsWorkspace
  }
  if ($WhatIf) {
    Plan 'escribir app/.env con el cliente SPA y el workspace del gate'
    Plan "npm ci y rayfin up --workspace-id $($appWs.id) --item-name $AppItemName (build, hosting y tabla GateRun)"
    Plan 'añadir <url de hosting>/blank.html a las redirect URIs del SPA'
  } else {
    Write-AppEnv $envValues
    if (-not (Test-Path (Join-Path $App 'node_modules'))) {
      $install = if (Test-Path (Join-Path $App 'package-lock.json')) { 'ci' } else { 'install' }
      Push-Location $App; npm $install --no-audit --no-fund; $code = $LASTEXITCODE; Pop-Location
      if ($code) { throw "npm $install falló." }
    }
    # rayfin up añade la URL de hosting a rayfin.yml y la registra en el backend: se restaura para no ensuciar git.
    $yml = Join-Path $App 'rayfin' 'rayfin.yml'
    $ymlBackup = Get-Content $yml -Raw
    try { Invoke-Rayfin @('up', '--workspace-id', $appWs.id, '--item-name', $AppItemName, '--yes') }
    finally { Set-Content $yml $ymlBackup -NoNewline -Encoding utf8 }
    $deployments = Get-Content (Join-Path $App 'rayfin' '.deployments.json') -Raw | ConvertFrom-Json
    $deployment = $deployments.deployments.($deployments.active)
    if ($deployment.hostingUrl) { Ensure-Spa @("http://localhost:$port/blank.html", "$($deployment.hostingUrl)/blank.html") | Out-Null }
  }
}

if ($SuccessCase) {
  Step 'Caso de éxito Ventas Retail'
  $modelWs = if ($SuccessCaseWorkspace) { Resolve-Workspace $SuccessCaseWorkspace } else { $tools }
  if ($modelWs.id -eq $tools.id) { Write-Warning 'El modelo compartirá capacidad con el generador de carga: el gate lo marcará como observación.' }
  if ($WhatIf) { Plan "lakehouse, modelo Direct Lake e informe de Ventas Retail en $($modelWs.displayName) ($($modelWs.sku)); escenario en $LakehouseName" }
  else {
    $demoVenv = Join-Path $Root '.venv-demo'
    $demoPy = if ($IsWin) { Join-Path $demoVenv 'Scripts' 'python.exe' } else { Join-Path $demoVenv 'bin' 'python' }
    if (-not (Test-Path $demoPy)) {
      if ($IsWin -and $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        # deltalake no publica wheels para Windows ARM64: Python x64 por emulación
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'En Windows ARM64 el caso de éxito necesita uv (winget install astral-sh.uv).' }
        uv venv $demoVenv --python cpython-3.12-windows-x86_64-none -q
        uv pip install --python $demoPy -q numpy pandas pyarrow deltalake httpx
      } else {
        python -m venv $demoVenv
        & $demoPy -m pip install -q --disable-pip-version-check numpy pandas pyarrow deltalake httpx
      }
    }
    $scope = if ($Subscription) { @('--subscription', $Subscription) } elseif ($Tenant) { @('--tenant', $Tenant) } else { @() }
    $env:PYTHONIOENCODING = 'utf-8'
    & $demoPy (Join-Path $Root 'demo' 'caso-exito' 'build.py') --workspace-id $modelWs.id --gate-workspace-id $tools.id --gate-lakehouse-id $lakehouseId @scope
    if ($LASTEXITCODE) { throw 'El caso de éxito falló.' }
  }
}

Step 'Resultado'
$summary = [ordered]@{
  tools_workspace = $tools.displayName; tools_workspace_id = $tools.id; lakehouse_id = $lakehouseId
  tools_portal = "https://app.fabric.microsoft.com/groups/$($tools.id)/list"
  capacity_metrics_workspace = $CapacityMetricsWorkspace
}
if ($deployment) { $summary.app_portal = $deployment.fabricDeepLink; $summary.app_hosting = $deployment.hostingUrl }
$summary.GetEnumerator() | ForEach-Object { Info ('{0,-28} {1}' -f $_.Key, $_.Value) }
if (-not $WhatIf) {
  $summary | ConvertTo-Json | Set-Content (Join-Path $PSScriptRoot '.deployment.json') -Encoding utf8
  Info 'guardado en deploy/.deployment.json (no se versiona)'
}
if ($deployment) { Info 'Abre la app desde app_portal: el hosting directo exige sesión de Fabric (assetAccess: protected).' }
