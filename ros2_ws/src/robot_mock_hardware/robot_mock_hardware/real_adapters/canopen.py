"""Shared CANopen bus owner for Robot B support motors."""

import json
import math
import os
import selectors
import subprocess
import threading
import time

from robot_test_core.adapters import DeviceAdapter, MotorAdapter
from robot_test_core.models import DeviceState, DeviceStatus


class CANopenBus(DeviceAdapter):
    """One native SDK process shared by all CANopen axes."""

    def __init__(self, config: dict):
        self.config = config

        self.condition = threading.Condition()

        self.process = None
        self.thread = None

        self.snapshot = None
        self.sample_time = 0.0

        self.error = ""
        self.last_backend_line = ""

        self.epoch = 0
        self.sequence = 0

        self.arm_requested = False

        self.quit = threading.Event()

        # axis -> node_id
        self.axes = {}

    def register_axis(
        self,
        axis: str,
        node_id: int,
    ) -> None:
        with self.condition:
            if self.process is not None:
                raise RuntimeError(
                    "Cannot register CANopen axis after backend start"
                )

            node_id = int(node_id)

            if not 1 <= node_id <= 127:
                raise ValueError(
                    f"Invalid CANopen node id: {node_id}"
                )

            if axis in self.axes:
                raise ValueError(
                    f"Duplicate CANopen axis: {axis}"
                )

            if node_id in self.axes.values():
                raise ValueError(
                    f"Duplicate CANopen node id: {node_id}"
                )

            self.axes[axis] = node_id

    def connect(self) -> None:
        with self.condition:
            if self.process is not None:
                return

            if not self.axes:
                raise RuntimeError(
                    "No CANopen axes registered"
                )

            executable = self.config["executable"]

            watchdog_ms = int(
                self.config.get(
                    "watchdog_ms",
                    500,
                )
            )

            torque_slope = int(
                self.config.get(
                    "torque_slope",
                    500,
                )
            )

            max_abs_torque = int(
                self.config.get(
                    "max_abs_torque",
                    1000,
                )
            )

            device_index = int(
                self.config.get(
                    "device_index",
                    0,
                )
            )

            interface = self.config.get(
                "interface",
                f"can{device_index}",
            )

            bitrate = int(
                self.config.get(
                    "bitrate",
                    1000000,
                )
            )

            # 厂家 SocketCAN backend:
            # devIndex 0 -> can0
            # devIndex 1 -> can1
            if interface != f"can{device_index}":
                raise ValueError(
                    f"Eyou CANopen SDK maps device_index "
                    f"{device_index} to can{device_index}; "
                    f"configured interface is {interface}"
                )

            if bitrate != 1000000:
                raise ValueError(
                    "This backend currently supports "
                    "the vendor SDK at 1 Mbps only"
                )

            # 厂家 SDK initDLL() 内部会执行：
            #
            # sudo ip link set can0 up type can ...
            #
            # 如果 can0 已经 UP，
            # SDK 会报 Device or resource busy。
            #
            # 因此启动 native process 前，
            # 主动把接口恢复到 DOWN。
            reset = subprocess.run(
                [
                    "sudo",
                    "-n",
                    "ip",
                    "link",
                    "set",
                    interface,
                    "down",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )

            if reset.returncode != 0:
                raise RuntimeError(
                    "Cannot prepare CAN interface "
                    "without passwordless sudo: "
                    + (
                        reset.stderr.strip()
                        or
                        f"ip link set {interface} down failed"
                    )
                )

            args = [
                executable,
                "--run",
                str(device_index),
                str(watchdog_ms),
                str(torque_slope),
                str(max_abs_torque),
            ]

            # 例如：
            #
            # support_left:1
            # support_right:2
            args.extend(
                f"{axis}:{node_id}"
                for axis, node_id
                in sorted(self.axes.items())
            )

            env = os.environ.copy()

            sdk_lib = self.config.get(
                "sdk_lib"
            )

            if sdk_lib:
                env["LD_LIBRARY_PATH"] = (
                    sdk_lib
                    + ":"
                    + env.get(
                        "LD_LIBRARY_PATH",
                        "",
                    )
                )

            log_path = self.config.get(
                "log_file"
            )

            log = (
                open(log_path, "ab")
                if log_path
                else None
            )

            try:
                self.process = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=(
                        log
                        if log
                        else subprocess.DEVNULL
                    ),
                    env=env,
                    bufsize=0,
                )
            finally:
                if log:
                    log.close()

            os.set_blocking(
                self.process.stdin.fileno(),
                False,
            )

            self.thread = threading.Thread(
                target=self._read,
                daemon=True,
                name="canopen-telemetry",
            )

            self.thread.start()

            # 启动时等第一帧 telemetry。
            # 如果 SDK 初始化直接失败，
            # 不要让 RobotController 假装连接成功。
            deadline = (
                time.monotonic()
                + 3.0
            )

            while (
                self.snapshot is None
                and not self.error
                and time.monotonic() < deadline
            ):
                if self.process.poll() is not None:
                    self.error = (
                        "CANopen process exited: "
                        f"{self.process.returncode}"
                    )
                    break

                self.condition.wait(
                    timeout=max(
                        0.0,
                        deadline
                        - time.monotonic(),
                    )
                )

            if self.snapshot is None:
                raise RuntimeError(
                    self.error
                    or
                    "No CANopen telemetry "
                    "after backend start"
                )

    def _read(self) -> None:
        selector = (
            selectors.DefaultSelector()
        )

        selector.register(
            self.process.stdout,
            selectors.EVENT_READ,
        )

        pending = b""

        try:
            while not self.quit.is_set():
                if not selector.select(
                    timeout=0.2
                ):
                    if (
                        self.process.poll()
                        is not None
                    ):
                        raise RuntimeError(
                            "CANopen process exited: "
                            f"{self.process.returncode}"
                        )

                    continue

                chunk = os.read(
                    self.process.stdout.fileno(),
                    8192,
                )

                if not chunk:
                    raise RuntimeError(
                        "CANopen process exited: "
                        f"{self.process.poll()}"
                    )

                pending += chunk

                while b"\n" in pending:
                    line, pending = (
                        pending.split(
                            b"\n",
                            1,
                        )
                    )

                    line = line.strip()

                    if not line:
                        continue

                    # 厂家 SDK 自己会向 stdout 打日志。
                    # 我们只解析带 @RTS 前缀的行。
                    if not line.startswith(
                        b"@RTS "
                    ):
                        self.last_backend_line = (
                            line.decode(
                                "utf-8",
                                errors="replace",
                            )[-500:]
                        )
                        continue

                    data = json.loads(
                        line[5:]
                    )

                    with self.condition:
                        self.snapshot = data

                        self.sample_time = (
                            time.monotonic()
                        )

                        self.condition.notify_all()

                if len(pending) > 65536:
                    raise ValueError(
                        "Invalid CANopen "
                        "telemetry framing"
                    )

        except Exception as exc:
            with self.condition:
                self.error = str(exc)

                self.condition.notify_all()

        finally:
            selector.close()

    def _send(
        self,
        command: str,
    ) -> None:
        if (
            self.process is None
            or self.process.poll()
            is not None
        ):
            raise RuntimeError(
                "CANopen backend not running"
            )

        data = (
            command + "\n"
        ).encode("ascii")

        written = os.write(
            self.process.stdin.fileno(),
            data,
        )

        if written != len(data):
            raise RuntimeError(
                "CANopen command pipe full"
            )

    def _fresh(self) -> bool:
        return (
            self.snapshot is not None
            and
            time.monotonic()
            - self.sample_time
            < 0.35
            and
            not self.error
        )

    def arm(self) -> None:
        with self.condition:
            if self.arm_requested:
                return

            if (
                not self._fresh()
                or not self.snapshot.get(
                    "healthy",
                    False,
                )
            ):
                raise RuntimeError(
                    "CANopen is not ready"
                )

            self.epoch = (
                time.monotonic_ns()
            )

            self.sequence = 0

            self._send(
                f"ARM "
                f"{self.epoch} "
                f"{time.monotonic_ns()}"
            )

            self.arm_requested = True

            # 等 native 确认已经真正进入 0x0F
            deadline = (
                time.monotonic()
                + 0.4
            )

            while (
                time.monotonic()
                < deadline
            ):
                if (
                    self._fresh()
                    and
                    self.snapshot.get(
                        "epoch"
                    )
                    == self.epoch
                    and
                    self.snapshot.get(
                        "armed",
                        False,
                    )
                ):
                    return

                self.condition.wait(
                    timeout=max(
                        0.0,
                        deadline
                        - time.monotonic(),
                    )
                )

            self.arm_requested = False

            raise RuntimeError(
                "CANopen arm "
                "acknowledgment timeout"
            )

    def command(
        self,
        axis: str,
        torque_raw: int,
    ) -> None:
        with self.condition:
            if axis not in self.axes:
                raise ValueError(
                    "Unknown CANopen axis: "
                    f"{axis}"
                )

            if (
                not self.arm_requested
                or not self._fresh()
            ):
                raise RuntimeError(
                    "CANopen command rejected: "
                    "disarmed or stale feedback"
                )

            max_abs_torque = int(
                self.config.get(
                    "max_abs_torque",
                    1000,
                )
            )

            torque_raw = int(
                torque_raw
            )

            if (
                abs(torque_raw)
                > max_abs_torque
            ):
                raise ValueError(
                    "Torque exceeds native "
                    "CANopen safety limit"
                )

            self.sequence += 1

            self._send(
                f"CMD "
                f"{self.epoch} "
                f"{self.sequence} "
                f"{time.monotonic_ns()} "
                f"{axis} "
                f"{torque_raw}"
            )

    def stop(self) -> None:
        with self.condition:
            already_stopped = (
                not self.arm_requested
                and self._fresh()
                and
                self.snapshot.get(
                    "healthy",
                    False,
                )
                and
                not self.snapshot.get(
                    "armed",
                    False,
                )
                and
                self.snapshot.get(
                    "epoch"
                )
                == self.epoch
                and
                all(
                    not bool(
                        n.get(
                            "enabled"
                        )
                    )
                    for n in
                    self.snapshot.get(
                        "nodes",
                        [],
                    )
                )
            )

            if already_stopped:
                return

            self.arm_requested = False

            self.epoch = (
                time.monotonic_ns()
            )

            self.sequence = 0

            self._send(
                f"STOP {self.epoch}"
            )

            deadline = (
                time.monotonic()
                + 0.6
            )

            while (
                time.monotonic()
                < deadline
            ):
                if (
                    self._fresh()
                    and
                    self.snapshot.get(
                        "epoch"
                    )
                    == self.epoch
                    and
                    not self.snapshot.get(
                        "armed",
                        False,
                    )
                    and
                    all(
                        not bool(
                            n.get(
                                "enabled"
                            )
                        )
                        for n in
                        self.snapshot.get(
                            "nodes",
                            [],
                        )
                    )
                ):
                    return

                self.condition.wait(
                    timeout=max(
                        0.0,
                        deadline
                        - time.monotonic(),
                    )
                )

            raise RuntimeError(
                "CANopen disable "
                "acknowledgment timeout"
            )

    def node_snapshot(
        self,
        axis: str,
    ):
        with self.condition:
            if not self.snapshot:
                return None

            for node in (
                self.snapshot.get(
                    "nodes",
                    [],
                )
            ):
                if (
                    node.get("axis")
                    == axis
                ):
                    return dict(node)

            return None

    def get_status(self) -> DeviceStatus:
        with self.condition:
            if not self._fresh():
                values = {
                    "backend":
                        "eyou_canopen",

                    "interface":
                        self.config.get(
                            "interface",
                            "can0",
                        ),
                }

                if self.last_backend_line:
                    values[
                        "last_backend_line"
                    ] = (
                        self.last_backend_line
                    )

                return DeviceStatus(
                    DeviceState.OFFLINE,

                    self.error
                    or
                    "No fresh CANopen "
                    "feedback",

                    values,
                )

            data = self.snapshot

            values = {
                k: v
                for k, v
                in data.items()
                if k != "nodes"
            }

            values.update(
                backend="eyou_canopen",

                interface=
                    self.config.get(
                        "interface",
                        "can0",
                    ),

                device_index=
                    int(
                        self.config.get(
                            "device_index",
                            0,
                        )
                    ),

                axis_count=
                    len(self.axes),
            )

            # Python 认为已经 ARM，
            # 但 native 因 watchdog 自己解除，
            # 则报告 latch fault。
            latched = (
                self.arm_requested
                and
                data.get("epoch")
                == self.epoch
                and
                not data.get(
                    "armed",
                    False,
                )
            )

            state = (
                DeviceState.OK
                if
                data.get(
                    "healthy",
                    False,
                )
                and not latched
                else
                DeviceState.ERROR
            )

            detail = (
                "CANopen watchdog/"
                "stop latch"
                if latched
                else
                "CANopen SDK feedback"
            )

            return DeviceStatus(
                state,
                detail,
                values,
            )

    def disconnect(self) -> None:
        process = self.process

        if process is None:
            return

        try:
            if process.poll() is None:
                try:
                    if self.arm_requested:
                        self.stop()
                except Exception:
                    pass

                process.terminate()

                try:
                    process.wait(
                        timeout=2.0
                    )
                except (
                    subprocess.TimeoutExpired
                ):
                    process.kill()

                    process.wait(
                        timeout=1.0
                    )

        finally:
            self.quit.set()

            if self.thread:
                self.thread.join(
                    timeout=1.0
                )

            if process.stdin:
                process.stdin.close()

            if process.stdout:
                process.stdout.close()

            self.process = None


