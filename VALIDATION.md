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

## 笔记本 UVC 摄像头（2026-09-17）

- 实际识别设备：USB2.0 FHD UVC WebCam，彩色入口 `/dev/video0`。
- UVCCameraAdapter 实际读取 8 帧 640×480×3 图像，状态 OK，约 5 FPS，失败计数 0；测试只输出尺寸/计数，不保存照片或录像。
- 一路 UVC + 七路 Mock 的 ROS/Qt 验收 16 项通过，含真实取图、ROS 预览、JOG、松手停车、Watchdog、STOP ALL、A 退出/重启、Mock 单路故障隔离。结果：`logs/uvc_results.txt`，CSV：`logs/laptop_uvc_acceptance/`。测试未保存含真实画面的截图，结束后释放摄像头。
- 10 个单元测试通过，新增 UVC 读失败重连、无设备失败隔离、取图阻塞时诊断/断开不阻塞。
- 入口：`scripts/start_laptop_camera_demo.sh`，仅使用临时配置，不更改默认 Mock YAML。说明见 `docs/笔记本摄像头测试.md`。
- 尚未做外接 USB 摄像头实际拔插及 20～30 分钟长期稳定性试验；这两项不能用短时读取成功替代。

## A/B LiDAR Mock 状态补齐（2026-09-17）

- 新增独立 MockLidarAdapter，A/B hardware.lidar 各一台；暂不猜测型号对应关系，model 为待确认。
- 按模拟时间累积扫描、点、包计数，支持掉线/恢复、错误/丢包/重连计数；仅发布 Diagnostics 与 CSV，不发布点云。
- 相关 3 个包实际 build 成功，11 个单元测试通过。43 项运行验收通过，含两台雷达计数增长、故障变红与计数停止、恢复/重连，以及原 P0/P1 和 1920×1080 无裁切检查。
- 结果：`logs/lidar_results.txt`；截图：`logs/lidar_1920x1080.png`；CSV：`logs/lidar_acceptance/`。
- 真实雷达驱动/点云尚未接入；模拟 packet/drop 数不能用来反推网桥实际吞吐。带宽估算及官方来源见 `docs/无线网桥与雷达预算.md`。
## Robot A 现场 RGB 与启动配置更新（2026-09-19）

- 真实网络对照：44/23/24 KB 的三路 5 Hz 测试消息，默认 DDS 下最长间隔 8.2 秒；
  UDP `maxMessageSize=1400` 后最长 0.21 秒，无超过 2 秒的间隔。保留 SHM，未修改系统网络参数。
- 第一轮真实相机验收发现 S-YUE 相机名称未被旧选择器匹配，故该轮三路验收失败；
  更新 site/control 中 USB 名称匹配与当前端口路径后重测通过。
- 60 秒真实 RGB 验收：成功解码 300/289/300 帧，最大间隔 0.214/0.404/0.215 秒；
  解码错误 0，超过两秒间隔 0。测试配置不包含电机或其他硬件。
- 使用新 DDS 配置的隔离 domain 86 Mock P0 ROS/Qt 回归通过，包括三端通信、多相机故障恢复、
  JOG 释放停车、Watchdog、STOP ALL、机器人断线/重连；这不是实机运动验收。
- Shell 语法检查、XML 解析及 `git diff --check` 通过。
- 机器人复查旧 `ros2_robot.service` 为 `LoadState=not-found`、inactive。
- 结果位于 `logs/rgb_mtu_validation/`，实际 RGB 接收 CSV 位于
  `logs/rgb_mtu_validation_fixed/`。本次为短时验证，不代表长时间或热插拔验收完成。

## Robot B 部署验证（2026-09-19）

- `phi@192.168.10.63:/home/phi/robot_test_system`：5 个 ROS 包构建成功；B 的 CAN 与两个支撑轴未加载。
- 三路 RGB 60 秒跨机解码 300/289/300 帧，最长间隔 0.405 秒，无解码错误或超过两秒间隔。
- MID360s `192.168.10.73`：约 20 万点/秒、200 IMU 包/秒，命令错误计数 0。
- 初始 EtherCAT 权限不足，经操作者授权配置 `cap_net_raw` 后，旧 20250807 SDK 仍报状态切换失败。
  在项目私有目录部署 20260109 SDK 并重新编译后，四从站均 OP，PDO 反馈正常，API/时序错误 0。
- 最终只读 ROS/Qt 集成检查通过：B 在线、三路预览、雷达、EtherCAT 正常；CAN/支撑轴不存在于设备列表。
  四轴均未使能，未执行运动或找零。截图时 A 不在线，未操作 A 的运行状态。
- 当前 B 保留临时用户监控服务运行，未设置开机自启；SDK 实时调度权限警告仍存在，运动实时性未验收。
- 结果：`logs/robot_b_deploy_validation/{rgb.json,final_status.json,dual_monitor.png}`。
