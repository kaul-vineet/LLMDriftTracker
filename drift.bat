@echo off
setlocal
pushd "%~dp0"
if "%1"=="setup"     ( python -m agent.wizard                          & goto :done )
if "%1"=="run"       ( python -m agent.main                            & goto :done )
if "%1"=="dashboard" ( python -m streamlit run dashboard/app.py        & goto :done )
echo.
echo   ^⚡  LLM Drift Tracker
echo.
echo   drift setup        run the setup wizard
echo   drift run          start the autonomous polling agent
echo   drift dashboard    launch the Streamlit dashboard
echo.
:done
popd
