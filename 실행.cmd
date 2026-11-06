@echo off
setlocal
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" goto missing_setup
if not exist "streamlit_app.py" goto missing_app
echo Open http://localhost:8501 if the browser does not open automatically.
echo Keep this window open. Press Ctrl+C here to stop the app.
".venv\Scripts\python.exe" -m streamlit run streamlit_app.py --server.address=127.0.0.1
set "PKOS_EXIT=%ERRORLEVEL%"
popd
if not "%PKOS_EXIT%"=="0" pause
exit /b %PKOS_EXIT%
:missing_setup
echo Run the setup .cmd file in this folder first.
goto failed
:missing_app
echo streamlit_app.py was not found. Extract the complete project ZIP first.
:failed
popd
pause
exit /b 1
