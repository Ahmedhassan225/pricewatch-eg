@echo off
rem Start PriceWatch EG (use with Windows Task Scheduler "At log on").
cd /d "%~dp0\.."
call .venv\Scripts\activate.bat
pricewatch serve
