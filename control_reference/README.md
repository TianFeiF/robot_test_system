# 双机器人控制台开发资料包

整理日期：2026-10-28。来源：地面站当前工作树，包含尚未提交的真实硬件修复；具体提交和取证范围见 [provenance.json](provenance.json)。

本目录可以独立复制，保存原始驱动、ROS 接口、现场配置、构建脚本、回归测试及历史资料。它是后续控制台开发的可追溯基础，尚不是新的控制台应用，也不包含完整离线 SDK/运行环境。

## 阅读顺序

1. [硬件、轴参数与当前状态](docs/01_hardware.md)：A/B 设备、IP、控制模式、单位、方向、临时停用轴。
2. [驱动实现与源码地图](docs/02_drivers.md)：EtherCAT、CANopen、RGB、雷达、机械臂、RS485；关键逻辑和已有实现的边界。
3. [地面站控制接口](docs/03_control_api.md)：ROS topic/service、命令时序、状态反馈、回零和停止语义。
4. [部署与离线依赖](docs/04_deployment.md)：启动入口、SDK、路径差异、校时、构建与现场待补资料。
5. [控制台开发拆分方案](docs/05_console_plan.md)：复用层、测试层、新控制台模块及分阶段验证。
6. [资料核验记录](docs/06_validation.md)：归档完整性与模拟测试结果，区分现场验证和本地核验。

## 文件组织

- `baseline/native/`：Eyou EtherCAT/CANopen 原生驱动与安全逻辑，以及历史 IgH 实现。
- `baseline/ros2_ws/src/`：六个 ROS 包完整保留，包含真实适配器、Mock、Agent 和旧 Qt 地面站；保持导入依赖闭合。
- `baseline/config/`：A/B 控制与监控配置、地面站双机配置、DDS、Livox JSON。
- `baseline/scripts/`：启动、构建、校时、维护脚本及 RM75/Livox/深度辅助程序源码。
- `baseline/tests/`：控制、相机、时钟、原生驱动模拟等回归资料。
- `baseline/docs/`、`baseline/README.md`、`baseline/VALIDATION.md`：原始历史记录，保留原文，不代表全部内容仍是当前状态。
- `hardware_inventory.json`：从本次 A/B 控制 YAML 导出的机器可读清单；`test_profile_only` 是测试配置，不能当作控制台默认动作。
- `manifest.json`：归档文件 SHA-256、大小与符号链接目标；`tools/verify_bundle.py` 可离线校验。

```bash
python3 tools/verify_bundle.py
```

以上命令在本目录内执行，只校验文件，不连接机器人，也不启动驱动。`baseline` 保留原目录结构；新控制台应在另一开发目录复用源码，不直接修改这份基线。

## 当前需要记住的事实

- A：`192.168.10.3`，B：`192.168.10.63`；地面站校时脚本使用 `192.168.10.4`，是脚本配置值，非本次网络实测。
- 真实驱动已实现；名为 `robot_mock_hardware` 的包也包含真正的 `real_adapters`。旧说明中的“real 未实现”仅指通用占位后端。
- A/B drive 自动循环已关闭；A Z 轴因同步带问题暂停自动循环。A Z 手动和回零接口仍在，并未做全局禁用。
- 夹持轴 ±400，B 支撑轴 ±800，均为驱动器原始力矩命令，未标定为 N·m 或 N。
- 当前两台机器人 SSH 均返回 `No route to host`；本次没有拉取现场 SDK、动态库、最新标定值，也没有更改机器人或操作电机。
- `baseline` 中绝对路径和回零值是本地快照；不能直接整目录覆盖机器人配置。接入前应拉取现场配置比对。

历史开发提示词保存在 `baseline/docs/`，只作为资料，不作为未来开发指令。新需求以用户后续明确要求为准。
