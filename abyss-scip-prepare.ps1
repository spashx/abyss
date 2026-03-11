#Requires -Version 5.1
<#
.SYNOPSIS
    Abyss SCIP Prepare — universal SCIP indexer launcher for all supported languages.

.DESCRIPTION
    This script:
    1. Validates the target project directory.
    2. Checks prerequisites (runtime, dependencies) for the selected indexer.
    3. Installs the indexer if not already present.
    4. Runs the indexer in the target directory.
    5. Renames the output to the canonical abyss.<type>.index.scip filename.
    6. Logs all output to a timestamped log file.
    7. Prompts the user to index the folder via Abyss MCP server.

    Supported indexer types:
      dotnet     — C# / .NET projects   (scip-dotnet via dotnet tool)
      python     — Python projects       (scip-python via pip)
      java       — Java/Kotlin projects  (scip-java fat JAR via Maven Central)
      typescript — TypeScript & JavaScript projects (scip-typescript via npm)

.PARAMETER Path
    Path to the project directory to index.

.PARAMETER Type
    SCIP indexer type: dotnet | python | java | typescript
    Note: "typescript" also covers JavaScript projects.

.EXAMPLE
    .\abyss-scip-prepare.ps1 -Path "C:\dev\my-app" -Type dotnet
    .\abyss-scip-prepare.ps1 "C:\dev\my-lib" typescript
    .\abyss-scip-prepare.ps1 "C:\dev\my-api" java
    .\abyss-scip-prepare.ps1 "C:\dev\my-bot" python
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0, HelpMessage = "Path to the project directory")]
    [string]$ProjectPath,

    [Parameter(Mandatory = $true, Position = 1, HelpMessage = "SCIP indexer type")]
    [ValidateSet("dotnet", "python", "java", "typescript")]
    [string]$Type
)

# ==================================================================
#  Configuration & Constants
# ==================================================================

$ErrorActionPreference = "Stop"
$ScriptVersion         = "1.0.0"
$Timestamp             = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$ScriptDir             = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$LogDir                = Join-Path $ScriptDir "logs"
$LogFile               = Join-Path $LogDir "scip-${Type}_${Timestamp}.log"

# -- Log level constants ----------------------------------------

$LOG_ERROR   = "ERROR"
$LOG_WARN    = "WARN"
$LOG_SUCCESS = "SUCCESS"
$LOG_STEP    = "STEP"
$LOG_INFO    = "INFO"

# -- Runtime command names -------------------------------------

$CMD_DOTNET  = "dotnet"
$CMD_PIP     = "pip"
$CMD_NPM     = "npm"
$CMD_NODE    = "node"
$CMD_MVN     = "mvn"
$CMD_JAVA    = "java"

# -- dotnet-specific -------------------------------------------

$DOTNET_TOOLS_SUBDIR   = ".dotnet\tools"

# -- scip-dotnet project discovery ----------------------------

$PATTERN_SLN    = "*.sln"
$PATTERN_CSPROJ = "*.csproj"
$PROJECT_DEPTH  = 2

# -- scip-java (via Coursier launcher) -----------------------
# scip-java_2.13 is a library JAR on Maven Central; it cannot be invoked
# directly via 'java -jar'.  Coursier resolves its dependencies at runtime.
# Reference: https://sourcegraph.github.io/scip-java/docs/getting-started.html#java-launcher

$SCIP_JAVA_ARTIFACT      = "scip-java_2.13"
$SCIP_JAVA_GROUP         = "com.sourcegraph"
$SCIP_JAVA_MAVEN_BASE    = "https://repo1.maven.org/maven2/com/sourcegraph/${SCIP_JAVA_ARTIFACT}"
$SCIP_JAVA_METADATA_URL  = "${SCIP_JAVA_MAVEN_BASE}/maven-metadata.xml"

# Coursier Windows launcher — single .bat file, no installation required.
# Source: https://get-coursier.io/docs/cli-installation
$SCIP_JAVA_COURSIER_URL  = "https://github.com/coursier/launchers/raw/refs/heads/master/coursier.bat"
$SCIP_JAVA_COURSIER_NAME = "coursier.bat"

