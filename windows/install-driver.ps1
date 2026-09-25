# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 BrLumen
#
# install-driver.ps1 -- bind Windows' in-box usbser.sys to the ChipDip
# RDC2-0064 so that it shows up as a COM port.  See rdc2-0064-usbser.inf for
# why the stock CDC binding fails on Windows.
#
# Windows 10/11 refuse to install a driver package without a signed catalog,
# even one that installs no binaries of its own.  This script does what Zadig
# does: it creates a self-signed code-signing certificate, builds and signs a
# catalog for the INF, trusts the certificate on this machine (Trusted Root
# Certification Authorities + Trusted Publishers), installs the package with
# pnputil and finally deletes the private key, so the certificate can never
# sign anything else.
#
# Usage (asks for elevation itself):
#   powershell -ExecutionPolicy Bypass -File windows\install-driver.ps1
#
# To undo: "pnputil /enum-drivers", find the entry whose Original Name is
# rdc2-0064-usbser.inf, then "pnputil /delete-driver oemNN.inf /uninstall".
# The certificate is "rdc2-sigrok RDC2-0064 driver package" in the two stores
# named above (certlm.msc).

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$InfName = 'rdc2-0064-usbser.inf'
$CatName = 'rdc2-0064-usbser.cat'
$Subject = 'CN=rdc2-sigrok RDC2-0064 driver package'
$HardwareId = 'USB\VID_0483&PID_A210'

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host 'Elevating...'
    $p = Start-Process -FilePath powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $PSCommandPath))
    exit $p.ExitCode
}

$src = Join-Path $PSScriptRoot $InfName
if (-not (Test-Path $src)) { throw "missing $src" }

# A scratch directory holding only the INF: New-FileCatalog hashes every
# file it finds there.
$work = Join-Path $env:TEMP 'rdc2-sigrok-driver'
if (Test-Path $work) { Remove-Item -Recurse -Force $work }
New-Item -ItemType Directory -Path $work | Out-Null
Copy-Item $src $work
$inf = Join-Path $work $InfName
$cat = Join-Path $work $CatName

Write-Host '==> Self-signed code-signing certificate'
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject `
    -CertStoreLocation 'Cert:\LocalMachine\My' -KeyExportPolicy NonExportable `
    -KeyLength 2048 -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(10)
try {
    # Trust first: Set-AuthenticodeSignature reports the chain status of the
    # signature it just made, and a self-signed certificate only verifies once
    # it is in Root.
    Write-Host '==> Trusting the certificate on this machine'
    $cer = Join-Path $work 'rdc2-sigrok-driver.cer'
    Export-Certificate -Cert $cert -FilePath $cer | Out-Null
    foreach ($store in 'Root', 'TrustedPublisher') {
        Import-Certificate -FilePath $cer -CertStoreLocation "Cert:\LocalMachine\$store" | Out-Null
    }

    Write-Host '==> Catalog'
    New-FileCatalog -Path $work -CatalogFilePath $cat -CatalogVersion 2 | Out-Null
    $sig = Set-AuthenticodeSignature -FilePath $cat -Certificate $cert -HashAlgorithm SHA256
    if ($sig.Status -ne 'Valid') { throw "signing the catalog failed: $($sig.StatusMessage)" }
} finally {
    # Only the public certificate stays (in Root/TrustedPublisher); the key
    # is gone, so nothing else can ever be signed with it.
    Remove-Item -Path $cert.PSPath -DeleteKey -Force
}

Write-Host '==> pnputil /add-driver /install'
& pnputil.exe /add-driver $inf /install
$rc = $LASTEXITCODE
# 259 = ERROR_NO_MORE_ITEMS: package added, but no present device needed it
# (board not plugged in); that is fine, it binds on the next plug-in.
if ($rc -ne 0 -and $rc -ne 259) { throw "pnputil failed with exit code $rc" }

Write-Host '==> Device state'
$devs = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -like "$HardwareId*" }
if (-not $devs) {
    Write-Host '    board not connected; the driver binds when it is plugged in'
} else {
    foreach ($d in $devs) {
        $code = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName DEVPKEY_Device_ProblemCode).Data
        Write-Host ('    {0,-8} code={1} service={2,-8} {3}' -f $d.Status, $code, $d.Service, $d.FriendlyName)
    }
}
