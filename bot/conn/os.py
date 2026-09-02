import subprocess
from subprocess import Popen
from typing import Any
from plyer import notification
import bot.base.log as logger

log = logger.get_logger(__name__)


# run_cmd 执行命令行
# 说明: 保留 shell=True 是因为 u2_ctrl 有依赖 shell 解析的嵌套引号+管道命令
# (如 get_front_activity)。注入面靠调用侧对 device_name 等外部输入加引号转义控制,
# 勿把未经引号包裹的配置项拼入命令串。
def run_cmd(cmd_string) -> Popen[bytes] | Popen[Any]:
    log.debug('run cmdline: {}'.format(cmd_string))
    return subprocess.Popen(cmd_string, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def push_system_notification(title, message, timeout):
    notification.notify(
        title=title,
        message=message,
        timeout=timeout
    )
