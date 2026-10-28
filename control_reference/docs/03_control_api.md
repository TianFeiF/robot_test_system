# 地面站控制接口契约

地面站通过ROS 2连接机器人Agent，EtherCAT/CANopen原生驱动继续驻留机器人本机。SSH用于文件同步和部署，不用于周期运动控制。所有业务接口前缀为 `/robot_a` 或 `/robot_b`。

## 现有接口

| 相对名称 | 类型 | 语义/频率 |
|---|---|---|
| `heartbeat` | `robot_test_msgs/msg/RobotHeartbeat` | stamp、robot_id、sequence、uptime、state、control_mode；1 Hz |
| `diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | System和各设备状态，KeyValue值为字符串；5 Hz |
| `jog_command` | `robot_test_msgs/msg/JogCommand` | stamp、axis、velocity；速度轴；BEST_EFFORT、depth=1 |
| `torque_command` | `robot_test_msgs/msg/TorqueCommand` | stamp、axis、torque；力矩轴；BEST_EFFORT、depth=1 |
| `arm` | `std_srvs/srv/SetBool` | true使能；false停止并解除使能 |
| `stop` | `std_srvs/srv/Trigger` | 停止整台机器人全部电机、取消回零/自动循环 |
| `home_z` | `std_srvs/srv/Trigger` | 异步启动三次力矩碰撞回零 |
| `zero_z` | `std_srvs/srv/Trigger` | 停止状态把当前位置设为零，不运动找零 |
| `cameras/<id>/image_raw/compressed` | `sensor_msgs/msg/CompressedImage` | 当前现场RGB，sensor-data QoS，目标5 FPS |
| `cameras/<id>/image_raw` | `sensor_msgs/msg/Image` | 只有配置transport=raw时使用，bgr8 |
| `start_auto` / `stop_auto` | `std_srvs/srv/Trigger` | 旧测试循环启动/停止；停止同整机STOP |
| `auto_keepalive` | `builtin_interfaces/msg/Time` | 旧自动测试保活，当前地面站10 Hz |
| `test_event` | `robot_test_msgs/msg/TestEvent` | 事件ID、时间、类型、说明；volatile，无离线补发 |
| `inject_fault` | `robot_test_msgs/srv/InjectFault` | Mock测试专用，不是硬件故障复位 |

`System`包含 `armed`、`control_mode`、`auto_state`、`monitor_only`。设备level为0正常、1警告、2错误、3离线/未知；System可能因相机错误显示FAULT，不能仅依System红色推断运动总线故障，应结合轴与总线诊断。

没有现成的任务Action、位置目标服务、单轴使能服务、点云topic、机械臂运动服务或末端RS485命令服务。STOP ALL是地面站向两台机器人各自调用STOP，不是跨机器原子服务。

## 手动运动时序

1. 检查机器人在线、实时反馈、新鲜度和控制配置；不能拿最后一帧缓存当实时状态。
2. 地面站异步请求 `arm(data=true)`，等成功返回。旧GUI使用每机器人token/队列generation，避免延迟回复或残留命令重新触发动作。
3. 速度轴连续发布 `JogCommand`；力矩轴连续发布 `TorqueCommand`。当前GUI按住按键时10 Hz发布。
4. 每条消息使用发送端真实当前时间戳；Agent拒绝未来、过期、早于ARM/STOP epoch的手动命令，拒绝不刷新看门狗。不要用机器人时间偏移伪造时间戳绕过校时检查。
5. 松手、JOG窗口失焦或主动STOP时停止发布，并请求该机器人 `stop`。界面关闭对两台发送STOP。
6. 只有响应及反馈确认后显示停止完成；超时显示“未确认”，禁止把“请求已发送”当停车成功。

当前速度量：drive rad/s、Z m/s；夹持/支撑torque为raw。左右夹持逻辑到物理方向的转换在适配器完成，GUI不重复转换。

看门狗2秒是断流限制，不是2秒脉冲命令。发送单条非零命令后等待看门狗来停车不应成为新控制台常规操作方式。

## 时间和队列

- ROS消息使用ROS/系统时间；本机看门狗使用monotonic。
- 地面站准备ARM/start_auto时，要求在线且心跳时间差在 −0.1～+0.25秒范围；该值含传输延迟，不是精确时钟偏差估计。
- 地面站队列中超过300 ms的运动/使能等请求被丢弃；STOP单独优先队列，触发generation递增取消旧请求。
- Agent手动命令接受 `0 <= age < timeout` 且stamp晚于最近ARM/STOP，当前timeout=2秒。
- `auto_keepalive`历史实现检查消息年龄，但没有使用与JOG完全相同的epoch校验；正式任务协议需统一生命周期处理。
- Ground约3秒未收到heartbeat显示OFFLINE；图像约2秒无新帧清空。工程缓存必须包含“最后接收时间”和“数据是否有效”。

## 回零与零点显示

`home_z.success=true`只代表工作线程启动；终态事件在机器人CSV/标准日志中是 `Z_HOME` 或 `Z_HOME_ERROR`。现有自定义TestEvent是向机器人记录事件的输入，并不是完整的机器人动作结果发布通道。

新控制台应增加显式回零进度/终态接口（建议ROS Action或专门状态消息），显示搜索、退回、次数、已取消、失败原因。当前 `auto_state=IDLE` 不足以判断回零是否正在进行。

`zero_z`修改零点并保存配置，不代表物理归零。A Z 当前维修停用自动测试，不能因此默认允许一键回零；本次资料整理不执行任何该动作。

## 只读监控

site配置 `monitor_only:true`、EtherCAT `read_only:true`。STOP明确返回不支持硬件操作，退出只释放资源；不能用只读Agent承担运动停车。控制台启动时应区分监控/控制模式，而不是仅看到在线就启用按钮。

## 可复用桥接调用

复用 `GroundBridge.submit(rid, action, token, **data)` 和 `signals.result`、`snapshot`、`frame`。`arm`在旧桥中固定发true；解除使能通过stop。GUI不直接碰ROS executor或驱动句柄。`snapshot`用于状态，订阅返回不等于命令确认；对需要反馈的动作须独立维护request状态。

建议新增统一CommandGateway封装rid、命令合法性、资源互斥、连接状态、参数单位和结果。具体API名称属于后续控制台设计，不更改本包的冻结基线。
