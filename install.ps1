# JobRadar installer for Windows. In PowerShell:
#   irm https://raw.githubusercontent.com/FuzzyLaDuzzy/jobradar/main/install.ps1 | iex
# Run it again to update: config.yaml, .env, the jobs database and the backups are never touched.
# Options when saving and running the file yourself: -Dir <folder>, -Source <local copy>, -Yes, -NoShortcuts, -NoStart.
param(
    [string]$Dir = "$env:LOCALAPPDATA\JobRadar",
    [string]$Source = "",  # a local copy of the project instead of downloading it
    [switch]$Yes,          # yes to every question (unattended)
    [switch]$NoShortcuts,  # no Start menu, sign-in or daily searches (e.g. a second copy)
    [switch]$NoStart
)
$ErrorActionPreference = "Stop"
$Repo = "https://github.com/FuzzyLaDuzzy/jobradar"
$Code = @("jobradar", "requirements.txt", "config.example.yaml", ".env.example", "README.md", "LICENSE")

function Say($text) { Write-Host "==> $text" -ForegroundColor Green }

function Ask($question) {
    if ($Yes) { return $true }
    try { $answer = Read-Host "$question [Y/n]" } catch { return $false }  # no console to ask: no
    return $answer -notmatch '^\s*(n|no|nao|não)\s*$'
}

function Find-Python {
    # py -3 (the launcher) first: "python" may be the Microsoft Store alias, which only opens the Store
    foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
        $exe = Get-Command $candidate[0] -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        $extra = @($candidate | Select-Object -Skip 1)
        try { $ok = & $exe.Source @extra -c "import sys; print(sys.version_info >= (3, 10))" 2>$null } catch { continue }
        if ($ok -eq "True") { return , (@($exe.Source) + $extra) }
    }
    return $null
}

# 1. Python 3.10 or later
$python = Find-Python
if (-not $python) {
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Ask "Python 3.10+ not found. Install Python 3.12 now (winget, just for you)?")) {
        winget install --id Python.Python.3.12 --exact --scope user --accept-package-agreements --accept-source-agreements
        $env:Path = "$env:LOCALAPPDATA\Programs\Python\Launcher;$env:LOCALAPPDATA\Programs\Python\Python312;$env:Path"
        $python = Find-Python
    }
    if (-not $python) { throw "JobRadar needs Python 3.10 or later: https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again." }
}
Say "Python: $(& $python[0] @($python | Select-Object -Skip 1) --version)"

# 2. The code (only the code: your settings, keys and jobs stay as they are)
New-Item -ItemType Directory -Force $Dir | Out-Null
if ($Source) {
    $from = (Resolve-Path $Source).Path
} else {
    Say "Downloading JobRadar from $Repo"
    $zip = Join-Path $env:TEMP "jobradar-main.zip"
    $unpacked = Join-Path $env:TEMP "jobradar-install"
    Invoke-WebRequest "$Repo/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
    if (Test-Path $unpacked) { Remove-Item $unpacked -Recurse -Force }
    Expand-Archive $zip $unpacked
    $from = Join-Path $unpacked "jobradar-main"
}
if (Test-Path "$Dir\jobradar") { Remove-Item "$Dir\jobradar" -Recurse -Force }  # files removed upstream go too
foreach ($item in $Code) {
    if (Test-Path "$from\$item") { Copy-Item "$from\$item" $Dir -Recurse -Force }
}
Say "Installed in $Dir"

# 3. Its own Python environment and packages
$venvPython = "$Dir\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Say "Creating the Python environment"
    & $python[0] @($python | Select-Object -Skip 1) -m venv "$Dir\.venv"
}
Say "Installing the packages (a minute or two the first time)"
& $venvPython -m pip install --disable-pip-version-check --quiet -r "$Dir\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "pip couldn't install the packages (see above)." }

# 4. Start menu, and optionally sign-in and the daily searches
$pythonw = "$Dir\.venv\Scripts\pythonw.exe"
function New-Shortcut($path) {
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = "-m jobradar"
    $shortcut.WorkingDirectory = $Dir
    $shortcut.IconLocation = "$Dir\jobradar\static\icon.ico"
    $shortcut.Save()
}
if (-not $NoShortcuts) {
    New-Shortcut "$([Environment]::GetFolderPath('Programs'))\JobRadar.lnk"
    Say "Added JobRadar to the Start menu"
}
if (-not $NoShortcuts -and (Ask "Open JobRadar when you sign in to Windows?")) {
    New-Shortcut "$([Environment]::GetFolderPath('Startup'))\JobRadar.lnk"
}
if (-not $NoShortcuts -and (Ask "Search for new jobs every day at 9:00 and 21:00 (even with JobRadar closed)?")) {
    try {
        $action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m jobradar refresh" -WorkingDirectory $Dir
        $triggers = @((New-ScheduledTaskTrigger -Daily -At 9am), (New-ScheduledTaskTrigger -Daily -At 9pm))
        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable  # runs on boot if the PC was off
        Register-ScheduledTask -TaskName "JobRadar refresh" -Action $action -Trigger $triggers -Settings $settings -Force | Out-Null
        Say "Daily searches set up (task 'JobRadar refresh')"
    } catch {
        Write-Warning "Couldn't create the daily searches: $($_.Exception.Message)"
    }
}

Say "Done. To update later, run the same line again. To uninstall: delete $Dir, the JobRadar shortcuts and the 'JobRadar refresh' task."
if (-not $NoStart) { Start-Process $pythonw -ArgumentList "-m", "jobradar" -WorkingDirectory $Dir }
