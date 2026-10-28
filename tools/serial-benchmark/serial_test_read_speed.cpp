// Linux raw serial benchmark. No SDK or Modbus library is linked.
#include "bench_common.hpp"
#include <array>
#include <cerrno>
#include <cstring>
#include <cstdint>
#include <fcntl.h>
#include <linux/serial.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <termios.h>
#include <unistd.h>

static uint16_t crc16(const uint8_t *bytes, size_t size) {
  uint16_t crc = 0xffff;
  for (size_t i=0; i<size; ++i) {
    crc ^= bytes[i];
    for (int bit=0; bit<8; ++bit) crc = (crc & 1) ? (crc >> 1)^0xa001 : crc >> 1;
  }
  return crc;
}
static std::array<uint8_t,8> request(int slave) {
  std::array<uint8_t,8> frame{static_cast<uint8_t>(slave),4,7,0xd0,0,24,0,0};
  const auto crc = crc16(frame.data(),6);
  frame[6] = crc & 0xff; frame[7] = crc >> 8;
  return frame;
}
static void check(bool result, const char *operation) {
  if (!result) throw std::runtime_error(std::string(operation)+": "+std::strerror(errno));
}
static void configure_low_latency(int fd, const Options &o) {
  const auto timer_before = timer_value(o.port);
  if (!o.low_latency) {
    std::cout << "LOW_LATENCY requested=0 result=unchanged timer_ms=" << timer_before << '\n';
    return;
  }
  serial_struct initial{};
  if (ioctl(fd,TIOCGSERIAL,&initial) < 0) {
    std::cerr << "WARN low_latency result=get_failed error=" << std::strerror(errno) << '\n';
    std::cout << "LOW_LATENCY requested=1 result=get_failed timer_ms=" << timer_value(o.port) << '\n';
    return;
  }
  auto updated = initial;
  updated.flags |= ASYNC_LOW_LATENCY;
  if (updated.flags != initial.flags && ioctl(fd,TIOCSSERIAL,&updated) < 0) {
    std::cerr << "WARN low_latency result=set_failed error=" << std::strerror(errno) << '\n';
    std::cout << "LOW_LATENCY requested=1 result=set_failed flags_before=" << initial.flags
      << " timer_before_ms=" << timer_before << " timer_after_ms=" << timer_value(o.port) << '\n';
    return;
  }
  serial_struct readback{};
  if (ioctl(fd,TIOCGSERIAL,&readback) < 0) {
    std::cerr << "WARN low_latency result=readback_failed error=" << std::strerror(errno) << '\n';
    std::cout << "LOW_LATENCY requested=1 result=readback_failed timer_after_ms=" << timer_value(o.port) << '\n';
    return;
  }
  const bool flag_set = (readback.flags & ASYNC_LOW_LATENCY) != 0;
  if (!flag_set) std::cerr << "WARN low_latency flag is clear after setup\n";
  std::cout << "LOW_LATENCY requested=1 result=" << (flag_set ? "flag_set" : "flag_clear")
    << " flags_before=" << initial.flags << " flags_after=" << readback.flags
    << " timer_before_ms=" << timer_before << " timer_after_ms=" << timer_value(o.port) << '\n';
}
class SerialPort {
  int fd = -1;
  void ready(short events, BenchClock::time_point deadline) {
    while (true) {
      const double remaining = std::chrono::duration<double,std::milli>(deadline-BenchClock::now()).count();
      if (remaining <= 0) throw std::runtime_error("Transaction deadline exceeded");
      pollfd p{fd,events,0};
      const int n = poll(&p,1,static_cast<int>(std::ceil(remaining)));
      if (n < 0 && errno == EINTR) continue;
      check(n >= 0,"poll");
      if (n == 0) throw std::runtime_error("Transaction deadline exceeded");
      if (p.revents & (POLLERR|POLLHUP|POLLNVAL)) throw std::runtime_error("Serial disconnected or poll error");
      if (p.revents & events) return;
    }
  }
public:
  explicit SerialPort(const Options &o) {
    if (o.baud != 460800) throw std::runtime_error("This controlled benchmark requires 460800 baud");
    fd = open(o.port.c_str(),O_RDWR|O_NOCTTY|O_NONBLOCK|O_CLOEXEC);
    check(fd >= 0,"open");
    try {
      check(ioctl(fd,TIOCEXCL)==0,"TIOCEXCL");
      termios t{};
      check(tcgetattr(fd,&t)==0,"tcgetattr");
      cfmakeraw(&t);
      t.c_cflag &= ~(PARENB|CSTOPB|CSIZE|CRTSCTS);
      t.c_cflag |= CS8|CLOCAL|CREAD;
      t.c_cc[VMIN]=0; t.c_cc[VTIME]=0;
      check(cfsetispeed(&t,B460800)==0 && cfsetospeed(&t,B460800)==0,"set baud");
      check(tcsetattr(fd,TCSANOW,&t)==0,"tcsetattr");
      check(tcflush(fd,TCIOFLUSH)==0,"tcflush");
      configure_low_latency(fd,o);
    } catch (...) { close(fd); fd=-1; throw; }
  }
  ~SerialPort() { if(fd>=0) close(fd); }
  std::array<uint8_t,53> query(int slave, int timeout_ms = 100) {
    const auto tx = request(slave);
    const auto deadline = BenchClock::now()+std::chrono::milliseconds(timeout_ms);
    size_t sent=0;
    while (sent<tx.size()) {
      ready(POLLOUT,deadline);
      const auto n=write(fd,tx.data()+sent,tx.size()-sent);
      if(n<0 && (errno==EAGAIN || errno==EINTR)) continue;
      check(n>0,"write"); sent+=static_cast<size_t>(n);
    }
    std::array<uint8_t,53> rx{};
    size_t received=0;
    while (received<rx.size()) {
      ready(POLLIN,deadline);
      const auto n=read(fd,rx.data()+received,rx.size()-received);
      if(n<0 && (errno==EAGAIN || errno==EINTR)) continue;
      check(n>0,"read"); received+=static_cast<size_t>(n);
      if(received>=2 && rx[1]==0x84) throw std::runtime_error("Device returned exception response");
    }
    if(rx[0]!=slave || rx[1]!=4 || rx[2]!=48 || crc16(rx.data(),rx.size())!=0)
      throw std::runtime_error("Invalid response address/function/byte count/CRC");
    return rx;
  }
};
int main(int argc,char **argv) {
  try {
    if(request(126)!=std::array<uint8_t,8>{0x7e,4,7,0xd0,0,0x18,0xfb,0x42} ||
       request(127)!=std::array<uint8_t,8>{0x7f,4,7,0xd0,0,0x18,0xfa,0x93})
      throw std::runtime_error("Request differs from known Revo2 query frame");
    const auto o=options(argc,argv);
    SerialPort port(o);
    for(int slave:o.slaves) {
      // Allow driver setup to settle without resending a timed-out request.
      const auto start = BenchClock::now();
      const auto rx=port.query(slave,1000);
      const double startup_ms = std::chrono::duration<double,std::milli>(BenchClock::now()-start).count();
      std::cout << "FIRST_FRAME slave=" << slave << " startup_ms=" << startup_ms
        << " tx=" << std::hex << std::setfill('0');
      for(auto b:request(slave)) std::cout << std::setw(2) << static_cast<int>(b);
      std::cout << " rx=";
      for(auto b:rx) std::cout << std::setw(2) << static_cast<int>(b);
      std::cout << std::dec << '\n';
    }
    return benchmark(o,"raw_cpp",[&](int slave){port.query(slave);});
  } catch(const std::exception &e) { std::cerr << e.what() << '\n'; return 1; }
}
