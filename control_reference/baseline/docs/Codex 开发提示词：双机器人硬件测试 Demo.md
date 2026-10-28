> 完成标记更新：2026-09-17。`~~删除线~~` 表示对应任务已在当前 **Mock Demo** 实现并验证；章节标题划线表示该章节的 Mock 交付已完成，章节内示例和代码原样保留，便于查阅。不是删除原文，也不表示真实硬件已接入。
>
> P0/P1 已完成；P2 中仅关键计数显示和 1920×1080 全屏 UI 优化已完成。系统监控、更完善的真实故障恢复、现场总线/5G/EMC 测试仍未完成，未划线。硬件背景、禁止事项、长期原则和未来方向保持原样。
>
> 当前相机配置为 A 默认 5 路（可关闭第 5 路变为 4 路）、B 3 路；实际配置采用 YAML 顶层 cameras 清单，原示例不改写。界面在 1920×1080、100% 缩放下全部当前设备行、8 路预览和控制区同时可见；历史日志滚动查看。
>
> 使用指南：`/home/tian/robot_test_system/docs/使用指南.md`；后续配置指南：`/home/tian/robot_test_system/docs/后续配置指南.md`；验证记录：`/home/tian/robot_test_system/VALIDATION.md`。原始备份：`/home/tian/robot_test_system/docs/reference/原开发提示词_完成标记前.md`。

# 双机器人硬件测试系统 Demo 开发任务

你现在需要从 0 开始帮我开发一套用于双机器人硬件测试的 ROS 2 Demo 系统。

请不要把它理解成最终机器人控制系统。

当前最紧急目标是：

> 4 天后机器人需要进行 EMC、等电位接触、等电位工作、磁场干扰、温湿度等测试，因此需要快速建立一套能够实时监控机器人硬件状态、进行基础运动控制、记录异常和测试日志的测试系统。

今晚我不在机器人旁边，手边只有一台和未来地面站环境基本一致的 Ubuntu 笔记本，因此今晚优先完成：

> Mock Robot A + Mock Robot B + Ground Test Station 的完整软件闭环。

明天到机器人现场后，只需要把 Mock Hardware Adapter 替换为真实 EtherCAT、CANopen、RM75、Camera、RS485 等硬件接口。

---

# 1. 当前硬件背景

系统包含：

- 地面站 PC
- Robot A
- Robot B
- 三端通过 IP 网络 / 5G 通信
- Robot A / B IPC 均为 Ubuntu 22.04
- ROS 2 Humble
- 地面站也是 Ubuntu 22.04 + ROS 2 Humble

## Robot A

Robot A 是主要作业机器人，硬件包括：

- Intel N305 IPC
- EtherCAT：
  - 1 个驱动轮
  - 2 个夹持轮
  - 1 个 Z 轴
- RM75 机械臂，以太网通信
- RS485 / Modbus RTU 末端设备
- D435 或 D456 深度相机
- RGB 相机
- LiDAR

## Robot B

Robot B 是支撑机器人，硬件包括：

- IPC
- EtherCAT：
  - 1 个驱动轮
  - 2 个夹持轮
  - 1 个 Z 轴
- CANopen：
  - 2 个支撑模块电机
- D435/D456 或其他相机
- RGB 相机
- LiDAR

当前硬件基础驱动基本测试过。

CANopen 暂未实际联调，但厂家提供 SDK，因此本阶段不需要真正接 CANopen 硬件。

---

# 2. 当前开发原则

本阶段只开发：

**Robot Hardware Test System v0.1**

不要开发完整的机器人生产控制系统。

请严格遵守：

## 本阶段需要

- ~~Robot A/B 在线状态~~
- ~~Heartbeat~~
- ~~Hardware Diagnostics~~
- ~~电机 Mock 控制~~
- ~~JOG~~
- ~~STOP~~
- ~~Watchdog~~
- ~~Auto Cycle~~
- ~~Device Error Counter~~
- ~~Fault Injection~~
- ~~本地日志~~
- ~~Ground Dashboard~~
- ~~Test Event Marker~~
- ~~Mock Camera~~
- ~~Mock Robot A/B~~

## 本阶段不要开发

