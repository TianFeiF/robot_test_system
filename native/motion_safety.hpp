#pragma once
#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>

using Clock = std::chrono::steady_clock;
static int64_t monotonic_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count();
}
static volatile std::sig_atomic_t running = 1;
static void shutdown_signal(int) { running = 0; }
constexpr double drive_scale = 65536.0 * 51 / (2 * 3.14159265358979323846);
constexpr double z_scale = 65536.0 * 101 / 0.02;
constexpr double drive_max = 2 * 3.14159265358979323846; // 60 output rpm
constexpr double z_max = 0.02 / 101; // 60 motor rpm
constexpr int64_t watchdog_ns = 500000000;

struct Safety {
    uint64_t epoch = 0, sequence = 0, watchdog_count = 0;
    bool armed = false, z_referenced = false, allow_unreferenced_z = false;
    int64_t z_started = 0;
    int32_t z_zero = 0;
    std::array<double, 4> command{};
    std::array<int64_t, 4> last_command{};
    std::array<bool, 4> requested{};
    void stop() { armed = false; command.fill(0); requested.fill(false); z_started = 0; }
    bool input(const std::string& line, int64_t now) {
        std::istringstream in(line);
        std::string op, trailing;
        uint64_t e;
        if (!(in >> op >> e)) return false;
        if (op == "STOP") { stop(); epoch = std::max(epoch, e); return true; }
        int64_t stamp;
        if (op == "ARM") {
            if (!(in >> stamp) || (in >> trailing) || e <= epoch || stamp > now || now - stamp >= watchdog_ns) return false;
            stop(); epoch = e; sequence = 0; armed = true;
            last_command.fill(now);
            return true;
        }
        unsigned axis; uint64_t seq; double value;
        if (op != "CMD" || !(in >> seq >> stamp >> axis >> value) || (in >> trailing) || !armed ||
            e != epoch || seq <= sequence || axis >= 4 || stamp > now || now - stamp >= watchdog_ns || !std::isfinite(value)) return false;
        if ((axis < 2 && (value < 0 || value > 1000)) || (axis == 2 && std::abs(value) > drive_max) ||
            (axis == 3 && ((!z_referenced && !allow_unreferenced_z) || std::abs(value) > z_max))) return false;
        if (axis == 3 && !requested[3]) z_started = now;
        sequence = seq; command[axis] = value; last_command[axis] = now; requested[axis] = true;
        return true;
    }
    void check(int64_t now, int32_t z_position, bool healthy, bool timing_ok) {
        if (!armed) return;
        if (!healthy || !timing_ok) { stop(); return; }
        bool any = false;
        for (unsigned i = 0; i < 4; ++i) {
            any |= requested[i];
            if (requested[i] && now - last_command[i] >= watchdog_ns) { ++watchdog_count; stop(); return; }
        }
        if (!any && now - last_command[0] >= watchdog_ns) { ++watchdog_count; stop(); return; }
        if (requested[3] && !z_referenced && now - z_started >= 2000000000) { stop(); return; }
        if (requested[3] && z_referenced) {
            double position = (static_cast<double>(z_position) - z_zero) / z_scale;
            // Stop at either limit; origin must be provided from a measured/homed reference.
            if (position < 0 || position > .3 || (position <= .0001 && command[3] < 0) ||
                (position >= .2999 && command[3] > 0)) stop();
        }
    }
};

static int self_test() {
    Safety s; const int64_t t = 1000000000;
    auto require = [](bool condition) { if (!condition) { std::cerr << "Safety self-test failed\n"; std::exit(10); } };
    require(!s.input("CMD 1 1 1000000000 2 0.1", t));
    require(s.input("ARM 1 1000000000", t));
    require(!s.input("CMD 1 1 1000000000 0 -1", t));
    require(!s.input("CMD 1 1 1000000000 2 7", t));
    require(!s.input("CMD 1 1 1000000000 3 0.0001", t));
    require(s.input("CMD 1 1 1000000000 2 0.1", t));
    require(!s.input("CMD 1 1 1000000000 2 0.2", t));
    s.check(t + watchdog_ns, 0, true, true); require(!s.armed && s.command[2] == 0);
    require(!s.input("CMD 1 2 1500000000 2 0.1", t + watchdog_ns));
    require(s.input("ARM 2 1500000000", t + watchdog_ns));
    require(s.input("STOP 3", t + watchdog_ns));
    require(!s.input("ARM 2 1500000000", t + watchdog_ns));
    require(s.input("ARM 4 1500000000", t + watchdog_ns));
    s.z_referenced = true;
    require(s.input("CMD 4 1 1500000000 3 -0.0001", t + watchdog_ns));
    s.check(t + watchdog_ns, 0, true, true); require(!s.armed);
    require(s.input("ARM 5 1500000000", t + watchdog_ns));
    s.check(t + watchdog_ns, 100, false, true); require(!s.armed);
    require(s.input("ARM 6 1500000000", t + watchdog_ns));
    s.check(t + watchdog_ns, 100, true, false); require(!s.armed);
    s.allow_unreferenced_z = true; s.z_referenced = false;
    require(s.input("ARM 7 2000000000", 2000000000));
    for (uint64_t seq = 1; seq <= 21; ++seq) {
        int64_t stamp = 2000000000 + static_cast<int64_t>(seq - 1) * 100000000;
        std::ostringstream line;
        line << "CMD 7 " << seq << ' ' << stamp << " 3 0.00005";
        require(s.input(line.str(), stamp));
        s.check(stamp, -12345, true, true);
        require(s.armed == (seq < 21));
    }
    std::cout << "PASS: native limits, epochs, replay rejection, watchdog, unreferenced Z 2s limit, bus/timing fault\n";
    return 0;
}
