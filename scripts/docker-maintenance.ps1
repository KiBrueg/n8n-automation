<#
.SYNOPSIS
    Обслуживание Docker на Windows (WSL2): чистка мусора + опц. сжатие vhdx.

.DESCRIPTION
    Docker сам место не отдаёт. Скрипт:
      1) удаляет неиспользуемые образы, build cache и остановленные контейнеры
         (VOLUMES НЕ ТРОГАЕТ — данные n8n/Postgres в безопасности);
      2) по флагу -Compact ужимает файл vhdx и реально возвращает место на диск.

    Запуск вручную:
        powershell -ExecutionPolicy Bypass -File scripts\docker-maintenance.ps1
        powershell -ExecutionPolicy Bypass -File scripts\docker-maintenance.ps1 -Compact

    Автозапуск раз в неделю — см. команду schtasks в конце файла.

.PARAMETER OlderThanHours
    Чистить только объекты старше N часов (по умолчанию 168 = 7 дней),
    чтобы не убить кэш текущей работы.

.PARAMETER Compact
    Дополнительно сжать vhdx (остановит WSL! закрой Docker Desktop заранее).

.PARAMETER VhdxPath
    Путь к docker_desktop_data.vhdx. Если не задан — ищется автоматически.
#>

param(
    [int]$OlderThanHours = 168,
    [switch]$Compact,
    [string]$VhdxPath
)

$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "==> $m" -ForegroundColor Green }
function Warn($m) { Write-Host "!!  $m" -ForegroundColor Yellow }

# --- 0. Проверка, что docker отвечает ---
try {
    docker version --format '{{.Server.Version}}' | Out-Null
} catch {
    Warn "Docker-движок не отвечает. Запусти Docker Desktop (Engine running) и повтори."
    exit 1
}

Info "Docker занято ДО чистки:"
docker system df

$filter = "until=${OlderThanHours}h"

Info "Удаляю остановленные контейнеры"
docker container prune -f | Out-Null

Info "Удаляю неиспользуемые образы старше $OlderThanHours ч"
docker image prune -af --filter $filter | Out-Null

Info "Чищу build cache старше $OlderThanHours ч"
docker builder prune -af --filter $filter | Out-Null

Info "Удаляю висячие (dangling) тома БЕЗ имени (именованные тома n8n/pg не трогаются)"
# только анонимные dangling-тома; named volumes (pg_data, n8n_data) защищены
docker volume ls -qf dangling=true | ForEach-Object { docker volume rm $_ 2>$null } | Out-Null

Info "Docker занято ПОСЛЕ чистки:"
docker system df

# --- Сжатие vhdx (опционально) ---
if ($Compact) {
    Info "Режим -Compact: остановка WSL и сжатие vhdx"

    if (-not $VhdxPath) {
        $candidates = @(
            "D:\DockerData",
            "$env:LOCALAPPDATA\Docker"
        )
        foreach ($root in $candidates) {
            if (Test-Path $root) {
                $found = Get-ChildItem -Path $root -Recurse -Filter "*.vhdx" -ErrorAction SilentlyContinue |
                         Sort-Object Length -Descending | Select-Object -First 1
                if ($found) { $VhdxPath = $found.FullName; break }
            }
        }
    }

    if (-not $VhdxPath -or -not (Test-Path $VhdxPath)) {
        Warn "Не нашёл vhdx автоматически. Укажи путь: -VhdxPath 'D:\DockerData\...\docker_desktop_data.vhdx'"
        exit 1
    }

    Info "Найден vhdx: $VhdxPath ($([math]::Round((Get-Item $VhdxPath).Length/1GB,2)) ГБ)"
    Warn "Останавливаю WSL (Docker Desktop должен быть закрыт)..."
    wsl --shutdown
    Start-Sleep -Seconds 5

    # diskpart compact — работает и на Windows Home (Optimize-VHD требует Hyper-V/Pro)
    $diskpartScript = @"
select vdisk file="$VhdxPath"
attach vdisk readonly
compact vdisk
detach vdisk
exit
"@
    $tmp = [System.IO.Path]::GetTempFileName()
    Set-Content -Path $tmp -Value $diskpartScript -Encoding ASCII
    Info "Сжатие через diskpart..."
    diskpart /s $tmp
    Remove-Item $tmp -Force

    Info "vhdx после сжатия: $([math]::Round((Get-Item $VhdxPath).Length/1GB,2)) ГБ"
    Info "Готово. Запусти Docker Desktop снова."
}

Info "Обслуживание завершено."

# ============================================================
# Автозапуск раз в неделю (вс, 04:00) — выполнить ОДИН раз в PowerShell (от админа):
#
#   $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
#       -Argument "-ExecutionPolicy Bypass -File `"$PWD\scripts\docker-maintenance.ps1`""
#   $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 4am
#   Register-ScheduledTask -TaskName "Docker Maintenance" -Action $action -Trigger $trigger `
#       -Description "Еженедельная чистка Docker (prune)"
#
# Сжатие vhdx раз в месяц лучше запускать вручную с -Compact, т.к. оно
# останавливает WSL и требует закрытого Docker Desktop.
# ============================================================
