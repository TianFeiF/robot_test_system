# 本次资料核验记录

日期：2026-10-28。任务：保全测试工程并单独提取驱动资料，供后续地面站控制台开发。

## 已完成

- 完整复制native、scripts、config、六个ROS包源码、tests、原始docs、README、VALIDATION和requirements；包括工作树中尚未提交的修复。
- 逐文件比较抽出源码与原工作树，内容一致；相对配置符号链接保留且位于归档内部。
- 从A/B当前control YAML生成hardware_inventory.json，区分设备参数与测试策略。
- 对抽出的Python文件进行语法编译检查，通过。
- 使用抽出的六个ROS包在 `/tmp/robot-control-reference-check` 独立构建，通过；build/install/log在归档外，不污染原工作区或资料包。
- 构建robot_test_msgs时CMake提示CATKIN兼容变量未使用，无构建失败。
- 使用独立构建的安装环境运行抽出目录下的单元测试：33项通过。测试包含原生假SDK、命令/符号/时钟、监控STOP、相机及自动轴筛选；A Z与A/B drive保持自动停用。
- 生成逐文件SHA-256/符号链接清单和只读校验脚本；打包后再解压到临时目录校验。
- 原工程只增加本资料目录和README入口；本次没有修改实际驱动、运行配置或启动服务。

## 验证边界

没有执行真实电机动作、设备重新连接或完整Qt/ROS现场验收。上述测试成功不等于新的正式控制台已经完成，也不等于厂商SDK已在新机安装。

两台机器人本次SSH结果：

| 主机 | 结果 |
|---|---|
| phi@192.168.10.3 | No route to host |
| phi@192.168.10.63 | No route to host |

因此无法核对现场最近源码、依赖版本、二进制与标定；本包不包含现场SDK和运行库。后续补采项见 [部署与离线依赖](04_deployment.md)。历史接入记录保留为历史证据，不当作本日实测结果。

## 复现

资料完整性只需要Python标准库：

```bash
# 在资料包根目录
python3 tools/verify_bundle.py
```

构建和测试需要已安装的ROS2 Humble、colcon、C++工具链和项目Python依赖。下面只构建/测试，不启动机器人：

```bash
source /opt/ros/humble/setup.bash
colcon --log-base /tmp/control-reference-recheck/log build \
  --base-paths "$PWD/baseline/ros2_ws/src" \
  --build-base /tmp/control-reference-recheck/build \
  --install-base /tmp/control-reference-recheck/install --symlink-install
source /tmp/control-reference-recheck/install/setup.bash
# python3需来自具备PySide6及系统ROS依赖的环境
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
  python3 -m unittest discover -s baseline/tests -p 'test_*.py'
```

冻结资料不建议原地编辑。需要更新时创建新版本及新manifest，保留本版证据。