# JVM exports required by scip-java for Java 17+ (uses internal javac APIs).
# Reference: https://sourcegraph.github.io/scip-java/docs/getting-started.html#java
$SCIP_JAVA_JVM_EXPORTS   = @(
    "--add-exports=jdk.compiler/com.sun.tools.javac.model=ALL-UNNAMED",
    "--add-exports=jdk.compiler/com.sun.tools.javac.api=ALL-UNNAMED",
    "--add-exports=jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED",
    "--add-exports=jdk.compiler/com.sun.tools.javac.util=ALL-UNNAMED",
    "--add-exports=jdk.compiler/com.sun.tools.javac.code=ALL-UNNAMED"
)

# -- Native output file produced by all indexers -------------

$NATIVE_INDEX_FILE = "index.scip"

# -- Section titles ------------------------------------------

$SECTION_VALIDATE = "Validating Target Directory"
$SECTION_PREREQS  = "Checking Prerequisites"
$SECTION_INSTALL  = "Installing Indexer"
$SECTION_INDEX    = "Generating SCIP Index"
$SECTION_VERIFY   = "Verifying Output"

# -- scip-java runtime state (populated by Install-ToolViaCoursier) ----------

$script:CoursierBatPath = $null
$script:ScipJavaVersion = $null

# ==================================================================
#  Central Routing Table
#  Each entry drives: dependency checks, installation, invocation,
#  and output file naming — zero duplication across indexers.
# ==================================================================

$SCIP_INDEXERS = [ordered]@{
    "dotnet" = @{
        # 'Tool'    = dotnet tool name (used for: dotnet tool install -g, Get-Command)
        # 'Command' = CLI executable name (same as Tool for dotnet)
        Tool            = "scip-dotnet"
        Command         = "scip-dotnet"
        OutputFile      = "abyss.dotnet.index.scip"
        InstallMethod   = "dotnet-tool-global"
        DependencyCheck = @($CMD_DOTNET)
        DependencyUrl   = "https://dotnet.microsoft.com/download"
        RunFunction     = "Invoke-ScipDotnet"
    }
    "python" = @{
        Tool            = "@sourcegraph/scip-python"
        Command         = "scip-python"
        OutputFile      = "abyss.python.index.scip"
        InstallMethod   = "npm-global"
        DependencyCheck = @($CMD_NODE, $CMD_NPM)
        DependencyUrl   = "https://nodejs.org"
        RunFunction     = "Invoke-ScipPython"
    }
    "java" = @{
        # Invoked via Coursier: coursier.bat launch <coord> -J<jvm-exports>... -- index
        # Command = $null: no standalone CLI; presence check is coursier.bat in $ScriptDir
        Tool            = "scip-java"
        Command         = $null
        OutputFile      = "abyss.java.index.scip"
        InstallMethod   = "coursier"
        DependencyCheck = @($CMD_JAVA)
        DependencyUrl   = "https://adoptium.net"
        RunFunction     = "Invoke-ScipJava"
    }
    "typescript" = @{
        # Tool = npm package name; Command = CLI name after npm install -g
        Tool            = "@sourcegraph/scip-typescript"
        Command         = "scip-typescript"
        OutputFile      = "abyss.typescript.index.scip"
        InstallMethod   = "npm-global"
        DependencyCheck = @($CMD_NODE, $CMD_NPM)
        DependencyUrl   = "https://nodejs.org"
        RunFunction     = "Invoke-ScipTypescript"
    }
}

# ==================================================================
#  Shared Helper Functions
# ==================================================================

function Write-Log {
    param([string]$Message, [string]$Level = $LOG_INFO)
    $entry = "[$((Get-Date).ToString('HH:mm:ss'))] [$Level] $Message"
    Add-Content -Path $LogFile -Value $entry -ErrorAction SilentlyContinue
    switch ($Level) {
        $LOG_ERROR   { Write-Host "  [X] $Message" -ForegroundColor Red }
        $LOG_WARN    { Write-Host "  [!] $Message" -ForegroundColor Yellow }
        $LOG_SUCCESS { Write-Host "  [+] $Message" -ForegroundColor Green }
        $LOG_STEP    { Write-Host "  [>] $Message" -ForegroundColor Cyan }
        default      { Write-Host "  [.] $Message" -ForegroundColor Gray }
    }
}

function Write-Header {
    $header = @"

    ___    ____  __  _______ _____
   /   |  / __ )\ \/ / ___// ___/
  / /| | / __  | \  /\__ \ \__ \
 / ___ |/ /_/ / / / ___/ /___/ /
