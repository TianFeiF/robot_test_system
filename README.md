# Robot Hardware Test System v0.1

ROS 2 Humble 双机器人硬件测试 **Mock Demo**。一台 Ubuntu 22.04 笔记本运行 Robot A、Robot B 和 PySide6 地面站。默认全 Mock；另提供 UVC 摄像头及 Robot A 现场真实监控配置。不是生产控制系统。

Robot A 远程接入进度、启动方式和未完成项见 [现场接入记录](docs/RobotA远程接入记录.md)：USB/D456 彩色和深度预览、MID360s 数据计数、RM75 状态已验证；真实电机控制后端已编译，实机联调因 EtherCAT 通信错误暂停，未完成运动验收。原有 Mock 配置保持独立。

详细文档：[使用指南](docs/使用指南.md) · [后续配置指南](docs/后续配置指南.md)。

只有笔记本也能测试：[笔记本摄像头测试](docs/笔记本摄像头测试.md)，运行 `./scripts/start_laptop_camera_demo.sh`。

## 快速启动（当前机器）

```bash
cd /home/tian/robot_test_system
./scripts/start_mock_demo.sh
```

一条命令启动两个 Agent 和地面站。退出地面站后启动脚本会关闭两个 Agent。需保留桌面会话。不要同时启动多份同 namespace 的 Agent 或多份控制地面站。

单独启动（3 个终端）：

```bash
./scripts/start_robot_a.sh
./scripts/start_robot_b.sh
./scripts/start_ground.sh
```

若分开启动，建议各终端先设置相同 `export ROBOT_TEST_SESSION=my_test_001`，便于汇总三端日志。同机默认 DDS 配置即可。测试脚本使用独立 `ROS_DOMAIN_ID=86`，避免与普通 Demo 混合。

也可直接运行：

```bash
source scripts/env.sh
ros2 launch robot_test_bringup mock_full_system.launch.py
# 另一个终端同样 source scripts/env.sh
ros2 run robot_test_ground ground_station
```

## 依赖与构建

要求 Ubuntu 22.04、ROS 2 Humble、Python 3.10、colcon、ament Python/CMake、rclpy、diagnostic_msgs、sensor_msgs、std_srvs、builtin_interfaces。

标准依赖安装示例（新机器，由操作者自行执行）：

```bash
sudo apt install python3-colcon-common-extensions python3-venv python3-pip \
  python3-yaml python3-numpy python3-opencv python3-psutil libxcb-cursor0 \
  ros-humble-rclpy ros-humble-diagnostic-msgs ros-humble-sensor-msgs \
  ros-humble-std-srvs ros-humble-rosidl-default-generators
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
```

当前机器已把 PySide6 装在 `.venv`；缺失的 `libxcb-cursor0` 仅下载解压至 `.local-deps`，启动脚本设置局部库路径，没有升级 Ubuntu、ROS 或修改系统库。启动脚本设置 `PYTHONNOUSERSITE=1`，避开当前用户目录中 NumPy 2 与系统 OpenCV 的 ABI 冲突，不卸载或修改用户包。OpenCV / NumPy 使用系统版本，不要混装 pip 的 OpenCV 和 NumPy 2。psutil 仅列为未来系统监控依赖，本版未实现 P2 系统监控。

地面站要通过启动脚本或先 `source scripts/env.sh`，使 ROS 的 Python 入口可找到项目内 PySide6。相机缺少 OpenCV/NumPy 时会显示错误，运动、Heartbeat 和 Diagnostics 仍运行。

## 操作与验收

