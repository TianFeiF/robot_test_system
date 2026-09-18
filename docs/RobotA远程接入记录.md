# Robot A 远程接入记录（2026-09-18）

机器人：`phi@192.168.10.3`，免密 SSH。工程部署在 `/home/phi/robot_test_system`。Ubuntu 22.04.5、ROS 2 Humble。保留原有 `/home/phi/ros2_robot_ws`、EtherCAT、相机等工程，未升级系统或 ROS。

**当前已按操作者要求停止本次监控服务及其采集子进程。电机没有使能，没有执行 JOG、力矩加载或找零。** `run_sender.service` 是原有图传服务，由操作者停止，本次未恢复或修改其开机配置。

## 已实现与实际验证

| 设备/功能 | 结果及边界 |
|---|---|
| 跨机 ROS 通信 | 地面站收到 Robot A Heartbeat、Diagnostics；测试事件在机器人 CSV 落盘 |
| USB 相机 | 实际画面，稳定设备路径，采集约 5 FPS |
| D456 彩色 | UVC 实际画面，约 5 FPS |
| D456 深度 | 原生 librealsense 深度采集及伪彩色预览，约 5 FPS；没有输出标定深度 ROS topic 或点云 |
| 三路图像传输 | JPEG CompressedImage；最终 20 秒验收收到 66/68/70 帧；实际跨网到达率受链路影响 |
| MID360s，192.168.10.23 | SDK 检测类型 35，真实点数据约 200,000 点/s、IMU 约 200 包/s；诊断和 CSV 保存累计计数，不保存完整点云，也未添加 PointCloud2 发布 |
| RM75，192.168.10.18:8080 | 使用已有 SDK 读取 7 关节角度及错误码；当前返回 4116，保留 ERROR 显示，未擅自清错或执行运动 |
| EtherCAT 四轴 | 初期成功读到状态字、编码器位置/速度；后续链路出现 CRC/帧错误和 CoE 超时，当前不能认为通信稳定 |
| RS485 | 按操作者要求暂缓，现场配置禁用 |

D456 的 librealsense 序列号为 `318122304261`，V4L 的设备路径标识含 `412243060479`。两种接口的标识不同，配置按实际枚举结果保存，不互相替换。

原始 BGR 图像跨网只收到约 3～4 帧/20 秒；JPEG 改动后，两路阶段达到 106/102 帧/20 秒。压缩在机器人采集线程中执行，地面站 ROS 线程解码，Qt 主线程只更新界面。默认 Mock 配置仍使用原始图像。

## 现场参数（操作者提供）

| 从站 | 轴 | 控制模式/参数 |
|---|---|---|
| 0 | clamp_left | 力矩原始值 0～1000 |
| 1 | clamp_right | 力矩原始值 0～1000 |
| 2 | drive | 16 位编码器、减速比 51，输出侧最大 60 rpm |
| 3 | z_axis | 16 位编码器、减速比 101、丝杆导程 20 mm，电机侧最大 60 rpm，行程 0～300 mm |

按每圈 `2^16 = 65536` 计数换算（旧代码用 65535，需后续实机量测确认厂商定义）：

- drive：`counts / (65536 × 51) × 2π` rad；最大 `2π` rad/s。
- z_axis：`counts / (65536 × 101) × 0.02` m；最大 `0.02 / 101` m/s，即约 `0.19802` mm/s。
- 夹持轴的力矩是驱动器原始指令，不是 Nm；尚无夹持轴位置/速度的减速比换算依据。
- 默认准备的低速测试值：drive `0.05 rad/s`，z_axis `0.05 mm/s`，夹持力矩原始值 `50`。这些值尚未用于实机运动。
- STOP/失联策略：操作者允许归零并去使能，本次后端按此策略实现。

`z_zero_counts` 仍为 `null`。不知道当前物理零点及方向，不把当前编码器数值自动当作零位。控制后端和界面均拦截未标定的 Z 运动；没有实现碰机械限位找零。旧工程把从站 0 当直线轴并包含自动碰限位逻辑，不能直接套用到当前映射。

## 两套配置

- `config/robot_a_site/robot_a.yaml`：默认现场**监控**，真实传感器 + EtherCAT SDO 只读查询，`monitor_only: true`。JOG、AUTO 禁用；它不能执行真实电机 STOP，STOP 服务会明确返回失败，不声称已停机。
- `config/robot_a_control/robot_a.yaml`：待继续联调的**控制配置**。同一 Agent/Adapter 架构，四轴共享一个原生 IgH 主站进程。当前不能作为已验收配置使用。自动循环禁用，Z 未标定锁止。
- `config/robot_a_site/mid360s.json`：只连接 `192.168.10.23`，接收主机 `192.168.10.3`。SDK 会配置点流目的地址、数据格式及正常采集模式。

控制后端 `native/ethercat_agent.cpp` 已编译并通过不连接硬件的自测：显式 arm epoch、过期/重复指令拒绝、独立 500 ms Watchdog、总线/周期故障停止、力矩/速度范围检查、Z 零位和软限位检查。只有收到有效轴指令才请求该轴使能。Python 退出时原生进程收到父进程退出信号，尝试归零去使能后释放主站。硬件 PDO watchdog 已请求开启，但**进程卡死或总线断开时驱动器的实际反应尚未实测**。

