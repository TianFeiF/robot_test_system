#include <eu_canopen.h>

#include <atomic>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <unistd.h>

using Clock = std::chrono::steady_clock;

namespace {

std::atomic<bool> g_quit{false};

void signal_handler(int) {
    g_quit.store(true);
}

struct NodeInfo {
    std::string axis;
    huint8 id = 0;

    canopen_NodeState node_state = canopen_NodeState_Unknown_state;
    huint16 statusword = 0;

    hint16 actual_torque = 0;
    hint32 actual_velocity = 0;
    hint32 actual_position = 0;

    huint16 error_code = 0;
    canopen_OperateMode operation_mode = canopen_OperateMode_Reserve;

    bool healthy = false;
};

class CanopenAgent {
public:
    CanopenAgent(
        huint8 dev_index,
        int watchdog_ms,
        huint32 torque_slope,
        int max_abs_torque,
        std::map<std::string, huint8> axis_nodes)
        : dev_index_(dev_index),
          watchdog_(std::chrono::milliseconds(watchdog_ms)),
          torque_slope_(torque_slope),
          max_abs_torque_(max_abs_torque),
          axis_nodes_(std::move(axis_nodes))
    {
        for (const auto &[axis, id] : axis_nodes_) {
            NodeInfo info;
            info.axis = axis;
            info.id = id;
            nodes_[axis] = info;
        }
    }

    ~CanopenAgent() {
        shutdown();
    }

    bool init() {
        if (CANOPEN_SUCCESS !=
            canopen_initDLL(
                canopen_DeviceType_Canable,
                dev_index_,
                canopen_Baudrate_1000))
        {
            std::cerr << "CANopen init failed" << std::endl;
            return false;
        }

        initialized_ = true;

        for (const auto &[axis, id] : axis_nodes_) {
            if (!configure_node(axis, id)) {
                std::cerr
                    << "CANopen node setup failed: axis="
                    << axis
                    << " node="
                    << static_cast<int>(id)
                    << std::endl;

                safe_stop(false);
                return false;
            }
        }

        last_command_ = Clock::now();

        poll_feedback();
        emit_snapshot();

        return true;
    }

    int run() {
        const int old_flags = fcntl(STDIN_FILENO, F_GETFL, 0);

        if (old_flags >= 0) {
            fcntl(
                STDIN_FILENO,
                F_SETFL,
                old_flags | O_NONBLOCK);
        }

        std::string pending;

        auto next_feedback = Clock::now();

        while (!g_quit.load()) {
            read_commands(pending);

            const auto now = Clock::now();

            // Native watchdog:
            // ARM 后超过 watchdog_ms 没收到 CMD，
            // 两个支撑电机全部回 0 torque 并退出 Operation Enabled。
            if (armed_ &&
                now - last_command_ >= watchdog_)
            {
                ++watchdog_count_;
                safe_stop(false);
            }

            // 20 Hz feedback
            if (now >= next_feedback) {
                poll_feedback();
                emit_snapshot();

                next_feedback =
                    now + std::chrono::milliseconds(50);
            }

            std::this_thread::sleep_for(
                std::chrono::milliseconds(5));
        }

        safe_stop(false);

        poll_feedback();
        emit_snapshot();

        return 0;
    }

private:
    bool sdk_ok(int rc) {
        if (rc == CANOPEN_SUCCESS) {
            return true;
        }

        ++api_error_count_;
        return false;
    }

    bool configure_node(
        const std::string &axis,
        huint8 id)
    {
        // 确保 NMT Operational。
        // 你的 Node2 之前是 127 = Pre-Operational，
        // 这里会启动它。
        if (!sdk_ok(
                canopen_setNodeState(
                    dev_index_,
                    id,
                    canopen_NMTState_Start_Node)))
        {
            return false;
        }

        std::this_thread::sleep_for(
            std::chrono::milliseconds(5));

        // Profile Torque
        if (!sdk_ok(
                canopen_setOperateMode(
                    dev_index_,
                    id,
                    canopen_OperateMode_ProfileTorque,
                    100)))
        {
            return false;
        }

        if (!sdk_ok(
                canopen_setSyncCounter(
                    dev_index_,
                    id,
                    0,
                    100)))
        {
            return false;
        }

        if (!sdk_ok(
                canopen_setTorqueSlope(
                    dev_index_,
                    id,
                    torque_slope_,
                    100)))
        {
            return false;
        }

        // 初始化时永远先给 0 torque
        if (!sdk_ok(
                canopen_setTargetTorque(
                    dev_index_,
                    id,
                    0,
                    100)))
        {
            return false;
        }

        // Shutdown
        if (!sdk_ok(
                canopen_setControlword(
                    dev_index_,
                    id,
                    0x06,
                    100)))
        {
            return false;
        }

        std::this_thread::sleep_for(
            std::chrono::milliseconds(2));

        // Switch On
        // 注意：这里还没 Operation Enabled
        if (!sdk_ok(
                canopen_setControlword(
                    dev_index_,
                    id,
                    0x07,
                    100)))
        {
            return false;
        }

        std::this_thread::sleep_for(
            std::chrono::milliseconds(2));

        std::cerr
            << "Configured CANopen torque axis "
            << axis
            << " node="
            << static_cast<int>(id)
            << std::endl;

        return true;
    }

