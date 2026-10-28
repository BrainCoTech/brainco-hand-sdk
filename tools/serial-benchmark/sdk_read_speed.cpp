// Control measurement using the SDK. The raw benchmark is separate.
#include "bench_common.hpp"
#include "stark-sdk.h"
#include <memory>
int main(int argc,char **argv) {
  try {
    const auto o=options(argc,argv);
    if(o.low_latency) throw std::runtime_error("--low-latency is for raw benchmarks; SDK initialization controls its own settings");
    init_logging_with_options(LOG_LEVEL_WARN,false);
    auto *handle=modbus_open(o.port.c_str(),o.baud);
    if(!handle) throw std::runtime_error("SDK modbus_open failed");
    struct Cleanup { DeviceHandler *handle; ~Cleanup(){modbus_close(handle);} } cleanup{handle};
    for(int slave:o.slaves) {
      auto *info=stark_get_device_info(handle,slave);
      if(!info) throw std::runtime_error("SDK get_device_info failed");
      std::cout << "DEVICE slave=" << slave << " serial=" << info->serial_number
        << " firmware=" << info->firmware_version << '\n';
      free_device_info(info);
    }
    return benchmark(o,"sdk_cpp",[&](int slave){
      auto *status=stark_get_motor_status(handle,slave);
      if(!status) throw std::runtime_error("SDK get_motor_status failed");
      free_motor_status_data(status);
    });
  } catch(const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
