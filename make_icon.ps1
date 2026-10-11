Add-Type -AssemblyName System.Drawing
$src = "icon.png"
$dst = "icon.ico"
$sizes = @(256, 128, 64, 48, 32, 16)
$srcImg = [System.Drawing.Image]::FromFile($src)
$images = @()
foreach ($s in $sizes) {
    $bmp = New-Object System.Drawing.Bitmap($srcImg, $s, $s)
    $images += $bmp
}
$icon = [System.Drawing.Icon]::FromHandle($images[0].GetHicon())
$stream = [System.IO.File]::Create($dst)
$icon.Save($stream)
$stream.Close()
foreach ($b in $images) { $b.Dispose() }
$srcImg.Dispose()
Write-Host "Created $dst with $($sizes.Count) sizes"