不要做：

- MoveIt
- 双机器人任务协同
- Mission Manager
- 自动路径规划
- 缺陷识别
- 完整 ros2_control 重构
- Zenoh
- DDS Router
- 数据库
- RViz 集成
- 复杂工业 UI
- 真实 EtherCAT 控制
- 真实 CANopen 控制
- 真实 RM75 控制
- 真实 RealSense 接入

这些以后再做。

---

# ~~3. 总体架构~~

当前架构：

```text
                     Ground Test Station
                  Ubuntu 22.04 + ROS2 Humble
                            │
                            │ ROS2
                            │
                  ┌─────────┴─────────┐
                  │                   │
                  ▼                   ▼
           Robot A Test Agent   Robot B Test Agent
                  │                   │
            Hardware Adapter    Hardware Adapter
                  │                   │
               MOCK                MOCK
```

未来真实系统只需要：

```text
MockMotorAdapter
        ↓
EtherCATMotorAdapter
```

或者：

```text
MockCameraAdapter
        ↓
RealSenseAdapter
```

上层 Robot Agent 和 Ground Station 不允许因为硬件替换而大改。

---

# ~~4. 核心架构要求~~

必须采用 Hardware Adapter 抽象。

禁止 Robot Agent 直接操作具体硬件实现。

例如：

```python
class MotorAdapter:

    def connect(self):
        pass

    def enable(self):
        pass

    def disable(self):
        pass

    def jog(self, velocity: float):
        pass

    def stop(self):
        pass

    def get_position(self) -> float:
        pass

    def get_velocity(self) -> float:
        pass

    def get_status(self):
        pass

    def get_error(self):
        pass
```

今晚实现：

```python
MockMotorAdapter
```

以后实现：

```python
EtherCATMotorAdapter
```

Robot Agent 只能操作：

```python
MotorAdapter
```

不能依赖具体 backend。

---

# ~~5. Camera Adapter~~

建立：

```python
class CameraAdapter:

    def connect(self):
        pass

    def disconnect(self):
        pass

    def is_connected(self) -> bool:
        pass

    def get_frame(self):
        pass

    def get_fps(self) -> float:
        pass

    def get_frame_count(self) -> int:
        pass

    def get_drop_count(self) -> int:
        pass
```

今晚使用：

```python
MockCameraAdapter
```

Mock Camera 可以生成测试画面，例如：

```text
ROBOT A MOCK CAMERA

Frame: 12381
FPS: 30.0

2026-09-16 23:42:18
```

Ground 能实时看到画面即可。

不追求高帧率。

---

# ~~6. 项目目录~~

优先使用一个 Git 仓库。

建议：

```text
robot_test_system/
│
├── README.md
├── requirements.txt
├── .gitignore
│
├── scripts/
│   ├── start_mock_demo.sh
│   ├── start_ground.sh
│   ├── start_robot_a.sh
│   └── start_robot_b.sh
│
└── ros2_ws/
    └── src/
        │
        ├── robot_test_msgs/
        │
        ├── robot_test_core/
        │
        ├── robot_test_agent/
        │
        ├── robot_mock_hardware/
        │
        ├── robot_test_ground/
        │
        └── robot_test_bringup/
```

如果 ROS 2 Python package 的实际目录层级需要调整，请按照 ROS 2 Humble 的标准 package 结构实现。

---

# ~~7. robot_test_core~~

这个包尽量不直接依赖具体硬件。

定义基本枚举和数据模型。

## ~~RobotState~~

```text
OFFLINE
INITIALIZING
READY
RUNNING
WARNING
FAULT
STOPPED
```

## ~~DeviceState~~

```text
UNKNOWN
OK
WARN
ERROR
OFFLINE
```

## ~~ControlMode~~

```text
MONITOR
MANUAL
AUTO_TEST
```

尽可能使用 Python Enum。

---

# ~~8. Robot A / B 不写两套 Agent~~

只写一个：

```text
RobotTestAgent
```

通过：

- namespace
- YAML
- robot_id

决定自己是 Robot A 还是 Robot B。

例如：

```bash
ros2 run robot_test_agent agent --ros-args -r __ns:=/robot_a
```

Robot B：

