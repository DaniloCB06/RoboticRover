#pragma once
#include <stdint.h>
#include <deque>
#include <string>
const int LOW=0, HIGH=1, OUTPUT=1;
extern uint32_t clockMs;
extern int outputs[70];
inline uint32_t millis() { return clockMs; }
inline void digitalWrite(int pin, int value) { outputs[pin]=value; }
inline void analogWrite(int pin, int value) { outputs[pin]=value; }
inline void pinMode(int, int) {}
struct SerialStub {
  std::deque<char> incoming;
  std::string outgoing;
  void begin(int) {}
  int available() { return incoming.size(); }
  char read() { char c=incoming.front(); incoming.pop_front(); return c; }
  void print(const char *s) { outgoing+=s; }
  void feed(const std::string &s) { for(char c:s) incoming.push_back(c); }
};
extern SerialStub Serial;
