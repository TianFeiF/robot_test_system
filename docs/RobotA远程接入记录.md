# Robot A 远程接入记录

## 2026-09-19：现场启动、视频分包与旧服务清理

本节为最新状态。机器人启动控制配置现在只需：

```bash
./scripts/start_robot_a_control.sh
```

地面站使用 `./scripts/start_ground_site.sh`；机器人只读模式使用
`./scripts/start_robot_a_site.sh`。三个入口默认 domain 30，仍允许显式指定
`ROS_DOMAIN_ID`；`ROBOT_TEST_CONFIG_DIR` 仍可覆盖配置目录。启动控制配置不会自动使能。

现场脚本通过 `scripts/site_network.sh` 加载 `config/fastdds_site.xml`，将 UDP
`maxMessageSize` 限制为 1400 字节，保留同机 SHM。图像由 DDS 分片，避免大 UDP 包在
1500 MTU 网络上形成大量 IP 分片。设置依据：[Fast DDS 2.6 transport 配置](https://fast-dds.docs.eprosima.com/en/2.6.x/fastdds/xml_configuration/transports.html)。
只改现场进程的配置，未修改系统 sysctl 或网卡；显式设置的 RMW/profile 环境变量保留。
**部署后两端都需重新启动现场进程**，已经运行的进程不会自动加载 XML。

独立测试使用与三路 JPEG 接近的 44000/23000/24000 字节消息，每路 5 Hz，
不读取相机、不加载电机。60 秒观测中，默认配置收到 145/144/143 条，最长间隔 8.2 秒；
1400 字节配置收到 301/300/300 条，最长间隔 0.21 秒，没有超过 2 秒的间隔。
地面站还观察到大量 IP 重组失败的累计计数；该计数包含其他程序流量，不能全部归因于本工程。

现场相机已更换：USB Camera 现在在 USB 端口 5，另一台是端口 6 的
`S-YUE 8MP USB Camera`，RealSense RGB 仍为端口 2 的 `1.3` 接口。
site/control 两份配置均扩展 USB 名称匹配并更新首台相机优选路径。
RGB 格式筛选和设备独占注册仍生效，避免把 RealSense 深度/红外节点当作彩色相机。

旧 `ros2_robot.service` 已复查为 `LoadState=not-found`、inactive；开机不会再通过该
unit 启动旧工程。`scripts/remove_legacy_robot_service.sh` 可用于清理同样的旧 unit，
需要本机 sudo 密码，先备份再停止/禁用/删除。此次操作者执行时 unit 已不存在。
旧的手动图传 `CAM_UDP/sender.py` 也已退出，避免占用相机；未删除其工程。

测试产物：`logs/rgb_mtu_validation/`，包括网络对照 JSON、真实 RGB 解码结果和
Mock ROS/Qt 回归日志。真实相机测试使用 `axes: {}`、`hardware: {}` 的临时监控配置，
没有启动电机驱动。修正相机匹配后，地面站 60 秒成功解码 300/289/300 帧，
最长间隔 0.214/0.404/0.215 秒，解码错误和超过两秒的间隔均为 0。
当前结果属于短时验证，仍需现场长时间运行观察热插拔和链路变化。

## 晚间更新：机器人修改合并与 RGB 传输排查

以下为 2026-09-18 的历史状态。机器人当时由操作者启动 control 配置，使用
`ROS_DOMAIN_ID=30`；本次未重启 Agent、未下发运动命令。当前 EtherCAT 使用 Eyou SDK，
不是下方早期记录中的 IgH 只读方案。

从机器人源码快照对比并保留了三处修改：control 配置 `allow_unreferenced_z: false`、
Livox 配置设备类型 `MID360`、RM75 错误数组 `[0]` 按正常状态处理。
快照位于本机 `/tmp/robot_a_review_20260918_2149/source/`，未用地面站旧版本覆盖机器人。

RGB 排查结果：

| 60 秒观测位置 | camera_1 | camera_2 | camera_3 |
|---|---:|---:|---:|
| 机器人本机收帧数 | 301 | 289 | 300 |
| 本机最大间隔（秒） | 0.201 | 0.400 | 0.201 |
| 地面站收帧数 | 112 | 111 | 115 |
| 地面站最大间隔（秒） | 14.391 | 10.206 | 10.206 |

以上是先后进行的观测，包含发现等待时间，不作为精确丢包率计算。对应期间采集诊断均正常，
机器人此前约四小时的相机日志也没有断线/重连计数。因此本次复现指向跨机图像传输；
不能据此排除其他时段的 USB 热插拔问题。独立话题 reliable 转发试验也出现 19～24 秒间隔，
未证明有改善；未切换生产 QoS。操作者确认 ping 重复包是已知正常现象，不将其认定为故障原因。
所有临时观察/转发进程均已退出。

地面站新增采集/接收 FPS 区分、收帧数、解码错误数、最长间隔，以及
`IMAGE_RX` 状态和 `IMAGE_RX_STALE` / `IMAGE_RX_OK` 事件日志。
采集正常但没有新图像时显示“采集正常 / 图像接收中断”，不再统一标为相机 OFFLINE。
这些改动在重启地面站后生效；机器人无需因此重启。

```bash
# 地面站连接当前已运行的 Robot A（监控界面）
ROS_DOMAIN_ID=30 ./scripts/start_ground_site.sh

# 独立只读探测，不调用任何运动服务
source scripts/env.sh
ROS_DOMAIN_ID=30 ROS_LOCALHOST_ONLY=0 python3 scripts/probe_rgb_transport.py --seconds 60
```

探测脚本统计收到的压缩消息，不验证 JPEG 解码；实际地面站统计成功解码的帧。
测试结果保存在 `logs/rgb_transport_review/`。21 项单元测试及 P0 ROS/Qt 回归通过，
包括多相机故障隔离、恢复和运动 Watchdog。跨机长间隔的根因尚未确定，不能宣称掉线已修复。

## 早期接入记录（历史）

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
