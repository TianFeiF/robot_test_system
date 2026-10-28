#!/usr/bin/env bash
# Sourced after env.sh by real-hardware launchers only.
export ROS_LOCALHOST_ONLY=0
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
# Bound UDP datagrams below Ethernet MTU; DDS handles image fragmentation.
# Preserve an explicitly supplied middleware profile.
export FASTRTPS_DEFAULT_PROFILES_FILE="${FASTRTPS_DEFAULT_PROFILES_FILE:-$PROJECT_ROOT/config/fastdds_site.xml}"
