@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title MSFS Emergency Response - Step 3
color 0F

echo ==================================================================
echo   MSFS 2024 Emergency Response - Step 3
echo ==================================================================
echo.

rem --------------------------------------------------------------------
rem Find a Python that ACTUALLY RUNS.
rem
rem Checking the command merely EXISTS is not enough: Windows ships a "py"
rem launcher and an app-execution-alias "python.exe" that both exist and
rem then do nothing useful. So every candidate is made to execute a real
rem line of Python, and only counts if that succeeds.
rem --------------------------------------------------------------------
set PYEXE=

py -3 -c "import sys" >nul 2>&1
if !errorlevel! equ 0 set PYEXE=py -3

if not defined PYEXE (
  py -c "import sys" >nul 2>&1
  if !errorlevel! equ 0 set PYEXE=py
)

if not defined PYEXE (
  python -c "import sys" >nul 2>&1
  if !errorlevel! equ 0 set PYEXE=python
)

if not defined PYEXE (
  python3 -c "import sys" >nul 2>&1
  if !errorlevel! equ 0 set PYEXE=python3
)

if not defined PYEXE goto NOPYTHON

echo Found a working Python:
%PYEXE% --version
echo.

echo ------------------------------------------------------------------
echo Installing the SimConnect library (needs internet, takes a moment)
echo ------------------------------------------------------------------
%PYEXE% -m pip install --upgrade --quiet SimConnect
if !errorlevel! neq 0 (
  echo.
  echo pip failed. Trying again and showing the full output:
  %PYEXE% -m pip install --upgrade SimConnect
)
echo Done.
echo.

echo ==================================================================
echo   BEFORE YOU CONTINUE
echo.
echo   MSFS 2024 must be RUNNING and you must be IN A FLIGHT,
echo   sat in the aircraft. Not the main menu, not a loading screen.
echo ==================================================================
echo.
pause
echo.

%PYEXE% step3_findvehicles.py

echo.
echo ==================================================================
echo   FINISHED
echo.
echo   A file called result3.txt is now in this same folder.
echo   Send me that file - you do not need to copy anything.
echo ==================================================================
echo.
pause
exit /b 0


:NOPYTHON
echo ##################################################################
echo   No working Python found.
echo.
echo   You may have the "py" launcher but no actual Python behind it -
echo   that is a common Windows state and it is probably what you hit.
echo ##################################################################
echo.
echo Two ways to fix it. Try A first, it is quicker.
echo.
echo   A) In this window, type:    py install 3.12
echo      Wait for it to finish, then close this window and
echo      double-click RUN_STEP3.bat again.
echo.
echo   B) Go to python.org/downloads, click the big yellow button,
echo      run the installer, and TICK "Add python.exe to PATH"
echo      on the first screen. Then double-click RUN_STEP3.bat again.
echo.
echo If neither works, take a photo of this window and send it to me.
echo.
pause
exit /b 1