class CANopenMotor(MotorAdapter):
    def __init__(
        self,
        bus: CANopenBus,
        config: dict,
    ):
        self.bus = bus
        self.config = config

        self.axis = (
            config["axis_name"]
        )

        self.node_id = int(
            config["node_id"]
        )

        self.sign = int(
            config.get(
                "torque_sign",
                1,
            )
        )

        if self.sign not in (-1, 1):
            raise ValueError(
                f"{self.axis}: "
                "torque_sign must "
                "be +1 or -1"
            )

        if (
            config.get(
                "control_mode"
            )
            != "torque"
        ):
            raise ValueError(
                f"{self.axis}: "
                "real CANopen motor "
                "must use "
                "control_mode: torque"
            )

        # 这里只注册映射。
        # 真正 initDLL 只有 CANopenBus 一次。
        self.bus.register_axis(
            self.axis,
            self.node_id,
        )

    def connect(self) -> None:
        self.bus.connect()

    def disconnect(self) -> None:
        # Shared bus
        pass

    def enable(self) -> None:
        self.bus.arm()

    def disable(self) -> None:
        self.bus.stop()

    def stop(self) -> None:
        self.bus.stop()

    def jog(
        self,
        velocity: float,
    ) -> None:
        raise ValueError(
            "CANopen support axis "
            "is torque controlled"
        )

    def set_torque(
        self,
        torque: float,
    ) -> None:
        if not math.isfinite(
            torque
        ):
            raise ValueError(
                "Torque must be finite"
            )

        minimum = float(
            self.config.get(
                "torque_raw_min",
                -1000,
            )
        )

        maximum = float(
            self.config.get(
                "torque_raw_max",
                1000,
            )
        )

        if not (
            minimum
            <= torque
            <= maximum
        ):
            raise ValueError(
                "Torque outside axis "
                f"limit [{minimum}, "
                f"{maximum}]"
            )

        # torque_sign 用来解决左右机械安装方向
        raw = (
            int(round(torque))
            * self.sign
        )

        self.bus.command(
            self.axis,
            raw,
        )

    def get_status(
        self,
    ) -> DeviceStatus:
        bus_status = (
            self.bus.get_status()
        )

        node = (
            self.bus.node_snapshot(
                self.axis
            )
        )

        if node is None:
            return DeviceStatus(
                bus_status.state,
                bus_status.detail,
                {
                    "backend":
                        "eyou_canopen",

                    "node_id":
                        self.node_id,

                    "control_mode":
                        "torque",
                },
            )

        values = dict(node)

        values.update(
            backend="eyou_canopen",

            control_mode="torque",

            commanded_torque_sign=
                self.sign,

            position=
                node.get(
                    "position_raw",
                    float("nan"),
                ),

            velocity=
                node.get(
                    "velocity_raw",
                    float("nan"),
                ),

            position_unit=
                "encoder_count_raw",

            velocity_unit=
                "drive_raw",

            torque_unit=
                "drive_raw",
        )

        if not node.get(
            "healthy",
            False,
        ):
            return DeviceStatus(
                DeviceState.ERROR,
                "CANopen node "
                "feedback fault",
                values,
            )

        return DeviceStatus(
            bus_status.state,
            bus_status.detail,
            values,
        )

    def get_position(self) -> float:
        node = (
            self.bus.node_snapshot(
                self.axis
            )
        )

        if not node:
            return float("nan")

        return float(
            node.get(
                "position_raw",
                float("nan"),
            )
        )

    def get_velocity(self) -> float:
        node = (
            self.bus.node_snapshot(
                self.axis
            )
        )

        if not node:
            return float("nan")

        return float(
            node.get(
                "velocity_raw",
                float("nan"),
            )
        )

    def get_error(self) -> str:
        node = (
            self.bus.node_snapshot(
                self.axis
            )
        )

        if not node:
            return (
                "No CANopen feedback"
            )

        if node.get("fault"):
            return (
                "CANopen fault "
                f"error_code="
                f"{node.get('error_code')} "
                f"statusword="
                f"{node.get('statusword')}"
            )

        return ""
