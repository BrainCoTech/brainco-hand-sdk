# BrainCo 灵巧手 SDK 开发示例

[![版本](https://img.shields.io/badge/版本-v2.0.2-blue.svg)](VERSION)
[![许可证](https://img.shields.io/badge/许可证-专有-red.svg)]()

[English](README.md) | [中文](README.zh.md)

本仓库提供了 BrainCo 灵巧手设备（包括 Revo1 和 Revo2 系列）的完整 SDK 开发示例。包含 C++ 和 Python 的即用代码示例，帮助开发者快速集成和控制灵巧机械手。

## 📖 官方文档

详细的技术规格和 API 参考文档，请访问：[BrainCo 灵巧手开发文档](https://www.brainco-hz.com/docs/revolimb-hand/index.html)

## 🚀 快速开始

### 系统要求

- **Python**：3.8 ~ 3.12
- **Linux**：Ubuntu 20.04/22.04 LTS (x86_64/aarch64), glibc ≥ 2.31
- **macOS**：10.15+
- **Windows**：10/11

### 安装步骤

1. 克隆本仓库：
```bash
git clone https://github.com/BrainCoTech/brainco-hand-sdk.git
cd brainco-hand-sdk
```

2. Python 开发环境配置：
```bash
cd python
pip3 install -r requirements.txt
```

3. Linux C++ 开发环境配置：
```bash
# 下载所需的库文件
./download-lib.sh
```

## 📚 平台示例

### Python 示例

Python 开发示例支持多种通信协议：
- **Revo1**：RS-485、CAN
- **Revo2**：RS-485、CANFD、EtherCAT

详细说明请参考：[Python 开发指南](python/README.md)

### C++ 示例（跨平台）

跨平台 C++ 开发示例，支持 Linux、macOS 和 Windows：
- **Revo1**：RS-485、CAN
- **Revo2**：RS-485、CAN、CANFD、EtherCAT

详细说明请参考：[C++ 开发指南](c/README.md)

> 💡 `c/demo/` 目录下的 C++ 演示程序与 `python/` 目录下的 Python 示例功能对应，两者提供等效的设备控制、监控和固件升级功能。

### 旧版 C++ 示例（已存档）

> ⚠️ **已存档**：`linux/` 和 `windows/` 文件夹已弃用并移动到 `archive/` 目录中。请迁移至统一的 `c/` 文件夹。

- [Linux 示例 (已存档)](archive/linux/) - 旧版 Linux 专用示例，已归档
- [Windows 示例 (已存档)](archive/windows/) - 旧版 Windows 专用示例，已归档

## 🔌 支持的通信协议

| 设备型号 | RS-485 | Protobuf | CAN | CANFD | EtherCAT |
|---------|--------|----------|-----|-------|----------|
| Revo1   | ✅     | ✅       | ✅  | ❌    | ❌       |
| Revo2   | ✅     | ❌       | ✅  | ✅    | ✅       |

## 📁 仓库结构

```
.
├── c/                   # ⭐ 跨平台 C++ 示例（推荐）
│   ├── demo/           # 主要演示程序（hand_demo、hand_monitor、hand_dfu）
│   ├── common/         # 共享代码库
│   └── platform/       # 平台特定代码
├── python/             # Python 示例和 SDK
│   ├── demo/           # ⭐ 统一演示程序（hand_demo、hand_monitor、hand_dfu）
│   ├── gui/            # GUI 调试工具
│   ├── revo1/          # Revo1 RS-485 示例
│   ├── revo1_can/      # Revo1 CAN 示例
│   ├── revo2/          # Revo2 RS-485 示例
│   ├── revo2_can/      # Revo2 CAN 示例
│   ├── revo2_canfd/    # Revo2 CANFD 示例
│   ├── revo2_ethercat/ # Revo2 EtherCAT 示例
│   └── revo2_tactile_grasp/ # Revo2 触觉抓取示例
├── archive/            # ⚠️ 已归档的旧版示例（linux/ 和 windows/）
├── dll/                # Windows 所需的 DLL 文件
└── dist/               # 发布文件

```

> ⚠️ **归档通知**：`linux/` 和 `windows/` 文件夹已过时并被移动到 `archive/` 文件夹。请使用统一的 `c/` 文件夹进行跨平台 C++ 开发。

## 🛠️ 开发指南

### 编译 C++ 示例

详细的编译说明请参考 [C++ 开发指南](c/README.md)。

### 运行 Python 示例

每个示例目录都包含独立的 README 文件，提供具体的使用说明。

更新历史请查看 [CHANGELOG](CHANGELOG.md) 文件。

## 🌐 开源与生态资源

- 🤖 **BrainCo 官方开源主页**: [BrainCoTech GitHub Organization](https://github.com/BrainCoTech) - 获取最新的固件、URDF 模型及生态应用项目
- 📖 **官方文档**: [BrainCo 灵巧手官方开发文档](https://www.brainco-hz.com/docs/revolimb-hand/index.html)
- 💽 **最新固件发布**: [revo-hand-firmware](https://github.com/BrainCoTech/revo-hand-firmware) - 提供适用于各版本灵巧手的稳定版固件
- 🦾 **ROS / ROS2 集成**:
  - [brainco_hand_ros2](https://github.com/BrainCoTech/brainco_hand_ros2) - 针对 ROS 2 提供的控制驱动层
  - [ros2_control_demos](https://github.com/BrainCoTech/ros2_control_demos) - 提供基于 ROS 2 Control 的操作示例
  - [revo2_description (ROS 2)](https://github.com/BrainCoTech/revo2_description) / [(ROS 1)](https://github.com/BrainCoTech/revo2_description_ros1) - 包含用于可视化与仿真的 URDF 描述
- 🎮 **仿真环境**:
  - [BrainCo Isaac Lab (RevoLab)](https://github.com/BrainCoTech/RevoLab) - 基于 NVIDIA Isaac Lab 打造的强化学习仿真环境
- 🌐 **生态联动应用合集 (官网指南)**:
  - [人形机器人 (Unitree G1) 联动方案](https://www.brainco-hz.com/docs/revolimb-hand/ecology/unitree.html) 及 [开源代码](https://github.com/BrainCoTech/unitree-g1-brainco-hand)
  - [协作机械臂 (6自由度) 夹取集成](https://www.brainco-hz.com/docs/revolimb-hand/ecology/mechanical_revo2.html)
  - [各种遥控操作方案 (肌电臂环 / 动捕手套)](https://www.brainco-hz.com/docs/revolimb-hand/ecology/arm.html)

## 🤝 技术支持

遇到问题？可以通过以下渠道获取我们提供的相关技术支持与帮助：

- 📋 **提交工单 (Submit a ticket)**: [https://web.static.brainco.cn/work-order](https://web.static.brainco.cn/work-order)
- 🐙 **GitHub**: [https://github.com/BrainCoTech](https://github.com/BrainCoTech)
- 💡 **参考文档**: 请优先查看子目录中的示例代码或查阅全文 API 文档
- 💬 **人工客服**: 直接联系 BrainCo 官方技术支持团队

## 📄 许可证

版权所有 © BrainCo Technology。保留所有权利。

---

**注意**：本 SDK 仅供开发和集成使用。使用前请确保您拥有必要的硬件设备和使用权限。
