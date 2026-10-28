// Compile against the robot's existing RealMan SDK. Query calls only.
#include "rm_interface.h"
#include <cstdlib>
#include <iostream>

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    if (rm_init(RM_DUAL_MODE_E) != 0) return 3;
    rm_set_timeout(500);
    auto *handle = rm_create_robot_arm(argv[1], std::atoi(argv[2]));
    if (!handle || handle->id <= 0) { rm_destroy(); return 4; }
    rm_current_arm_state_t state{};
    int result = rm_get_current_arm_state(handle, &state);
    if (result == 0) {
        std::cout << "{\"joint_degrees\":[";
        for (int i = 0; i < 7; ++i) std::cout << (i ? "," : "") << state.joint[i];
        std::cout << "],\"arm_errors\":[";
        for (int i = 0; i < state.err.err_len && i < 24; ++i)
            std::cout << (i ? "," : "") << state.err.err[i];
        std::cout << "]}" << std::endl;
    }
    rm_delete_robot_arm(handle);
    rm_destroy();
    return result == 0 ? 0 : 5;
}