/_/  |_/_____/ /_/ /____//____/

  S C I P   P R E P A R E  --  $($Type.ToUpper())

  Version $ScriptVersion
  $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

"@
    Write-Host $header -ForegroundColor DarkCyan
    Write-Host ("=" * 58) -ForegroundColor DarkGray
    Write-Host "  Generate abyss.$Type.index.scip for SCIP-enriched Abyss indexing" -ForegroundColor White
    Write-Host ("=" * 58) -ForegroundColor DarkGray
    Write-Host ""
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host ("  --- $Title " + ("-" * [Math]::Max(0, 48 - $Title.Length))) -ForegroundColor DarkCyan
    Write-Host ""
}

function Write-Footer {
    param([bool]$Success)
    Write-Host ""
    Write-Host ("=" * 58) -ForegroundColor DarkGray
    if ($Success) {
        Write-Host "  SCIP index generated successfully!" -ForegroundColor Green
        Write-Host ""
        Write-Host "  Next step: Index this folder in Abyss via Copilot Chat:" -ForegroundColor White
        Write-Host ""
        Write-Host "    > Index the directory $ResolvedPath" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  Abyss will automatically detect all *index.scip files" -ForegroundColor Gray
        Write-Host "  and use them for SCIP enrichment (symbols, call graphs, etc.)." -ForegroundColor Gray
    }
    else {
        Write-Host "  SCIP index generation FAILED." -ForegroundColor Red
        Write-Host "  Check the log file for details:" -ForegroundColor Gray
        Write-Host "    $LogFile" -ForegroundColor Yellow
    }
    Write-Host ("=" * 58) -ForegroundColor DarkGray
    Write-Host ""
}

function Invoke-ExternalCommand {
    <#
    .SYNOPSIS
        Run an external executable, capture stdout+stderr and exit code.
        Appends a formatted block to the log file.
    .OUTPUTS
        [hashtable] @{ Output=[string]; ExitCode=[int] }
    #>
    param(
        [string]   $Description,
        [string]   $Executable,
        [string[]] $Arguments
    )
    $savedEAP               = $ErrorActionPreference
    $ErrorActionPreference  = "Continue"
    $output                 = & $Executable @Arguments 2>&1 | Out-String
    $exitCode               = $LASTEXITCODE
    $ErrorActionPreference  = $savedEAP
    Add-Content -Path $LogFile -Value "`n--- $Description ---`n$output`n--- end (exit: $exitCode) ---"
    return @{ Output = $output.Trim(); ExitCode = $exitCode }
}

function Assert-Dependency {
    <#
    .SYNOPSIS
        Verify a required runtime command is available in PATH. Aborts on failure.
    #>
    param([string]$Command, [string]$InstallUrl)
    $cmd = Get-Command $Command -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Log "'$Command' not found in PATH." $LOG_ERROR
        Write-Log "Install it from: $InstallUrl" $LOG_WARN
        Write-Footer -Success $false
        exit 1
    }
    $result  = Invoke-ExternalCommand -Description "$Command --version" -Executable $Command -Arguments @("--version")
    $version = ($result.Output -split "`n" | Select-Object -First 1).Trim()
    Write-Log "$Command found: $version" $LOG_SUCCESS
}

function Rename-ScipOutput {
    <#
    .SYNOPSIS
        Rename the native index.scip to the canonical abyss.<type>.index.scip.
    .OUTPUTS
        Destination path [string] on success, $null if source not found.
    #>
    param([string]$WorkingDir, [string]$TargetName)
    $sourcePath = Join-Path $WorkingDir $NATIVE_INDEX_FILE
    $destPath   = Join-Path $WorkingDir $TargetName
    if (-not (Test-Path $sourcePath)) {
        return $null
    }
    if (Test-Path $destPath) {
        Remove-Item $destPath -Force
    }
    Move-Item -Path $sourcePath -Destination $destPath
    return $destPath
}

# ==================================================================
#  Installer Functions
# ==================================================================