```bash
ros2 run robot_test_agent agent --ros-args -r __ns:=/robot_b
```

或者通过 launch 文件实现。

优先使用 launch。

---

# ~~9. 配置文件~~

建立：

```text
robot_a.yaml
robot_b.yaml
```

例如 Robot A：

```yaml
robot:
  id: robot_a
  display_name: Robot A

hardware:

  ethercat:
    enabled: true
    backend: mock

  camera:
    enabled: true
    backend: mock

  rm75:
    enabled: true
    backend: mock

  rs485:
    enabled: true
    backend: mock

  canopen:
    enabled: false

test:

  watchdog_timeout_ms: 500

  heartbeat_hz: 1.0

  diagnostics_hz: 2.0

  auto_cycle:
    enabled: true

    drive_motor:
      enabled: true
      positive_target: 1.0
      negative_target: -1.0
      velocity: 0.1
      dwell_sec: 1.0
```

Robot B：

```yaml
robot:
  id: robot_b
  display_name: Robot B

hardware:

  ethercat:
    enabled: true
    backend: mock

  camera:
    enabled: true
    backend: mock

  rm75:
    enabled: false

  rs485:
    enabled: false

  canopen:
    enabled: true
    backend: mock

test:

  watchdog_timeout_ms: 500

  heartbeat_hz: 1.0

  diagnostics_hz: 2.0
```

未来只需要：

```yaml
backend: mock
```

替换为：

```yaml
backend: real
```

---

# ~~10. ROS Namespace~~

所有 Robot A topic 必须位于：

```text
/robot_a/*
```

Robot B：

```text
/robot_b/*
```

避免任何 A/B topic 混在一起。

---

# ~~11. Heartbeat~~

实现：

```text
/robot_a/heartbeat
/robot_b/heartbeat
```

频率：

```text
1 Hz
```

可以自定义：

```text
RobotHeartbeat.msg
```

建议：

```text
builtin_interfaces/Time stamp
string robot_id
uint64 sequence
float64 uptime
string state
string control_mode
```

Ground 必须根据 Heartbeat 判断在线状态。

如果超过：

```text
3 秒
```

没有收到 heartbeat：

```text
ROBOT OFFLINE
```

Robot Panel 明显显示异常。

重新收到 heartbeat 后自动恢复 ONLINE。

Ground 不允许必须重启才能恢复。

---

# ~~12. Diagnostics~~

使用 ROS 2 标准：

```text
diagnostic_msgs/DiagnosticArray
```

如果方便，可以使用：

```text
diagnostic_updater
```

Robot A 至少包含：

```text
System
EtherCAT
Drive Motor
Clamp Left
Clamp Right
Z Axis
Camera
RM75
RS485
Network
```

Robot B：

```text
System
EtherCAT
Drive Motor
Clamp Left
Clamp Right
Z Axis
Camera
CANopen
Support Left
Support Right
Network
```

每个设备至少：

```text
status

OK
WARN
ERROR
OFFLINE
```

并附带必要 KeyValue。

---

# ~~13. Counter~~

这是测试系统非常重要的一部分。

所有设备不要只保存 connected=true/false。

必须尽量提供累计计数。

Camera：

```text
frame_count
drop_count
disconnect_count
reconnect_count
```

Communication：

```text
rx_count
tx_count
timeout_count
error_count
reconnect_count
```

EtherCAT Mock：

```text
cycle_count
error_count
slave_lost_count
recover_count
```

CANopen Mock：

```text
message_count
timeout_count
error_count
```

RS485：

```text
request_count
response_count
timeout_count
crc_error_count
```

Counter 后续真实测试要用于分析 EMC 和等电位冲击。

---

# ~~14. Mock Motor~~

Mock Motor 需要真的模拟位置变化。

例如内部：

```python
position += velocity * dt
```

至少模拟：

```text
enabled
position
velocity
error
connected
```

支持：

```text
enable
disable
jog
stop
```

这样 Ground JOG 后必须可以看到 position 连续变化。

---

# ~~15. JOG~~

实现：

```text
/robot_a/jog_command
/robot_b/jog_command
```

可以定义：

```text
JogCommand.msg
```

