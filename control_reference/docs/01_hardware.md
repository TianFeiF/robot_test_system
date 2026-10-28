# 硬件、参数与状态

本表取自本次 `baseline/config/robot_{a,b}_control/robot_{a,b}.yaml` 和驱动源码。现场机器当前不可达，以下“当前”指本地代码基线。

## 主机与设备

| 项目 | Robot A | Robot B |
|---|---|---|
| SSH | `phi@192.168.10.3` | `phi@192.168.10.63` |
| 当前控制工程目录 | `/home/phi/robot_test_system` | `/home/phi/robot_test_system_git` |
| ROS namespace | `/robot_a` | `/robot_b` |
| EtherCAT | Eyou，专用口 `enp2s0`，4 从站 | 同 A |
| CANopen | 不使用 | `can0`、device_index=0、1 Mbps |
| 激光雷达 | MID360s，`192.168.10.23` | MID360s，`192.168.10.73` |
| 雷达 JSON 类型键 | `MID360` | `Mid360s` |
| RGB | 4 路 UVC，含 RealSense RGB | 3 路 UVC，含 RealSense/S-YUE |
| 机械臂 | RM75，`192.168.10.18:8080`，已实现状态读取 | 当前配置无此设备 |
| 末端 RS485 | 经睿尔曼机械臂末端 RS485 接张大头驱动；协议接入未实现 | 当前配置无此设备 |

雷达型号的口头命名相近，但 JSON 大小写/型号键不同，保持现场文件原样。地面站与机器人 ROS 使用 domain 30、Fast DDS；不要将 EtherCAT 专用口当作普通视频网口。

## 运动轴

| 轴 | 总线/编号 | 控制方式 | 对上层单位 | 当前限制/方向 |
|---|---|---|---|---|
| clamp_left（A/B） | EtherCAT 索引0，SDK ID1 | CST，mode 10 | 原始力矩值 | ±400；`torque_sign=-1` |
| clamp_right（A/B） | EtherCAT 索引1，SDK ID2 | CST，mode 10 | 原始力矩值 | ±400；`torque_sign=+1` |
| drive（A/B） | EtherCAT 索引2，SDK ID3 | CSV，mode 9 | rad、rad/s | 输出侧上限60 rpm，即2π rad/s |
| z_axis（A/B） | EtherCAT 索引3，SDK ID4 | CSV，mode 9 | m、m/s | 输出侧上限30 rpm，折合0.01 m/s |
| support_left（仅B） | CANopen node 1 | Profile Torque | 原始力矩值 | ±800；`torque_sign=+1` |
| support_right（仅B） | CANopen node 2 | Profile Torque | 原始力矩值 | ±800；`torque_sign=+1` |

上层给左右夹持相同的逻辑正力矩时，左驱动实际接收负值、右驱动接收正值。新控制台不应再次取反。

编码器与换算：

- drive：65536 count/rev，减速比51；`rad = position_raw × 2π / (65536×51)`；`raw_velocity = rad/s × 65536×51/(2π)`。
- Z：65536 count/rev，减速比101，丝杆导程0.02 m；`m = (position_raw − z_zero_counts) × 0.02/(65536×101)`；速度同尺度转换。
- Z 总行程500 mm。当前普通软件边界为 −20～500 mm，自动测试窗口为0～20 mm；三者不能混用。
- 显式回零期间，原生驱动向负方向搜索可到旧参考点下500 mm；这是历史回零搜索例外，不是普通控制范围。
- 用户现场定义“电机正转朝零点”；当前实际软件 `z_homing.direction=-1`。物理正转描述与逻辑位置正方向需分别记录，不能凭名称把现有软件方向改成 +1。
- 支撑轴位置/速度仍为驱动原始反馈，未配置编码器、减速比和工程单位换算。夹持轴也没有完整机械换算参数；旧界面显示的角度不应视为已标定机械量。

## 已完成测试后的配置状态

| 轴 | A 自动循环 | B 自动循环 | 手动配置 |
|---|---|---|---|
| drive | 关闭 | 关闭 | `jog_velocity=0.05 rad/s` |
| 左/右夹持 | ±400，5秒换向 | 同 A | 按键绝对值400 |
| Z | 关闭：同步带问题 | 0～20 mm，0.01 m/s往返 | `jog_velocity=0.00005 m/s` |
| 左/右支撑 | 无 | ±800，5秒换向 | 按键绝对值800 |

drive 仍保留10°/s的自动参数，但 `enabled:false`，不会执行。上述循环属于旧测试策略，控制台不应启动即执行。

手动命令丢失看门狗为2秒，EtherCAT和CANopen原生看门狗也为2秒。它不是“每次按按钮固定走2秒”：旧地面站按住连续发命令，松手发STOP。

A Z 的自动停用不是硬件隔离：手动与 `home_z` 仍可调用。新控制台应显著展示维修状态，不能把“轴未参与自动循环”解释为“该轴已修复”。本次不更改其现有接口。

## 标定和配置所有权

本地 YAML 的 `z_zero_counts` 分别为 A `-1582005`、B `-13988040`；这些只是快照数值，不代表机器人最新值。回零会在机器人端原子更新 YAML，不能通过整份本地 YAML 覆盖现场标定。后续建议将标定独立存储，再由控制台只读显示。

相机选择依据 `rgb_selector.name_regex` 和 `preferred_path`，完整端口映射见 [机器清单](../hardware_inventory.json)。现场采集640×480、目标5 FPS、JPEG彩色视频；不依赖固定 `/dev/videoN`，不要求深度可用。