function Install-ToolViaDotnetGlobal {
    param([string]$ToolName)
    Write-Log "Installing $ToolName via: $CMD_DOTNET tool install -g $ToolName" $LOG_STEP
    $result = Invoke-ExternalCommand -Description "dotnet tool install -g $ToolName" `
        -Executable $CMD_DOTNET -Arguments @("tool", "install", "-g", $ToolName)
    if ($result.ExitCode -ne 0) {
        Write-Log "Failed to install $ToolName (exit $($result.ExitCode))" $LOG_ERROR
        Write-Log "Try manually: $CMD_DOTNET tool install -g $ToolName" $LOG_WARN
        return $false
    }
    # Ensure ~/.dotnet/tools is in the current session PATH
    $toolsPath = Join-Path $env:USERPROFILE $DOTNET_TOOLS_SUBDIR
    if ($env:PATH -notlike "*$toolsPath*") {
        $env:PATH = "$toolsPath;$env:PATH"
    }
    Write-Log "$ToolName installed successfully" $LOG_SUCCESS
    return $true
}

function Install-ToolViaPip {
    param([string]$ToolName)
    Write-Log "Installing $ToolName via: $CMD_PIP install $ToolName" $LOG_STEP
    $result = Invoke-ExternalCommand -Description "pip install $ToolName" `
        -Executable $CMD_PIP -Arguments @("install", $ToolName)
    if ($result.ExitCode -ne 0) {
        Write-Log "Failed to install $ToolName (exit $($result.ExitCode))" $LOG_ERROR
        Write-Log "Try manually: $CMD_PIP install $ToolName" $LOG_WARN
        return $false
    }
    Write-Log "$ToolName installed successfully" $LOG_SUCCESS
    return $true
}

function Install-ToolViaNpmGlobal {
    param([string]$PackageName)
    Write-Log "Installing $PackageName via: $CMD_NPM install -g $PackageName" $LOG_STEP
    $result = Invoke-ExternalCommand -Description "npm install -g $PackageName" `
        -Executable $CMD_NPM -Arguments @("install", "-g", $PackageName)
    if ($result.ExitCode -ne 0) {
        Write-Log "Failed to install $PackageName (exit $($result.ExitCode))" $LOG_ERROR
        Write-Log "Try manually: $CMD_NPM install -g $PackageName" $LOG_WARN
        return $false
    }
    Write-Log "$PackageName installed successfully" $LOG_SUCCESS
    return $true
}

function Resolve-ScipJavaLatestVersion {
    <#
    .SYNOPSIS
        Query Maven Central metadata to find the latest stable release version of scip-java_2.13.
        Prefers the <release> tag (latest stable) over <latest> (may include RC/unstable builds).
        The resolved version is later passed to 'coursier launch <group:artifact:version>'.
    .OUTPUTS
        [string] Latest stable version, or $null on failure.
    #>
    Write-Log "Resolving latest stable $SCIP_JAVA_ARTIFACT version from Maven Central..." $LOG_STEP
    try {
        $savedEAP              = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $response              = Invoke-WebRequest -Uri $SCIP_JAVA_METADATA_URL -UseBasicParsing -ErrorAction Stop
        $ErrorActionPreference = $savedEAP
    }
    catch {
        $ErrorActionPreference = $savedEAP
        Write-Log "Failed to fetch Maven metadata: $_" $LOG_ERROR
        return $null
    }
    try {
        [xml]$meta  = $response.Content
        # Prefer <release> (latest stable) over <latest> (may include unstable/RC builds)
        $version    = $meta.metadata.versioning.release
        if (-not $version) { $version = $meta.metadata.versioning.latest }
        if (-not $version) { $version = $meta.metadata.versioning.versions.version | Select-Object -Last 1 }
    }
    catch {
        Write-Log "Failed to parse Maven metadata XML: $_" $LOG_ERROR
        return $null
    }
    if (-not $version) {
        Write-Log "No version found in Maven metadata" $LOG_ERROR
        return $null
    }
    Write-Log "Latest stable $SCIP_JAVA_ARTIFACT version: $version" $LOG_SUCCESS
    return $version
}

function Install-ToolViaCoursier {
    <#
    .SYNOPSIS
        Ensure the Coursier launcher (coursier.bat) is available and the latest
        stable scip-java version is resolved.  Coursier is a single .bat file that
        fetches and caches Maven dependencies at runtime -- no separate JAR management.
        Reference: https://sourcegraph.github.io/scip-java/docs/getting-started.html#java-launcher
    #>

    # Download coursier.bat if not already cached next to this script
    $coursierPath = Join-Path $ScriptDir $SCIP_JAVA_COURSIER_NAME
    if (-not (Test-Path $coursierPath)) {
        Write-Log "Downloading Coursier launcher ($SCIP_JAVA_COURSIER_NAME)..." $LOG_STEP
        Write-Log "URL: $SCIP_JAVA_COURSIER_URL" $LOG_INFO
        try {
            $savedEAP              = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            Invoke-WebRequest -Uri $SCIP_JAVA_COURSIER_URL -OutFile $coursierPath -UseBasicParsing -ErrorAction Stop
            $ErrorActionPreference = $savedEAP
        }
        catch {
            $ErrorActionPreference = $savedEAP
            Write-Log "Failed to download Coursier: $_" $LOG_ERROR
            Write-Log "Download it manually from: https://get-coursier.io/docs/cli-installation" $LOG_WARN
            return $false
        }
        if (-not (Test-Path $coursierPath)) {
            Write-Log "$SCIP_JAVA_COURSIER_NAME not found after download: $coursierPath" $LOG_ERROR
            return $false
        }
        Write-Log "Coursier launcher downloaded: $SCIP_JAVA_COURSIER_NAME" $LOG_SUCCESS
    }
    else {
        Write-Log "Coursier launcher found: $SCIP_JAVA_COURSIER_NAME" $LOG_SUCCESS
    }
    $script:CoursierBatPath = $coursierPath

    # Resolve the latest stable scip-java release version from Maven Central
    $version = Resolve-ScipJavaLatestVersion
    if (-not $version) {
        Write-Log "Cannot determine latest scip-java version -- check your internet connection" $LOG_ERROR
        Write-Log "Browse available versions at: $SCIP_JAVA_MAVEN_BASE/" $LOG_WARN
        return $false
    }
    $script:ScipJavaVersion = $version
    Write-Log "Will use: $SCIP_JAVA_GROUP`:${SCIP_JAVA_ARTIFACT}:${version}" $LOG_INFO
    return $true
}

