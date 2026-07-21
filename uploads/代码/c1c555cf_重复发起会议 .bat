@echo off
setlocal enabledelayedexpansion
set DEVICE_IP=172.16.161.179
set loop_count=0

:loop
set /a loop_count+=1
echo ========== %loop_count% ==========
adb -s %DEVICE_IP% shell input tap 1282 912
powershell -command "Start-Sleep -Milliseconds 7000"
adb -s %DEVICE_IP% shell input tap 2738 1944
powershell -command "Start-Sleep -Milliseconds 300"
adb -s %DEVICE_IP% shell input tap 2678 1626
powershell -command "Start-Sleep -Milliseconds 300"
adb -s %DEVICE_IP% shell input tap 2678 1626
powershell -command "Start-Sleep -Milliseconds 5000"
goto loop
pause