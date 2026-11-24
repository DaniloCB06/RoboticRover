// Parser e FSM reais do firmware, executados no computador.
#include "rover_protocol.h"
#include <iostream>
#include <string>
int main() {
  rover::Controller control;
  std::string command;
  while (std::getline(std::cin, command)) {
    size_t split = command.find(' ');
    uint32_t now = (uint32_t)std::stoul(command.substr(0, split));
    std::string raw = command.substr(split + 1);
    if (raw == "TICK") { control.tick(now); std::cout << control.left << "," << control.right << "," << control.armed << std::endl; continue; }
    rover::Frame f;
    if (!rover::decode(&raw[0], f)) { control.stop(); std::cout << "INVALID" << std::endl; continue; }
    rover::Frame response = control.process(f, now);
    char out[rover::MAX_FRAME]; rover::encode(out, response);
    std::cout << out << std::flush;
  }
}
