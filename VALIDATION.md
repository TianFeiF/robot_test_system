# 验收记录

日期：2026-09-16，Ubuntu 22.04.5 / Python 3.10.12 / ROS 2 Humble。

完成 P0 构建和运行验收后才加入 P1，未开展 P2 系统监控或 UI 美化。所有检查均使用软件 Mock，没有连接真实机器人。

## 实际执行

- 分阶段执行 `colcon build --symlink-install`，6 个 ROS 包均构建成功。
- 5 个安全单元测试通过：500 ms 精确边界、STOP 解除使能、非法速度/故障、逐轴 watchdog、可选设备异常隔离、STOP 失败仍尝试 disable 并继续停止其他轴（部分用例包含多项断言）。
- 完整验收通过 30 个检查点，使用真正的 A/B ROS 子进程、rclpy Ground Bridge、PySide6 控件和桌面 xcb 平台。详见 [完整结果](logs/full_results.txt)。
- 最后整理 Factory 为“电机继承所属总线 backend”后，额外检查 CANopen real 配置仅切换支撑轴，EtherCAT 轴仍保持 mock；P0 8 项回归再次通过。详见 [最终 P0 回归](logs/p0_results.txt)。

## 完整验收覆盖

A/B ONLINE、Heartbeat 和 Diagnostics；按住 JOG 位置增长、松手停车；丢失指令本地 watchdog 停车；STOP ALL 与残留 JOG 拦截；A 退出约 3 秒 OFFLINE、B 不受影响、A 重启自动恢复；两路持续相机预览；默认 ±1.0 目标 / 0.1 速度 / 1 秒停留的正反循环；STOP 打断 Auto、Auto 保活断流停车、双 Auto 的 STOP ALL；camera、EtherCAT、motor、RS485、CANopen、network 故障恢复；Heartbeat Drop 和恢复；相机重连累计计数；三端事件 ID/时间戳一致；三端状态 CSV 有记录。

最后完整验收中，从停止发送 JOG 到 Ground 从 Diagnostics 观察到零速度为 **0.591 秒**，包括 5 Hz Diagnostics 的观测延迟；最终 P0 回归为 **0.592 秒**。控制器单元测试验证 0.499 秒仍运动、0.500 秒停止。该值不是硬实时保证。

完整验收截图：[地面站截图](logs/full_ground.png)。完整验收 CSV 位于 `logs/final_acceptance/`；最终 P0 回归位于 `logs/factory_regression/`。

## 发现并修复的问题

- rclpy Node 已有只读 publishers 属性：重命名为 jog_publishers / service_clients。
- Humble DiagnosticStatus.level 是单字节 bytes：发布和接收端按 bytes 正确处理。
- 缺少 PySide6 和 libxcb-cursor0：仅安装或解压到项目目录。
- 用户级 NumPy 2 与系统 OpenCV ABI 不兼容：项目启动时设置 PYTHONNOUSERSITE=1，使用系统 NumPy 1.21.5 和 OpenCV 4.5.4；不修改用户已有安装。故障期间仍实际通过 P0 控制回归。

## 边界

真实驱动尚未实现，real Adapter 为明确报错的预留接口。软件 STOP 不等于硬件急停。累计计数在进程重启时重置，CSV 追加保留。事件不补发给离线机器人。跨设备时间同步和真实驱动器独立保护需现场实现与验证。GUI、日志和 DDS 在这台笔记本已验证，未进行 EMC / 5G / 多机或长时间稳定性实测。

## 多相机更新验收（2026-09-16）

- 更新为 YAML 顶层 cameras 清单，默认 A=5 路、B=3 路；A 第五路可独立禁用。
- 6 个 ROS 包重新构建成功，7 个单元测试通过。
- A=5/B=3：36 项运行检查通过，覆盖全部 8 路真实 ROS 图像和 Qt 预览、逐路 Diagnostics、单路故障隔离/恢复及完整 P0/P1 回归。结果：[8 路验收](logs/multicamera_8_results.txt)。
- A=4/B=3：临时 YAML 禁用第五路，14 项运行检查通过，确认只创建 7 路设备和预览，故障隔离、JOG、Watchdog、STOP ALL、离线恢复正常。结果：[7 路验收](logs/multicamera_7_results.txt)。默认 YAML 未被测试修改。
- 截图：[A5/B3](logs/multicamera_8_ground.png)、[A4/B3](logs/multicamera_7_ground.png)。
- 最新接口为 `/robot_a/cameras/camera_1/image_raw` 等各路独立 topic；上面的双路相机记录是初版历史验收。

## 1920×1080 全屏布局与文档更新（2026-09-17）

- 8 路相机改为同排显示；全部当前设备行可见，Position / Velocity 独立列，按设备类型显示带名称的关键计数。历史日志保留滚动，完整原始诊断值可在提示和 CSV 查阅。
- 在严格 1920×1080 Qt 窗口尺寸下，实际启动 A/B ROS 子进程和 8 路相机。检查窗口尺寸、各相机/控制组件边界、两表横纵滚动范围为零、表格文字宽度无省略。截图：[1920×1080 布局](logs/dashboard_1920x1080.png)。
- 包含布局检查的完整回归 37 项通过；7 个安全/相机单元测试通过。完整运行输出仍在 `logs/multicamera_8_results.txt`，日志目录 `logs/fullscreen_acceptance/`。
- 测试机器物理桌面为 2560×1600、Qt DPR=1；未修改系统显示设置。1920×1080 验证使用精确窗口画布，桌面全屏和 F11/Esc 另行验证。
- 新增 `docs/使用指南.md`、`docs/后续配置指南.md`。主目录原开发提示词用 Markdown 删除线标记已完成项，原文备份在 `docs/reference/原开发提示词_完成标记前.md`；去除新增说明和删除线后与备份逐字一致。