内容：

```text
string axis
float64 velocity
```

axis 至少支持：

```text
drive
clamp_left
clamp_right
z_axis
```

Robot B 后续预留：

```text
support_left
support_right
```

Ground JOG 按钮：

```text
JOG -
STOP
JOG +
```

---

# ~~16. JOG Watchdog~~

这是 P0 功能。

JOG 命令不能：

```text
发一次
→
永远运动
```

Ground 按住 JOG 时应持续发送命令。

例如：

```text
10 Hz
```

Robot Agent 保存：

```text
last_motion_command_time
```

如果：

```text
超过 watchdog_timeout_ms
```

未收到新的运动指令：

```text
motor.stop()
```

默认：

```text
500 ms
```

该值放 YAML。

Mock 中必须可以验证。

---

# ~~17. STOP~~

实现独立 STOP。

推荐：

```text
/robot_a/stop
/robot_b/stop
```

可使用：

```text
std_srvs/Trigger
```

STOP 必须：

- ~~所有 Mock Motor 速度置 0~~
- ~~Auto Cycle 停止~~
- ~~清理当前 JOG 状态~~
- ~~Robot 状态切到 STOPPED 或 READY~~
- ~~写日志~~

Ground 有：

```text
STOP
```

以及：

```text
STOP ALL
```

STOP ALL 同时向 A/B 发送 STOP。

注意：

软件 STOP 不是硬件急停，README 必须明确说明。

---

# ~~18. Auto Cycle~~

实现简单的自动测试模式。

目的：

以后进入 EMC、磁场测试时，让电机自动低速往复运行。

Mock Motor 中：

```text
positive target
↓
dwell
↓
negative target
↓
dwell
↓
repeat
```

至少支持 Drive Motor。

如果结构方便，可以支持多个 axis。

状态机类似：

```text
IDLE
MOVE_POSITIVE
DWELL_POSITIVE
MOVE_NEGATIVE
DWELL_NEGATIVE
STOPPING
```

Ground 提供：

```text
START AUTO TEST
STOP AUTO TEST
```

Auto Cycle 参数来自 YAML。

---

# ~~19. Fault Injection~~

今晚必须加入 Mock Fault Injection。

至少能模拟：

```text
Camera Offline
EtherCAT Error
Motor Fault
Robot Heartbeat Drop
RS485 Timeout
CANopen Offline
Network Warning
```

实现方式不限。

可以使用：

- ROS parameter
- service
- debug panel

如果开发简单，优先通过 Ground Debug Panel。

例如：

```text
[Camera Fault]
[EtherCAT Fault]
[Motor Fault]
[Heartbeat Drop]
```

再次点击可恢复。

---

# ~~20. Robot Offline 测试~~

必须验证：

启动：

```text
Robot A
Robot B
Ground
```

Ground：

```text
A ONLINE
B ONLINE
```

关闭 Robot A Agent。

3 秒以内：

```text
A OFFLINE
B ONLINE
```

重新启动 Robot A。

Ground 自动：

```text
A ONLINE
```

Ground 不允许重启。

---

# ~~21. Ground Station 技术栈~~

使用：

```text
Python
PySide6
rclpy
```

不要使用 Web UI。

不要使用 Electron。

不要为了 UI 引入复杂框架。

---

# ~~22. PySide6 和 ROS2 线程模型~~

严禁在 PySide6 GUI 主线程直接阻塞：

```python
rclpy.spin()
```

建议结构：

```text
PySide6 Main Thread

        │

    Qt Signal

        ▲

ROS Bridge / State Model

        ▲

ROS2 Executor Thread
```

即：

- ~~Qt 主线程只负责 UI~~
- ~~ROS 2 在独立线程运行~~
- ~~ROS callback 不直接操作 Qt widget~~
- ~~使用 Qt Signal 更新界面~~

注意线程安全。

---

# ~~23. Ground State Model~~

不要让 ROS callback 直接：

```python
label.setText(...)
```

建立例如：

```text
RobotViewModel
```

保存：

```text
robot_id
online
last_heartbeat
robot_state
control_mode
devices
position
velocity
error_count
```

ROS 更新 Model。

Model 通知 UI。

