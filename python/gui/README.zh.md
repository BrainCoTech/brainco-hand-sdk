# Stark SDK GUI (图形界面工具)

> ⚠️ **注意**: 本工具仅供**调试与开发**使用。如果需要在稳定的生产环境或追求更好的用户体验，请使用官方的 [BrainCo RevoHand Software](https://www.brainco-hz.com/docs/revolimb-hand/index.html)。

用于控制和监控 Stark 灵巧手设备的统一图形界面工具。

## 功能介绍

### 支持的协议
- ✅ Modbus/RS485
- ✅ CAN 2.0 (ZQWL)
- ✅ CANFD (ZQWL)
- ✅ SocketCAN (仅 Linux，通过自动检测支持)
- ✅ EtherCAT (仅 Linux，手动连接)

### 支持的设备
- Revo1 基础版 (Basic) / 触觉版 (Touch) / 进阶版 (Advanced) / 进阶触觉版 (AdvancedTouch)
- Revo2 基础版 (Basic) / 电容触觉版 (Touch) / 模量触觉版 (TouchPressure)

### 语言支持
- English (默认)
- 中文

切换语言：菜单栏 → Language → 切换至目标语言

### 核心功能

#### 1. 连接管理
- 多协议支持（Modbus、CAN、CANFD、SocketCAN）
- 自动检测设备（同时支持 Linux 下的 SocketCAN 协议自动检测）
- CAN 总线扫描（CAN 节点号: 1, 2 / CANFD 节点号: 0x7E, 0x7F）
- 实时连接状态监控

#### 2. 电机控制 (Motor Control)
- 位置控制模式 (Position control)
- 速度控制模式 (Speed control)
- 电流/力矩控制模式 (Torque control)
- 单指独立控制
- 全局控制（全开 / 全关 / 急停）
- 实时状态面板显示

#### 3. 触觉传感器 (Touch Sensor)
- 开启/关闭独立手指的触觉传感器
- 传感器校准
- 传感器复位
- 实时触觉数据展示：
  - 法向力 (Normal force)
  - 剪切向力/摩擦力 (Tangential force)
  - 接近感应距 (Proximity)
  - 传感器工作状态指示
- 提供直观的 5指 数据实时曲线图

##### 🔎 3D 力与力矩可视化指南 (专为 Revo2 Force 阵列传感器设计)
对于支持 3D 力觉和力矩阵列的高级传感器（例如 ArrayPressure），GUI 用了一个极具几何美感的 **2D 雷达矢量罗盘** 彻底替代了传统的波形图，以此建立极度直觉的物理感知：
1. **法向力 (`Fz`)**: 由**罗盘中心彩色气泡的直径大小**表示。手指受到的正向按压力量越大，气泡膨胀得越大。
2. **剪切/摩擦力 (`Fx`, `Fy`)**: 由**动态的白色高亮箭头**表示。该箭头会精确指向物品滑动物理摩擦的方向，其伸长的距离直接映射了剪切合力的绝对大小 ($\sqrt{Fx^2 + Fy^2}$)。
3. **扭转力矩 (`Mx`, `My`)**: 由**图表下半区较小雷达上的橙黄色圆点**表示。它等效于压力中心 (CoP) 偏移量——当你抓握物体时，如果物体不均匀地压在传感器边缘而形成跷跷板式的扭转，中心小黄点就会立刻飞向偏载的那一侧边缘，成为绝佳的失稳告警雷达。

#### 4. 数据采集 (Data Collection)
- 可配置的采集频率 (1-1000 Hz)
- 可配置的采集时长
- 支持的数据流：
  - 电机状态流（位置、速度、电流）
  - 触觉信号流（压力、接近距离）
- 一键导出 CSV
- 实时数据流监控

#### 5. 动作序列 (Action Sequence)
- 预置快捷动作（握拳、张开、捏合、点指等）
- 用户自定义动作序列录制
- 支持以 JSON 导入/导出
- 支持直接刷入设备内部快捷插槽
- 点击播放/停止预览

#### 6. 实时波形监控 (Realtime Monitor)
- 波形图示 (支持显示 位置、速度、电流、触觉信号)
- 虚拟手 3D 映射效果
- 可调监控窗口期 (5秒-60秒)
- 可调界面刷新率 (10-100Hz)
- 链路质量统计（刷新率统计、延迟度量、丢包与异常捕捉）

#### 7. DFU 固件升级 (NEW)
- 一键选择固件文件
- 自动识别所需升级的手部型号
- 固件兼容性预警
- 进度条可视化
- 刷机日志显示

#### 8. 系统配置 (System Config)
- 查看设备详细硬件参数
- 动态更改总线节点 (Slave ID)
- 从机软重启
- 一键恢复出厂设置

## ID (节点号) 寻址参考

### CAN 2.0 协议
- 默认 ID: 1 (左手), 2 (右手)
- 快速扫描配置: [1, 2]

### CANFD 协议
- 默认 ID: 0x7E 即 126 (左手), 0x7F 即 127 (右手)
- 快速扫描配置: [0x7E, 0x7F]

### SocketCAN (Linux 平台)
- 物理 ID 寻址与上方的 CAN 2.0 / CANFD 保持完全一致

### EtherCAT (Linux 平台)
- 连接界面直接在下拉菜单选中 "EtherCAT"
- 主站位置：通常为 0 (首个主站总线网络)
- 从站位置：基于 0 起始的对应总线硬件索引
- 支持的面板子集：Motor Control、Touch Sensor 以及 Timing Test 测试面板
- **不**支持的面板系统（动作下发、DFU升级及部分设置）将会自动隐藏
- 其它网络工具亦支持通过菜单栏的 Data Collector 挂接测试
- 点击 "Auto Detect" 即可自动识别
- 使用前需提前带起 Linux 网络接口：
  ```bash
  sudo ip link set can0 type can bitrate 1000000
  sudo ip link set can0 up
  ```

### Modbus 协议 (串口版)
- 默认 ID: 1
- 支持通过系统配置面板修改硬件烧录的 ID

## 安装与部署

### 基础依赖安装

```bash
pip install PySide6 bc_stark_sdk
```

或者使用提供的 requirements.txt 文件全量配置：

```bash
pip install -r requirements.txt
```

## 运行使用

### 启动项目

请直接执行下述命令：

```bash
python main.py
```

如果你在上一层（它的父目录）环境，也可以使用包调用启动：

```bash
python -m gui.main
```

### 推荐工作流测试

1. **连接硬件 (Connect Device)**
   - 选好对应的串口协议或总线 (Modbus/RS485 等)
   - 配置相关的参数（串口路径、波特率、节点 ID）
   - 单击 "Connect" 连入系统
2. **驱动电机 (Control Motors)**
   - 点击最顶部的 "Motor Control" (电机控制)
   - 选择所需的控制闭环环路（模式位置/速度等）
   - 随心拖动滑块操纵物理手指反馈
   - 点击最上方的快捷功能来感受机械手的全开、全合操作
3. **监控触觉传感器 (View Touch Data)**
   - 点击切换到 "Touch Sensor" (触觉传感器) 选项卡
   - 点击 "Enable Touch" 取消休眠并加电
   - 观测来自真实硅胶指尖的受力图形渲染
4. **日志采集化 (Collect Data)**
   - 点击切换到 "Data Collection" (数据收集)
   - 设定采集相关的帧率（频率）、采集总时间甚至保存路径
   - 选择你需要观察的数据通道组合
   - 开启录制大门 "Start Collection"
5. **硬件配置管理 (System Configuration)**
   - 点击切换到 "System Config"
   - 系统会自动下发查询并吐出所有硬件元信息
   - 在此安全调节底层参数

## 开发者视角

### 文件与模块工程架构

```
gui/
├── __init__.py                 # 包初始化配置
├── main.py                     # 全局核心启动入口
├── main_window.py              # 顶层窗口窗体
├── i18n.py                     # 国际化语言支持包
├── styles.py                   # UI QSS 样式常量表
├── connection_panel.py         # 连接面板业务 (支持一键检测和 CAN 嗅探扫描)
├── motor_control_panel.py      # 电机驱动主板
├── touch_sensor_panel.py       # 触觉核心面板 (可视化与波形)
├── data_collector_panel.py     # 数据集采集业务
├── action_sequence_panel.py    # 动作宏录制面板
├── timing_test_panel.py        # 延迟与压力吞吐测试面板
├── realtime_monitor_panel.py   # 实时监控台 (动态全局高频波形显示)
├── hand_visualization.py       # OpenGL/3D GUI 手部虚拟映射工具
├── dfu_panel.py                # DFU 固件全自动升级模块 (NEW)
├── system_config_panel.py      # 硬件元系统控制面板
├── mock_touch_gui.py           # 离线伪造数据（独立脱网压测仪）测试专用程序
├── README.md                   # 英文说明文档
├── README.zh.md                # 也就是阁下正在阅读的这份本尊文档
└── requirements.txt            # 系统所必需的三方组件包
```

### 快速增加自定义国际化化翻译

你仅需在 `i18n.py` 补充对应的字典翻译即可：

```python
TRANSLATIONS_XX = {
    "app_title": "你自己的语言映射",
    # ... 在这里追加全部的 Key 
}
```

随后至 `I18n.__init__` 中注册生效该语言：

```python
self._translations = {
    "en": TRANSLATIONS_EN,
    "zh": TRANSLATIONS_ZH,
    "xx": TRANSLATIONS_XX  # <-- 直接加在这里
}
```

### 追加或扩展开发者自己的调试面板

如果你想要增加一套新面板（例如加入一套 AI 预测控制台）：
1. 创建并封装一个新的针对 `QWidget` 的基础类
2. 继承并复写核心设备注入事件： `set_device(device, slave_id, device_info)`
3. 加入标准 `update_texts()` 方法拥抱全球化的动态语种切换系统
4. 直接把它安插到 `main_window.py` 中央窗体的容器堆栈当中

## 答疑与故障排查

### 无法接通底层设备？

1. 首先请检查系统对于 TTY / 波特核心驱动的占有权（以 Linux 为例）：
   ```bash
   sudo chmod 666 /dev/ttyUSB0
   ```

2. 侦测是否有其他驻留的后门进程/监控器霸占了端口资源：
   ```bash
   lsof /dev/ttyUSB0
   ```

3. 验证一下是否正确安装了底层 C 驱动：
   ```bash
   python -c "import bc_stark_sdk; print(bc_stark_sdk.__version__)"
   ```

### 为什么双击没反应，跑不起来 GUI 面板？

1. 查验 PySide6 渲染框架是否成功就绪：
   ```bash
   python -c "import PySide6; print(PySide6.__version__)"
   ```

2. 判断系统 Python 释出版本 (我们要求的绝杀红线是 3.8 或以上):
   ```bash
   python --version
   ```

## 许可证支持

© 2026 BrainCo. 保留所有最终解释权。
