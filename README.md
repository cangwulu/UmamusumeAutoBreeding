# UmamusumeAutoTrainer

> **社区续更版 | Community Continuation**
>
> 本项目基于 [shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer) 继续维护。
> 原项目已长时间未更新，本仓库由社区接手维护，新增功能并修复已知问题。

---

## 📌 关于本项目

**原项目地址：** https://github.com/shiokaze/UmamusumeAutoTrainer

**原作者：** [@shiokaze](https://github.com/shiokaze)

感谢原作者 [@shiokaze](https://github.com/shiokaze) 以及所有为原项目贡献过的开发者。本仓库在原项目基础上进行功能扩展和 Bug 修复，旨在为《闪耀！优俊少女》玩家提供持续更新的自动育成工具。

⚠ 此项目目前只支持**国服/简体中文版**游戏, 不支持包括英文版在内的任何其它版本。

⚠ This project currently only supports **Simplified Chinese version** of Umamusume game. We do not have any plans to support other versions (including Global version) in the predictable future.

---

## 🆕 本版本与原版的区别

| 特性 | 原版 (shiokaze) | 本续更版 |
|------|----------------|---------|
| 剧本支持 | URA、青春杯 | URA、青春杯、**凯旋门**（新增） |
| 维护状态 | 已停止更新 | **持续维护中** |

### 更新日志

<details>
<summary>点击查看详细更新日志</summary>

#### [Unreleased]
- 新增凯旋门剧本适配

#### 原版本更新历史
- 原项目更新记录请参见 [原仓库 Commit 历史](https://github.com/shiokaze/UmamusumeAutoTrainer/commits/main/)

</details>

---

## 📜 许可证与版权声明

本项目是基于 [shiokaze/UmamusumeAutoTrainer](https://github.com/shiokaze/UmamusumeAutoTrainer) 的衍生作品。

- **原项目**未指定开源许可证，原作者 [@shiokaze](https://github.com/shiokaze) 保留原始代码的所有权利。
- **本续更版本**新增的代码和修改采用 [MIT License](LICENSE) 开源协议。
- 如果你要使用本项目代码，请同时尊重原作者的贡献，并在你的衍生作品中保留本声明。

---

## ⚡ 使用说明

### 1. 下载

```bash
git clone https://github.com/cangwulu/UmamusumeAutoTrainer.git
cd UmamusumeAutoTrainer
```

### 2. 安装依赖

1. 安装 Python 3.10.9，[下载地址](https://www.python.org/downloads/release/python-3109/)
2. 双击运行 `install.ps1`，如果打开是记事本，右键文件→打开方式→选择 PowerShell 运行。启动时需要保证当前目录下没有 `venv` 文件夹。
   - （如果不在中国大陆地区或不需要国内镜像，可将 `install.ps1` 中的 pip 命令改为 `pip install --upgrade -r requirements.txt`）

### 3. 配置

修改 `config.yaml`：

```yaml
bot:
  auto:
    adb:
      device_name: "127.0.0.1:16384" # 改为模拟器的 adb 端口
      delay: 0
    cpu_alloc: 4 # 分配的 cpu 数量
```

常见模拟器端口：
- （推荐使用）**mumu12**: `127.0.0.1:16384`
- **雷电/蓝叠模拟器**: `emulator-5554`

#### 蓝叠模拟器每次启动端口号都不一样（Hyper-V）

在蓝叠模拟器的数据目录下找到 `bluestacks.conf`：
- 国际版默认路径：`C:\ProgramData\BlueStacks_nxt\bluestacks.conf`
- 中国内地版默认路径：`C:\ProgramData\BlueStacks_nxt_cn\bluestacks.conf`

```yaml
bot:
  auto:
    adb:
      device_name: "127.0.0.1:16384"
      delay: 0
      bluestacks_config_path: "C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf"
      bluestacks_config_keyword: "bst.instance.Rvc64.status.adb_port"
    cpu_alloc: 4
```

### 4. 模拟器设置

- 设置模拟器分辨率为 **720 × 1280**，DPI **180**（竖屏）
- mumu 模拟器**不能开启后台保活功能**

### 5. 启动

双击运行 `run.ps1` 即可。

控制台显示以下内容即为启动成功：

```
UAT running on http://127.0.0.1:8071
```

复制到浏览器访问即可通过 Web UI 配置任务并启动脚本。

<img alt="LOGO" src="docs/1.png" width="680" height="565" />

---

## ⚠️ 注意事项

1. 游戏内画面选项必须是**标准版**，不能是简易版
2. 如果马娘育成阶段中包含了自选赛事或粉丝数量要求的比赛（如小栗帽第三年的 2 场 G1 和乌拉拉的粉丝数目标等），需要使用对应马娘的预设或在自定义赛程中自行配置参加哪场比赛
3. 目标属性尽量与携带的支援卡类型比例匹配，不要带了例如 3 智 3 速又设置了很高的耐力和力量目标
4. 暂时不支持选择育成马娘和种马，启动时会使用游戏内保存的上次育成的马娘和种马。如果没有保存记录，先手动选择完成后在启动
5. 不推荐携带友人卡，因为暂时没有对友人卡出行写特定策略，所以效果不如带其他类型支援卡
6. 启动脚本时应处于主菜单或者任意育成界面

### 如果出现异常

1. 如果出现了模拟器连接失败、connection reset 等错误，关闭正在运行的加速器（如 uu 加速器）并使用任务管理器关闭 `adb.exe` 后重启模拟器以及脚本程序
2. 如果出现了识别错误导致程序报错、进入了预期之外的界面、或者卡在某一界面不动的情况下，人工操作进入下一回合并在 Web UI 内重置任务再启动即可。可以保存一下卡住的界面截图并附上报错日志提 Issue

---

## ❓ 常见问题

#### 1. 运行 install.ps1 或 run.ps1 时闪退
可以先打开控制台再运行 PowerShell 脚本，此时报错即可看到报错原因。

#### 2. 系统禁止运行 PowerShell 脚本
参考：https://www.jianshu.com/p/4eaad2163567

#### 3. 脚本启动时报错
检查用户文件夹是否为中文  
参考： https://github.com/shiokaze/UmamusumeAutoTrainer/issues/18  
https://github.com/shiokaze/UmamusumeAutoTrainer/issues/24

#### 4. 启动成功，但是 Web UI 打不开，且浏览器控制台报错
如果报错信息是：`Failed to load module script: Expected a JavaScript module script but the server responded with a MIME type of "text/plain".`  
参考： https://github.com/shiokaze/UmamusumeAutoTrainer/issues/9  
https://github.com/shiokaze/UmamusumeAutoTrainer/issues/25

---

## 📝 TODO

- [ ] 定时执行任务
- [ ] 育成中 AI 逻辑优化
- [ ] 事件支持配置选项
- [ ] 自动完成每日金币/支援点/JJC
- [ ] 凯旋门剧本完善与优化

---

## 🤝 参与开发

如果觉得现在的代码有不足之处，欢迎提交 Issue 和 Pull Request！

### 贡献者

- [@shiokaze](https://github.com/shiokaze) — 原项目作者

---

*本项目仅供学习研究使用，请勿用于商业用途。*
