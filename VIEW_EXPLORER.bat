@echo off
REM One-click launcher for the September 11 Explorer.
REM Double-click this file, or run it from a terminal.
REM
REM Works from the repository root and from an unzipped
REM phase0-scale-corpus artifact. It only serves the Explorer directory
REM over HTTP and opens your browser -- nothing is installed or changed.

setlocal
cd /d "%~dp0"

REM Prefer the Windows launcher (py), fall back to python on PATH.
REM Plain labels, not nested if-blocks: %ERRORLEVEL% inside a parenthesised
REM block expands when the block is parsed, not when it runs.
set "PY="
where py >nul 2>nul && set "PY=py"
if defined PY goto :found
where python >nul 2>nul && set "PY=python"
if defined PY goto :found
echo.
echo   Python was not found on this machine.
echo   Install it from https://www.python.org/downloads/ and tick
echo   "Add python.exe to PATH", then run this file again.
echo.
pause
exit /b 1

:found
REM The launcher logic lives in tools\view_explorer.py so it can be tested.
if exist "tools\view_explorer.py" goto :helper

REM Inside an unzipped artifact there is no tools directory; serve directly.
if exist "explorer\index.html" goto :artifact
if exist "index.html" goto :here
echo.
echo   Could not find the Explorer next to this file.
echo   Run it from the repository root, or from an unzipped
echo   phase0-scale-corpus artifact.
echo.
pause
exit /b 2

:helper
%PY% "tools\view_explorer.py" %*
goto :done

:artifact
start "" http://localhost:8000/
%PY% -m http.server 8000 --directory explorer
goto :done

:here
start "" http://localhost:8000/
%PY% -m http.server 8000

:done
if %ERRORLEVEL% NEQ 0 pause
endlocal
