@echo off
echo =========================================
echo Global Nexus Blog - Auto Article Generator
echo =========================================

:: プロジェクトディレクトリに移動
cd /d "D:\app\global-nexus-blog"

:: 仮想環境を使用している場合は以下のREMを外して有効化
:: call .\.venv\Scripts\activate

:: Ollamaが起動しているか確認し、起動していなければ裏で起動する
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe">NUL
if "%ERRORLEVEL%"=="1" (
    echo Starting Ollama server...
    start /b ollama serve
    timeout /t 5 /nobreak
)

:: メインのPythonスクリプトを実行
echo Running AI Content Generator...
python main.py

echo Process completed.