# Revo2 串口读取对照工具

用于在同一台 Linux 主机、同一串口和同一只 Revo2 上，对比原始 Python 串口、原始 C++ 串口与 SDK C++ 的读取耗时。原始两版通过串口直接发送查询字节，不依赖 SDK 或 Modbus 库。

## 使用范围

- 查询电机状态：功能码 `04`、起始寄存器 `2000 / 0x07D0`、24 个寄存器。
- 固定 460800 baud、8N1、无软硬件流控；地址支持 `126`、`127` 或 `126,127`。
- 使用前确认设备型号、寄存器含义、当前波特率及地址与上述条件一致。串口应由当前测试程序单独使用；先结束其他占用该端口的程序。
- Python 需要 PySerial；C++ 使用 Linux POSIX 串口接口，需要在目标主机上编译。已验证 Linux x86_64，Linux ARM 仍需在目标主机上验证。该目录提供源码，SDK 库需另行准备。
- 该工具发送只读查询。`--low-latency` 会尝试修改主机串口驱动的低延迟标志，成功后退出程序不自动回退该标志。

## 文件

| 文件 | 用途 |
|---|---|
| `serial_test_read_speed.py` | Python 原始串口读取 |
| `serial_test_read_speed.cpp` | C++ 原始串口读取 |
| `bench_common.hpp` | C++ 参数解析、统计和 CSV 输出，编译时与 `.cpp` 放在同一目录 |
| `sdk_read_speed.cpp` | 可选 SDK C++ 对照，需要另行准备对应架构的 SDK |
| `requirements.txt` | Python 依赖 |

## Python 原始串口

在本目录中，使用准备好的 Python 环境安装依赖，然后顺序运行。将端口改为实际设备路径，例如 `/dev/ttyAMA0` 或 `/dev/ttyUSB0`。

```bash
python3 -m pip install -r requirements.txt
serial_port=/dev/ttyUSB0
python3 serial_test_read_speed.py "$serial_port" 460800 126 5 python-126.csv --low-latency
python3 serial_test_read_speed.py "$serial_port" 460800 127 5 python-127.csv --low-latency
python3 serial_test_read_speed.py "$serial_port" 460800 126,127 5 python-dual.csv --low-latency
```

参数顺序为 `PORT BAUD SLAVES SECONDS CSV`，测量时间范围为大于 0、最多 60 秒。`126,127` 表示在同一串口连接中交替读取两只手，不能并行启动两个程序占用该端口。

## C++ 原始串口

在目标主机上编译，不需要 SDK 头文件或库：

```bash
g++ -std=c++17 -O2 -Wall -Wextra -Werror serial_test_read_speed.cpp -o serial_test_read_speed
serial_port=/dev/ttyUSB0
./serial_test_read_speed "$serial_port" 460800 126 5 cpp-126.csv --low-latency
./serial_test_read_speed "$serial_port" 460800 127 5 cpp-127.csv --low-latency
./serial_test_read_speed "$serial_port" 460800 126,127 5 cpp-dual.csv --low-latency
```

C++ 的可选 `--low-latency` 放在最后。ARM 主机应编译自己的可执行文件。

## 低延迟设置与读回

原始两版只有指定 `--low-latency` 才尝试设置；省略时保留当前低延迟标志，输出 `requested=0 result=unchanged`。

指定后，程序直接调用 Linux `TIOCGSERIAL` / `TIOCSSERIAL`，启用 `ASYNC_LOW_LATENCY`，再读回 flags。该过程不使用 SDK。输出示例：

```text
LOW_LATENCY requested=1 result=flag_set flags_before=... flags_after=... timer_before_ms=16 timer_after_ms=1
```

- `flag_set`：读回的低延迟标志已置位，可能是本次设置，也可能原本就已开启。
- `get_failed`、`set_failed`、`readback_failed`、`flag_clear`：状态读取、设置或验证未成功，程序打印 `WARN` 后继续尝试读取。请保留告警，并在结果中记录设置状态。
- `timer_before_ms` / `timer_after_ms`：读取 USB 串口驱动提供的 `latency_timer`。FTDI 驱动可能将其切到 1 ms，但以实际读回值为准。
- `unavailable`：没有读到该 sysfs 参数。硬件 UART 通常没有 FTDI 的这个文件，驱动设置结果请查看 `result` 字段。

