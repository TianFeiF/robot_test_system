# 部署、构建与离线依赖

本包是源码资料归档，不包含完整SDK/系统包/虚拟环境，不能仅凭解压就在新机器驱动硬件。2026-10-28 两台SSH均 `No route to host`，没有补采现场库和配置；以下路径来自现有脚本与历史记录，联网后需再次核验。

## 现有启动入口

原工程根目录中：

| 场景 | 命令 |
|---|---|
| A真实控制 | `sudo ./scripts/start_robot_a_control.sh` |
| B真实控制 | `sudo ./scripts/start_robot_b_control.sh` |
| 地面站双机器人 | `./scripts/start_ground_dual.sh`（正常桌面用户环境） |
| A/B只读监控 | `./scripts/start_robot_a_site.sh` / `./scripts/start_robot_b_site.sh` |
| 三端一键测试启动 | `./scripts/start_site_all.sh` |

A工程 `/home/phi/robot_test_system`；B控制工程 `/home/phi/robot_test_system_git`。地面站 `config/dual_robot_site/*.yaml` 是指向两份control YAML的相对符号链接，归档保留链接。

`env.sh`读取工程内 `ros2_ws/install/setup.bash`，所以构建必须在 `ros2_ws` 内执行，不是在工程根目录。新控制台建议作为新包/新工作区运行，第一阶段继续连接已部署Agent。

```bash
# 在准备好的依赖环境内，从工程根目录构建；不启动驱动
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install
```

一键脚本依赖SSH、用户systemd服务、设备权限；它不会ARM，但会启动硬件会话，退出清理自己启动的会话。其预检查仍查 `eyou_agent`，而控制配置实际使用 `eyou_agent.zero-fix`，不能不检查就复制用于正式控制台。

## 软件与SDK清单

| 依赖 | 来源/本地历史路径 | 需要保留 |
|---|---|---|
| Ubuntu/ROS | Ubuntu22.04 x86_64、ROS2 Humble、Python3.10 | 系统版本、ROS包版本、离线deb依赖 |
| Python/Qt | `requirements.txt`：PySide6 6.8.3；numpy/OpenCV/PyYAML/psutil走Ubuntu包 | 匹配版本wheels/debs；不要混装NumPy2破坏系统OpenCV |
| EtherCAT SDK | 优先 `.local-deps/eyou_ethercat_sdk_x86_64_linux_gnu_20260109`，或A下载目录同名文件夹；B历史也使用 `/home/phi/下载/{include,lib}` | 实际运行版本的include/lib、example、许可证与版本证据 |
| CANopen SDK | B `.local-deps/eyou_canopen_sdk`（曾链接到旧工程目录） | 整个include/lib/example及许可；包括libeu_canopen、candrv、eds、resources、log及CAN底层库 |
| Livox SDK2 | `.local-deps/Livox-SDK2` | 源码、许可、版本、静态构建产物及依赖 |
| RM75 SDK | `/home/phi/ros2_robot_ws/src/ros2_rm_robot-humble/rm_driver` | `include/rm_driver`、`lib/linux_x86_c++_v1.1.3`、许可/版本 |
| IgH | 历史 `/home/phi/ethercat/include`、`/usr/local/lib` | 仅历史备查，不启动旧主站 |
| RealSense深度 | pkg-config realsense2 | 仅历史可选；当前RGB不依赖深度 |

本地 `.local-deps` 没有完整上述SDK，未冒充已备份。新机离线部署还需确认C++编译器、cmake、colcon、ament、ROS消息生成器、Fast DDS、系统视频/网络依赖。无需要求机器人联网下载，可在地面站准备同版本包后通过SSH传输。

## 构建脚本陷阱

- `build_eyou_helper.sh`构建 `.local-deps/bin/eyou_agent`，配置却指定 `.local-deps/bin/eyou_agent.zero-fix`。未来统一名称前，先在单独暂存目录构建、执行 `--self-test`，再按配置部署；不要生成新文件却仍运行旧文件。
- `build_eyou_canopen_helper.sh`使用B工程的SDK路径，运行由配置注入 `LD_LIBRARY_PATH`。用 `ldd`检查间接依赖，不能只看编译成功。
- `build_robot_a_helpers.sh`串联了旧IgH、RM75、Livox和深度构建，不是纯当前Eyou构建入口。新控制项目应拆分这些脚本。
- EtherCAT需要原始网口权限（sudo或已设置cap_net_raw）；重建二进制不保留capability。过去授权过的文件不代表新目录下新文件已有权限。
- CAN接口初始化有 `sudo -n ip link set ... down`，需要既有权限配置。现场不能并行运行旧ROS主站、旧相机sender、另一个Agent。
- B的雷达/日志部分绝对路径仍指旧 `/home/phi/robot_test_system`，不能全局替换成 `_git` 而不核对实际依赖和链接。

## 网络与时间

`site_network.sh`设置domain30、ROS_LOCALHOST_ONLY=0、Fast DDS配置。`fastdds_site.xml`将UDP最大消息设1400字节以减少IP分片问题，保留DDS自身分片。地面站RGB接收问题排查需同时看采集和接收状态。

`setup_site_time_sync.sh`以 `192.168.10.4` 为地面站时间源；它会修改系统服务，ground分支若缺chrony会调用apt。只作为部署资料，本次未执行。禁止在运动期间通过调整系统时间规避命令时间戳拒绝。

## 机器人再次可达后需要补采的资料

1. 两台当前control/site YAML、Livox JSON、源码差异和git提交；特别保存现场 `z_zero_counts`。
2. 当前实际运行的原生二进制、对应SDK include/lib/example/许可证、SHA-256、编译信息和 `ldd`依赖。
3. 版本信息：OS/ROS、Python/Qt、SDK版本；网卡名、CAN节点配置、相机USB路径；只收相关设备信息，不收SSH密钥或密码。
4. 原服务禁用状态、必要的设备权限/用户服务说明；不照搬未知系统服务。
5. 对照当前归档做差异合并，保留机器人现场更改，不将本地control YAML整体覆盖回去。

建议把补采资料放在新目录 `remote_evidence/<robot>/<采集时间>/`，注明“现场证据”；不要直接修改冻结 `baseline`。SDK例程可能含自动使能/回零，采集文件与运行例程是两件事。