function Install-IndexerTool {
    <#
    .SYNOPSIS
        Dispatcher: routes to the correct installer based on $Indexer.InstallMethod.
        Calls Write-Footer + exit 1 on failure.
    #>
    param([hashtable]$Indexer)
    $ok = switch ($Indexer.InstallMethod) {
        "dotnet-tool-global" { Install-ToolViaDotnetGlobal -ToolName $Indexer.Tool }
        "pip"                { Install-ToolViaPip          -ToolName $Indexer.Tool }
        "npm-global"         { Install-ToolViaNpmGlobal    -PackageName $Indexer.Tool }
        "coursier"           { Install-ToolViaCoursier }
        default {
            Write-Log "Unknown install method: '$($Indexer.InstallMethod)'" $LOG_ERROR
            $false
        }
    }
    if (-not $ok) {
        Write-Footer -Success $false
        exit 1
    }
}

# ==================================================================
#  Indexer Functions — one per type
#  Signature: param([string]$TargetDir, [hashtable]$Indexer)
#  Returns:   final output path [string] on success, $false on failure
# ==================================================================

function Invoke-ScipDotnet {
    param([string]$TargetDir, [hashtable]$Indexer)

    # Discover the nearest .sln (preferred) or .csproj file
    $slnFiles    = Get-ChildItem -Path $TargetDir -Filter $PATTERN_SLN    -Recurse -Depth $PROJECT_DEPTH -ErrorAction SilentlyContinue
    $csprojFiles = Get-ChildItem -Path $TargetDir -Filter $PATTERN_CSPROJ -Recurse -Depth $PROJECT_DEPTH -ErrorAction SilentlyContinue

    if ($slnFiles.Count -gt 0) {
        $targetFile = $slnFiles[0].FullName
        Write-Log "Found $($slnFiles.Count) solution file(s); using: $targetFile" $LOG_INFO
    }
    elseif ($csprojFiles.Count -gt 0) {
        $targetFile = $csprojFiles[0].FullName
        Write-Log "No .sln found; using project file: $targetFile" $LOG_INFO
    }
    else {
        Write-Log "No .sln or .csproj files found in $TargetDir" $LOG_ERROR
        return $false
    }

    $projectDir  = Split-Path $targetFile -Parent
    $projectFile = Split-Path $targetFile -Leaf

    # Step: restore dependencies
    Write-Log "Running: $CMD_DOTNET restore `"$targetFile`"" $LOG_STEP
    $result = Invoke-ExternalCommand -Description "dotnet restore" `
        -Executable $CMD_DOTNET -Arguments @("restore", $targetFile)
    if ($result.ExitCode -ne 0) {
        Write-Log "dotnet restore failed (exit $($result.ExitCode))" $LOG_ERROR
        return $false
    }
    Write-Log "Dependencies restored" $LOG_SUCCESS

    # Step: run scip-dotnet (must run from project dir; outputs index.scip there)
    Write-Log "Running: $($Indexer.Command) index `"$projectFile`" (cwd: $projectDir)" $LOG_STEP
    Push-Location $projectDir
    try {
        $result = Invoke-ExternalCommand -Description "scip-dotnet index" `
            -Executable $Indexer.Command -Arguments @("index", $projectFile)
    }
    finally { Pop-Location }

    if ($result.ExitCode -ne 0) {
        Write-Log "$($Indexer.Command) failed (exit $($result.ExitCode))" $LOG_ERROR
        return $false
    }

    # Rename index.scip -> abyss.dotnet.index.scip
    $finalPath = Rename-ScipOutput -WorkingDir $projectDir -TargetName $Indexer.OutputFile
    if (-not $finalPath) {
        Write-Log "$NATIVE_INDEX_FILE not found in $projectDir after indexing" $LOG_ERROR
        return $false
    }
    Write-Log "Renamed $NATIVE_INDEX_FILE -> $($Indexer.OutputFile)" $LOG_SUCCESS
    return $finalPath
}

