@echo off
REM One-click launcher for the September 11 Explorer.
REM Double-click this file, or run it from a terminal.
REM
REM Works in three places, no setup:
REM   * the repository root
REM   * an unzipped phase0-scale-corpus artifact (next to the explorer folder)
REM   * inside the explorer folder itself
REM It only serves files over HTTP and opens your browser. Nothing is
REM installed, downloaded, or changed.

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
REM Use the full launcher when it is beside this file or under tools\.
if exist "view_explorer.py" goto :helper_here
if exist "tools\view_explorer.py" goto :helper_tools

REM No helper: serve directly. Still fine, just fewer niceties.
if exist "explorer\index.html" goto :artifact
if exist "index.html" goto :here
echo.
echo   Could not find the Explorer next to this file.
echo   Put this file in the repository root, or beside the
echo   'explorer' folder from an unzipped phase0-scale-corpus artifact.
echo.
pause
exit /b 2

:helper_here
%PY% "view_explorer.py" %*
goto :done

:helper_tools
%PY% "tools\view_explorer.py" %*
goto :done

:artifact
if not exist "explorer\data\explorer.json" echo   Warning: explorer\data\explorer.json is missing; the page will be empty.
start "" http://localhost:8000/
echo   Serving explorer on http://localhost:8000/  (close this window to stop)
%PY% -m http.server 8000 --directory explorer
goto :done

:here
if not exist "data\explorer.json" echo   Warning: data\explorer.json is missing; the page will be empty.
start "" http://localhost:8000/
echo   Serving on http://localhost:8000/  (close this window to stop)
%PY% -m http.server 8000

:done
if %ERRORLEVEL% NEQ 0 pause
endlocal