---

# ~~24. Ground UI~~

当前阶段不追求美观。

优先：

- 清楚
- 稳定
- 信息密度高
- 能快速发现异常

建议：

```text
┌────────────────────────────────────────────────────┐
│ ROBOT HARDWARE TEST SYSTEM                        │
├──────────────────────┬─────────────────────────────┤
│ ROBOT A              │ ROBOT B                     │
│                      │                             │
│ ● ONLINE             │ ● ONLINE                    │
│ ● EtherCAT           │ ● EtherCAT                  │
│ ● Drive              │ ● Drive                     │
│ ● Clamp L            │ ● Clamp L                   │
│ ● Clamp R            │ ● Clamp R                   │
│ ● Z                  │ ● Z                         │
│ ● Camera             │ ● Camera                    │
│ ● RM75               │ ● CANopen                   │
│ ● RS485              │ ● Support                   │
│                      │                             │
│ heartbeat            │ heartbeat                   │
│ uptime               │ uptime                      │
├──────────────────────┴─────────────────────────────┤
│ Camera A              Camera B                     │
│                                                    │
│ [ preview ]           [ preview ]                  │
├────────────────────────────────────────────────────┤
│ ROBOT: [A]                                           │
│ AXIS : [Drive]                                       │
│                                                      │
│ [JOG -]    [STOP]    [JOG +]                        │
│                                                      │
│ [START AUTO]                 [STOP ALL]              │
├────────────────────────────────────────────────────┤
│ EVENT                                               │
│                                                      │
│ [TEST START]                                        │
│ [EMC]                                               │
│ [EQUIPOTENTIAL CONTACT]                             │
│ [EQUIPOTENTIAL WORK]                                │
│ [MAGNETIC FIELD]                                    │
│ [TEMP/HUMIDITY]                                     │
│ [TEST END]                                          │
├────────────────────────────────────────────────────┤
│ LOG                                                 │
│ ...                                                 │
└────────────────────────────────────────────────────┘
```

正常：

绿色。

WARN：

黄色。

ERROR / OFFLINE：

红色。

UNKNOWN：

灰色。

尽量统一颜色逻辑。

---

# ~~25. Mock Camera Preview~~

如果时间允许，实现 Mock Camera。

Mock Camera 生成 OpenCV / NumPy 测试图：

例如：

```text
ROBOT A MOCK CAMERA

Frame = XXXXX

FPS = XX.X

TIME = XX:XX:XX
```

Ground 能持续显示。

Robot B 同样。

不追求性能。

5~10 FPS 足够。

---

# ~~26. Event Marker~~

这是测试非常重要的功能。

Ground 提供：

```text
TEST START
EMC START
EQUIPOTENTIAL CONTACT
EQUIPOTENTIAL WORK
MAGNETIC FIELD
TEMP HUMIDITY
TEST END
```

点击事件以后：

1. ~~Ground 本地写日志~~
2. ~~ROS2 发布 event~~
3. ~~Robot A 收到并写本地日志~~
4. ~~Robot B 收到并写本地日志~~

事件必须包含：

```text
timestamp
event_type
description
```

确保三端后续能按时间对齐。

---

# ~~27. 日志~~

Robot A：

```text
logs/
<session_id>/
    robot_a_status.csv
    robot_a_events.csv
```

Robot B：

```text
robot_b_status.csv
robot_b_events.csv
```

Ground：

```text
ground_events.csv
ground_status.csv
```

建议字段：

```text
timestamp
robot
device
level
event
value
detail
```

状态日志不需要 100 Hz。

建议 1~5 Hz。

异常事件立即写入。

日志必须：

- ~~flush~~
- ~~程序异常退出后尽量不丢大量数据~~

不要为了日志引入数据库。

CSV + 普通 log 即可。

---

# 28. 系统监控

如果实现成本低，Robot Test Agent 监控：

```text
CPU %
Memory %
CPU temperature
uptime
```

Linux 可使用 psutil 和 `/sys`。

如果 CPU 温度接口在当前 PC 不存在：

不要让程序崩溃。

显示 UNKNOWN。

---

# ~~29. Network Mock / Heartbeat~~