function Invoke-ScipPython {
    param([string]$TargetDir, [hashtable]$Indexer)

    # Run from project root; scip-python outputs index.scip by default
    Write-Log "Running: $($Indexer.Command) index . (cwd: $TargetDir)" $LOG_STEP
    Push-Location $TargetDir
    try {
        $result = Invoke-ExternalCommand -Description "scip-python index" `
            -Executable $Indexer.Command -Arguments @("index", ".")
    }
    finally { Pop-Location }

    if ($result.ExitCode -ne 0) {
        Write-Log "$($Indexer.Command) failed (exit $($result.ExitCode))" $LOG_ERROR
        return $false
    }

    $finalPath = Rename-ScipOutput -WorkingDir $TargetDir -TargetName $Indexer.OutputFile
    if (-not $finalPath) {
        Write-Log "$NATIVE_INDEX_FILE not found in $TargetDir after indexing" $LOG_ERROR
        return $false
    }
    Write-Log "Renamed $NATIVE_INDEX_FILE -> $($Indexer.OutputFile)" $LOG_SUCCESS
    return $finalPath
}

function Invoke-ScipJava {
    param([string]$TargetDir, [hashtable]$Indexer)

    # scip-java index requires a Maven (pom.xml) or Gradle build file at the project root.
    # The build file must exist in $TargetDir itself -- scip-java does not search subdirectories.
    $buildFile = Get-ChildItem -Path $TargetDir -Depth 0 -ErrorAction SilentlyContinue `
                     -Include "pom.xml","build.gradle","build.gradle.kts","settings.gradle","settings.gradle.kts" |
                 Select-Object -First 1
    if (-not $buildFile) {
        Write-Log "No build file found in $TargetDir" $LOG_ERROR
        Write-Log "scip-java index requires pom.xml (Maven) or build.gradle / settings.gradle (Gradle) at the project root" $LOG_WARN
        return $false
    }
    Write-Log "Build file found: $($buildFile.Name)" $LOG_INFO

    # Coursier launch syntax:
    #   coursier.bat launch <group:artifact:version> -J<jvm-flag>... -- <app-args>...
    # The -J prefix passes each flag to the JVM; everything after -- goes to scip-java.
    # Java 17+ requires --add-exports for the internal javac APIs used by scip-java.
    $coord      = "${SCIP_JAVA_GROUP}:${SCIP_JAVA_ARTIFACT}:${script:ScipJavaVersion}"
    $jvmFlags   = $SCIP_JAVA_JVM_EXPORTS | ForEach-Object { "-J$_" }
    $launchArgs = @("launch", $coord) + $jvmFlags + @("--", "index")

    Write-Log "Running: coursier launch $coord -- index (cwd: $TargetDir)" $LOG_STEP
    Push-Location $TargetDir
    try {
        $result = Invoke-ExternalCommand -Description "scip-java index" `
            -Executable $script:CoursierBatPath -Arguments $launchArgs
    }
    finally { Pop-Location }

    if ($result.ExitCode -ne 0) {
        Write-Log "scip-java failed (exit $($result.ExitCode))" $LOG_ERROR
        return $false
    }

    $finalPath = Rename-ScipOutput -WorkingDir $TargetDir -TargetName $Indexer.OutputFile
    if (-not $finalPath) {
        Write-Log "$NATIVE_INDEX_FILE not found in $TargetDir after indexing" $LOG_ERROR
        return $false
    }
    Write-Log "Renamed $NATIVE_INDEX_FILE -> $($Indexer.OutputFile)" $LOG_SUCCESS
    return $finalPath
}

function Invoke-ScipTypescript {
    param([string]$TargetDir, [hashtable]$Indexer)

    # Verify that at least one TS/JS file exists before proceeding
    $tsFiles = Get-ChildItem -Path $TargetDir -Recurse -ErrorAction SilentlyContinue `
        -Include "*.ts","*.tsx","*.js","*.jsx","*.mts","*.mjs","*.cts","*.cjs" |
        Where-Object { $_.FullName -notmatch "[\\/]node_modules[\\/]" }
    if (-not $tsFiles) {
        Write-Log "No TypeScript or JavaScript files found in $TargetDir" $LOG_ERROR
        Write-Log "scip-typescript requires at least one .ts, .tsx, .js, or .jsx file" $LOG_WARN
        return $false
    }
    Write-Log "Found $($tsFiles.Count) TypeScript/JavaScript file(s)" $LOG_INFO

    # Ensure tsconfig.json exists; create minimal one if absent
    $tsconfigPath = Join-Path $TargetDir "tsconfig.json"
    if (-not (Test-Path $tsconfigPath)) {
        Write-Log "tsconfig.json not found -- creating minimal config" $LOG_WARN
        $tsconfigContent = @"
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowJs": true,
    "resolveJsonModule": true,
    "moduleResolution": "node",
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  },
  "include": ["./**/*"],
  "exclude": ["node_modules", "dist", "build", ".git"]
}
"@
        try {
            Set-Content -Path $tsconfigPath -Value $tsconfigContent -Encoding UTF8 -ErrorAction Stop
            Write-Log "Created minimal tsconfig.json" $LOG_SUCCESS
        }
        catch {
            Write-Log "Failed to create tsconfig.json: $_" $LOG_ERROR
            return $false
        }
    }
    else {
        Write-Log "tsconfig.json found" $LOG_SUCCESS
    }

    # Install npm dependencies when package.json is present
    $packageJson = Join-Path $TargetDir "package.json"
    if (Test-Path $packageJson) {
        $lockFile = Join-Path $TargetDir "package-lock.json"
        $npmCmd   = if (Test-Path $lockFile) { "ci" } else { "install" }
        Write-Log "Running: $CMD_NPM $npmCmd (cwd: $TargetDir)" $LOG_STEP
        Push-Location $TargetDir
        try {
            $result = Invoke-ExternalCommand -Description "npm $npmCmd" `
                -Executable $CMD_NPM -Arguments @($npmCmd)
        }
        finally { Pop-Location }
        if ($result.ExitCode -ne 0) {
            Write-Log "npm $npmCmd failed (exit $($result.ExitCode)) -- continuing" $LOG_WARN
        }
        else {
            Write-Log "npm dependencies installed" $LOG_SUCCESS
        }
    }

    Write-Log "Running: $($Indexer.Command) index (cwd: $TargetDir)" $LOG_STEP
    Push-Location $TargetDir
    try {
        $result = Invoke-ExternalCommand -Description "scip-typescript index" `
            -Executable $Indexer.Command -Arguments @("index")
    }
    finally { Pop-Location }

    if ($result.ExitCode -ne 0) {
        Write-Log "$($Indexer.Command) failed (exit $($result.ExitCode))" $LOG_ERROR
        return $false
    }

    $finalPath = Rename-ScipOutput -WorkingDir $TargetDir -TargetName $Indexer.OutputFile
    if (-not $finalPath) {
        Write-Log "$NATIVE_INDEX_FILE not found in $TargetDir after indexing" $LOG_ERROR
        return $false
    }
    Write-Log "Renamed $NATIVE_INDEX_FILE -> $($Indexer.OutputFile)" $LOG_SUCCESS
    return $finalPath
}

# ==================================================================
#  Main Script
# ==================================================================

Write-Header

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

Add-Content -Path $LogFile -Value "Abyss SCIP Prepare [$Type] -- Log started $Timestamp"
Add-Content -Path $LogFile -Value ("=" * 60)

$indexer = $SCIP_INDEXERS[$Type]

# -- Step 1: Validate target directory -------------------------

Write-Section $SECTION_VALIDATE

$ResolvedPath = (Resolve-Path -Path $ProjectPath -ErrorAction SilentlyContinue).Path
if (-not $ResolvedPath -or -not (Test-Path $ResolvedPath -PathType Container)) {
    Write-Log "Directory not found: $ProjectPath" $LOG_ERROR
    Write-Footer -Success $false
    exit 1
}

Write-Log "Target directory : $ResolvedPath" $LOG_INFO
Write-Log "Indexer type     : $Type  ($($indexer.Tool))" $LOG_INFO
Write-Log "Output file      : $($indexer.OutputFile)" $LOG_INFO

# -- Step 2: Check prerequisites --------------------------------

Write-Section $SECTION_PREREQS

foreach ($dep in $indexer.DependencyCheck) {
    Assert-Dependency -Command $dep -InstallUrl $indexer.DependencyUrl
}

# -- Step 3: Install indexer if absent -------------------------

Write-Section $SECTION_INSTALL

if ($Type -eq "java") {
    # Java indexer has no standalone CLI — Install-ToolViaCoursier downloads
    # the Coursier launcher and resolves the scip-java version from Maven Central.
    Install-IndexerTool -Indexer $indexer
}
else {
    $toolCmd = Get-Command $indexer.Command -ErrorAction SilentlyContinue
    if (-not $toolCmd) {
        Write-Log "$($indexer.Command) not found -- installing..." $LOG_WARN
        Install-IndexerTool -Indexer $indexer

        # Re-check (PATH may have been updated, e.g. dotnet tools)
        $toolCmd = Get-Command $indexer.Command -ErrorAction SilentlyContinue
        if (-not $toolCmd) {
            Write-Log "$($indexer.Command) still not found after install" $LOG_ERROR
            Write-Footer -Success $false
            exit 1
        }
        Write-Log "$($indexer.Command) available: $($toolCmd.Source)" $LOG_SUCCESS
    }
    else {
        Write-Log "$($indexer.Command) found: $($toolCmd.Source)" $LOG_SUCCESS
    }
}

# -- Step 4: Run indexer ----------------------------------------

Write-Section $SECTION_INDEX

$outputPath = & $indexer.RunFunction -TargetDir $ResolvedPath -Indexer $indexer

if (-not $outputPath) {
    Write-Footer -Success $false
    exit 1
}

# -- Step 5: Verify output --------------------------------------

Write-Section $SECTION_VERIFY

if (Test-Path $outputPath) {
    $fileInfo = Get-Item $outputPath
    $sizeKB   = [Math]::Round($fileInfo.Length / 1KB, 1)
    $sizeMB   = [Math]::Round($fileInfo.Length / 1MB, 2)

    $modifiedAt = $fileInfo.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
    $sizeStr    = if ($sizeMB -ge 1) { "$sizeMB MB" } else { "$sizeKB KB" }

    Write-Log "$($indexer.OutputFile) created successfully" $LOG_SUCCESS
    Write-Log "Location : $outputPath" $LOG_INFO
    Write-Log "Size     : $sizeStr" $LOG_INFO
    Write-Log "Modified : $modifiedAt" $LOG_INFO

    Add-Content -Path $LogFile -Value "`n$($indexer.OutputFile) generated: $outputPath ($sizeKB KB)"
}
else {
    Write-Log "Output file not found: $outputPath" $LOG_ERROR
    Write-Footer -Success $false
    exit 1
}

# -- Done -------------------------------------------------------

$completionTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $LogFile -Value "`nCompleted successfully at $completionTime"

Write-Footer -Success $true

Write-Host "  Log file: $LogFile" -ForegroundColor DarkGray
Write-Host ""