    bool enable_all() {
        for (const auto &[axis, id] : axis_nodes_) {
            (void)axis;

            // ARM 永远先清零
            if (!sdk_ok(
                    canopen_setTargetTorque(
                        dev_index_,
                        id,
                        0,
                        100)))
            {
                return false;
            }

            if (!sdk_ok(
                    canopen_setControlword(
                        dev_index_,
                        id,
                        0x06,
                        100)))
            {
                return false;
            }

            std::this_thread::sleep_for(
                std::chrono::milliseconds(2));

            if (!sdk_ok(
                    canopen_setControlword(
                        dev_index_,
                        id,
                        0x07,
                        100)))
            {
                return false;
            }

            std::this_thread::sleep_for(
                std::chrono::milliseconds(2));

            // Enable Operation
            if (!sdk_ok(
                    canopen_setControlword(
                        dev_index_,
                        id,
                        0x0F,
                        100)))
            {
                return false;
            }
        }

        return true;
    }

    void safe_stop(bool count_errors = true) {
        if (!initialized_) {
            armed_ = false;
            return;
        }

        for (const auto &[axis, id] : axis_nodes_) {
            (void)axis;

            // 第一优先：目标转矩清零
            const int rc_torque =
                canopen_setTargetTorque(
                    dev_index_,
                    id,
                    0,
                    50);

            // 然后退出 Operation Enabled
            // 保持 Switch On
            const int rc_control =
                canopen_setControlword(
                    dev_index_,
                    id,
                    0x07,
                    50);

            if (count_errors) {
                if (rc_torque != CANOPEN_SUCCESS) {
                    ++api_error_count_;
                }

                if (rc_control != CANOPEN_SUCCESS) {
                    ++api_error_count_;
                }
            }
        }

        armed_ = false;
    }

    void handle_line(const std::string &line) {
        std::istringstream iss(line);

        std::string op;
        iss >> op;

        if (op == "ARM") {
            uint64_t epoch = 0;
            uint64_t client_ns = 0;

            if (!(iss >> epoch >> client_ns)) {
                ++protocol_error_count_;
                return;
            }

            if (!all_nodes_healthy_) {
                ++protocol_error_count_;
                return;
            }

            safe_stop(false);

            if (!enable_all()) {
                safe_stop(false);
                return;
            }

            epoch_ = epoch;
            sequence_ = 0;
            armed_ = true;

            last_command_ = Clock::now();

            return;
        }

        if (op == "CMD") {
            uint64_t epoch = 0;
            uint64_t sequence = 0;
            uint64_t client_ns = 0;

            std::string axis;
            double value = 0.0;

            if (!(iss
                  >> epoch
                  >> sequence
                  >> client_ns
                  >> axis
                  >> value))
            {
                ++protocol_error_count_;
                return;
            }

            if (!armed_ ||
                epoch != epoch_ ||
                sequence <= sequence_)
            {
                ++protocol_error_count_;
                return;
            }

            const auto it =
                axis_nodes_.find(axis);

            if (it == axis_nodes_.end()) {
                ++protocol_error_count_;
                return;
            }

            const int torque =
                static_cast<int>(
                    std::llround(value));

            // Native 层再做一次 ±1000 上限保护
            if (std::abs(torque) >
                max_abs_torque_)
            {
                ++protocol_error_count_;
                return;
            }

            if (!sdk_ok(
                    canopen_setTargetTorque(
                        dev_index_,
                        it->second,
                        static_cast<hint16>(torque),
                        50)))
            {
                safe_stop(false);
                return;
            }

            sequence_ = sequence;

            last_command_ = Clock::now();

            return;
        }

        if (op == "STOP") {
            uint64_t epoch = 0;

            if (!(iss >> epoch)) {
                ++protocol_error_count_;
                return;
            }

            safe_stop();

            epoch_ = epoch;
            sequence_ = 0;

            return;
        }

        ++protocol_error_count_;
    }