1. 等待 A/B 均显示 ONLINE，设备状态绿色。Heartbeat 为 1 Hz；Diagnostics 默认 5 Hz；Heartbeat 接收间隔达到 3 秒显示 OFFLINE。离线设备状态标为 OFFLINE，位置/计数为最后接收的旧数据，重连无需重启地面站。
2. 选择机器人和轴，按住 JOG + / −。地面站先请求 arm，再以 10 Hz 发送指令，表格中的 position 连续变化。速度和上限来自 YAML。
3. 松手立即发送 STOP。窗口失焦也会停止当前 JOG。若进程或网络断流，Agent 自己的 10 ms 检查循环在最后有效指令 500 ms 后停车并解除使能。
4. STOP 停止选定机器人的所有电机和自动循环；STOP ALL 对 A/B 分别调用 STOP。检查 velocity 为 0、enabled=False、auto_state=IDLE。STOP 后持续到达的 JOG 不会恢复运动，必须重新按下 JOG 或明确启动 Auto。
5. START AUTO TEST 使 drive 按 YAML 目标往复：默认 +1.0、停 1 秒、−1.0、停 1 秒，再循环，速度 0.1。STOP AUTO TEST、STOP、STOP ALL 都能中断。自动运动也有 10 Hz 地面站保活，保活丢失 500 ms 停车。界面失焦不会取消已启动的 Auto；关闭界面会 STOP ALL。
6. MOCK FAULT 选择设备，再 INJECT / RECOVER：camera_1 等各路相机掉线、ethercat 错误、drive/其他轴故障、heartbeat 丢失、rs485 超时、canopen 离线、network 警告。恢复不自动重新使能运动。运动总线或电机故障立即停止所有电机；可选相机故障不阻塞其他模块。
7. 关闭 A Agent，约 3 秒后仅 A OFFLINE；重新运行 `start_robot_a.sh`，A 自动恢复 ONLINE。Heartbeat 判定依据本机 monotonic 接收时间。
8. 输入事件描述，点击 EQUIPOTENTIAL CONTACT 等标记。Ground 先落盘，再向 A/B 各自 namespace 发布同一事件 ID、UTC 时间戳和描述。在线三端日志可直接对齐。
9. Robot A 默认 5 路相机、Robot B 3 路，各路独立显示画面、帧号和时间，约 5 FPS。默认全屏，1920×1080（100% 缩放）下全部相机横排同时可见；F11 切换全屏，Esc 回到窗口。采集线程与运动 executor 隔离，地面站只存最新帧；ROS 回调不操作 QWidget。离线或两秒无新帧会清空预览，避免把旧画面误作实时画面。

**软件 STOP 不是硬件急停。** Python/ROS 2 的 500 ms Watchdog 是软件时限，调度和通信有抖动；进程卡死、OS 故障和物理断电保护必须由真实硬件驱动器/安全回路完成。界面 STOP 服务失败或超时会写到日志区；失联机器人的停车依赖其本地 Watchdog，不能把发送 STOP 等同于硬件停车已确认。

## 日志

路径 `logs/<session_id>/`：

- `robot_a_status.csv`、`robot_a_events.csv`
- `robot_b_status.csv`、`robot_b_events.csv`
- `ground_status.csv`、`ground_events.csv`

字段：timestamp、robot、device、level、event、value、detail。状态每秒记录，事件立即记录并 flush；设备计数以 JSON 放在 value 字段，界面也会显示。CSV 追加写入，Agent 重启不会覆盖同 session 的日志。计数是**进程生命周期内累计值**，重启会归零；可通过 uptime / heartbeat sequence 判断新一轮进程。

脚本默认生成 UTC 启动 session；`ROBOT_TEST_SESSION` 可显式统一，`ROBOT_TEST_LOG_ROOT` 可指定根目录。直接 ros2 启动且没有环境变量时，使用当前目录 `logs/UTC日期/`。flush 不等于每行 fsync，不能保证掉电零丢失。磁盘写入失败会报告并保持控制循环运行。

事件使用可靠、volatile DDS QoS，**离线期间不补发**；离线机器人不会拥有其断线期间的事件记录，需现场核对三端 CSV。未来多机部署需要操作者事先同步系统时间（本 Demo 不更改系统时间配置）。

## 相机数量与配置

相机清单位于各机器人 YAML 顶层 `cameras`，不再使用单路 `hardware.camera`。A 默认启用 camera_1 到 camera_5，B 启用 camera_1 到 camera_3。相机实际类型、安装位置尚未指定，因此暂用中性编号。

A 只有 4 路时，在 `ros2_ws/src/robot_test_bringup/config/robot_a.yaml` 把 `cameras.camera_5.enabled` 改为 `false`，然后重启 Agent 和地面站；不需要修改代码或重新 build。其他相机编号不会变化。恢复为 true 即回到 5 路。

```yaml
cameras:
  camera_5:
    enabled: false  # A 为 4 路时关闭第五路
    backend: mock
    fps: 5
    label: ROBOT A CAMERA 5
```

每路使用独立 Adapter、采集线程、ROS topic、Diagnostics 行、计数及 CSV 设备名。例如 `/robot_a/cameras/camera_5/image_raw`；故障面板可单独选择 camera_5。单路故障仅清空其预览，其他相机和运动控制继续运行。每路 backend 可以单独配置，后续可混合不同真实相机驱动。

## ROS 接口（两机器人相同）

以下接口前缀为 `/robot_a` 或 `/robot_b`，无混用 namespace 的机器人业务 topic：

| 接口 | 类型 | 用途 |
|---|---|---|
| heartbeat | robot_test_msgs/RobotHeartbeat | 1 Hz 状态、模式、uptime、sequence |
| diagnostics | diagnostic_msgs/DiagnosticArray | 设备状态和累计计数 |
| jog_command | robot_test_msgs/JogCommand | 时间戳、轴、速度；best effort / depth 1 |
| arm | std_srvs/SetBool | 显式使能 / 停车解除使能 |
| stop / stop_auto | std_srvs/Trigger | 停止全部轴及 Auto |
| start_auto | std_srvs/Trigger | 启动 YAML 定义的 drive 往复 |
| auto_keepalive | builtin_interfaces/Time | 自动模式保活时间戳 |
| inject_fault | robot_test_msgs/InjectFault | device、fault、active |
| test_event | robot_test_msgs/TestEvent | 同一时间戳、事件 ID、类型、描述 |
| cameras/<camera_id>/image_raw | sensor_msgs/Image | bgr8，sensor data QoS |

