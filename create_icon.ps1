$img = [System.Drawing.Image]::FromFile("icon.png")
$icon = [System.Drawing.Icon]::FromHandle($img.GetHicon())
$icon.Save("icon.ico")
$img.Dispose()
Write-Host "Created icon.ico"