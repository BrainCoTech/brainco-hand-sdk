#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <signal.h>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

namespace {

bool parse_number(const char *text, unsigned long max, unsigned long *value) {
  if (text == nullptr || *text == '\0' || *text == '-') {
    return false;
  }
  char *end = nullptr;
  errno = 0;
  const unsigned long parsed = std::strtoul(text, &end, 10);
  if (errno != 0 || *end != '\0' || parsed > max) {
    return false;
  }
  *value = parsed;
  return true;
}

int run_ethercat(const std::vector<std::string> &arguments,
                 const std::string *input = nullptr) {
  std::vector<char *> argv;
  argv.push_back(const_cast<char *>("ethercat"));
  for (const auto &argument : arguments) {
    argv.push_back(const_cast<char *>(argument.c_str()));
  }
  argv.push_back(nullptr);

  int input_pipe[2] = {-1, -1};
  if (input != nullptr && pipe(input_pipe) != 0) {
    std::fprintf(stderr, "pipe failed: %s\n", std::strerror(errno));
    return -1;
  }

  const pid_t child = fork();
  if (child < 0) {
    if (input != nullptr) {
      close(input_pipe[0]);
      close(input_pipe[1]);
    }
    std::fprintf(stderr, "fork failed: %s\n", std::strerror(errno));
    return -1;
  }
  if (child == 0) {
    if (input != nullptr) {
      close(input_pipe[1]);
      if (dup2(input_pipe[0], STDIN_FILENO) < 0) {
        _exit(127);
      }
      close(input_pipe[0]);
    }
    execvp(argv[0], argv.data());
    std::fprintf(stderr, "Cannot execute ethercat: %s\n", std::strerror(errno));
    _exit(127);
  }

  bool input_failed = false;
  if (input != nullptr) {
    close(input_pipe[0]);
    struct sigaction ignore = {};
    struct sigaction previous = {};
    ignore.sa_handler = SIG_IGN;
    if (sigaction(SIGPIPE, &ignore, &previous) != 0) {
      input_failed = true;
    } else {
      std::size_t offset = 0;
      while (offset < input->size()) {
        const ssize_t written = write(input_pipe[1], input->data() + offset,
                                      input->size() - offset);
        if (written < 0 && errno == EINTR) {
          continue;
        }
        if (written <= 0) {
          break;
        }
        offset += static_cast<std::size_t>(written);
      }
      input_failed = offset != input->size();
      sigaction(SIGPIPE, &previous, nullptr);
    }
    close(input_pipe[1]);
  }

  int status = 0;
  while (waitpid(child, &status, 0) < 0) {
    if (errno != EINTR) {
      std::fprintf(stderr, "waitpid failed: %s\n", std::strerror(errno));
      return -1;
    }
  }
  if (input_failed) {
    std::fprintf(stderr, "Failed to send authorization code to ethercat.\n");
    return -1;
  }
  if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
    std::fprintf(stderr, "ethercat command failed (status %d).\n", status);
    return -1;
  }
  return 0;
}

void print_usage(const char *program) {
  std::fprintf(stderr,
               "Usage: %s <wrist|control> <firmware_file> "
               "[slave_position] [master_id]\n",
               program);
}

} // namespace

int main(int argc, char **argv) {
  if (argc == 2 && std::strcmp(argv[1], "--help") == 0) {
    print_usage(argv[0]);
    return 0;
  }
  if (argc < 3 || argc > 5) {
    print_usage(argv[0]);
    return 1;
  }

  const std::string target = argv[1];
  const std::string file_type = target == "wrist" ? "1" : "2";
  if (target != "wrist" && target != "control") {
    print_usage(argv[0]);
    return 1;
  }

  unsigned long slave_position = 0;
  unsigned long master_id = 0;
  if ((argc >= 4 && !parse_number(argv[3], USHRT_MAX, &slave_position)) ||
      (argc == 5 && !parse_number(argv[4], UCHAR_MAX, &master_id))) {
    std::fprintf(stderr, "Invalid slave position or master ID.\n");
    return 1;
  }

  const std::string firmware_path = argv[2];
  std::ifstream firmware(firmware_path, std::ios::binary | std::ios::ate);
  if (!firmware || firmware.tellg() <= 0) {
    std::fprintf(stderr, "Firmware file is missing, unreadable, or empty: %s\n",
                 firmware_path.c_str());
    return 1;
  }

  const std::string basename = firmware_path.substr(firmware_path.find_last_of('/') + 1);
  const std::size_t extension = basename.find_last_of('.');
  const std::string foe_name = basename.substr(0, extension);
  if (foe_name.empty()) {
    std::fprintf(stderr, "Firmware filename must have a nonempty stem.\n");
    return 1;
  }

  const std::string master = std::to_string(master_id);
  const std::string slave = std::to_string(slave_position);
  const std::vector<std::string> selection = {"-m", master, "-p", slave};

  std::printf("Master %s, slave %s, target %s, firmware %s\n", master.c_str(),
              slave.c_str(), target.c_str(), firmware_path.c_str());
  std::fflush(stdout);

  const char *entered_code = getpass("FoE authorization code (ask technical support): ");
  if (entered_code == nullptr || *entered_code == '\0') {
    std::fprintf(stderr, "An authorization code is required.\n");
    return 1;
  }
  const std::string auth_code = entered_code;

  auto command = selection;
  command.insert(command.end(), {"download", "-t", "uint8", "0x8000", "0x15", file_type});
  if (run_ethercat(command) != 0) {
    return 1;
  }

  command = selection;
  command.insert(command.end(), {"download", "-t", "string", "0x8000", "0x16", "-"});
  if (run_ethercat(command, &auth_code) != 0) {
    return 1;
  }

  command = selection;
  command.insert(command.end(), {"foe_write", "-o", foe_name, firmware_path});
  if (run_ethercat(command) != 0) {
    return 1;
  }

  std::puts("FoE transfer completed. Read back the firmware version after the "
            "device restarts to confirm the upgrade.");
  return 0;
}
