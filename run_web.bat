@echo off
echo Starting Content Ops Agent Web UI...
echo.
echo Using conda environment: only
echo Opening browser at: http://localhost:8501
echo.
conda run -n only streamlit run src/web/app.py
pause