# Revo2 CAN FD 收发与 SDK 对照测试

本包包含直接收发报文、CAN FD 协议解析说明和 Python SDK 调用示例。两套程序均在 Linux 上使用 SocketCAN，不需要 ROS 或 ZCANPro。先运行直接收发版，再运行 SDK 版，对照同一设备的原始报文与 SDK 解析结果。

## 文件

| 文件 | 用途 |
| --- | --- |
| [CANFD_PROTOCOL.zh.md](CANFD_PROTOCOL.zh.md) | CAN ID、数据字段、字节序、寄存器、CRC16、补齐、正常和异常应答定义 |
| [direct/canfd_direct.py](direct/canfd_direct.py) | Python 标准库直接收发，不依赖 BrainCo SDK |
| [direct/README.zh.md](direct/README.zh.md) | 直接收发版的配置、运行、日志和张合说明 |
| [direct/frame_reference.txt](direct/frame_reference.txt) | 126、127 的完整请求与构造应答示例 |
| [sdk/canfd_sdk.py](sdk/canfd_sdk.py) | 使用已安装的 BrainCo Python SDK，通过 SDK 的 SocketCAN 传输调用设备 |
| [sdk/README.zh.md](sdk/README.zh.md) | SDK 环境确认、运行、异常与对照说明 |
| [direct/test_canfd_direct.py](direct/test_canfd_direct.py)、[sdk/test_canfd_sdk.py](sdk/test_canfd_sdk.py) | 协议和 SDK 调用的离线测试，不连接设备 |
| [package.py](package.py) | 按固定文件清单生成 ZIP 和 SHA256 校验值 |

报文中的 SN、状态及控制应答示例为按协议构造的数据，不是真机抓包，不应当作实际设备返回值或动作结果。

## 运行前

- Linux、Python 3.10 及以上版本，`can0` 已启用 CAN FD。
- 仲裁域 1 Mbps / 75% 采样点，数据域 5 Mbps / 75% 采样点。配置方法见直接收发版说明；两组测试保持配置不变。
- 连接一只手时，只填其实际地址 `--slaves 126` 或 `--slaves 127`；连接两只时才用 `--slaves 126,127`。地址本身不代表左右手。
- 默认主站 ID 为 1。停止 ROS 节点和其他主动收发程序，两套脚本也不要同时主动发送；独立 `candump` 可以同时被动抓包。
- 直接收发版仅需 Python 标准库；SDK 版还需在同一 Python 环境中安装适配 Linux CPU 架构的 `bc-stark-sdk`。本包不含 SDK 安装包，不自动升级或替换 SDK。
- `candump` 来自 `can-utils`；Debian/Ubuntu 可用 `sudo apt install can-utils` 安装。

先查看当前总线配置：

```bash
ip -details -statistics link show dev can0
```

以下命令均在解压后的本包根目录运行，以只连接从站 127 为例。默认只读，读取 SN、固件版本、左右手信息和马达状态，不触发手指动作。

## 第一组：直接收发

终端 A，先启动独立抓包：

```bash
timeout 100s candump -L can0 > can-direct.log 2>&1
```

终端 B，运行 60 秒：

```bash
python3 direct/canfd_direct.py --interface can0 --slaves 127 --status-count 24 --duration 60 --hz 10 --output direct-run-127
```

这里使用 `--status-count 24`，与 SDK 一次读取完整马达状态的长度一致。若要对照 12+12 分段读取，另跑一组 `--status-count 12`，不要混为同一种报文。

第一组结束后等待抓包到时结束，或按 Ctrl+C 停止该次 `candump`，再进行第二组。大写 `-L` 输出文本日志，不要改成小写 `-l`；`timeout` 到时返回 124 属于预期。

## 第二组：SDK

先确认实际加载的 SDK 版本、库路径和校验值：

```bash
python3 sdk/canfd_sdk.py --info-only
```

终端 A，重新启动抓包：

```bash
timeout 100s candump -L can0 > can-sdk.log 2>&1
```

终端 B：

```bash
python3 -u sdk/canfd_sdk.py --interface can0 --slaves 127 --duration 60 --hz 10 --output sdk-run-127 > sdk-console.log 2>&1
```

重复测试时换一个新的 `--output` 目录名称，程序不会覆盖已存在的结果目录。

两版的 `--hz 10` 都表示一轮依次读取所有已选手的目标频率；超时或调用变慢会降低实际频率，不追赶补发。SDK 版保留已安装 SDK 自身的超时、重试和解析行为。

## 张合与报文预览

默认 `monitor` 模式只读。先预览拟发送报文或 API，不打开设备：

```bash
python3 direct/canfd_direct.py --slaves 127 --action close --dry-run
python3 sdk/canfd_sdk.py --slaves 127 --action close --dry-run
```

只有显式指定 `--action open` 或 `--action close` 才执行动作。实际命令、百分比位置映射、动作条件和后续状态读取见两版说明。动作执行前确认手周围无遮挡、未抓持物体；脚本不自动循环张合。

## 提供结果与定位

请提供 `direct-run-127/`、`can-direct.log`、`sdk-run-127/`、`sdk-console.log`、`can-sdk.log`；若测试 126 或两只手，提供对应结果。脚本运行时生成的设备 SN 和本地库路径用于关联测试，应只提供给参与排查的人员。

直接收发版记录每帧 CAN ID、完整数据、有效长度、实际长度、CRC16 重算和补齐；SDK 版记录实际加载版本、API 耗时、异常原文和解析结果。两者都记录接口状态。

若直接收发正常而 SDK 报错，先检查 SDK 报错当次 `candump` 中的原始帧：原始帧 CRC16 也错误时，继续对照设备发送与控制器、驱动接收；原始帧正确而 SDK 对同一帧报错时，再检查 SDK 接收数据、长度和解析。先对齐地址、固件、读取数量、频率、采样点和具体时段，再判断差异。

这些示例需要在目标 Linux 设备上验证实际通信及动作；离线检查、API 预览和模块加载不替代实机测试。

## 维护与离线验证

在本目录分别运行两组离线测试，不加载设备、不执行动作：

```bash
python3 -m unittest discover -s direct -p 'test_*.py'
python3 -m unittest discover -s sdk -p 'test_*.py'
```

生成可单独解压使用的诊断包：

```bash
python3 package.py --output revo2_canfd_diagnostics.zip
```

打包程序只包含上表列出的文件和本 README，另生成 `SHA256SUMS`；不包含测试结果、运行日志或 SDK 原生库。目标 ZIP 已存在时拒绝覆盖。解压后可在包根目录运行本文命令。
