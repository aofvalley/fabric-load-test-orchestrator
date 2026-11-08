#Requires -Version 7
<#
.SYNOPSIS
  Quita el gate (y, con -App, la Fabric App) tras confirmar escribiendo el nombre del workspace.

.DESCRIPTION
  Borra NB_Gate_* y PL_PromotionGate del workspace de herramientas. No toca el orquestador de carga, el lakehouse,
  Files/PromotionGate ni las tablas gate_*: son la auditoría de promociones. Con -App borra también el item de la app.
  El registro SPA de Entra y la carpeta del caso de éxito se borran a mano. -WhatIf solo lista.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)] [string]$ToolsWorkspace,
  [string]$AppWorkspace,
  [string]$AppItemName = 'PromotionGateApp',
  [switch]$App,
  [string]$Subscription,
  [string]$Tenant,
  [switch]$WhatIf
)
$ErrorActionPreference = 'Stop'
$scope = if ($Subscription) { @('--subscription', $Subscription) } elseif ($Tenant) { @('--tenant', $Tenant) } else { @() }
$token = az account get-access-token --resource https://api.fabric.microsoft.com @scope --query accessToken -o tsv 2>$null
if (-not $token) { throw 'Sin token de Azure CLI para Fabric: az login.' }
$h = @{ Authorization = "Bearer $token" }
$api = 'https://api.fabric.microsoft.com/v1'
function Find-Workspace([string]$NameOrId) {
  $ws = (Invoke-RestMethod "$api/workspaces" -Headers $h).value | Where-Object { $_.id -eq $NameOrId -or $_.displayName -eq $NameOrId }
  if (-not $ws) { throw "No encuentro el workspace '$NameOrId'." }
  $ws
}

$targets = @()
$tools = Find-Workspace $ToolsWorkspace
$names = 'PL_PromotionGate', 'NB_Gate_ModelReview', 'NB_Gate_LoadTestReport', 'NB_Gate_CapacityMetrics', 'NB_Gate_Verdict'
$targets += (Invoke-RestMethod "$api/workspaces/$($tools.id)/items" -Headers $h).value |
  Where-Object { $names -contains $_.displayName } | ForEach-Object { [pscustomobject]@{ ws = $tools; item = $_ } }
if ($App) {
  if (-not $AppWorkspace) { throw '-App necesita -AppWorkspace.' }
  $appWs = Find-Workspace $AppWorkspace
  $targets += (Invoke-RestMethod "$api/workspaces/$($appWs.id)/items" -Headers $h).value |
    Where-Object { $_.displayName -eq $AppItemName -and $_.type -ne 'SQLEndpoint' } | ForEach-Object { [pscustomobject]@{ ws = $appWs; item = $_ } }
}
if (-not $targets) { Write-Host 'No hay nada que borrar.'; exit 0 }
Write-Host 'Se borrarían:'
$targets | ForEach-Object { Write-Host ("  {0} / {1} ({2})" -f $_.ws.displayName, $_.item.displayName, $_.item.type) }
if ($WhatIf) { exit 0 }
if ((Read-Host "Escribe '$($tools.displayName)' para confirmar") -cne $tools.displayName) { Write-Host 'Cancelado.'; exit 1 }
foreach ($t in $targets) {
  Invoke-RestMethod -Method Delete "$api/workspaces/$($t.ws.id)/items/$($t.item.id)" -Headers $h | Out-Null
  Write-Host "Borrado $($t.item.displayName)"
}