当前原生程序中的轴映射、编码器比例、模式、速度硬上限和 Z 行程是此 Robot A 的固定参数；改硬件参数必须同时修改原生程序并重编译，不能只改 YAML。YAML 的 JOG 测试值可以降低指令幅度，但不能提高原生硬上限。

新增 `/robot_a/torque_command`（`robot_test_msgs/TorqueCommand`）：时间戳、轴名、torque。力矩轴拒绝速度 JOG，速度轴拒绝力矩指令；夹持操作按钮显示 `TORQUE 50 (hold)` / `TORQUE 0 (hold)`，松开后 STOP。新消息已在两端重新构建。

## EtherCAT 当前阻塞

2026-09-18 原生后端首次仅建立 PDO 通信、未发送 ARM 时：

- 从站未稳定进入 OP，Domain WorkingCounter 为 `0/12`。
- CoE 下载应答超时，PDO 映射过程失败，出现 AL `0x001D` / `0x001E`。
- `enp2s0` 为 100 Mb/s 全双工，但网卡接收 CRC 错误持续增加（观察到约 7449 → 8062），并伴随帧错误。
- 后续只读查询也出现失败，界面如实显示 OFFLINE。

需要操作者检查物理链路、串联线和供电，再继续核实 PDO 配置；当前证据不足以把问题完全归因于网线。操作者已要求暂停测试，自行处理硬件。本次没有尝试盲目清错、驱动器复位或持久化参数写入。

## 恢复监控

硬件处理完后，机器人端：

```bash
ssh phi@192.168.10.3
cd /home/phi/robot_test_system
./scripts/start_robot_a_site.sh
```

地面站端：

```bash
cd /home/sgcc/robot_test_system
./scripts/start_ground_site.sh
```

三端原则仍是一个 namespace 只启动一个 Agent。现场配置只显示 Robot A；此时不要再启动同 domain 的本机 Mock Robot A。默认 `ROS_DOMAIN_ID=0`、`ROS_LOCALHOST_ONLY=0`。可在两端显式设置相同 `ROBOT_TEST_SESSION` 对齐日志目录。

本次临时用户服务名为 `robot-a-site-monitor`，当前已停止，未设置开机自启。若单元仍存在，可在机器人端 `systemctl --user start robot-a-site-monitor` 恢复，`systemctl --user stop robot-a-site-monitor` 停止；勿与前台脚本同时启动。

控制配置留给链路和零位确认后的联调：两端分别设置 `ROBOT_TEST_CONFIG_DIR` 为各自工程下 `config/robot_a_control` 后使用相同启动脚本。**当前只提供配置入口，不代表真实控制验收通过。**

## 构建与依赖

```bash
# Robot A；依赖源码已放到本工程 .local-deps，未全局安装 Livox SDK。
cd /home/phi/robot_test_system
./scripts/build_robot_a_helpers.sh
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install --packages-up-to robot_test_agent robot_test_bringup
```

复用机器上现有 IgH、librealsense 2.57.0、RealMan x86 SDK。Livox 使用[官方 SDK2](https://github.com/Livox-SDK/Livox-SDK2)，源码 revision `08f523c930b2f0ba1e98a6afaa8d7476bf479908`，位于机器人 `.local-deps/Livox-SDK2`。其原有许可文件保留在依赖源码内。普通源码同步需排除 `.local-deps`、`.venv`、`logs`、`build/install/log`，不要覆盖其他驱动工程。

## 验证记录与产物

- 地面站 6 包、机器人 5 包构建成功。
- 17 项 Python 单元测试通过，含力矩范围/类型拒绝、Watchdog、单位换算、映射、陈旧反馈及只读模式。
- 既有 P0 ROS/Qt 回归通过：Mock JOG、释放停车、Watchdog、STOP ALL、断线重连和相机故障隔离。
- 原生 EtherCAT `--self-test` 通过；真实 PDO 建链测试未通过，未进行运动测试。
- 实机地面站界面验证通过：Robot A 在线、三路预览新鲜、监控模式运动按钮禁用。
- `logs/robot_a_site_validation/ground_probe.json`：真实诊断和收帧计数。
- `logs/robot_a_site_validation/ground_ui.png`、`camera_1.jpg`～`camera_3.jpg`：现场截图。
- 机器人日志：`/home/phi/robot_test_system/logs/robot_a_site_20260918/`，早期验证记录另在 `robot_a_site_validation`。
- `tests/site_readonly_probe.py` 仅用于单独启动的现场监控配置，验证图像/雷达、拒绝使能及测试事件。不要把它用于真实控制配置。

下一步：处理 EtherCAT 链路并复测；确认 Z 当前物理位置、方向和零位建立方式；核实 RM75 的 4116 错误；然后才进行四轴低速/低力矩、失联停车和找零的实机验收。
