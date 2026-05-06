$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=================================="
Write-Host "DP采集器 - 构建环境检查"
Write-Host "=================================="

if (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Host ("✅ 找到 Git: " + (git --version))
}
else {
    Write-Host "⚠️ 未找到 Git"
    Write-Host "   如果只是当前目录已有完整源码，可以继续打包。"
    Write-Host "   如果需要 git clone / git pull，请先安装 Git: https://git-scm.com/download/win"
}

$PythonCmd = $null
$PythonArgs = @()
if (Get-Command python3.11 -ErrorAction SilentlyContinue) {
    $PythonCmd = "python3.11"
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCmd = "py"
    $PythonArgs = @("-3.11")
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
}

if (-not $PythonCmd) {
    Write-Error "未找到 Python，请先安装 Python 3.11+。"
}

& $PythonCmd @PythonArgs -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" 2>$null
if ($LASTEXITCODE -ne 0) {
    $VersionText = & $PythonCmd @PythonArgs --version 2>&1
    Write-Error "Python 版本不受支持: $VersionText。当前本地构建固定使用 Python 3.11.x。"
}

$VersionText = & $PythonCmd @PythonArgs --version 2>&1
Write-Host ("✅ 找到 Python: " + $VersionText)
Write-Host ""

& $PythonCmd @PythonArgs bootstrap_build.py @args
exit $LASTEXITCODE
