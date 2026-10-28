// Robot A: isolated IgH master, explicit arm epochs, per-axis 500 ms watchdog.
#include <ecrt.h>
#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <fcntl.h>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <thread>
#include <sys/prctl.h>
#include <unistd.h>

#include "motion_safety.hpp"

static ec_pdo_entry_info_t entries[] = {
    {0x6040,0,16},{0x607a,0,32},{0x60ff,0,32},{0x6071,0,16},{0x6060,0,8},{0x607c,0,32},{0x60c2,1,8},
    {0x6041,0,16},{0x6064,0,32},{0x606c,0,32},{0x6077,0,16},{0x6061,0,8},{0x603f,0,16},{0x2026,0,8}
};
static ec_pdo_info_t pdos[] = {{0x1600,7,entries},{0x1a00,7,entries+7}};
static ec_sync_info_t syncs[] = {
    {0,EC_DIR_OUTPUT,0,nullptr,EC_WD_DISABLE},{1,EC_DIR_INPUT,0,nullptr,EC_WD_DISABLE},
    {2,EC_DIR_OUTPUT,1,pdos,EC_WD_ENABLE},{3,EC_DIR_INPUT,1,pdos+1,EC_WD_DISABLE},{0xff,EC_DIR_OUTPUT,0,nullptr,EC_WD_DISABLE}
};

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--self-test") return self_test();
    if (argc < 2 || std::string(argv[1]) != "--run") return 2;
    Safety safety;
    if (argc == 3) {
        std::string value(argv[2]); size_t used = 0;
        long long zero = std::stoll(value, &used);
        if (used != value.size() || zero < INT32_MIN || zero > INT32_MAX) return 2;
        safety.z_zero = zero; safety.z_referenced = true;
    }
    signal(SIGTERM, shutdown_signal); signal(SIGINT, shutdown_signal);
    signal(SIGPIPE, SIG_IGN); prctl(PR_SET_PDEATHSIG, SIGTERM);
    if (getppid() == 1) return 3;
    fcntl(STDIN_FILENO, F_SETFL, O_NONBLOCK);
    fcntl(STDOUT_FILENO, F_SETFL, O_NONBLOCK);
    auto* master = ecrt_request_master(0);
    if (!master) { std::cerr << "Cannot acquire EtherCAT master\n"; return 4; }
    ecrt_master_set_send_interval(master, 1000);
    auto fail = [&](const char* text) { std::cerr << text << '\n'; ecrt_release_master(master); return 5; };
    ec_master_info_t info{};
    if (ecrt_master(master, &info) || info.slave_count != 4) return fail("Expected exactly four slaves");
    auto* domain = ecrt_master_create_domain(master);
    if (!domain) return fail("Cannot create domain");
    std::array<ec_slave_config_t*,4> slaves{};
    unsigned offsets[4][14]{};
    for (unsigned i = 0; i < 4; ++i) {
        slaves[i] = ecrt_master_slave_config(master, 0, i, 0x1097, 0x2406);
        if (!slaves[i] || ecrt_slave_config_pdos(slaves[i], EC_END, syncs)) return fail("PDO config failed");
        ecrt_slave_config_dc(slaves[i], 0x0300, 1000000, 0, 0, 0);
        for (unsigned j = 0; j < 14; ++j) {
            int offset = ecrt_slave_config_reg_pdo_entry(slaves[i], entries[j].index, entries[j].subindex, domain, nullptr);
            if (offset < 0) return fail("PDO registration failed");
            offsets[i][j] = static_cast<unsigned>(offset);
        }
    }
    if (ecrt_master_activate(master)) return fail("Master activation failed");
    auto* data = ecrt_domain_data(domain);
    if (!data) return fail("No process data");
    std::string input;
    uint64_t cycles=0, timing_faults=0;
    int64_t previous=monotonic_ns(), next=previous;
    int shutdown_cycles=100;
    while (running || shutdown_cycles-- > 0) {
        const int64_t now = monotonic_ns();
        bool timing_ok = now - previous < 50000000;
        if (!timing_ok) ++timing_faults;
        previous = now;
        ecrt_master_application_time(master, now);
        ecrt_master_receive(master); ecrt_domain_process(domain);
        ec_domain_state_t ds{}; ecrt_domain_state(domain, &ds);
        ec_master_state_t ms{}; ecrt_master_state(master, &ms);
        bool healthy = ms.link_up && ms.slaves_responding == 4 && ds.wc_state == EC_WC_COMPLETE;
        std::array<uint16_t,4> sw{}, errors{};
        std::array<int32_t,4> position{}, velocity{};
        std::array<int16_t,4> torque{};
        std::array<int8_t,4> mode{};
        for (unsigned i=0;i<4;++i) {
            ec_slave_config_state_t state{}; ecrt_slave_config_state(slaves[i], &state);
            sw[i]=EC_READ_U16(data+offsets[i][7]); position[i]=EC_READ_S32(data+offsets[i][8]);
            velocity[i]=EC_READ_S32(data+offsets[i][9]); torque[i]=EC_READ_S16(data+offsets[i][10]);
            mode[i]=EC_READ_S8(data+offsets[i][11]); errors[i]=EC_READ_U16(data+offsets[i][12]);
            healthy = healthy && state.operational && !(sw[i]&8) && errors[i]==0;
            if (safety.requested[i] && mode[i] != (i<2 ? 10 : 9)) healthy=false;
        }
        // Reject queued commands after an expired deadline, before accepting a newer packet.
        safety.check(now, position[3], healthy, timing_ok);
        char buffer[2048]; auto bytes=read(STDIN_FILENO,buffer,sizeof(buffer));
        if (bytes==0) running=0;
        if (bytes>0) input.append(buffer,bytes);
        if (input.size()>8192) { input.clear(); safety.stop(); }
        for (unsigned limit=0;limit<32;++limit) {
            auto end=input.find('\n'); if(end==std::string::npos) break;
            auto line=input.substr(0,end); input.erase(0,end+1);
            safety.input(line,now);
        }
        safety.check(now, position[3], healthy, timing_ok);
        if (!running) safety.stop();
        for (unsigned i=0;i<4;++i) {
            bool active=safety.armed && safety.requested[i] && healthy;
            uint16_t control=0;
            if(active) {
                switch(sw[i]&0x6f) {
                    case 0x40: control=6; break;
                    case 0x21: control=7; break;
                    case 0x23: case 0x27: control=15; break;
                    default: control=0;
                }
            }
            EC_WRITE_U16(data+offsets[i][0], control);
            EC_WRITE_S32(data+offsets[i][1], position[i]);
            EC_WRITE_S32(data+offsets[i][2], active && i>=2 ? static_cast<int32_t>(safety.command[i]*(i==2?drive_scale:z_scale)) : 0);
            EC_WRITE_S16(data+offsets[i][3], active && i<2 ? static_cast<int16_t>(safety.command[i]) : 0);
            EC_WRITE_S8(data+offsets[i][4], i<2?10:9);
            EC_WRITE_S32(data+offsets[i][5],0);
            EC_WRITE_U8(data+offsets[i][6],1);
        }
        ecrt_master_sync_reference_clock(master); ecrt_master_sync_slave_clocks(master);
        ecrt_domain_queue(domain); ecrt_master_send(master);
        if (++cycles%50==0) {
            std::ostringstream out;
            out << "{\"healthy\":" << (healthy?"true":"false") << ",\"armed\":" << (safety.armed?"true":"false")
                << ",\"epoch\":" << safety.epoch << ",\"cycle_count\":" << cycles
                << ",\"working_counter\":" << ds.working_counter << ",\"watchdog_count\":" << safety.watchdog_count
                << ",\"timing_faults\":" << timing_faults << ",\"z_referenced\":" << (safety.z_referenced?"true":"false") << ",\"slaves\":[";
            for(unsigned i=0;i<4;++i) {
                out << (i?",":"") << "{\"statusword\":"<<sw[i]<<",\"position_raw\":"<<position[i]
                    <<",\"velocity_raw\":"<<velocity[i]<<",\"torque_raw\":"<<torque[i]
                    <<",\"operation_mode\":"<<int(mode[i])<<",\"error_code\":"<<errors[i]<<"}";
            }
            out << "]}\n";
            auto line=out.str();
            auto sent=write(STDOUT_FILENO,line.data(),line.size());
            if(sent<0 && errno==EPIPE) running=0;
        }
        next += 1000000;
        if(next<now) next=now+1000000;
        std::this_thread::sleep_until(Clock::time_point(std::chrono::nanoseconds(next)));
    }
    ecrt_master_deactivate(master); ecrt_release_master(master);
}
