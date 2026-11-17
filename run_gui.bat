@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo 正在启动 Sionna RT GUI 并加载户型图 3D 室内场景 (scenes/apartment.xml)...
"E:\program\anaconda\envs\research\Scripts\sionna-rt-gui.exe" "scenes\apartment.xml" --config "configs\ble_indoor.yaml"
pause
