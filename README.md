# BrainCo RevoHand SDK Examples

[![Version](https://img.shields.io/badge/version-v2.0.2-blue.svg)](VERSION)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)]()

[English](README.md) | [中文](README.zh.md)

This repository provides comprehensive SDK examples for BrainCo RevoHand devices, including both Revo1 and Revo2 series. It contains ready-to-use code samples in C++ and Python to help developers quickly integrate and control the dexterous robotic hand.

## 📖 Official Documentation

For detailed technical specifications and API references, visit: [BrainCo RevoHand Documentation](https://www.brainco-hz.com/docs/revolimb-hand/index.html)

## 🚀 Quick Start

### System Requirements

- **Python**: 3.8 ~ 3.12
- **Linux**: Ubuntu 20.04/22.04 LTS (x86_64/aarch64), glibc ≥ 2.31
- **macOS**: 10.15+
- **Windows**: 10/11

### Installation

1. Clone this repository:
```bash
git clone https://github.com/BrainCoTech/brainco-hand-sdk.git
cd brainco-hand-sdk
```

2. For Python development:
```bash
cd python
pip3 install -r requirements.txt
```

3. For C++ development on Linux:
```bash
# Download required libraries
./download-lib.sh
```

## 📚 Examples by Platform

### Python Examples

Python development examples support multiple communication protocols:
- **Revo1**: RS-485, CAN
- **Revo2**: RS-485, CANFD, EtherCAT

For detailed instructions: [Python Development Guide](python/README.md)

### C++ Examples (Cross-platform)

Cross-platform C++ development examples supporting Linux, macOS, and Windows:
- **Revo1**: RS-485, CAN
- **Revo2**: RS-485, CAN, CANFD, EtherCAT

For detailed instructions: [C++ Development Guide](c/README.md)

> 💡 The C++ demos in `c/demo/` correspond to the Python demos in `python/` - both provide equivalent functionality for device control, monitoring, and firmware upgrade.

### Legacy C++ Examples (Archived)

> ⚠️ **Archived**: The `linux/` and `windows/` folders have been moved to the `archive/` directory. Please use the unified `c/` folder for cross-platform C++ development.

- [Linux Examples (Archived)](archive/linux/) - Legacy Linux-specific examples, moved to archive
- [Windows Examples (Archived)](archive/windows/) - Legacy Windows-specific examples, moved to archive

## 🔌 Supported Communication Protocols

| Device | RS-485 | Protobuf | CAN | CANFD | EtherCAT |
|--------|--------|----------|-----|-------|----------|
| Revo1  | ✅     | ✅       | ✅  | ❌    | ❌       |
| Revo2  | ✅     | ❌       | ✅  | ✅    | ✅       |

## 📁 Repository Structure

```
.
├── c/                   # ⭐ Cross-platform C++ examples (recommended)
│   ├── demo/           # Main demos (hand_demo, hand_monitor, hand_dfu)
│   ├── common/         # Shared code library
│   └── platform/       # Platform-specific code
├── python/              # Python examples and SDK
│   ├── demo/           # ⭐ Unified demos (hand_demo, hand_monitor, hand_dfu)
│   ├── gui/            # GUI debugging tool
│   ├── revo1/          # Revo1 RS-485 examples
│   ├── revo1_can/      # Revo1 CAN examples
│   ├── revo2/          # Revo2 RS-485 examples
│   ├── revo2_can/      # Revo2 CAN examples
│   ├── revo2_canfd/    # Revo2 CANFD examples
│   ├── revo2_ethercat/ # Revo2 EtherCAT examples
│   └── revo2_tactile_grasp/ # Revo2 tactile grasping examples
├── archive/            # ⚠️ Archived legacy examples (linux/ and windows/)
├── dll/                # Required DLL files for Windows
└── dist/               # Distribution files

```

> ⚠️ **Archived Notice**: The `linux/` and `windows/` folders are obsolete and have been moved to the `archive/` folder. Please use the unified `c/` folder for cross-platform C++ development.

## 🛠️ Development

### Building C++ Examples

Refer to the [C++ Development Guide](c/README.md) for detailed compilation instructions.

### Running Python Examples

Each example directory contains its own README with specific usage instructions.

See [CHANGELOG](CHANGELOG.md) for update history.

## 🌐 Open Source & Ecosystem Resources

- 🤖 **BrainCo Open Source Hub**: [BrainCoTech GitHub Organization](https://github.com/BrainCoTech) - Discover latest firmware updates, URDF models, and ecosystem integrations
- 📖 **Official Documentation**: [BrainCo Dexterous Hand Docs](https://www.brainco-hz.com/docs/revolimb-hand/index.html)
- 💽 **Firmware Releases**: [revo-hand-firmware](https://github.com/BrainCoTech/revo-hand-firmware) - Official firmware variants for Revo devices
- 🦾 **ROS / ROS 2 Integration**:
  - [brainco_hand_ros2](https://github.com/BrainCoTech/brainco_hand_ros2) - Official ROS 2 Driver
  - [ros2_control_demos](https://github.com/BrainCoTech/ros2_control_demos) - ROS 2 Control integration examples
  - URDF Models: [ROS 2](https://github.com/BrainCoTech/revo2_description) | [ROS 1](https://github.com/BrainCoTech/revo2_description_ros1)
- 🎮 **Simulation**:
  - [BrainCo Isaac Lab (RevoLab)](https://github.com/BrainCoTech/RevoLab) - Reinforcement learning environments built upon NVIDIA Isaac Lab
- 🌐 **Ecosystem App Guides**:
  - [Unitree G1 Humanoid Integration](https://github.com/BrainCoTech/unitree-g1-brainco-hand)
  - [6-DoF Robot Arm Integration](https://www.brainco-hz.com/docs/revolimb-hand/ecology/mechanical_revo2.html)
  - [Teleoperation via EMG & Data Gloves](https://www.brainco-hz.com/docs/revolimb-hand/ecology/arm.html)

## 🤝 Support

Need help? Reach out to us through the following channels:

- 📋 **Submit a ticket**: [https://web.static.brainco.cn/work-order](https://web.static.brainco.cn/work-order)
- 🐙 **GitHub**: [https://github.com/BrainCoTech](https://github.com/BrainCoTech)
- 💡 **References**: Check the example code in subdirectories and review the API documentation above
- 💬 **Direct Support**: Contact the BrainCo technical support team

## 📄 License

Copyright © BrainCo Technology. All rights reserved.

---

**Note**: This SDK is provided for development and integration purposes. Please ensure you have the necessary hardware and permissions before use.
