# 사용법:
# 1) 이 파일을 이미지 폴더에 복사
#    C:\Users\bang4\OneDrive\바탕 화면\jacket\이미지파일\rename_jacket_images.ps1
# 2) 그 폴더에서 PowerShell 실행:
#    Set-ExecutionPolicy -Scope Process Bypass
#    .\rename_jacket_images.ps1
#
# AI-Hub 원본 이름 → field_jacket_aihub_<id>_<view>.jpg

$ErrorActionPreference = "Stop"
$dir = $PSScriptRoot
if (-not $dir) { $dir = Get-Location }

$map = @{
  "01_sou_063354_316767_back_01outer_02jacket_woman.jpg"  = "field_jacket_aihub_316767_back.jpg"
  "01_sou_063362_316807_back_01outer_02jacket_woman.jpg"  = "field_jacket_aihub_316807_back.jpg"
  "01_sou_063375_316874_wear_01outer_02jacket_woman.jpg"  = "field_jacket_aihub_316874_wear.jpg"
  "01_sou_063377_316881_front_01outer_02jacket_woman.jpg" = "field_jacket_aihub_316881_front.jpg"
  "01_sou_063382_316909_wear_01outer_02jacket_woman.jpg"  = "field_jacket_aihub_316909_wear.jpg"
  "01_sou_063393_316964_wear_01outer_02jacket_woman.jpg"  = "field_jacket_aihub_316964_wear.jpg"
  "01_sou_063394_316969_wear_01outer_02jacket_woman.jpg"  = "field_jacket_aihub_316969_wear.jpg"
}

Write-Host "폴더: $dir"
$done = 0
foreach ($srcName in $map.Keys) {
  $dstName = $map[$srcName]
  $stem = [System.IO.Path]::GetFileNameWithoutExtension($srcName)
  $candidates = @(
    (Join-Path $dir $srcName),
    (Join-Path $dir ($stem + ".JPG")),
    (Join-Path $dir ($stem + ".jpeg")),
    (Join-Path $dir ($stem + ".JPEG")),
    (Join-Path $dir ($stem + ".png")),
    (Join-Path $dir ($stem + ".PNG"))
  )
  $found = $null
  foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c) { $found = $c; break }
  }
  if (-not $found) {
    Write-Host "[없음] $srcName" -ForegroundColor Yellow
    continue
  }
  $dst = Join-Path $dir $dstName
  if ((Split-Path $found -Leaf) -eq $dstName) {
    Write-Host "[이미OK] $dstName"
    $done++
    continue
  }
  if (Test-Path -LiteralPath $dst) {
    Write-Host "[건너뜀] 대상 이미 존재: $dstName" -ForegroundColor Yellow
    continue
  }
  Rename-Item -LiteralPath $found -NewName $dstName
  Write-Host "[변경] $(Split-Path $found -Leaf) -> $dstName" -ForegroundColor Green
  $done++
}

Write-Host ""
Write-Host "완료: $done 개"
Write-Host "이름을 바꾼 뒤 Cursor 채팅에 이미지 업로드하거나"
Write-Host "레포 benchmarks/fixtures/ 폴더에 복사하세요."
