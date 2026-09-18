#include "eu_ethercat.h"
#include <array>
#include <cstdlib>
std::array<huint16,5> words{0,0x40,0x40,0x40,0x40};
std::array<eth_OperateMode,5> modes{};
std::array<hint32,5> velocities{},torques{};
static void valid(huint16 slave) { if(slave<1 || slave>4) std::abort(); }
int eth_initDLL(const char*,int,int* count) { *count=4; return 0; }
int eth_freeDLL() { for(int i=1;i<=4;++i) if(words[i]==0x27 || torques[i] || velocities[i]) std::abort(); return 0; }
int eth_setControlWord(huint16 s,huint16 word) { valid(s); words[s]=word==6?0x21:word==7?0x23:word==15?0x27:0x40; return 0; }
int eth_setOperateMode(huint16 s,eth_OperateMode mode) { valid(s);modes[s]=mode;return 0; }
int eth_setTargetTorque(huint16 s,hint32 value) {valid(s);torques[s]=value;return 0;}
int eth_setTargetVelocity(huint16 s,hint32 value) {valid(s);velocities[s]=value;return 0;}
int eth_getActualPosition(huint16 s,hint32* value) {valid(s);*value=s*100;return 0;}
int eth_getActualVelocity(huint16 s,hint32* value) {valid(s);*value=velocities[s];return 0;}
int eth_getActualTorque(huint16 s,hint16* value) {valid(s);*value=torques[s];return 0;}
int eth_getStatusWord(huint16 s,huint16* value) {valid(s);*value=words[s];return 0;}
int eth_getOperateMode(huint16 s,eth_OperateMode* value) {valid(s);*value=modes[s];return 0;}
int eth_getSlaveState(huint16 s,eth_State* value) {valid(s);*value=eth_State_Operational;return 0;}
