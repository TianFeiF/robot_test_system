#pragma once
#include <cstdint>
using huint16=uint16_t; using hint32=int32_t; using hint16=int16_t;
constexpr int ETH_SUCCESS=0;
enum eth_State { eth_State_Operational=8 };
enum eth_OperateMode { eth_OperateMode_CyclicSyncVelocity=9, eth_OperateMode_CyclicSyncTorque=10 };
int eth_initDLL(const char*,int,int*); int eth_freeDLL();
int eth_setControlWord(huint16,huint16); int eth_setOperateMode(huint16,eth_OperateMode);
int eth_setTargetTorque(huint16,hint32); int eth_setTargetVelocity(huint16,hint32);
int eth_getActualPosition(huint16,hint32*); int eth_getActualVelocity(huint16,hint32*);
int eth_getActualTorque(huint16,hint16*); int eth_getStatusWord(huint16,huint16*);
int eth_getOperateMode(huint16,eth_OperateMode*); int eth_getSlaveState(huint16,eth_State*);
