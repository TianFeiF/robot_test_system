# Z 轴力矩突变回零测试

两台机器人已经部署 `home_z` 服务。它不会在启动时自动执行；只有收到服务请求后才会动作。流程是：

1. 读取 Z 轴静止力矩，建立基线。
2. 按配置的 `direction` 低速向零点方向运动。
3. 当绝对力矩同时超过“基线 + `torque_delta_raw`”和“基线 × `torque_ratio`”时，记录当前编码器计数，认为碰到零点。
4. 反向退回 `backoff_sec`，重复 3 次。
5. 取 3 个碰撞计数的平均值写入 `z_zero_counts`，并立即启用该零点；机器人重启后从配置恢复。

当前控制配置：速度 `0.001 m/s`，退回 `0.5 s`，力矩增量阈值 `500`，比例阈值 `2.0`，单次寻找超时基准 `600 s`。找零超时会按 Z 轴配置行程自动放大，覆盖整段约 `500 mm` 行程；回零专用负向搜索允许到旧零点下约 `500 mm`，正常运动软件下限仍是 `-20 mm`。回零和手动运动看门狗均为 `2 s`。按当前速度，超时约为 `634 s`。阈值在 `config/robot_a_control/robot_a.yaml` 和 `config/robot_b_control/robot_b.yaml` 的 `hardware.ethercat.z_homing` 中，可根据实际力矩量程调整。不要为了消除误触发把阈值调到接近噪声。

## 测试步骤

先确认 Z 轴机械路径畅通、零点方向无误、夹持轴和其他机构不会同时动作。当前 `direction: -1` 表示编码器位置减小的方向是零点方向；若现场相反，停机后把它改成 `1`，再重新构建/复制配置。

分别在两台机器人上启动控制程序（启动后不会自动使能）：

```bash
# Robot A
cd /home/phi/robot_test_system
sudo ./scripts/start_robot_a_control.sh

# Robot B
cd /home/phi/robot_test_system_git
sudo ./scripts/start_robot_b_control.sh
```

在机器人终端或地面站环境中确认服务存在：

```bash
ros2 service list | grep home_z
```

一次只测试一台，保持另一台停止。Robot A：

```bash
ros2 service call /robot_a/home_z std_srvs/srv/Trigger "{}"
```

Robot B：

```bash
ros2 service call /robot_b/home_z std_srvs/srv/Trigger "{}"
```

服务响应只表示后台找零线程已经启动：`Z homing started; use STOP to cancel`。完成后在事件日志中会写入三次碰撞编码器计数和平均值，例如 `hits=[...], average=...`。随后检查：

```bash
grep -n 'z_zero_counts' config/robot_a_control/robot_a.yaml
grep -n 'z_zero_counts' config/robot_b_control/robot_b.yaml
tail -f logs/<本次启动目录>/robot_a_events.csv
```

事件应出现 `Z_HOME`，诊断中的 Z 轴 `homed` 应为 `True`。回零完成后必须再次执行 ARM/手动动作测试；回零服务结束时所有轴保持停止和去使能。

若返回 `found no torque spike`，先查看事件中的 threshold、当前 `torque_raw` 和连接状态，再调整阈值。若 Z 轴向远离零点运动，立即按 STOP，修改 `direction` 后重试。不要在未确认方向时连续重复测试。

地面站窗口也会显示 `HOME Z (3x TORQUE)` 按钮；它与上述服务相同。`ZERO Z (STOPPED)` 仍是当前位置直接置零，不执行碰撞检测。

## 地面站自动循环

两台机器人都重启控制程序后，再启动地面站。先让每台机器人完成一次回零，确认诊断中的 `z_referenced=True`，再分别选择 Robot A、Robot B 点击 `START AUTO TEST`。当前周期为：A/B 夹持力矩在 `±400` 间、B 支撑 CANopen 力矩在 `±800` 间每 5 秒换向（完整周期 10 秒）；左右夹持轴按安装方向映射，左侧物理输出为负、右侧为正；drive 不参与自动循环（仍可手动 JOG）；Robot A 的 Z 轴因同步带问题暂停自动循环；Robot B 的 Z 轴以 `0.01 m/s` 在回零点到 20 mm 区间往返。机械安全范围仍为零点下 20 mm 到零点上 500 mm。点击 `STOP AUTO TEST` 或 `STOP ALL` 后应立即停止并去使能。
