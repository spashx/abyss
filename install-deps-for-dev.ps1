#Requires -Version 5.1
<#
.SYNOPSIS
    Prepares the Abyss MCP repository for local development.

.DESCRIPTION
    Creates a Python 3.13 virtual environment with uv, installs dependencies from
    requirements.txt, and prints the mcp.json settings needed to run Abyss from source.
#>

[CmdletBinding()]
param()

# Stop on any error encountered during script execution
$ErrorActionPreference = "Stop"

# ═══════════════════════════════════════════════════════════════════════════
# Configuration Variables
# ═══════════════════════════════════════════════════════════════════════════
# Use Python 3.13 for compatibility with modern async/type hints and performance
$PythonVersion = "3.13"

# Detect repository root: use PSScriptRoot if run as script, else current working directory
# This ensures the script works whether executed from repo root or a subdirectory
$repoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$repoRoot = [System.IO.Path]::GetFullPath($repoRoot)

# Virtual environment path: isolated Python environment for this project
# Located in .venv/ to be ignored by .gitignore and avoid polluting the system Python
$venvPath = Join-Path $repoRoot ".venv"

# ChromaDB persistence directory: where embeddings and vector database are stored
# Created by the ingestion pipeline; manually tracked here for reference (used in documentation)
$dbPath = Join-Path $repoRoot "data\chroma_db"

# Dependency manifest: defines all required packages (llama-index, chromadb, tree-sitter, etc.)
$requirementsPath = Join-Path $repoRoot "requirements.txt"

# Python executable in the virtual environment
# Used by uv to isolate installations and ensure dependency consistency
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

# ═══════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════

# Write a colored log message to console
# Usage: Displays step progress and status to the user in a consistent format
function Write-Step {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Cyan
    )

    Write-Host $Message -ForegroundColor $Color
}

# Check if a command/executable is available on the PATH
# Returns $true if found, $false otherwise
# Usage: Validate prerequisites like 'uv' package manager before proceeding
function Test-CommandExists {
    param([string]$Name)

    return $null -ne (Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

# Execute a command and fail fast if exit code is non-zero
# Provides consistent error handling and informative error messages
# Usage: Wraps uv commands to ensure any installation failures stop the script immediately
function Invoke-Checked {
    param(
        [string]$Description,     # User-friendly description of what's running
        [string]$FilePath,        # Executable path (e.g., "uv", "python.exe")
        [string[]]$ArgumentList   # Command arguments
    )

    Write-Step $Description
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
    }
}

# ═══════════════════════════════════════════════════════════════════════════
# Pre-Setup Validation
# ═══════════════════════════════════════════════════════════════════════════

Write-Host ""
Write-Host "======== Abyss MCP Repository Setup ========" -ForegroundColor White
Write-Host ""
Write-Host "Repository root: $repoRoot"
Write-Host ""

# Verify requirements.txt exists - essential for uv to know what to install
# Fail early if the repository structure is incomplete
if (-not (Test-Path -Path $requirementsPath -PathType Leaf)) {
    throw "Missing requirements.txt at $requirementsPath"
}

# Verify 'uv' is available - modern fast Python package manager
# uv replaces pip/virtualenv with superior performance and deterministic dependency resolution
# https://github.com/astral-sh/uv
if (-not (Test-CommandExists -Name "uv")) {
    throw "uv is not installed or not available on PATH. Install it from https://github.com/astral-sh/uv"
}

# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Create Python Virtual Environment
# ═══════════════════════════════════════════════════════════════════════════
# Benefits of virtual environments:
# - Isolates project dependencies from system Python
# - Prevents version conflicts with other projects
# - Enables reproducible builds across machines
# - Allows safe pip upgrades without system impact

Invoke-Checked -Description "[1/3] Creating Python $PythonVersion virtual environment at $venvPath..." -FilePath "uv" -ArgumentList @("venv", $venvPath, "--python", $PythonVersion)

# Verify Python executable exists in the new virtual environment
# This confirms uv successfully created a functional Python installation
if (-not (Test-Path -Path $pythonExe -PathType Leaf)) {
    throw "Virtual environment was created, but Python was not found at $pythonExe"
}

Write-Step "[OK] Virtual environment created successfully." -Color Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Install Dependencies
# ═══════════════════════════════════════════════════════════════════════════
# Installs all packages listed in requirements.txt into the virtual environment:
# - LlamaIndex: orchestrates document indexing, chunking, embedding, and storage
# - ChromaDB: vector database for semantic search
# - sentence-transformers: local embedding model (all-MiniLM-L6-v2)
# - tree-sitter: code syntax parsing for multiple languages
# - Protobuf/grpcio-tools: SCIP protocol support for source code analysis
# - markitdown: universal document converter (PDF, DOCX, PPTX → Markdown)
# 
# Flags:
# - --native-tls: uses OS SSL certificates instead of bundled roots (faster, more secure)

Invoke-Checked -Description "[2/3] Installing Python dependencies from requirements.txt..." -FilePath "uv" -ArgumentList @("pip", "install", "--python", $pythonExe, "-r", $requirementsPath, "--native-tls")

Write-Step "[OK] Dependencies installed successfully." -Color Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Configuration & MCP Server Setup
# ═══════════════════════════════════════════════════════════════════════════
# The Model Context Protocol (MCP) allows Claude/IDE extensions to invoke Abyss tools
# mcp.json tells the MCP client how to start the Abyss server as a subprocess

# PYTHONPATH: ensures Python can import the 'abyss' package from src/ directory
# Without this, the MCP client won't be able to find the abyss module
# Kept here as a reference variable for the mcp.json configuration shown below
$pythonPathEnv = Join-Path $repoRoot "src"

Write-Step "[3/3] Final setup steps..."
Write-Host ""
Write-Host "======== IMPORTANT: Configuration Required ========" -ForegroundColor Yellow
Write-Host ""
Write-Host "Update your mcp.json file with the following configuration:"
Write-Host "Replace <local_repos_path> with the full path to this repository."
Write-Host ""
Write-Host "EXAMPLE (mcp.json):"
Write-Host ""
Write-Host "{"
Write-Host '  "servers": {'
Write-Host '    "abyss": {'
Write-Host ('      "command": "<local_repos_path>\.venv\Scripts\python.exe",')
Write-Host '      "args": ['
Write-Host '        "-m",'
Write-Host '        "abyss"'
Write-Host '      ],'
Write-Host '      "env": {'
Write-Host ('        "PYTHONPATH": "<local_repos_path>\src"')
Write-Host '      }'
Write-Host '    }'
Write-Host '  }'
Write-Host "}"
Write-Host ""
Write-Host "========== Setup Complete! ==========" -ForegroundColor Green
Write-Host ""
Write-Host "Configuration Notes:"
Write-Host "  - command: Points to the Python executable in the virtual environment"
Write-Host "  - args: Runs Abyss as a Python module (-m abyss)"
Write-Host "  - env.PYTHONPATH: Allows Python to import from src/ (required for 'import abyss')"
Write-Host "  - mcp.json typically lives in ~/.config/Claude/ or your IDE's MCP config directory"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Update mcp.json with the configuration above"
Write-Host "  2. Verify the paths match your repository location"
Write-Host "  3. Start the MCP server as configured in your MCP client"
Write-Host ""