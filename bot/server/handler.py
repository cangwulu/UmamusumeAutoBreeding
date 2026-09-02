import os

from fastapi import FastAPI, Path
from fastapi.middleware.cors import CORSMiddleware

from bot.base.log import task_log_handler
from bot.engine import ctrl as bot_ctrl
from bot.server.protocol.task import *
from starlette.responses import FileResponse

server = FastAPI()

server.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # 通配源与 allow_credentials=True 是浏览器拒绝的无效组合；本服务无 cookie 认证
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@server.post("/task")
def add_task(req: AddTaskRequest):
    bot_ctrl.add_task(req.app_name, req.task_execute_mode, req.task_type, req.task_desc,
                      req.cron_job_config, req.attachment_data)


@server.delete("/task")
def delete_task(req: DeleteTaskRequest):
    bot_ctrl.delete_task(req.task_id)


@server.get("/task")
def get_task():
    return bot_ctrl.get_task_list()

@server.get("/log/{task_id}")
def get_task_log(task_id):
    return task_log_handler.get_task_log(task_id)


@server.post("/action/bot/reset-task")
def reset_task(req: ResetTaskRequest):
    bot_ctrl.reset_task(req.task_id)


@server.post("/action/bot/start")
def start_bot():
    bot_ctrl.start()


@server.post("/action/bot/stop")
def stop_bot():
    bot_ctrl.stop()


@server.get("/")
async def get_index():
    return FileResponse('public/index.html', headers={
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    })


# ===== M1 规划闭环 Web API（库存点选/大赛登记/规划）+ 图片静态 =====
# 注意: 必须注册在下方 catch-all 静态兜底路由之前, 否则 /api/* 会被兜底抢走
from module.umamusume.planning import web_api as _plan_web_api  # noqa: E402

server.include_router(_plan_web_api.router)
server.include_router(_plan_web_api.media_router, prefix="/media")


# public 目录的绝对根，兜底路由只允许服务该目录内的文件（防 ../ 路径穿越）
PUBLIC_ROOT = os.path.realpath("public")


@server.get("/{whatever:path}")
async def get_static_files_or_404(whatever):
    # 设置防缓存头
    no_cache_headers = {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }
    # 归一化后必须仍位于 public 目录内，否则拒绝（路径穿越防护）
    file_path = os.path.realpath(os.path.join(PUBLIC_ROOT, whatever))
    if not (file_path == PUBLIC_ROOT or file_path.startswith(PUBLIC_ROOT + os.sep)):
        return FileResponse('public/index.html', headers=no_cache_headers)
    if os.path.isfile(file_path):
        if file_path.endswith((".js", ".mjs")):
            return FileResponse(file_path, media_type="application/javascript", headers=no_cache_headers)
        else:
            return FileResponse(file_path, headers=no_cache_headers)
    return FileResponse('public/index.html', headers=no_cache_headers)
