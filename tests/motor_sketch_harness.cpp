#include "Arduino.h"
#include <cassert>
uint32_t clockMs=0;
int outputs[70]={0};
SerialStub Serial;
#include "../firmware/arduino-mega/rover_manual/rover_manual.ino"

void send(uint32_t seq,const char *op,int a=0,int b=0,int ttl=0) {
  rover::Frame frame={1,seq,"",a,b,ttl};
  strcpy(frame.op,op);
  char data[rover::MAX_FRAME]; rover::encode(data,frame);
  Serial.feed(data);
  while(Serial.available()) loop();
}
void assertStopped() {
  assert(!controller.armed && controller.left==0 && controller.right==0);
#if ROVER_DRIVER == 1
  assert(outputs[5]==0 && outputs[6]==0 && outputs[11]==0 && outputs[10]==0);
#else
  assert(outputs[8]==0 && outputs[9]==0);
#endif
}
int main() {
  setup(); assertStopped();
  send(1,"HELLO"); send(2,"ARM"); send(3,"WHEELS",80,80,300);
#if ROVER_DRIVER == 1
  assert(outputs[5]==80 && outputs[6]==0 && outputs[11]==80 && outputs[10]==0);
#else
  assert(outputs[8]==80 && outputs[9]==80 && outputs[4]==1 && outputs[5]==0);
#endif
  clockMs=301; loop(); assertStopped();
  send(4,"ARM"); send(5,"WHEELS",80,80,300);
  Serial.feed("RR1|partial"); loop();
  clockMs+=101; loop(); assertStopped();
  Serial.feed("discard until newline\n"); while(Serial.available()) loop();
  send(6,"ARM"); send(7,"WHEELS",80,80,300);
  Serial.feed(std::string(200,'x')+"\n"); while(Serial.available()) loop(); assertStopped();
  send(8,"ARM"); send(9,"WHEELS",80,80,300);
  Serial.feed("RR1|bad-crc\n"); while(Serial.available()) loop(); assertStopped();
  send(10,"ARM"); send(11,"WHEELS",80,80,300);
  clockMs+=301;
  Serial.feed(std::string(1000,'x')); loop(); assertStopped();
}
