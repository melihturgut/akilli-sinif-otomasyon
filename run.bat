@echo off
chcp 65001 >nul
echo ============================================
echo   Akilli Sinif Otomasyonu - IoT Simulasyonu
echo ============================================
echo.
echo Flask kuruluyor...
python -m pip install flask --quiet
echo.
echo Sunucu baslatiliyor...
echo Telefonda erisim icin ayni Wi-Fi aginda olun.
echo.
python app.py
pause
