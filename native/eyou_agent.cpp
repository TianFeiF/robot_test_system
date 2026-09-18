// Eyou SDK 20260109: CSV for drive/Z, CST for clamps. No homing or fault reset.
#include "eu_ethercat.h"
#include "motion_safety.hpp"
#include <fcntl.h>
#include <sys/prctl.h>
#include <unistd.h>
#include <thread>

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--self-test") return self_test();
    if (argc < 3 || (std::string(argv[1]) != "--run" && std::string(argv[1]) != "--monitor")) return 2;
    const bool monitor = std::string(argv[1]) == "--monitor";
    Safety safety;
    // Operator requested no homing. Unreferenced Z accepts only <=2 s manual bursts.
    safety.allow_unreferenced_z = true;
    signal(SIGINT, shutdown_signal); signal(SIGTERM, shutdown_signal); signal(SIGPIPE, SIG_IGN);
    prctl(PR_SET_PDEATHSIG, SIGTERM); if (getppid() == 1) return 3;
    int output = dup(STDOUT_FILENO);
    dup2(STDERR_FILENO, STDOUT_FILENO); // Keep SDK log lines out of the JSON protocol.
    fcntl(output, F_SETFL, O_NONBLOCK); fcntl(STDIN_FILENO, F_SETFL, O_NONBLOCK);
    int count = 0;
    if (eth_initDLL(argv[2], 1, &count) != ETH_SUCCESS) {
        std::cerr << "Eyou init failed: check CAP_NET_RAW, interface, and sole master ownership\n";
        eth_freeDLL(); return 4;
    }
    if (count != 4) { std::cerr << "Expected four Eyou slaves, got " << count << '\n'; eth_freeDLL(); return 5; }
    auto zero_outputs = [&]() {
        for (huint16 slave=1; slave<=4; ++slave) {
            if (slave<=2) eth_setTargetTorque(slave,0); else eth_setTargetVelocity(slave,0);
            eth_setControlWord(slave,0);
        }
    };
    if (!monitor) {
        zero_outputs();
        for (huint16 slave=1; slave<=4; ++slave) {
            if (eth_setOperateMode(slave, slave<=2 ? eth_OperateMode_CyclicSyncTorque : eth_OperateMode_CyclicSyncVelocity) != ETH_SUCCESS) {
                zero_outputs(); eth_freeDLL(); return 6;
            }
        }
    }
    std::string pending;
    uint64_t samples=0, timing_faults=0, api_errors=0;
    int64_t previous=monotonic_ns(), next=previous;
    int closing=20;
    while(running || closing-- > 0) {
        int64_t now=monotonic_ns();
        bool timing_ok=now-previous<50000000; if(!timing_ok) ++timing_faults; previous=now;
        std::array<hint32,4> pos{},vel{};
        std::array<hint16,4> torque{};
        std::array<huint16,4> status{};
        std::array<eth_OperateMode,4> mode{};
        std::array<eth_State,4> state{};
        bool healthy=true;
        for(unsigned i=0;i<4;++i) {
            huint16 slave=i+1;
            int rc=0;
            rc |= eth_getActualPosition(slave,&pos[i]); rc |= eth_getActualVelocity(slave,&vel[i]);
            rc |= eth_getActualTorque(slave,&torque[i]); rc |= eth_getStatusWord(slave,&status[i]);
            rc |= eth_getOperateMode(slave,&mode[i]); rc |= eth_getSlaveState(slave,&state[i]);
            if(rc) ++api_errors;
            healthy = healthy && !rc && state[i]==eth_State_Operational && !(status[i]&8);
            if (!monitor) healthy = healthy && int(mode[i])==(i<2?10:9);
        }
        safety.check(now,pos[3],healthy,timing_ok);
        char buffer[2048]; auto n=read(STDIN_FILENO,buffer,sizeof(buffer));
        if(n==0) running=0;
        if(n>0) pending.append(buffer,n);
        if(pending.size()>8192) { pending.clear(); safety.stop(); }
        for(unsigned limit=0;limit<32;++limit) {
            auto end=pending.find('\n'); if(end==std::string::npos) break;
            auto line=pending.substr(0,end); pending.erase(0,end+1);
            if(!monitor) safety.input(line,now);
        }
        safety.check(monotonic_ns(),pos[3],healthy,timing_ok);
        if(!running) safety.stop();
        if(!monitor) {
            bool output_error=false;
            for(unsigned i=0;i<4;++i) {
                bool active=safety.armed && safety.requested[i] && healthy;
                huint16 control=0;
                if(active) {
                    switch(status[i]&0x6f) {
                        case 0x40: control=6; break;
                        case 0x21: control=7; break;
                        case 0x23: case 0x27: control=15; break;
                        default: control=0;
                    }
                }
                int rc=i<2 ? eth_setTargetTorque(i+1,active ? static_cast<hint32>(safety.command[i]) : 0)
                            : eth_setTargetVelocity(i+1,active ? static_cast<hint32>(safety.command[i]*(i==2?drive_scale:z_scale)) : 0);
                rc |= eth_setControlWord(i+1,control);
                output_error |= rc!=0;
            }
            if(output_error) { ++api_errors; safety.stop(); zero_outputs(); healthy=false; }
        }
        if(++samples%10==0) {
            std::ostringstream out;
            out << "{\"healthy\":"<<(healthy?"true":"false")<<",\"armed\":"<<(safety.armed?"true":"false")
                <<",\"epoch\":"<<safety.epoch<<",\"sample_count\":"<<samples<<",\"watchdog_count\":"<<safety.watchdog_count
                <<",\"timing_faults\":"<<timing_faults<<",\"api_error_count\":"<<api_errors
                <<",\"z_referenced\":false,\"slaves\":[";
            for(unsigned i=0;i<4;++i) {
                out<<(i?",":"")<<"{\"statusword\":"<<status[i]<<",\"position_raw\":"<<pos[i]
                   <<",\"velocity_raw\":"<<vel[i]<<",\"torque_raw\":"<<torque[i]
                   <<",\"operation_mode\":"<<int(mode[i])<<",\"slave_state\":"<<int(state[i])
                   <<",\"sdk_slave_id\":"<<i+1<<",\"fault\":"<<((status[i]&8)?"true":"false")<<"}";
            }
            out<<"]}\n"; auto line=out.str();
            if(write(output,line.data(),line.size())<0 && errno==EPIPE) running=0;
        }
        next+=5000000; if(next<now) next=now+5000000;
        std::this_thread::sleep_until(Clock::time_point(std::chrono::nanoseconds(next)));
    }
    if(!monitor) zero_outputs();
    eth_freeDLL(); close(output);
}