    void read_commands(std::string &pending) {
        char buffer[4096];

        for (;;) {
            const ssize_t n =
                ::read(
                    STDIN_FILENO,
                    buffer,
                    sizeof(buffer));

            if (n > 0) {
                pending.append(
                    buffer,
                    static_cast<size_t>(n));
                continue;
            }

            if (n == 0) {
                g_quit.store(true);
            }

            if (n < 0 &&
                errno != EAGAIN &&
                errno != EWOULDBLOCK &&
                errno != EINTR)
            {
                g_quit.store(true);
            }

            break;
        }

        size_t pos = 0;

        while ((pos = pending.find('\n')) !=
               std::string::npos)
        {
            std::string line =
                pending.substr(0, pos);

            pending.erase(0, pos + 1);

            if (!line.empty()) {
                handle_line(line);
            }
        }

        if (pending.size() > 65536) {
            pending.clear();
            ++protocol_error_count_;
        }
    }

    void poll_feedback() {
        bool all_ok = true;

        for (auto &[axis, info] : nodes_) {
            (void)axis;

            bool critical_ok = true;

            canopen_NodeState node_state =
                canopen_NodeState_Unknown_state;

            huint16 statusword = 0;
            hint16 actual_torque = 0;

            hint32 actual_velocity =
                info.actual_velocity;

            hint32 actual_position =
                info.actual_position;

            huint16 error_code = 0;

            canopen_OperateMode operation_mode =
                canopen_OperateMode_Reserve;

            // 与安全有关的字段
            critical_ok &=
                sdk_ok(
                    canopen_getNodeState(
                        dev_index_,
                        info.id,
                        &node_state,
                        10));

            critical_ok &=
                sdk_ok(
                    canopen_getStatusWord(
                        dev_index_,
                        info.id,
                        &statusword,
                        10));

            critical_ok &=
                sdk_ok(
                    canopen_getActualTorque(
                        dev_index_,
                        info.id,
                        &actual_torque,
                        10));

            critical_ok &=
                sdk_ok(
                    canopen_getServoErrorCode(
                        dev_index_,
                        info.id,
                        &error_code,
                        10));

            critical_ok &=
                sdk_ok(
                    canopen_getOperateMode(
                        dev_index_,
                        info.id,
                        &operation_mode,
                        10));

            // 位置/速度只用于 telemetry。
            // 偶发读取失败不直接触发运动故障。
            sdk_ok(
                canopen_getActualVelocity(
                    dev_index_,
                    info.id,
                    &actual_velocity,
                    10));

            sdk_ok(
                canopen_getActualPos(
                    dev_index_,
                    info.id,
                    &actual_position,
                    10));

            info.node_state = node_state;
            info.statusword = statusword;
            info.actual_torque = actual_torque;
            info.actual_velocity = actual_velocity;
            info.actual_position = actual_position;
            info.error_code = error_code;
            info.operation_mode = operation_mode;

            const bool nmt_ok =
                node_state ==
                canopen_NodeState_Operational;

            const bool fault =
                (statusword & 0x0008u) != 0 ||
                error_code != 0;

            const bool mode_ok =
                operation_mode ==
                canopen_OperateMode_ProfileTorque;

            info.healthy =
                critical_ok &&
                nmt_ok &&
                !fault &&
                mode_ok;

            all_ok &= info.healthy;
        }

        all_nodes_healthy_ = all_ok;

        ++sample_count_;
    }

    void emit_snapshot() const {
        std::ostringstream out;

        out
            << "{\"healthy\":"
            << (all_nodes_healthy_
                    ? "true"
                    : "false")

            << ",\"armed\":"
            << (armed_
                    ? "true"
                    : "false")

            << ",\"epoch\":"
            << epoch_

            << ",\"sequence\":"
            << sequence_

            << ",\"sample_count\":"
            << sample_count_

            << ",\"watchdog_count\":"
            << watchdog_count_

            << ",\"api_error_count\":"
            << api_error_count_

            << ",\"protocol_error_count\":"
            << protocol_error_count_

            << ",\"nodes\":[";

        bool first = true;

        for (const auto &[axis, info] : nodes_) {
            if (!first) {
                out << ',';
            }

            first = false;

            out
                << "{\"axis\":\""
                << axis
                << "\""

                << ",\"node_id\":"
                << static_cast<int>(info.id)

                << ",\"healthy\":"
                << (info.healthy
                        ? "true"
                        : "false")

                << ",\"node_state\":"
                << static_cast<int>(
                       info.node_state)

                << ",\"statusword\":"
                << info.statusword

                << ",\"enabled\":"
                << (((info.statusword &
                      0x006fu) ==
                     0x0027u)
                        ? "true"
                        : "false")

                << ",\"fault\":"
                << ((((info.statusword &
                        0x0008u) != 0) ||
                     info.error_code != 0)
                        ? "true"
                        : "false")

                << ",\"actual_torque\":"
                << info.actual_torque

                << ",\"velocity_raw\":"
                << info.actual_velocity

                << ",\"position_raw\":"
                << info.actual_position

                << ",\"error_code\":"
                << info.error_code

                << ",\"operation_mode\":"
                << static_cast<int>(
                       info.operation_mode)

                << '}';
        }

        out << "]}";

        // SDK 自己可能向 stdout 打日志，
        // 所以使用固定前缀让 Python 只解析我们的 JSON。
        std::cout
            << "@RTS "
            << out.str()
            << std::endl;
    }

