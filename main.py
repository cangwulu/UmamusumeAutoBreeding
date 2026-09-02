import sys
import threading

from bot.base.manifest import register_app
from bot.engine.scheduler import scheduler
from module.umamusume.manifest import UmamusumeManifest
from uvicorn import run

if __name__ == '__main__':
    # 版本门禁: 3.10 <= v < 3.13 (paddlepaddle==2.6.2 无 cp312+ 稳定依赖, 推荐 3.11)
    if not (sys.version_info.major == 3 and 10 <= sys.version_info.minor <= 12):
        print("\033[33m{}\033[0m".format("注意：python 版本号不正确，可能无法正常运行"))
        print("建议python版本：3.10~3.12 当前：" + sys.version)
    register_app(UmamusumeManifest)
    scheduler_thread = threading.Thread(target=scheduler.init, args=())
    scheduler_thread.start()
    print("UAT running on http://127.0.0.1:8071")
    run("bot.server.handler:server", host="127.0.0.1", port=8071, log_level="error")

