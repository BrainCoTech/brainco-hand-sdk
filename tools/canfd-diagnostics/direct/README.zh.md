# Revo2 CAN FD 原始收发排查

使用 Python 3.10 及以上版本，通过 Linux SocketCAN 直接收发，不使用 ROS、BrainCo SDK 或第三方 Python 包。可直接在 Linux 上运行，无需 ZCANPro 上位机。支持从站 126、127，默认主站 ID 为 1。默认只读；指定 `--action open` 或 `--action close` 才发送一次位置控制命令。

## 运行

先停止 ROS 控制节点和其他主动收发程序，保留被动抓包。确认现场 `can0` 已启用 CAN FD，仲裁域为 **1 Mbps、75% 采样点**，数据域为 **5 Mbps、75% 采样点**：

```bash
ip -details -statistics link show dev can0
```

脚本不会修改接口波特率、采样点或设备配置，输出会记录运行前后的接口状态和错误计数。接口已经正确配置时，无需重新配置。若尚未配置，可在停止控制程序后手动执行以下命令；这会短暂关闭 `can0`：

```bash
sudo ip link set dev can0 down
sudo ip link set dev can0 type can bitrate 1000000 sample-point 0.75 dbitrate 5000000 dsample-point 0.75 fd on restart-ms 100
sudo ip link set dev can0 up
ip -details -statistics link show dev can0
```

以最后查询输出的 `bitrate`、`sample-point`、`dbitrate`、`dsample-point` 为准。若硬件不支持这些参数，应保留错误信息并核对控制器能力。

读取两只手，持续 60 秒：

```bash
python3 canfd_direct.py --interface can0 --slaves 126,127 --duration 60 --hz 10
```

只连接一只手时，使用 `--slaves 126` 或 `--slaves 127`，避免另一地址持续超时。若 SocketCAN 操作被系统拒绝，使用现场有权限的账户执行。

默认每轮分别读取 2000 起的 12 个寄存器、2012 起的 12 个寄存器。对比一次读取 24 个寄存器的情况：

```bash
python3 canfd_direct.py --interface can0 --slaves 127 --status-count 24 --duration 60 --hz 10
```

`--hz 10` 指全部所选手完成一轮状态读取的目标频率。两只手、12 寄存器模式，每轮共 4 次请求；超时会降低实际频率，不会追赶补发。启动时各读一次 SN、固件版本和 SKU。CRC 错误、异常应答和超时都保留，不自动重试。

如未安装 `candump`，先安装 Linux 发行版的 `can-utils` 包，例如 Debian/Ubuntu 使用 `sudo apt install can-utils`。在另一终端独立抓包：

```bash
timeout 100s candump -L can0 > can-capture.log 2>&1
```

这是大写 `-L`，表示输出文本日志；不要改成小写 `-l`。100 秒后自动停止，`timeout` 返回 124 属于预期；也可按 Ctrl+C 提前结束。它和脚本使用独立接收 socket，可用于比较同一条应答在两处是否一致。

## 张合命令

以下命令会使所选手运动。确认周围无遮挡、手未抓持物体后执行；程序只发送一次目标位置，不循环张合、不自动恢复原位置，也不自动重发控制命令。

先预览报文，不接触硬件：

```bash
python3 canfd_direct.py --slaves 126,127 --action close --dry-run
```

控制 126 张开，随后读取 3 秒状态：

```bash
python3 canfd_direct.py --interface can0 --slaves 126 --action open --duration 3
```

控制 126 闭合，随后读取 3 秒状态：

```bash
python3 canfd_direct.py --interface can0 --slaves 126 --action close --duration 3
```

控制 127 时将参数改为 `--slaves 127`。使用 `--slaves 126,127` 会依次控制两只手。

位置使用 1070～1072 的百分比控制，与寄存器 937 的单位模式无关。六通道沿用协议顺序：`Thumb`、`ThumbAux`、`Index`、`Middle`、`Ring`、`Pinky`。

| 命令 | 六通道目标百分比 |
| --- | --- |
| `open` | `[0, 0, 0, 0, 0, 0]` |
| `close` | `[50, 50, 100, 100, 100, 100]` |