低延迟设置的效果取决于具体驱动。对比时记录有效设置；若 SDK 打开串口后改变了设置，应在相同设置下重新测原始版本。

## SDK C++ 对照

使用与目标主机架构匹配的 SDK 头文件和动态库。`sdk_dist` 填写 SDK 的 `dist` 绝对路径：

```bash
sdk_dist=/absolute/path/to/sdk/dist
g++ -std=c++17 -O2 -Wall -Wextra -Werror sdk_read_speed.cpp \
  -I "$sdk_dist/include" -L "$sdk_dist/shared/linux" \
  -Wl,-rpath,"$sdk_dist/shared/linux" -lbc_stark_sdk -o sdk_read_speed
ldd ./sdk_read_speed
serial_port=/dev/ttyUSB0
./sdk_read_speed "$serial_port" 460800 126 5 sdk-126.csv
./sdk_read_speed "$serial_port" 460800 127 5 sdk-127.csv
./sdk_read_speed "$serial_port" 460800 126,127 5 sdk-dual.csv
```

确认 `ldd` 中的 SDK 路径符合预期，并记录 SDK 包版本。此程序使用 SDK 自身的串口初始化，不接受原始版的 `--low-latency` 选项。SDK 版本不同，初始化行为也可能不同。

## 地址与响应校验

两只手使用不同的完整请求帧，包括各自的 CRC：

| Slave ID | 请求帧 |
|---|---|
| 126 / 0x7E | `7E 04 07 D0 00 18 FB 42` |
| 127 / 0x7F | `7F 04 07 D0 00 18 FA 93` |

正常响应为 53 字节。原始两版检查响应地址、功能码、字节数及 CRC；C++ 累积处理分段 read/write，Python 通过 PySerial 读取完整响应。启动时每个地址的首次查询最多等 1 秒，输出 `startup_ms`；这允许驱动设置切换后的首个完整响应到达，不重发超时请求。随后预热和正式测量使用约 100 ms 的事务时间边界。遇到超时、短帧或校验错误会停止，避免将残留回复计入后续查询。Modbus RTU 没有事务序号，因此开始测试前还需确保没有其他主站或上次运行遗留的在途请求。

## 结果解读

启动时输出设置状态和首个原始请求/响应。预热后开始计时，测量循环内不打印、不主动 sleep，逐次数据在结束后写入 CSV。最后一行 JSON 包含：

| 字段 | 含义 |
|---|---|
| `successes` / `failures` | 成功事务数和失败数 |
| `rpc_hz` | 所有地址合计的成功查询次数/秒 |
| `per_hand_hz` | 每秒完整轮数；双手交替且零失败时等于每只手的查询频率 |
| `median_ms` / `p95_ms` / `max_ms` | 成功调用的中位、P95 和最大耗时 |
| `timer_before` / `timer_after` | 测量阶段前后的 FTDI 定时器读回值；不同于设置动作之前的值 |

原始实现计时包括请求构造、发送、接收和校验；SDK 对照计时包括状态 API 调用和释放返回数据。它们测的是主机调用耗时，不是单独的设备内部处理时间。统计不含启动同步和预热，启动耗时需另看 `startup_ms`；预热或打开串口失败时程序直接报错，可能不会生成统计 JSON。

若原始两版明显快于 SDK，应核对实际库版本、初始化、读取与调度路径；若三者均慢，应检查共同的驱动、链路和设备条件。若 Python 与 C++ 原始版之间也有明显差异，应先比较串口配置与读取方式。在同机、同设备、同参数下重复运行，确认差异是否稳定。

复测时保留完整终端输出和 CSV，并记录串口、波特率、地址、设备固件、SDK 版本及有效低延迟设置。可用 `2>&1 | tee run.log` 保存输出，确保同时保留 `WARN`。