今晚只有一台 PC，因此网络延迟不是真实网络测试。

但至少：

- ~~Heartbeat 工作~~
- ~~Offline detection 工作~~
- ~~可模拟 heartbeat drop~~

如果方便：

Ground 可以计算：

```text
last heartbeat age
```

真实 RTT 明天再接。

不要今晚做复杂 ping subsystem。

---

# ~~30. Launch~~

最终至少提供：

```text
mock_full_system.launch.py
```

启动：

```text
Mock Robot A
Mock Robot B
```

Ground GUI 可以选择一起启动或者独立启动。

最终最好：

```bash
ros2 launch robot_test_bringup mock_full_system.launch.py
```

能够启动 A/B。

然后：

```bash
ros2 run robot_test_ground ground_station
```

启动 Ground。

如果 PySide6 放进 launch 不稳定，就不要强行一起启动。

---

# ~~31. Shell Script~~

生成：

```text
scripts/start_mock_demo.sh
scripts/start_ground.sh
scripts/start_robot_a.sh
scripts/start_robot_b.sh
```

脚本负责：

```text
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
```

再启动对应程序。

不要过度复杂。

---

# ~~32. README~~

README 必须包含：

## ~~安装依赖~~

包括：

```text
ROS2 Humble
PySide6
psutil
opencv-python
numpy
```

如果 ROS 自带的 OpenCV 环境冲突，则优先使用系统 ROS 推荐方式。

## ~~Build~~

例如：

```bash
cd ros2_ws

colcon build --symlink-install

source install/setup.bash
```

## ~~Mock Demo 启动方式~~

## ~~Ground 启动方式~~

## ~~JOG 测试方式~~

## ~~Fault Injection 使用方式~~

## ~~STOP ALL~~

## ~~日志路径~~

## ~~如何从 mock 切换 real~~

---

# ~~33. Real Hardware 预留接口~~

虽然今晚不实现真实硬件，但必须为以下 adapter 预留目录和类：

```text
EtherCATMotorAdapter

CANopenMotorAdapter

RealSenseCameraAdapter

RM75Adapter

RS485Adapter

LidarAdapter
```

这些可以暂时：

```python
raise NotImplementedError
```

但项目结构必须准备好。

---

# 34. 明天真实硬件接入原则

未来真实硬件 adapter 必须保持和 mock 相同接口。

例如：

```text
MockMotorAdapter
        │
        │ same API
        ▼
EtherCATMotorAdapter
```

上层：

```text
RobotTestAgent
```

不能改业务代码。

通过 YAML：

```yaml
backend: mock
```

切换：

```yaml
backend: real
```

~~实现 backend factory。~~

例如：

```python
create_motor_adapter(config)
```

---

# 35. Coding Style

要求：

- Python 3
- 类型标注
- dataclass 可用
- 避免巨大单文件
- 清晰模块化
- 关键状态机写注释
- 日志使用 Python logging
- 不允许大量裸 print
- 不允许 ROS callback 操作 Qt widget
- 不允许硬编码 robot_a / robot_b 到大量业务代码
- 不允许硬编码测试速度
- 参数放 YAML
- 不允许因为一个可选设备异常导致整个 Robot Agent 崩溃

---

# 36. Error Handling

所有 Hardware Adapter 都应考虑：

```text
connect failure
read failure
timeout
exception
device offline
```

原则：

某个 Camera 掉线：

```text
Camera = ERROR
```

Robot Agent 继续运行。

CANopen 掉线：

```text
CANopen = ERROR
```

其他模块继续。

不能：

```text
一个 USB Camera exception
→
整个 Agent crash
```

---

# 37. 当前优先级

严格按照以下优先级开发。

## P0

必须完成：

1. ~~ROS2 workspace~~
2. ~~RobotTestAgent~~
3. ~~Robot A/B namespace~~
4. ~~MockMotorAdapter~~
5. ~~Heartbeat~~
6. ~~Diagnostics~~
7. ~~Ground A/B ONLINE~~
8. ~~JOG~~
9. ~~STOP~~
10. ~~Watchdog~~

## P1

随后完成：

