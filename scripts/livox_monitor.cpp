// Built against Livox SDK2; config is scoped to the selected lidar IP.
#include "livox_lidar_api.h"
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstring>
#include <iostream>
#include <thread>
#include <arpa/inet.h>
#include <sys/prctl.h>
#include <unistd.h>

using Clock = std::chrono::steady_clock;
std::atomic<uint64_t> packets{0}, points{0}, imu_packets{0}, command_errors{0};
std::atomic<long long> last_packet_ms{0};
std::atomic<int> device_type{0};
volatile std::sig_atomic_t running = 1;
uint32_t selected_handle;
std::string selected_ip;
long long now_ms() {
    return std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
}
void stop(int) { running = 0; }
void command_result(livox_status status, uint32_t, LivoxLidarAsyncControlResponse* response, void*) {
    if (status != kLivoxLidarStatusSuccess || !response || response->ret_code) ++command_errors;
}
void discovered(uint32_t handle, const LivoxLidarInfo* info, void*) {
    if (!info || selected_ip != info->lidar_ip) return;
    device_type = info->dev_type;
    SetLivoxLidarPclDataType(handle, kLivoxLidarCartesianCoordinateHighData, command_result, nullptr);
    SetLivoxLidarWorkMode(handle, kLivoxLidarNormal, command_result, nullptr);
}
void point_data(uint32_t handle, uint8_t type, LivoxLidarEthernetPacket* data, void*) {
    if (handle != selected_handle || !data) return;
    ++packets;
    points += data->dot_num;
    device_type = type;
    last_packet_ms = now_ms();
}
void imu_data(uint32_t handle, uint8_t, LivoxLidarEthernetPacket* data, void*) {
    if (handle == selected_handle && data) ++imu_packets;
}
int main(int argc, char** argv) {
    if (argc != 3) return 2;
    selected_ip = argv[2];
    in_addr address{};
    if (inet_pton(AF_INET, argv[2], &address) != 1) return 2;
    selected_handle = address.s_addr;
    signal(SIGTERM, stop); signal(SIGINT, stop);
    prctl(PR_SET_PDEATHSIG, SIGTERM);
    if (getppid() == 1) return 4;
    DisableLivoxSdkConsoleLogger();
    if (!LivoxLidarSdkInit(argv[1])) return 3;
    SetLivoxLidarPointCloudCallBack(point_data, nullptr);
    SetLivoxLidarImuDataCallback(imu_data, nullptr);
    SetLivoxLidarInfoChangeCallback(discovered, nullptr);
    uint64_t previous_points = 0;
    auto previous_ms = now_ms();
    while (running) {
        std::this_thread::sleep_for(std::chrono::seconds(1));
        auto now = now_ms();
        auto total = points.load();
        auto last = last_packet_ms.load();
        std::cout << "{\"packet_count\":" << packets.load()
                  << ",\"point_count\":" << total
                  << ",\"points_per_second\":" << (total - previous_points) * 1000.0 / (now - previous_ms)
                  << ",\"imu_packet_count\":" << imu_packets.load()
                  << ",\"command_error_count\":" << command_errors.load()
                  << ",\"device_type\":" << device_type.load()
                  << ",\"last_packet_age_ms\":" << (last ? now - last : -1) << "}" << std::endl;
        previous_ms = now; previous_points = total;
    }
    LivoxLidarSdkUninit();
}
