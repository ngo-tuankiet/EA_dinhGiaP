@echo off
setlocal EnableExtensions
chcp 65001 >nul

title He thong dinh gia VN100

pushd "%~dp0"

echo ============================================================
echo    HE THONG DINH GIA CO PHIEU TU DONG VN100 - WINDOWS
echo ============================================================
echo.
echo Dang kiem tra Python va khoi dong ung dung...
echo.

set "PYTHON_CMD="
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PYTHON_CMD=python"
    )
)

if "%PYTHON_CMD%"=="" (
    echo Khong tim thay Python.
    echo Vui long cai Python 3.11+ tai https://www.python.org/downloads/windows/
    echo Khi cai dat, hay tick "Add python.exe to PATH", sau do chay lai file nay.
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if not %ERRORLEVEL%==0 (
    echo Python tren may qua cu. Vui long cai Python 3.11+ roi chay lai.
    echo.
    pause
    exit /b 1
)

set "VENV_DIR=%USERPROFILE%\.venv"
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Dang tao moi truong Python tai %VENV_DIR%...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if not %ERRORLEVEL%==0 (
        echo Tao moi truong Python that bai.
        echo.
        pause
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"

python -c "import importlib.util, subprocess, sys; required=['streamlit','sqlalchemy','pandas','pydantic_settings','dotenv']; missing=[name for name in required if importlib.util.find_spec(name) is None]; print('Dang cai/cap nhat thu vien can thiet...') if missing else None; subprocess.check_call([sys.executable,'-m','pip','install','-U','pip']) if missing else None; subprocess.check_call([sys.executable,'-m','pip','install','-r','requirements.txt']) if missing else None"
if not %ERRORLEVEL%==0 (
    echo Cai thu vien that bai. Hay kiem tra ket noi internet va chay lai file nay.
    echo.
    pause
    exit /b 1
)

python scripts\ensure_portable_db.py
if not %ERRORLEVEL%==0 (
    echo Khong the chuan bi database portable.
    echo Hay kiem tra file vn100_full.db.gz co nam trong thu muc du an khong.
    echo.
    pause
    exit /b 1
)

set "ROOT_DIR=%CD%"
set "ROOT_URL=%ROOT_DIR:\=/%"
set "DATABASE_URL_READONLY=sqlite:///%ROOT_URL%/vn100_full.db"
set "DATABASE_URL_WRITE=sqlite:///%ROOT_URL%/vn100_full.db"
set "STREAMLIT_SERVER_FILE_WATCHER_TYPE=none"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

echo.
echo Ung dung dang chay tai: http://localhost:8502
echo Neu trinh duyet khong tu mo, hay copy dia chi tren vao Chrome/Edge.
echo De tat ung dung, dong cua so nay hoac bam Ctrl+C.
echo.

start "" "http://localhost:8502"
python -m streamlit run streamlit_app.py --server.port 8502 --server.headless true --server.fileWatcherType none

popd
endlocal