`close` 是固定测试姿态；实际动作速度和限位沿用设备当前配置。每对通道打包为一个寄存器，前一通道放低字节，后一通道放高字节，寄存器在线路上按大端发送。控制前 SN、固件和 SKU 三项读取均须成功，否则跳过该手的控制命令。写应答仅表示命令回显已收到，实际运动结果应查看后续状态。

## 报文和 CRC

全部使用扩展帧、CAN FD、BRS 开启。ID 格式为：

```text
CAN ID = (slave_id << 16) | (master_id << 8) | logical_length
```

SocketCAN 的扩展帧标志由脚本单独设置，不算入这里显示的 29 位 CAN ID。数据中多字节寄存器采用大端；应用层 CRC16 使用 Modbus 算法，初始值 `0xFFFF`、反向多项式 `0xA001`，低字节先发。

| 项目 | 功能码 | 起始寄存器 | 数量 |
| --- | --- | --- | --- |
| SN | `0x04` | 3010 / `0x0BC2` | 10 |
| 固件版本 | `0x04` | 3000 / `0x0BB8` | 10 |
| 左右手 SKU | `0x03` | 901 / `0x0385` | 1 |
| 位置、速度 | `0x04` | 2000 / `0x07D0` | 12 |
| 电流、马达状态 | `0x04` | 2012 / `0x07DC` | 12 |
| 完整马达状态 | `0x04` | 2000 / `0x07D0` | 24 |
| 六通道百分比位置 | `0x10` | 1070 / `0x042E` | 3 |

SKU 值 1、3 对应右手，2、4 对应左手；从站地址本身不决定左右手。SN、固件版本按返回字节序解码为 ASCII。马达数据记录原始寄存器值：位置为无符号，速度、电流解读为有符号 16 位数，马达状态保留原值；不额外缩放或推断当前单位模式。

12 寄存器读应答的逻辑长度为 29 字节：前 27 字节参与 CRC16，第 28、29 字节存放 CRC16。24 寄存器应答对应 53 字节：前 51 字节参与 CRC16，第 52、53 字节为 CRC16。实际 CAN FD 数据可能更长，末尾补零不参与应用层 CRC16。它与 CAN FD 控制器自行处理的链路层 CRC 是两层校验。

完整请求、预期应答 ID、应答格式示例和控制回显格式见 [frame_reference.txt](frame_reference.txt)。文件中的应答数据为按协议构造的示例，不是真机抓包。实际状态、SN、固件数据及其 CRC 随设备变化，不应直接拿示例应答替代设备应答。

## 发回哪些结果

每次运行会创建独立的 `canfd-direct-时间` 目录：

- `frames.jsonl`：完整请求与接收数据、软件事务序号、CAN ID、FD/BRS/ESI、逻辑和实际长度、补齐字节、报文携带与独立重算的 CRC16、解析结果及超时。
- `summary.json`：收发、有效/无效应答、超时统计和结束时的 `can0` 状态。

请发回整个结果目录；若另开了 `candump`，同时发回 `can-capture.log`。脚本记录 UTC 和主机单调时钟，时间戳取自主机处理时刻，不是控制器硬件时间戳。

排查顺序：

1. 脚本与 `candump` 同一应答均 CRC 不匹配：应答数据在原始 `can0` 接收路径中已不一致，继续对照总线旁路抓包，区分手端发送与 CAN 控制器、驱动接收环节。
2. 两处原始字节不同：核对是否确实是同一应答，以及是否还有其他主动发包程序，再查接收、复制或缓存环节。
3. 原始报文 CRC 正确、ROS 报错：对照 ROS 实际使用的完整应答、逻辑长度、CRC 取值位置和请求匹配。

协议没有事务序号，同一主从、相同功能码和长度的延迟应答无法仅靠这几个字段证明归属。脚本会记录并排出发送前已排队的帧，仍需要独占主动收发来减少混淆。异常 CRC、截短、异常码和应答头不匹配分别记录；不能只看终端最后一行判断根因。

## 离线检查

仅打印拟发送报文，任何平台均可运行：

```bash
python3 canfd_direct.py --slaves 126,127 --dry-run
```

离线检查不能替代目标 Linux 设备上的 SocketCAN 实机运行。张合指令需要在现场确认实际动作及状态回读。
