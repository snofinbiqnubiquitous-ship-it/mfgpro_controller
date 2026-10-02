@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions DisableDelayedExpansion
set "MFG_SETUP_RESULT=1"
set "MFG_SETUP_NO_PAUSE="
set "MFG_SETUP_PUSHED="
if /i "%~1"=="--no-pause" set "MFG_SETUP_NO_PAUSE=1"

pushd "%~dp0"
if errorlevel 1 goto folder_error
set "MFG_SETUP_PUSHED=1"
echo QAD / MFG:PRO - First-time setup
echo.
if not exist "requirements.txt" goto requirements_missing
if not exist "*.pyw" goto application_missing
if not exist "addons\" (
    set "MFG_SETUP_MISSING_FILE=addons folder"
    goto application_missing
)
for %%F in ("terminal_core.py" "order_entry.py" "order_history.py" "order_date_picker.py" "ui_fonts.py" "qad_report.py" "addon_host.py") do (
    if not exist "%%~F" (
        set "MFG_SETUP_MISSING_FILE=%%~F"
        goto application_missing
    )
)
if exist ".venv\Scripts\python.exe" goto check_environment
if exist ".venv" goto environment_error

where py.exe >nul 2>&1
if errorlevel 1 goto try_python
py -3.12 -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto create_py312
py -3 -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto create_py3

:try_python
where python.exe >nul 2>&1
if errorlevel 1 goto python_missing
python -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto python_missing
echo [1/4] Creating a local Python environment...
python -m venv ".venv"
if errorlevel 1 goto environment_error
goto check_environment

:create_py312
echo [1/4] Creating a local environment with Python 3.12...
py -3.12 -m venv ".venv"
if errorlevel 1 goto environment_error
goto check_environment

:create_py3
echo [1/4] Creating a local Python environment...
py -3 -m venv ".venv"
if errorlevel 1 goto environment_error

:check_environment
".venv\Scripts\python.exe" -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto environment_error
".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if not errorlevel 1 goto install_packages
".venv\Scripts\python.exe" -m ensurepip --upgrade
if errorlevel 1 goto install_error

:install_packages
echo [2/4] Installing required libraries...
echo An internet connection is needed for the first installation.
".venv\Scripts\python.exe" -X utf8 -m pip --disable-pip-version-check install -r "requirements.txt"
if errorlevel 1 goto install_error

echo [3/4] Checking dependencies...
".venv\Scripts\python.exe" -X utf8 -m pip --disable-pip-version-check check
if errorlevel 1 goto install_error

echo [4/4] Checking application imports...
".venv\Scripts\python.exe" -X utf8 -c "from pathlib import Path; assert Path('\u81ea\u4f5c\u30e2\u30c0\u30f3\u30bf\u30fc\u30df\u30ca\u30eb.pyw').is_file(), 'The main .pyw file is missing'; import customtkinter, paramiko, pyte, PIL, dateutil, tkcalendar, babel; import terminal_core, order_entry, order_history, order_date_picker, ui_fonts, qad_report, addon_host; import glob, py_compile; [py_compile.compile(f, doraise=True) for f in glob.glob('addons/*.py')]; print('Application imports: OK')"
if errorlevel 1 goto import_error

echo.
echo Setup completed successfully.
echo Double-click the .pyw file to start the application.
echo A company VPN connection is required for QAD login.
set "MFG_SETUP_RESULT=0"
goto finish

:requirements_missing
echo [ERROR] requirements.txt was not found.
echo Place this BAT file in the application folder.
goto finish

:application_missing
echo [ERROR] Application files are missing: %MFG_SETUP_MISSING_FILE%
echo Extract the complete application folder, including the .pyw file.
goto finish

:python_missing
echo [ERROR] Python 3.10 or later with tkinter is required.
echo Install Python 3.12 for Windows with Python launcher and tcl/tk,
echo then run this BAT file again. See README.md for instructions.
goto finish

:environment_error
echo [ERROR] The local Python environment could not be created or started.
echo Do not use a .venv folder copied from another PC.
echo Rename the existing .venv folder, then run this BAT file again.
echo Also check that you can write to the application folder.
goto finish

:install_error
echo [ERROR] Library installation or dependency checks failed.
echo Check the error above and your internet connection.
goto finish

:import_error
echo [ERROR] Application imports failed.
echo Check the error above and ensure all application files are present.
goto finish

:folder_error
echo [ERROR] The application folder could not be opened.
echo Extract the ZIP to a writable folder before running this BAT file.

:finish
echo.
if defined MFG_SETUP_PUSHED popd
if not defined MFG_SETUP_NO_PAUSE pause
endlocal & exit /b %MFG_SETUP_RESULT%
