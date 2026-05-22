@echo off
REM Akilli Sinif - Internet uzerinden erisim (Cloudflare Tunnel)
REM Bu batch hem Flask sunucusunu hem de Cloudflare tunnel'i baslatir.

echo ===========================================================
echo   Akilli Sinif Otomasyonu - Internet Modu
echo ===========================================================
echo.
echo   Bu script iki pencere acar:
echo     1) Flask sunucusu (yerel - localhost:5000)
echo     2) Cloudflare Tunnel (public HTTPS URL)
echo.
echo   Public URL ikinci pencerede gosterilir
echo   (.trycloudflare.com ile biten adres)
echo.
echo ===========================================================
echo.

REM Flask sunucusunu yeni pencerede baslat
start "Akilli Sinif - Sunucu" cmd /k "cd /d %~dp0 && python app.py"

REM Sunucu acilana kadar bekle
timeout /t 4 /nobreak >nul

REM Cloudflare tunnel'i yeni pencerede baslat
start "Akilli Sinif - Tunnel" cmd /k ""C:\Users\Melih\cloudflared\cloudflared.exe" tunnel --url http://localhost:5000 --no-autoupdate"

echo.
echo Iki pencere acildi.
echo Tunnel penceresinde 'https://....trycloudflare.com' adresini gorebilirsin.
echo Bu URL'yi paylasarak herhangi bir cihazdan eris.
echo.
echo Onemli: QR kodlarini ureteceksen, /qr sayfasini MUTLAKA bu public URL ile ac.
echo (Aksi halde QR kodlar localhost icerigi olur ve cep telefonlardan acilmaz.)
echo.
pause
