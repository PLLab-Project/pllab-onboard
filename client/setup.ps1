# Set up `ssh pllab` on Windows for a PLLab-Project organization member.
# Safe to run again: each step checks what is already done.
$ErrorActionPreference = 'Stop'

$Org = 'PLLab-Project'
$HostName = if ($env:PLLAB_HOST) { $env:PLLAB_HOST } else { 'ssh.pl-official.site' }
$Alias = if ($env:PLLAB_ALIAS) { $env:PLLAB_ALIAS } else { 'pllab' }
$HostKey = 'ssh.pl-official.site ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEYfMUnsI9YTzVvGLFVO85uC/ZdIggHcijwbS7duiD+X'
$SshDir = Join-Path $HOME '.ssh'
$Key = if ($env:PLLAB_KEY) { $env:PLLAB_KEY } else { Join-Path $SshDir 'pllab_ed25519' }
$Begin = '# >>> pllab-onboard >>>'
$End = '# <<< pllab-onboard <<<'

function Step($text) { Write-Host "`n==> $text" }
function Fail($text) { Write-Host "`nERROR: $text" -ForegroundColor Red; exit 1 }
function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }

function Write-Utf8($path, $lines) {
    [IO.File]::WriteAllLines($path, [string[]]$lines, (New-Object Text.UTF8Encoding $false))
}

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

function Install-Tools {
    Step 'Check ssh, cloudflared and gh'
    if (-not (Have ssh) -or -not (Have ssh-keygen)) {
        Fail 'OpenSSH client is missing. Settings > System > Optional features > Add "OpenSSH Client".'
    }
    $packages = @{ cloudflared = 'Cloudflare.cloudflared'; gh = 'GitHub.cli' }
    foreach ($tool in $packages.Keys) {
        if (Have $tool) { continue }
        if (-not (Have winget)) { Fail "winget is missing. Install $tool manually, then run this again." }
        winget install --id $packages[$tool] --exact --silent --accept-package-agreements --accept-source-agreements
        Refresh-Path
        if (-not (Have $tool)) { Fail "$tool was installed but is not on PATH. Open a new terminal and run this again." }
    }
}

function Connect-GitHub {
    Step 'Sign in to GitHub'
    gh auth status --hostname github.com *> $null
    if ($LASTEXITCODE -ne 0) {
        gh auth login --hostname github.com --git-protocol https --web --scopes admin:public_key
        if ($LASTEXITCODE -ne 0) { Fail 'GitHub sign-in failed.' }
    }
    $script:Login = (gh api user --jq .login).Trim()
    Write-Host "GitHub user: $Login"
}

function Get-OrgState {
    $state = gh api "user/memberships/orgs/$Org" --jq .state 2>$null
    if ($LASTEXITCODE -ne 0) { return 'none' }
    return $state.Trim()
}

function Join-Org {
    Step "Check $Org membership"
    $state = Get-OrgState
    if ($state -eq 'pending') {
        gh api --method PATCH "user/memberships/orgs/$Org" -f state=active *> $null
        $state = Get-OrgState
    }
    if ($state -eq 'pending') {
        Write-Host "Accept the invitation in a browser: https://github.com/orgs/$Org/invitation"
        for ($i = 0; $state -ne 'active'; $i++) {
            if ($i -ge 60) { Fail 'The invitation is still not accepted.' }
            Start-Sleep -Seconds 10
            $state = Get-OrgState
        }
    }
    if ($state -ne 'active') { Fail "$Login is not in $Org. Ask an organization owner to invite $Login." }
    Write-Host "Member of $Org"
}

function Register-Key {
    Step "Register this computer's SSH key on GitHub"
    New-Item -ItemType Directory -Force $SshDir | Out-Null
    if (-not (Test-Path $Key)) {
        cmd /c "ssh-keygen -q -t ed25519 -N `"`" -C `"pllab $Login@$env:COMPUTERNAME`" -f `"$Key`""
        if ($LASTEXITCODE -ne 0) { Fail 'ssh-keygen failed.' }
    }
    $pub = (Get-Content "$Key.pub" -Raw).Split(' ')[1]
    $remote = (Invoke-RestMethod "https://github.com/$Login.keys") -split "`n" | ForEach-Object { ($_ -split ' ')[1] }
    if ($remote -contains $pub) { Write-Host 'Key already on GitHub'; return }
    if (-not ((gh auth status --hostname github.com 2>&1 | Out-String) -match 'admin:public_key')) {
        gh auth refresh --hostname github.com --scopes admin:public_key
    }
    gh ssh-key add "$Key.pub" --title "pllab $env:COMPUTERNAME"
    if ($LASTEXITCODE -ne 0) { Fail 'Could not add the key to GitHub.' }
}

function Get-LinuxUser {
    if ($env:PLLAB_USER) { return $env:PLLAB_USER }
    $name = $Login.ToLowerInvariant()
    if ($name -notmatch '^[a-z]') { $name = "gh-$name" }
    return $name
}

function Write-SshConfig {
    Step "Write the '$Alias' entry to $SshDir\config"
    $config = Join-Path $SshDir 'config'
    $lines = if (Test-Path $config) { @(Get-Content $config) } else { @() }
    $outside = New-Object System.Collections.Generic.List[string]
    $skip = $false
    foreach ($line in $lines) {
        if ($line -eq $Begin) { $skip = $true; continue }
        if ($line -eq $End) { $skip = $false; continue }
        if (-not $skip) { $outside.Add($line) }
    }
    while ($outside.Count -gt 0 -and $outside[0].Trim() -eq '') { $outside.RemoveAt(0) }
    foreach ($line in $outside) {
        if ($line -match "^\s*host\s" -and ($line -split '\s+') -contains $Alias) {
            Fail "$config already has a 'Host $Alias' entry. Remove it, or run again with PLLAB_ALIAS set to another name."
        }
    }
    $known = Join-Path $SshDir 'known_hosts_pllab'
    Write-Utf8 $known @($HostKey)
    $cloudflared = (Get-Command cloudflared).Source
    $block = @(
        $Begin
        "Host $Alias"
        "    HostName $HostName"
        "    User $(Get-LinuxUser)"
        "    IdentityFile `"$Key`""
        '    IdentitiesOnly yes'
        "    UserKnownHostsFile `"$known`""
        '    StrictHostKeyChecking yes'
        "    ProxyCommand `"$cloudflared`" access ssh --hostname %h"
        $End
        ''
    )
    Write-Utf8 $config ($block + $outside)
}

function Wait-ForLogin {
    Step "Connect with 'ssh $Alias'"
    for ($i = 1; $true; $i++) {
        ssh -o BatchMode=yes -o ConnectTimeout=20 $Alias true 2>$null
        if ($LASTEXITCODE -eq 0) { break }
        if ($i -gt 18) { Fail "Login still fails after 3 minutes. Run 'ssh -v $Alias' and send the output to a server admin." }
        Write-Host "Waiting for the server to create your account ($i/18)"
        Start-Sleep -Seconds 10
    }
    Write-Host "`nDone. Connect with: ssh $Alias"
}

Install-Tools
Connect-GitHub
Join-Org
Register-Key
Write-SshConfig
Wait-ForLogin
