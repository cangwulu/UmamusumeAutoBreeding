@echo off
REM ============================================================
REM  启动 UmamusumeAutoTrainer 规划 Web 服务
REM  !!! 必须用 uat 环境 (含 cv2 4.5.5 / paddle 等) !!!
REM  main.py 顶层 import cv2，其他 Python(如 .local\bin\python3.12) 会报 ModuleNotFoundError
REM  默认监听 http://127.0.0.1:8071  (Ctrl+C 停止)
REM ============================================================
cd /d "E:\shouyou\saimaniang\UmamusumeAutoTrainer"
if not exist "E:\MINICONDA\envs\uat\python.exe" (
  echo [错误] 找不到 uat 环境: E:\MINICONDA\envs\uat\python.exe
  echo 请先确认 conda 环境 uat 已存在 (conda env list)。
  pause
  exit /b 1
)
"E:\MINICONDA\envs\uat\python.exe" main.py
pause
