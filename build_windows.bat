@echo off
REM Build the Windows apps into dist\windows\:
REM   LandmarkConverter.exe   GUI (drag & drop window; you can also drop files onto the .exe)
REM   landmark_convert.exe    command-line converter (drop files onto it for the old console prompt)
REM Usage: build_windows.bat   (from the repo root, in a Windows Python env with requirements.txt installed)
setlocal
cd /d "%~dp0"
set OUT=dist\windows
if not exist %OUT% mkdir %OUT%
copy /y "%~f0" %OUT%\ >nul
echo %date% %time%  "%~f0" %* >> %OUT%\run_command.txt

python -m PyInstaller --noconfirm --onefile --windowed --name LandmarkConverter ^
    --collect-all tkinterdnd2 --distpath %OUT% --workpath build\win-gui --specpath build\win-gui ^
    landmark_convert_gui.py || exit /b 1
python -m PyInstaller --noconfirm --onefile --console --name landmark_convert ^
    --distpath %OUT% --workpath build\win-cli --specpath build\win-cli ^
    landmark_convert.py || exit /b 1
copy /y landmark_convert.py %OUT%\ >nul
copy /y landmark_convert_gui.py %OUT%\ >nul
echo Built: %OUT%\LandmarkConverter.exe  %OUT%\landmark_convert.exe