JOG 接受范围：已 arm、MANUAL 模式、轴有效、有限数值、配置限速内、消息年龄小于 watchdog，且晚于最后一次 arm/stop。拒绝指令不会刷新 Watchdog。Mock 当前使用线性位置/速度单位，真实接入必须在 Adapter 内明确转换单位和限位。

## 结构和真实硬件扩展

- `robot_test_msgs`：ROS 消息和服务。
- `robot_test_core`：枚举、Adapter 抽象、运动状态机、Watchdog、CSV。
- `robot_mock_hardware`：Mock 电机/总线/相机、Factory、`real_adapters/`。
- `robot_test_agent`：一个 Agent，namespace + YAML 决定 A/B；仅通过契约操作设备。
- `robot_test_ground`：ROS executor 独立线程、带锁 ViewModel、Qt 主线程。
- `robot_test_bringup`：YAML 和 launch。

配置位于 `ros2_ws/src/robot_test_bringup/config/robot_{a,b}.yaml`。A 四个 EtherCAT 轴并有 RM75/RS485 状态；B 四个 EtherCAT 轴、两个 CANopen 支撑轴。RM75/RS485 当前为状态与通信计数模拟，不含真实命令。硬件标志 `enabled` 控制设备及所属总线的轴；轴列表定义电机，每个轴默认继承其 bus 的 backend。

真实驱动扩展流程：

1. 实现 `MotorAdapter` / `CameraAdapter` / `DeviceAdapter` 对应方法。已预留 EtherCATMotorAdapter、CANopenMotorAdapter、RealSenseCameraAdapter、RM75Adapter、RS485Adapter、LidarAdapter 类。
2. 在 Factory 注册构造器；电机配置保留 bus，用于选择 EtherCAT 或 CANopen。真实 backend 不支持 Mock Fault Injection。
3. 修改对应硬件总线 YAML 的 backend 为 real（关联轴自动继承），并填写真实驱动需要的参数。**目前这些类尚未实现，切换 real 会明确显示错误，不会连接真实硬件，也不会偷偷回退成 Mock。**
4. 实现并验证驱动层独立 Watchdog、硬件急停、限位、单位换算、总线时限及重连；再现场联调。

Adapter 的 connect/update/status/stop 必须有界、不能无限等待；共享总线应封装在 Adapter 工厂创建的 backend 会话中。Camera get_frame 在独立线程执行，其状态、故障和 connect/disconnect 必须线程安全。业务层不需要因换驱动重写。当前非相机异常隔离后保持 ERROR，修复真实读写异常的自动重连策略留给 backend。

## 自动验收

```bash
source scripts/env.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
# 测试创建并清理自己的 A/B 子进程；请勿在 domain 86 同时启动其他 Demo。
ROS_DOMAIN_ID=86 ROS_LOCALHOST_ONLY=1 QT_QPA_PLATFORM=offscreen \
  python3 tests/acceptance_p0.py
ROS_DOMAIN_ID=86 ROS_LOCALHOST_ONLY=1 QT_QPA_PLATFORM=offscreen \
  TEST_P1=1 ROBOT_TEST_SESSION=acceptance python3 tests/acceptance_p0.py
```

P0 验收包括真实 ROS 子进程、Qt 控件、JOG、断流 Watchdog、STOP ALL、A 退出和重启。完整验收额外运行默认参数的正反向 Auto、保活断流、所有故障恢复、三端 CSV 事件和相机预览。移除 `QT_QPA_PLATFORM=offscreen` 可在真实桌面看到测试窗口。结果和截图保存在 `logs/`。执行记录见 `VALIDATION.md`。

多相机回归（A=4/B=3 使用临时配置，不改默认 YAML）：

```bash
source scripts/env.sh
ROS_DOMAIN_ID=86 ROS_LOCALHOST_ONLY=1 QT_QPA_PLATFORM=offscreen \
  TEST_CAMERA_COUNT=4 ROBOT_TEST_SESSION=cameras_4_3 python3 tests/acceptance_p0.py
```

最新多相机结果和截图为 `logs/multicamera_8_results.txt`、`logs/multicamera_8_ground.png` 以及 `multicamera_7_*`。

新增：A/B 各一行 LiDAR Mock 状态，支持故障注入与计数。参考 [无线网桥与雷达预算](docs/无线网桥与雷达预算.md)。
