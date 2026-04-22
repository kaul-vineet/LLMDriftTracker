@echo off
setlocal
pushd "%~dp0"
if "%1"=="setup"     ( python -m agent.wizard                          & goto :done )
if "%1"=="run"       ( python -m agent.main                            & goto :done )
if "%1"=="eval"      ( python -m agent.main --force-eval               & goto :done )
if "%1"=="dashboard" ( python -m streamlit run dashboard/app.py        & goto :done )
echo.
echo   ^⚡  ASHOKA
echo.
echo   drift setup        run the setup wizard
echo   drift run          start the autonomous polling agent
echo   drift eval         force-run evals for all monitored bots now
echo   drift dashboard    launch the Streamlit dashboard
echo.
:done
popd
