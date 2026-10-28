# 驱动实现与源码地图

本页路径相对于 `baseline/`。保留完整六个包是为了可追溯及导入依赖完整；后续可以拆分，不应只复制一个 `real_adapters` 目录后假定即可运行。

## 复用代码定位

| 功能 | 源码 | 复用说明 |
|---|---|---|
| 适配器契约/状态枚举 | `ros2_ws/src/robot_test_core/robot_test_core/{adapters,models}.py` | Motor/Device/Camera、状态/模式 |
| 设备创建与共享总线 | `ros2_ws/src/robot_mock_hardware/robot_mock_hardware/factory.py` | 实际控制后端是 eyou / eyou_canopen，不是占位 real |
| EtherCAT接口 | `ros2_ws/src/robot_mock_hardware/robot_mock_hardware/real_adapters/ethercat.py` | 一条总线一个原生子进程，4个轴共用 |
| EtherCAT原生 | `native/eyou_agent.cpp`、`native/motion_safety.hpp` | SDK访问、使能序列、模式、单位转换与看门狗 |
| CANopen接口 | `ros2_ws/src/robot_mock_hardware/robot_mock_hardware/real_adapters/canopen.py` | node映射、子进程、力矩符号、反馈 |
| CANopen原生 | `native/eyou_canopen_agent.cpp` | Profile Torque、节点状态、停止与反馈 |
| RGB发现和采集 | `real_adapters/{rgb_devices,uvc_camera}.py`（同适配器目录） | 名称/USB路径匹配，避免重复占用，重连 |
| 雷达统计 | `real_adapters/livox.py`、`scripts/livox_monitor.cpp` | Livox SDK2点/包/IMU统计，无点云发布 |
| RM75状态 | `real_adapters/telemetry.py`、`scripts/rm75_read_state.cpp` | `rm_init`/连接/`rm_get_current_arm_state`/关闭 |
| 控制状态机 | `ros2_ws/src/robot_test_core/robot_test_core/controller.py` | ARM/JOG/力矩/停止、设备错误与软件看门狗 |
| ROS服务与回零 | `ros2_ws/src/robot_test_agent/robot_test_agent/node.py` | namespace、服务、命令时间戳、3次碰撞回零 |
| RGB ROS发布 | `ros2_ws/src/robot_test_agent/robot_test_agent/camera_stream.py` | 采集线程与ROS回调隔离，最新帧邮箱 |
| 地面站ROS桥 | `ros2_ws/src/robot_test_ground/robot_test_ground/bridge.py` | Qt与ROS线程隔离、STOP优先、状态缓存 |
| 旧测试策略 | `auto_cycle.py`、`extensions.py`、`test_panel.py` | 留作回归，不作为正式任务执行器 |

## EtherCAT

原生循环约5 ms调用SDK，约50 ms发一行JSON反馈；这不是对底层SDK真实PDO周期的额外保证。4从站数量和索引在C++中固定，硬限位也写在头文件中，因此只改YAML不能改变全部底层限制。

配置索引0～3映射SDK ID1～4。夹持为CST，drive/Z为CSV。读状态包括原始位置、速度、力矩、模式、从站状态和状态字；输出根据0x40→0x21→0x23/0x27推进ControlWord 6/7/15。故障不会自动复位。

Python与原生驱动通过stdin文本命令、stdout JSON通信；SDK日志转stderr，不能混入JSON：

```text
ARM <epoch> <monotonic_ns>
CMD <epoch> <sequence> <monotonic_ns> <axis_index> <value>
STOP <epoch>
HOME <epoch>
ZERO <new_epoch> <encoder_counts>
```

这些是机器人内部协议，不是地面站直接发送的网络协议。epoch/sequence防重放，STOP清零命令并去使能；只有已经请求过运动的轴才进入运行使能路径。

`EtherCATBus.stop()`等待匹配epoch、健康且新鲜的反馈及四轴不再Operation Enabled，超时约0.3秒会报告停车未确认，不能在新界面将它显示为停车成功。反馈新鲜窗口0.25秒；原生循环大于50 ms的时序异常会触发停止逻辑。

同一总线的 `motor.stop()/disable()` 会停止共享总线，当前ROS `stop`也停止整台机器人全部轴。新控制台若需要单轴停止/保持，需新增语义并验证，不能直接复用该调用当单轴STOP。

历史 `native/ethercat_agent.cpp` 使用IgH，仅保留资料。当前现场配置选择Eyou，不应恢复旧 `ros2_robot.service` 或并行运行两个主站。

## Robot B CANopen

使用Eyou CANopen SDK，`canopen_DeviceType_Canable`、1 Mbps、node1/2。初始化设节点Operational、Profile Torque模式、斜坡500和零力矩；ARM执行驱动使能，命令按配置的力矩上限800再次检查。

启动参数：

```text
eyou_canopen_agent --run <device_index> <watchdog_ms> <torque_slope> <max_abs_torque> <axis:node_id> ...
```

适配器启动前会执行 `sudo -n ip link set can0 down`，SDK随后初始化接口。它不是纯只读操作，部署时不能在另一CAN程序运行时试启动。运行环境需 `sdk_lib` 注入 `LD_LIBRARY_PATH`，库间存在动态依赖，不能只带 `libeu_canopen.so`。

Feedback中位置/速度仍是原始单位；Profile Torque不等于EtherCAT CST。共同接口统一的是逻辑力矩命令和状态，不代表两种驱动实时特性相同。

## 相机、雷达、机械臂和末端

- RGB：优先可用MJPG，其次YUYV；名称+USB路径识别彩色节点。断开后按约2秒重试重新发现；RealSense走RGB UVC，不依赖深度SDK。采集独立线程，JPEG质量75；只保留最新帧，跨机订阅compressed topic。
- 地面站需要同时展示采集FPS、接收FPS、最后帧年龄、重连计数，避免“机器人采集正常”掩盖接收中断。DDS的1400字节配置、相机独占及重插发现逻辑需要一并保留。
- 雷达：当前只有计数与健康状态。没有PointCloud2、地图或导航模块。后续点云显示需要单独实现发布/订阅，不能从已有统计接口中恢复点云。
- RM75：当前实现状态读取、关节/错误等反馈。没有关节运动、笛卡尔运动或末端动作命令。
- RS485：用户设备为睿尔曼末端485连接张大头驱动；当前 `enabled:false/backend:unavailable`。型号、地址、波特率、协议/校验、末端接口配置未在本地代码中落实。不能用猜测寄存器表替代厂商资料。
- `real_adapters/__init__.py`中的通用 `real` 类仍是占位；`realsense_depth.py`等是历史/可选实现，RGB配置不依赖它。

## 回零实现边界

在停止状态采集20个绝对力矩样本，阈值 `max(mean + 500, mean × 2)`；这是raw值，不是碰撞力牛顿数。按配置方向以0.001 m/s寻找力矩达到阈值的点，反向退出0.5秒，共3次，原始位置平均后设置并保存零点。

每次接近超时取配置600秒与按行程/速度推导值的较大者。`home_z`立即回复“已开始”，真正成功看 `Z_HOME`，失败看 `Z_HOME_ERROR`；`zero_z`只把当前位置设为零。现有判断没有独立力传感器标定，也没有连续样本确认、运动中自适应负载模型或3次命中离散度验收。重载A与轻载B不能据现有阈值推导相同物理碰撞力。

后续控制台接入前应把回零作为独立运行状态，处理回零/ARM/Auto/退出之间的互斥；现有回零线程绕过普通controller运动路径，不应宣称已有完整任务仲裁。
