#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $SdkDirectory
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$versions = Get-Content -Raw -LiteralPath (Join-Path $repo 'configs/phase1-versions.json') | ConvertFrom-Json
$SdkDirectory = [IO.Path]::GetFullPath($SdkDirectory)
$repoPrefix = [IO.Path]::TrimEndingDirectorySeparator($repo) + [IO.Path]::DirectorySeparatorChar
if ($SdkDirectory.Equals($repo, [StringComparison]::OrdinalIgnoreCase) -or
    $SdkDirectory.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Use an SDK directory outside the repository.'
}
New-Item -ItemType Directory -Path $SdkDirectory -Force | Out-Null

function Expand-VerifiedArchive($Name, $Url, $Checksum, $Destination) {
    $archive = Join-Path $SdkDirectory $Name
    if (!(Test-Path -LiteralPath $archive -PathType Leaf)) {
        Invoke-WebRequest -Uri $Url -OutFile $archive
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $Checksum) {
        throw "Invalid checksum for $archive"
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $Destination -Force
}

$release = Join-Path $SdkDirectory 'release'
$source = Join-Path $SdkDirectory 'source'
$fmt = $versions.fmt.tag
$api = $versions.asaapi
Expand-VerifiedArchive 'AsaApi.zip' "https://github.com/ArkServerApi/AsaApi/releases/download/$($api.tag)/$($api.archive)" $api.sha256 $release
Expand-VerifiedArchive 'source.zip' "https://codeload.github.com/ArkServerApi/AsaApi/zip/$($api.commit)" $api.source_sha256 $source
Expand-VerifiedArchive "fmt-$fmt.zip" "https://codeload.github.com/fmtlib/fmt/zip/refs/tags/$fmt" $versions.fmt.sha256 $SdkDirectory

$build = Join-Path $repo 'build/phase1'
& cmake -S (Join-Path $repo 'plugin') -B $build -G 'Visual Studio 17 2022' -A x64 -T v143 `
    "-DASAAPI_SOURCE=$source/AsaApi-$($api.commit)" "-DASAAPI_LIB=$release/Lib/AsaApi.lib" `
    "-DFMT_INCLUDE=$SdkDirectory/fmt-$fmt/include"
if ($LASTEXITCODE -ne 0) { throw "CMake configuration failed ($LASTEXITCODE)" }
& cmake --build $build --config Release
if ($LASTEXITCODE -ne 0) { throw "DLL build failed ($LASTEXITCODE)" }
