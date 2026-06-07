param(
    [ValidateSet('prepare', 'run', 'debug', 'clean', 'emoji-zip', 'build-icons', 'help')]
    [string]$target = 'help'
)

$VENV_DIR = "venv"
$PYTHON = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }
$PIP = "$VENV_DIR\Scripts\pip.exe"
$PYTHON_VENV = "$VENV_DIR\Scripts\python.exe"

function Log-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Log-Error($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Target-Prepare {
    Log-Info "Checking virtual environment..."

    if (-not (Test-Path "$VENV_DIR\Scripts\python.exe")) {
        Log-Info "Creating virtual environment..."
        & $PYTHON -m venv $VENV_DIR
        if (-not (Test-Path "$VENV_DIR\Scripts\python.exe")) {
            Log-Error "Failed to create virtual environment."
            exit 1
        }
        Log-Info "Virtual environment created."
    }

    Log-Info "Installing/upgrading pip..."
    & $PYTHON_VENV -m pip install --upgrade pip

    Log-Info "Installing Python dependencies..."
    if (Test-Path "requirements.txt") {
        & $PYTHON_VENV -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) {
            Log-Error "pip install failed. Check requirements.txt."
            exit 1
        }
    } else {
        Log-Error "requirements.txt not found."
        exit 1
    }

    Log-Info "Setup complete. Run '.\Makefile.ps1 run' to start the app."
}

function Target-Run {
    if (-not (Test-Path $PYTHON_VENV)) {
        Log-Error "Virtual environment not found. Run '.\Makefile.ps1 prepare' first."
        exit 1
    }
    Log-Info "Starting Lawenda..."
    & $PYTHON_VENV main.py
}

function Target-Debug {
    if (-not (Test-Path $PYTHON_VENV)) {
        Log-Error "Virtual environment not found. Run '.\Makefile.ps1 prepare' first."
        exit 1
    }
    Log-Info "Starting Lawenda (debug mode)..."
    $env:KIVY_LOG_LEVEL = 'debug'
    & $PYTHON_VENV main.py
}

function Target-Clean {
    Log-Info "Cleaning __pycache__ directories..."
    Get-ChildItem -Path . -Directory -Recurse -Filter "__pycache__" | ForEach-Object {
        Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
        Log-Info "  removed $($_.FullName)"
    }

    if (Test-Path "bin") {
        Log-Info "Removing bin/ directory..."
        Remove-Item -Recurse -Force "bin" -ErrorAction SilentlyContinue
    }

    Log-Info "Clean complete."
}

function Target-EmojiZip {
    if (-not (Test-Path $PYTHON_VENV)) {
        Log-Error "Virtual environment not found. Run '.\Makefile.ps1 prepare' first."
        exit 1
    }
    Log-Info "Packing emoji PNGs into ZIP..."
    & $PYTHON_VENV scripts/build_emoji_zip.py
}

function Target-BuildIcons {
    if (-not (Test-Path $PYTHON_VENV)) {
        Log-Error "Virtual environment not found. Run '.\Makefile.ps1 prepare' first."
        exit 1
    }
    Log-Info "Building app icons..."
    & $PYTHON_VENV scripts/build_icons.py
}

function Target-Help {
    Write-Host @"
Lawenda – Windows Helper
-------------------------
Usage: .\Makefile.ps1 -target <command>

Commands:
  prepare      Create venv, install dependencies (pip install -r requirements.txt)
  run          Start the application
  debug        Start with KIVY_LOG_LEVEL=debug
  clean        Remove __pycache__ and bin/ directory
  emoji-zip    Pack emoji PNGs into assets/Emoji_PNG.zip
  build-icons  Generate app icons from assets/icon/source.png
  help         Show this help message

Examples:
  .\Makefile.ps1 -target prepare
  .\Makefile.ps1 -target run
"@
}

# Dispatch to the selected target
switch ($target) {
    'prepare'     { Target-Prepare }
    'run'         { Target-Run }
    'debug'       { Target-Debug }
    'clean'       { Target-Clean }
    'emoji-zip'   { Target-EmojiZip }
    'build-icons' { Target-BuildIcons }
    'help'        { Target-Help }
}
