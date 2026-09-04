@echo off
REM ============================================================
REM  启动 UmamusumeAutoTrainer 规划 Web 服务 (并自动打开网页)
REM  !!! 必须用 uat 环境 (含 cv2 4.5.5 / paddle 等) !!!
REM  main.py 顶层 import cv2，其他 Python(如 .local\bin\python3.12) 会报 ModuleNotFoundError
REM  默认监听 http://127.0.0.1:8071  ->  规划页 /planning.html
REM  如服务已在跑，本脚本只打开网页，不会重复监听端口
REM ============================================================
cd /d "E:\shouyou\saimaniang\UmamusumeAutoTrainer"

REM --- uat 环境检查 ---
if not exist "E:\MINICONDA\envs\uat\python.exe" (
  echo [错误] 找不到 uat 环境: E:\MINICONDA\envs\uat\python.exe
  echo 请先确认 conda 环境 uat 已存在 (conda env list)。
  pause
  exit /b 1
)

REM --- 已在运行? 直接开网页 ---
netstat -ano 2>nul | findstr /r ":8071 .*LISTENING" >nul
if %errorlevel%==0 (
  echo 规划服务已在运行，正在打开网页...
  start http://127.0.0.1:8071/planning.html
  goto :eof
)

REM --- 启动服务 (独立窗口, 崩溃也保留报错) ---
echo 正在启动规划服务 (http://127.0.0.1:8071) ...
start "UmamusumeAutoTrainer 服务" cmd /k E:\MINICONDA\envs\uat\python.exe main.py

REM --- 等几秒让 uvicorn 绑定端口 ---
timeout /t 6 /nobreak >nul

netstat -ano 2>nul | findstr /r ":8071 .*LISTENING" >nul
if %errorlevel%==0 (
  echo 服务已启动，正在打开规划页...
  start http://127.0.0.1:8071/planning.html
) else (
  echo [警告] 6 秒后仍未监听 8071 端口，服务可能启动失败。
  echo 请查看 "UmamusumeAutoTrainer 服务" 窗口的报错（常见：cv2 未安装 / 端口被占）。
  echo 也可手动在浏览器访问 http://127.0.0.1:8071/planning.html
)
pause
