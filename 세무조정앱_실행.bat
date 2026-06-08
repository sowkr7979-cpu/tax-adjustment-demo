@echo off
rem ============================================
rem  Tax Adjustment App Launcher
rem  Double-click this file to start the app.
rem  Keep this window open while using the app.
rem ============================================
cd /d "%~dp0"
start "" http://localhost:8501
python -m streamlit run src/app.py --server.port 8501
pause
