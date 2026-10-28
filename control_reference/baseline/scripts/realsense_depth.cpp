// Depth-only capture; RGB remains available to the UVC camera adapter.
#include <librealsense2/rs.hpp>
#include <csignal>
#include <cstdint>
#include <iostream>
#include <sys/prctl.h>
#include <unistd.h>

volatile std::sig_atomic_t capture_running = 1;
void stop_capture(int) { capture_running = 0; }
int main(int argc, char** argv) {
    if (argc != 2) return 2;
    signal(SIGTERM, stop_capture); signal(SIGINT, stop_capture);
    prctl(PR_SET_PDEATHSIG, SIGTERM);
    if (getppid() == 1) return 3;
    try {
        rs2::pipeline pipeline;
        rs2::config config;
        config.enable_device(argv[1]);
        config.enable_stream(RS2_STREAM_DEPTH, 640, 480, RS2_FORMAT_Z16, 15);
        pipeline.start(config);
        rs2::colorizer colorizer;
        while (capture_running) {
            auto depth = pipeline.wait_for_frames(2000).get_depth_frame();
            auto frame = colorizer.colorize(depth).as<rs2::video_frame>();
            uint32_t width = frame.get_width(), height = frame.get_height();
            uint32_t header[] = {width, height, width * height * 3};
            std::cout.write(reinterpret_cast<char*>(header), sizeof(header));
            const char* pixels = static_cast<const char*>(frame.get_data());
            for (unsigned row = 0; row < height; ++row)
                std::cout.write(pixels + row * frame.get_stride_in_bytes(), width * 3);
            std::cout.flush();
            if (!std::cout) break;
        }
        pipeline.stop();
    } catch (const std::exception& error) {
        std::cerr << error.what() << std::endl;
        return 4;
    }
}
