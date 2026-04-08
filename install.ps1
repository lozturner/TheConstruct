# TheConstruct — one-line installer for Windows (PowerShell).
#
# Usage (paste this one line into PowerShell):
#   iwr -useb https://raw.githubusercontent.com/lozturner/theconstruct/claude/multi-agent-orchestration-ipOZM/install.ps1 | iex
#
# Clones/updates the repo into %USERPROFILE%\TheConstruct, makes a venv,
# installs deps, puts a shortcut on your Desktop, and launches the local
# web app at http://localhost:7117/.

$ErrorActionPreference = "Stop"

$Repo   = "https://github.com/lozturner/theconstruct.git"
$Branch = "claude/multi-agent-orchestration-ipOZM"
$Dst    = Join-Path $env:USERPROFILE "TheConstruct"
$Port   = 7117

function Say($msg) { Write-Host "[TheConstruct] $msg" -ForegroundColor Cyan }

# 1. Need Python and git. Help the user if they're missing.
foreach ($cmd in "python","git") {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "[TheConstruct] $cmd is not installed or not on PATH." -ForegroundColor Red
        if ($cmd -eq "python") { Write-Host "  Install from https://www.python.org/downloads/ (check 'Add to PATH')." }
        if ($cmd -eq "git")    { Write-Host "  Install from https://git-scm.com/download/win" }
        exit 1
    }
}

# 2. Clone or update.
if (Test-Path $Dst) {
    Say "Updating existing install at $Dst"
    Push-Location $Dst
    git fetch origin $Branch 2>&1 | Out-Null
    git checkout $Branch 2>&1 | Out-Null
    git reset --hard "origin/$Branch" 2>&1 | Out-Null
    Pop-Location
} else {
    Say "Cloning into $Dst"
    git clone --branch $Branch --depth 1 $Repo $Dst | Out-Null
}

Push-Location $Dst

# 3. venv + deps.
$Venv    = Join-Path $Dst ".venv"
$VenvPy  = Join-Path $Venv "Scripts\python.exe"
$VenvPw  = Join-Path $Venv "Scripts\pythonw.exe"
if (-not (Test-Path $VenvPy)) {
    Say "Creating virtual environment"
    python -m venv $Venv
}

Say "Installing Python dependencies (this takes a minute)"
& $VenvPy -m pip install --upgrade pip --quiet
& $VenvPy -m pip install --quiet -r requirements.txt

Say "Installing Chromium for Playwright"
& $VenvPy -m playwright install chromium 2>&1 | Out-Null

# 4. Desktop shortcut -> launches the app without a console window.
$Shortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "TheConstruct.lnk"
$WScript  = New-Object -ComObject WScript.Shell
$Sc       = $WScript.CreateShortcut($Shortcut)
$Sc.TargetPath       = $VenvPw
$Sc.Arguments        = "`"$Dst\app.py`""
$Sc.WorkingDirectory = $Dst
$Sc.IconLocation     = "$VenvPy,0"
$Sc.Description      = "TheConstruct — YouTube link in, Desktop folder out"
$Sc.Save()
Say "Desktop shortcut created: $Shortcut"

# 5. Launch now.
Say "Starting TheConstruct at http://localhost:$Port/ ..."
Start-Process -FilePath $VenvPw -ArgumentList "`"$Dst\app.py`"" -WorkingDirectory $Dst
Start-Sleep -Seconds 2
Start-Process "http://localhost:$Port/"

Pop-Location
Say "Done. Double-click the Desktop shortcut next time."
