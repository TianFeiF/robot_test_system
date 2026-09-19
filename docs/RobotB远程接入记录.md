# Robot B 部署记录（2026-09-19）

目标主机 `phi@192.168.10.63`（pc-02），免密 SSH；Ubuntu 22.04.5 x86_64、ROS 2 Humble。
工程部署在 `/home/phi/robot_test_system`，保留原 `ros2_robot_ws`、CAN 和图传工程。

## 配置与启动

- `config/robot_b_site/robot_b.yaml`：真实设备监控，禁止 ARM/运动。
- `config/robot_b_control/robot_b.yaml`：真实控制配置，轴映射、编码器和减速比经操作者确认与 A 相同；尚未进行 B 的运动验收。
- CAN 总线 `enabled: false`，不加载 support_left/support_right，不启动 CANopen 节点。
- 现场 domain 默认为 30，使用同一 `config/fastdds_site.xml` 进行 DDS 小包传输。

```bash
# Robot B 前台监控
./scripts/start_robot_b_site.sh
# Robot B 控制入口（勿与监控进程同时启动；启动不会自动使能）
./scripts/start_robot_b_control.sh
# 地面站同时监控 A/B
./scripts/start_ground_dual.sh
```

双机界面使用 `config/dual_robot_site` 中指向各自 site YAML 的相对符号链接，
两台机器人均使用监控界面，不复制两套容易失配的参数。

本次部署启动了临时用户服务 `robot-b-site-monitor`，未设置开机启动。
切换前台或控制配置前，先在 B 执行 `systemctl --user stop robot-b-site-monitor`。
服务采用 transient/collect，停止后 unit 会被回收；再次启动可使用上面的前台脚本。

## 设备

| 设备 | 配置 |
|---|---|
| EtherCAT | enp2s0；从站 0/1/2/3 = clamp_left/clamp_right/drive/z_axis；Eyou SDK |
| RGB 1 | USB Camera，USB 端口 3，当前 `/dev/video0` |
| RGB 2 | RealSense RGB，USB 端口 2 的 1.3 接口，当前 `/dev/video6` |
| RGB 3 | S-YUE 8MP USB Camera，USB 端口 1，当前 `/dev/video8` |
| 雷达 | MID360s，192.168.10.73；SDK 接收端为 192.168.10.63 |

相机均为 640×480、目标 5 FPS、JPEG 彩色视频；选择器按 USB 路径和名称发现彩色节点，
不依赖固定 video 编号，不采集深度。SDK 雷达配置类型键为 `Mid360s`，不能照抄 A 的 `MID360`。
本工程目前提供点/包/IMU 接收统计，没有地面站点云显示。

## 构建与权限

已成功构建 5 个 ROS 包。B 原有 20250807 版 Eyou SDK 位于 `/home/phi/下载/{include,lib}`，
辅助程序虽能编译并通过自检，但实机初始化报 `ec_statecheck failed`。
将 A 已验证的 20260109 SDK 放入本工程 `.local-deps/eyou_ethercat_sdk_x86_64_linux_gnu_20260109`，
重新编译后四从站进入 OP，反馈正常。原 SDK 未覆盖，旧辅助程序保存为
`.local-deps/bin/eyou_agent_20250807_backup`。构建脚本优先寻找本工程缓存，其次为下载目录，
仍支持 `ROBOT_TEST_EYOU_SDK` 指定路径。Livox SDK2 复用 A 已验证的源码并保留许可，在 B 静态编译。

```bash
./scripts/build_eyou_helper.sh
./scripts/build_livox_helper.sh
source /opt/ros/humble/setup.bash
cd ros2_ws
PYTHONNOUSERSITE=1 colcon build --symlink-install --packages-up-to robot_test_agent robot_test_bringup
```

重新编译 Eyou 程序会清除文件 capability，EtherCAT 运行需要相应原始网络权限。
操作者已明确授权，为 `.local-deps/bin/eyou_agent` 设置了 `cap_net_raw=ep`。
SDK 请求实时线程优先级仍有权限警告；本次未扩大到实时调度权限，监控中时序故障计数为 0，
不能据此认定运动控制的实时性已经验收。

密码未写入配置、脚本或文档。原有 systemd unit 内容均已被注释，未修改它们。
源码同步不包含地面站的 `.venv`、构建产物、日志和 `.git`，依赖在目标机独立构建。

## 验证结果

- 三路真实彩色视频跨机解码 60 秒：300/289/300 帧，最大间隔 0.208/0.405/0.208 秒，
  解码错误和超过两秒间隔均为 0。
- MID360s 正常接收约 200000 点/秒、200 IMU 包/秒，设备类型反馈 35，命令错误为 0。
- 新版 SDK：EtherCAT 4 个从站均为 OP，`healthy=True`，API/时序错误为 0。
  四轴 `enabled=False`，System `armed=False`，未进行 JOG、力矩加载或找零。
- 加入 EtherCAT 后再次通过只读 ROS/Qt 集成检查：B 在线、三路预览正常、雷达和总线正常、CAN/支撑轴不在设备列表。
- `logs/robot_b_deploy_validation/rgb.json`、`final_status.json` 和 `dual_monitor.png` 为地面站产物。
  截图时 A 没有在线；本次没有启动或重启 A。
- B 当前保留 `robot-b-site-monitor` 临时监控服务运行；不是开机自启服务。
