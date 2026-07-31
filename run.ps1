param(
    [string]$ViewerCode,
    [string]$AdminCode,
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

function Read-SecretCode {
    param([string]$Prompt)

    $secureValue = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

if ([string]::IsNullOrWhiteSpace($ViewerCode)) {
    $ViewerCode = Read-SecretCode "일반 사용자 접속 코드를 입력하세요"
}

if ([string]::IsNullOrWhiteSpace($AdminCode)) {
    $AdminCode = Read-SecretCode "관리자 접속 코드를 입력하세요"
}

if ([string]::IsNullOrWhiteSpace($ViewerCode) -or [string]::IsNullOrWhiteSpace($AdminCode)) {
    throw "일반 사용자 코드와 관리자 코드를 모두 입력해야 합니다."
}

if ($ViewerCode -eq $AdminCode) {
    throw "일반 사용자 코드와 관리자 코드는 서로 다르게 설정해야 합니다."
}

$env:VIEWER_CODE = $ViewerCode
$env:ADMIN_CODE = $AdminCode

python -c "import streamlit, pandas" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "필수 패키지가 없습니다. 먼저 'python -m pip install -r requirements.txt'를 실행하십시오."
}

python -m streamlit run app.py --server.port $Port