11. ~~Auto Cycle~~
12. ~~Fault Injection~~
13. ~~Logs~~
14. ~~Event Marker~~
15. ~~Robot Offline detection~~
16. ~~YAML config~~
17. ~~Mock Camera~~
18. ~~Ground Camera Preview~~

## P2

如果今晚仍有时间：

19. System monitor
20. ~~Counter 美化~~
21. ~~UI 优化~~
22. 更完善的错误恢复

不要在 P0/P1 未完成时做 P2。

---

# ~~38. 今晚最终验收标准~~

最终我要在这一台 Ubuntu 笔记本上做到：

启动：

```text
Robot A Mock
Robot B Mock
Ground
```

Ground 显示：

```text
Robot A ONLINE
Robot B ONLINE
```

两台设备状态均正常。

然后：

## ~~JOG~~

选择：

```text
Robot A
Drive
```

按：

```text
JOG+
```

Mock Motor：

```text
velocity > 0
position 连续增加
```

松开：

```text
motor.stop()
```

如果 Ground 不再发 JOG：

```text
500 ms watchdog
```

自动 Stop。

---

## ~~STOP ALL~~

Robot A/B 所有 Mock Motor：

```text
velocity = 0
```

Auto Cycle 停止。

---

## ~~Auto Cycle~~

Robot A Drive：

```text
正向
→
停
→
反向
→
停
→
循环
```

Ground 能看到 Position 改变。

---

## ~~Fault~~

制造：

```text
Robot A Camera Fault
```

Ground：

```text
Camera 绿色 → 红色
```

恢复：

```text
红色 → 绿色
```

---

## ~~Robot Offline~~

关闭 Robot A。

3 秒以内：

```text
Robot A OFFLINE
```

Robot B 不受影响。

重新启动 Robot A：

```text
Robot A ONLINE
```

Ground 不重启。

---

## ~~Event~~

点击：

```text
EQUIPOTENTIAL CONTACT
```

Ground：

```text
写日志
```

Robot A：

```text
写日志
```

Robot B：

```text
写日志
```

三端都有 timestamp。

---

# 39. 开发过程要求

请直接开始工作。

不要一开始只写长篇设计方案。

流程应为：

1. ~~检查当前操作系统和 ROS2 环境~~
2. ~~建立项目~~
3. ~~建立 ROS package~~
4. ~~编写最小可运行版本~~
5. ~~build~~
6. ~~运行~~
7. ~~根据错误修复~~
8. ~~继续加入下一功能~~
9. ~~最后运行完整 Mock Demo~~

每完成一个阶段，请实际：

```bash
colcon build
```

并运行测试。

不要只生成代码而不运行。

如果某个依赖不存在：

优先判断：

- 是否可以安装
- 是否可以换标准库
- 是否暂时降级

不要因为非核心依赖阻塞整个工程。

---

# 40. 不要擅自做的事情

不要：

- 修改 Ubuntu 版本
- 升级 ROS2
- 更换 ROS2 Humble
- 引入 Docker
- 引入 Kubernetes
- 引入 Web 前端
- 引入数据库
- 引入 Zenoh
- 引入复杂 DDS 配置
- 引入 MoveIt
- 引入真实硬件控制
- 引入复杂权限系统
- 做最终工业 UI

当前目标只有：

> 一个稳定、清晰、能模拟两台机器人并支持 Ground 实时监控和测试控制的 Mock Demo。

---

# 41. 项目未来方向

请在设计代码时知道未来会逐步演变为：

```text
Ground Mission Manager
        ↓
Dual Robot Coordinator
        ↓
Robot Agent
        ↓
ros2_control
        ↓
EtherCAT / CANopen / RS485
```

但当前 RobotTestAgent 只是第一阶段测试版本。

因此：

```text
Hardware Adapter
Diagnostics
Logger
Watchdog
Config
Ground State Model
```

这些部分尽量设计成未来可以继续复用。

不要为了未来做过度设计。

---

# 42. 最重要的原则

本阶段遵循：

> Working Demo > Perfect Architecture

但：

> Hardware Abstraction、Watchdog、STOP、日志、错误隔离不能省。

请从检查当前目录和 ROS2 Humble 环境开始，直接创建项目并运行第一版 Mock Robot A/B。