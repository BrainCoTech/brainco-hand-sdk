#pragma once
#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using BenchClock = std::chrono::steady_clock;
struct Options {
  std::string port, csv;
  unsigned baud;
  std::vector<int> slaves;
  double seconds;
  bool low_latency;
};
inline Options options(int argc, char **argv) {
  if (argc != 6 && argc != 7) throw std::runtime_error("Usage: PROGRAM PORT BAUD SLAVES SECONDS CSV [--low-latency]");
  if (argc == 7 && std::string(argv[6]) != "--low-latency") throw std::runtime_error("Unknown option");
  Options o{argv[1], argv[5], static_cast<unsigned>(std::stoul(argv[2])), {}, std::stod(argv[4]), argc == 7};
  std::stringstream stream(argv[3]);
  std::string item;
  while (std::getline(stream, item, ',')) {
    int slave = std::stoi(item);
    if (slave != 126 && slave != 127) throw std::runtime_error("Only Revo2 addresses 126/127 are allowed");
    o.slaves.push_back(slave);
  }
  if (o.slaves.empty() || o.slaves.size() > 2 || !std::isfinite(o.seconds) || o.seconds <= 0 || o.seconds > 60)
    throw std::runtime_error("Invalid duration or slave list");
  if (o.slaves.size() == 2 && o.slaves[0] == o.slaves[1]) throw std::runtime_error("Duplicate slave");
  return o;
}
inline std::string timer_value(const std::string &port) {
  std::ifstream input("/sys/bus/usb-serial/devices/" + port.substr(port.find_last_of('/') + 1) + "/latency_timer");
  std::string value;
  return (input >> value) ? value : "unavailable";
}
template<class Query> int benchmark(const Options &o, const char *backend, Query query) {
  for (int i = 0; i < 20; ++i) for (int slave : o.slaves) query(slave);
  const auto timer_before = timer_value(o.port);
  struct Sample { int slave; double start_s, elapsed_ms; bool ok; };
  std::vector<Sample> samples;
  samples.reserve(100000);
  int failures = 0, cycles = 0;
  std::string error;
  const auto start = BenchClock::now();
  while (std::chrono::duration<double>(BenchClock::now() - start).count() < o.seconds) {
    for (int slave : o.slaves) {
      const auto t = BenchClock::now();
      bool ok = true;
      try { query(slave); } catch (const std::exception &e) { ok = false; ++failures; error = e.what(); }
      const auto end = BenchClock::now();
      samples.push_back({slave, std::chrono::duration<double>(t-start).count(),
        std::chrono::duration<double,std::milli>(end-t).count(), ok});
      if (!ok) break;
    }
    if (failures) break;
    ++cycles;
  }
  const double elapsed = std::chrono::duration<double>(BenchClock::now()-start).count();
  std::ofstream csv(o.csv);
  if (!csv) throw std::runtime_error("Cannot create sample CSV");
  csv << "slave,start_s,elapsed_ms,success\n" << std::setprecision(12);
  std::vector<double> durations;
  for (const auto &s : samples) {
    csv << s.slave << ',' << s.start_s << ',' << s.elapsed_ms << ',' << s.ok << '\n';
    if (s.ok) durations.push_back(s.elapsed_ms);
  }
  std::sort(durations.begin(), durations.end());
  auto percentile = [&](double p) { return durations.empty() ? 0.0 : durations[static_cast<size_t>(p*(durations.size()-1))]; };
  std::cout << std::fixed << std::setprecision(6)
    << "{\"backend\":\"" << backend << "\",\"slaves\":[";
  for (size_t i=0; i<o.slaves.size(); ++i) std::cout << (i ? "," : "") << o.slaves[i];
  std::cout << "],\"timer_before\":\"" << timer_before << "\",\"timer_after\":\"" << timer_value(o.port)
    << "\",\"cycles\":" << cycles << ",\"successes\":" << durations.size() << ",\"failures\":" << failures
    << ",\"elapsed_s\":" << elapsed << ",\"rpc_hz\":" << durations.size()/elapsed
    << ",\"per_hand_hz\":" << cycles/elapsed << ",\"median_ms\":" << percentile(.5)
    << ",\"p95_ms\":" << percentile(.95) << ",\"max_ms\":" << percentile(1) << "}\n";
  if (failures) std::cerr << "Transaction failed; stopping to avoid stale-response reuse: " << error << '\n';
  return failures ? 1 : 0;
}
