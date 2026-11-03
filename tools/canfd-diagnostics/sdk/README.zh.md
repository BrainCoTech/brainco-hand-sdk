# Revo2 Python SDK + Linux SocketCAN 对照测试

在直接收发测试正常后，通过已安装的 BrainCo Python SDK 执行相同项目，比较 SDK 解析与原始报文。脚本直接使用 SDK 的 Linux SocketCAN 传输，不需要 ROS 或 ZCANPro。

支持从站 126、127，默认主站 ID 为 1。默认只读 SN、固件版本、左右手信息和马达状态；只有显式指定 `--action open` 或 `--action close` 才发送位置控制命令。一个地址对应一只手；只接一只时只填写它的地址，避免另一地址超时。

## 环境

使用 Linux 和 Python 3.10 及以上版本，并在运行脚本的同一个 Python 环境中安装适配本机 CPU 架构的 `bc-stark-sdk` 包。本 ZIP 仅含示例和说明，不含 SDK wheel 或原生库，不会安装、升级或替换现有 SDK。

先使用现有程序相同的 SDK 包和 Python 环境，避免同时改变 SDK 版本和调用方式。确认实际加载的 SDK：

```bash
python3 canfd_sdk.py --info-only
```

输出包含包版本、SDK 自报版本、原生库绝对路径和 SHA256。比较不同 SDK 版本时分别保存这份输出。不要只根据 wheel 文件名或环境名称判断实际加载版本。

本例使用 `init_socketcan_canfd`、`init_device_handler`、`get_device_info`、`get_motor_status`、`set_finger_positions` 和 `close_socketcan`。若现有 SDK 不提供这些接口，保留错误信息并使用提供这些接口的匹配版本。脚本不修改 SDK 的收发回调或 CRC 校验规则。

停止 ROS 节点及其他主动收发程序，保留被动 `candump`。确认 `can0` 使用仲裁域 **1 Mbps / 75%**、数据域 **5 Mbps / 75%**：

```bash
ip -details -statistics link show dev can0
```

脚本只记录接口配置，不修改波特率或采样点。若需要重新配置接口，参照直接收发版说明，在开始两组测试前配置一次，保持测试期间配置一致。

## 两组对照

SDK 的 `get_motor_status` 一次读取 2000～2023 共 24 个寄存器。直接收发版应加 `--status-count 24`，以比较相同长度的马达状态应答；直接版默认的 12+12 分段模式可以另跑一组，不要混为同一种报文。

下面以只连接 127 为例。连接 126 时替换为 `--slaves 126`；确实连接两只手时可用 `--slaves 126,127`，每轮依次读取两只手。

第一组，在直接收发版目录运行：

```bash
python3 canfd_direct.py --interface can0 --slaves 127 --status-count 24 --duration 60 --hz 10 --output direct-run-127
```

同时在另一终端抓包：

```bash
timeout 100s candump -L can0 > can-direct.log 2>&1
```

完成第一组后结束对应抓包，再开始第二组。在本 SDK 版目录运行：

```bash
python3 -u canfd_sdk.py --interface can0 --slaves 127 --duration 60 --hz 10 --output sdk-run-127 > sdk-console.log 2>&1
```

同时在另一终端重新抓包：

```bash
timeout 100s candump -L can0 > can-sdk.log 2>&1
```

`candump` 来自 Linux 的 `can-utils` 包；Debian/Ubuntu 可使用 `sudo apt install can-utils` 安装。使用大写 `-L`，不要改为小写 `-l`。`timeout` 到时返回 124 属于预期，也可用 Ctrl+C 提前结束抓包。

`--hz 10` 是每轮读取全部所选手的目标频率，不是每只手各占一个独立线程。调用变慢时不追赶补发。脚本不添加应用层重试或人为覆盖 SDK 超时；SDK 内部的等待、重试和解析行为由实际加载版本决定。停止信号会在正在进行的 SDK 调用返回后生效，故测试可能比设定时长稍长。

启动时通过 `get_device_info` 获取 SN、固件版本、左右手和硬件类型，并初始化 SDK 的设备上下文。它可能包含多条内部请求，不能按“一次 API 调用等于一帧”计数。设备信息失败后仍会记录后续马达读取尝试，并标注上下文未初始化；不会强制覆盖硬件型号，也不会向该手发送动作命令。

## 张合对照

以下命令会使手运动。确认手周围无遮挡、未抓持物体后执行。程序每只手只调用一次位置设置，不循环张合，不自动恢复原位置。

先查看 API 计划，不加载 SDK、不打开设备：

```bash
python3 canfd_sdk.py --slaves 126,127 --action close --dry-run
```

控制 127 张开或闭合，随后读 3 秒马达状态：

```bash
python3 -u canfd_sdk.py --interface can0 --slaves 127 --action open --duration 3 > sdk-open.log 2>&1
python3 -u canfd_sdk.py --interface can0 --slaves 127 --action close --duration 3 > sdk-close.log 2>&1
```

两条命令分别独立执行，并按需要运行 `open` 恢复张开。六通道顺序为 `Thumb`、`ThumbAux`、`Index`、`Middle`、`Ring`、`Pinky`：

| 命令 | SDK 位置参数 | 直接收发版对应百分比 |
| --- | --- | --- |
| `open` | `[0, 0, 0, 0, 0, 0]` | `[0, 0, 0, 0, 0, 0]` |
| `close` | `[500, 500, 1000, 1000, 1000, 1000]` | `[50, 50, 100, 100, 100, 100]` |

对已识别的 Revo2，`set_finger_positions` 将这些参数转换为 1070 起的百分比位置写入，不修改单位模式。目标和直接收发版一致，速度、限位等沿用设备现有配置。设备信息读取失败或 SDK 未识别为 Revo2 时跳过动作。

某些 SDK 版本对写应答的检查较宽松，因此 `set_finger_positions` 返回成功不能单独证明写应答 CRC 正确，也不能证明实际到位。检查 `candump` 中写入应答，并对照后续马达状态。

## 发回的结果

请提供：

- `direct-run-127/` 和 `can-direct.log`。
- `sdk-run-127/`、`sdk-console.log` 和 `can-sdk.log`。
- 若做了动作测试，附上对应的结果目录、控制台日志及抓包。

SDK 结果目录包含 `environment.json`、`events.jsonl`、`summary.json`，记录实际 SDK 来源、API 开始/结束、异常原文、耗时、状态结果和运行前后接口统计。SDK 原生日志启用 Debug 级别；是否包含完整帧取决于实际 SDK 版本，`candump` 是独立原始报文证据，不能省略。

优先对齐同一从站、固件、主站 ID、接口设置、24 寄存器读取长度及频率。两组测试是顺序运行，不要同时打开两个主动收发脚本。同一长度协议应答没有事务序号，仍需结合时序和完整数据核对归属。

直接收发正常而 SDK 报错时，先检查 SDK 故障当次抓包：若原始帧 CRC16 本来就不匹配，继续检查设备发送及控制器、驱动接收；若原始帧 CRC16 正确，SDK 对同一帧报错，再核对 SDK 收包数据、长度和解析。不同时间采集的“正常”和“异常”不能单独证明根因。

马达结果为 SDK 解析后的数据，单位和枚举按所用 SDK 定义；与直接版原始寄存器比较时先核对缩放和符号。日志同时记录 UTC 与主机单调时钟，不是控制器硬件时间戳。

本例需要在目标 Linux 设备上验证实际 SocketCAN 通信；API 预览、模块加载或离线检查不能替代实机测试。
