# Cài đặt Agent Biên bản họp — chạy 1 lần. Mọi công cụ đều miễn phí, chạy trên máy.
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$skill = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "=== CÀI ĐẶT AGENT BIÊN BẢN HỌP ===" -ForegroundColor Cyan

# 1. Python
$py = $null
foreach ($c in @("python", "py")) { if (Get-Command $c -ErrorAction SilentlyContinue) { $py = $c; break } }
if ($py) { & $py -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)"; if ($LASTEXITCODE -ne 0) { $py = $null } }
if (-not $py) {
  Write-Host "[1/5] Chưa có Python 3.10+ -> đang cài Python 3.12 bằng winget..." -ForegroundColor Yellow
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  Write-Host "Đã cài Python. HÃY ĐÓNG cửa sổ này và chạy lại CAI-DAT.bat." -ForegroundColor Green
  Read-Host "Nhấn Enter để đóng"; exit
}
Write-Host "[1/5] Python: OK" -ForegroundColor Green

# 2. FFmpeg (đọc audio/video)
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ff) { $ff = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1 }
if (-not $ff) {
  Write-Host "[2/5] Đang cài FFmpeg bằng winget..." -ForegroundColor Yellow
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
} else { Write-Host "[2/5] FFmpeg: OK" -ForegroundColor Green }

# 3. Thư viện Python
Write-Host "[3/5] Đang cài thư viện Python (vài phút)..." -ForegroundColor Yellow
& $py -m pip install --user --upgrade -r (Join-Path $skill "requirements.txt")

# 4. Model nhận diện giọng nói (~45 MB)
$models = Join-Path $skill "models"
New-Item -ItemType Directory -Force $models | Out-Null
$seg = Join-Path $models "sherpa-onnx-pyannote-segmentation-3-0\model.int8.onnx"
$emb = Join-Path $models "speaker-embedding.onnx"
if (-not (Test-Path $seg)) {
  Write-Host "[4/5] Đang tải model tách người nói..." -ForegroundColor Yellow
  $tar = Join-Path $models "seg.tar.bz2"
  Invoke-WebRequest "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2" -OutFile $tar
  tar -xjf $tar -C $models; Remove-Item $tar
}
if (-not (Test-Path $emb)) {
  Write-Host "[4/5] Đang tải model nhận dạng giọng..." -ForegroundColor Yellow
  Invoke-WebRequest "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx" -OutFile $emb
}
Write-Host "[4/5] Model giọng nói: OK" -ForegroundColor Green

# 5. Model chuyển giọng nói thành chữ (Whisper large-v3-turbo, ~1.6 GB, tải 1 lần)
Write-Host "[5/5] Đang tải model Whisper (lần đầu có thể mất 5-15 phút)..." -ForegroundColor Yellow
& $py -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cpu', compute_type='int8'); print('Whisper: OK')"

Write-Host ""
& $py (Join-Path $skill "scripts\mm.py") doctor
Write-Host ""
Write-Host "Xong! Mở Claude và nói: 'Làm biên bản cuộc họp từ file ...'" -ForegroundColor Cyan
Read-Host "Nhấn Enter để đóng"