    void shutdown() {
        if (!initialized_) {
            return;
        }

        safe_stop(false);

        canopen_freeDLL(dev_index_);

        initialized_ = false;
    }

    huint8 dev_index_;

    std::chrono::milliseconds watchdog_;

    huint32 torque_slope_;

    int max_abs_torque_;

    std::map<std::string, huint8>
        axis_nodes_;

    std::map<std::string, NodeInfo>
        nodes_;

    bool initialized_ = false;
    bool armed_ = false;

    bool all_nodes_healthy_ = false;

    uint64_t epoch_ = 0;
    uint64_t sequence_ = 0;

    uint64_t sample_count_ = 0;
    uint64_t watchdog_count_ = 0;

    uint64_t api_error_count_ = 0;
    uint64_t protocol_error_count_ = 0;

    Clock::time_point last_command_ =
        Clock::now();
};

bool parse_axis_node(
    const std::string &text,
    std::string &axis,
    huint8 &node_id)
{
    const auto colon = text.find(':');

    if (colon == std::string::npos ||
        colon == 0 ||
        colon + 1 >= text.size())
    {
        return false;
    }

    axis = text.substr(0, colon);

    const int id =
        std::stoi(
            text.substr(colon + 1));

    if (id < 1 || id > 127) {
        return false;
    }

    node_id =
        static_cast<huint8>(id);

    return true;
}

}  // namespace


int main(
    int argc,
    char **argv)
{
    std::signal(
        SIGINT,
        signal_handler);

    std::signal(
        SIGTERM,
        signal_handler);

    if (argc < 7 ||
        std::string(argv[1]) != "--run")
    {
        std::cerr
            << "Usage: "
            << argv[0]
            << " --run"
            << " <device_index>"
            << " <watchdog_ms>"
            << " <torque_slope>"
            << " <max_abs_torque>"
            << " <axis:node_id>"
            << " [axis:node_id ...]"
            << std::endl;

        return 2;
    }

    try {
        const int dev_index_i =
            std::stoi(argv[2]);

        const int watchdog_ms =
            std::stoi(argv[3]);

        const int torque_slope_i =
            std::stoi(argv[4]);

        const int max_abs_torque =
            std::stoi(argv[5]);

        if (dev_index_i < 0 ||
            dev_index_i > 255 ||
            watchdog_ms <= 0 ||
            watchdog_ms > 500 ||
            torque_slope_i <= 0 ||
            max_abs_torque <= 0 ||
            max_abs_torque > 32767)
        {
            std::cerr
                << "Invalid CANopen agent arguments"
                << std::endl;

            return 2;
        }

        std::map<std::string, huint8>
            axis_nodes;

        for (int i = 6; i < argc; ++i) {
            std::string axis;
            huint8 node_id = 0;

            if (!parse_axis_node(
                    argv[i],
                    axis,
                    node_id))
            {
                std::cerr
                    << "Invalid axis mapping: "
                    << argv[i]
                    << std::endl;

                return 2;
            }

            if (axis_nodes.count(axis)) {
                std::cerr
                    << "Duplicate axis mapping: "
                    << axis
                    << std::endl;

                return 2;
            }

            for (const auto &[
                     existing_axis,
                     existing_id]
                 : axis_nodes)
            {
                (void)existing_axis;

                if (existing_id ==
                    node_id)
                {
                    std::cerr
                        << "Duplicate node ID: "
                        << static_cast<int>(
                               node_id)
                        << std::endl;

                    return 2;
                }
            }

            axis_nodes[axis] =
                node_id;
        }

        CanopenAgent agent(
            static_cast<huint8>(
                dev_index_i),

            watchdog_ms,

            static_cast<huint32>(
                torque_slope_i),

            max_abs_torque,

            std::move(axis_nodes));

        if (!agent.init()) {
            return 4;
        }

        return agent.run();

    } catch (const std::exception &exc) {
        std::cerr
            << "CANopen agent fatal error: "
            << exc.what()
            << std::endl;

        return 3;
    }
}
