#pragma once
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace rover {
const uint8_t MAX_FRAME = 128;
const int MAX_PWM = 120;  // Limite de bancada, não calibração do motor NXT.
struct Frame { uint32_t session, sequence; char op[9]; int32_t a, b, ttl; };

inline uint16_t crc16(const char *data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= (uint16_t)(uint8_t)data[i] << 8;
    for (uint8_t j = 0; j < 8; ++j)
      crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}

inline bool number(const char *s, int base, bool sign, int64_t low, int64_t high, int64_t &out) {
  if (!*s) return false;
  const char *p = s;
  if (sign && *p == '-') ++p;
  if (!*p) return false;
  uint64_t value = 0;
  for (; *p; ++p) {
    int digit = (*p >= '0' && *p <= '9') ? *p - '0' :
      (*p >= 'A' && *p <= 'F') ? *p - 'A' + 10 :
      (*p >= 'a' && *p <= 'f') ? *p - 'a' + 10 : 99;
    if (digit >= base) return false;
    value = value * base + digit;
    if (value > 0xFFFFFFFFULL) return false;
  }
  out = (*s == '-') ? -(int64_t)value : (int64_t)value;
  return out >= low && out <= high;
}

inline bool decode(char *line, Frame &f) {
  char *last = strrchr(line, '|');
  if (!last || strlen(last + 1) != 4) return false;
  int64_t checksum;
  if (!number(last + 1, 16, false, 0, 65535, checksum) || crc16(line, last - line) != checksum) return false;
  *last = 0;
  char *parts[7]; parts[0] = line;
  uint8_t count = 1;
  for (char *p = line; *p; ++p) {
    if (*p == '|') { if (count == 7) return false; *p = 0; parts[count++] = p + 1; }
  }
  if (count != 7 || strcmp(parts[0], "RR1") || strlen(parts[1]) != 8 || strlen(parts[3]) > 8) return false;
  int64_t v;
  if (!number(parts[1], 16, false, 1, 0xFFFFFFFFLL, v)) return false;
  f.session = (uint32_t)v;
  if (!number(parts[2], 10, false, 1, 0xFFFFFFFFLL, v)) return false;
  f.sequence = (uint32_t)v;
  strcpy(f.op, parts[3]);
  if (!number(parts[4], 10, true, -32768, 32767, v)) return false; f.a = (int32_t)v;
  if (!number(parts[5], 10, true, -32768, 32767, v)) return false; f.b = (int32_t)v;
  if (!number(parts[6], 10, false, 0, 500, v)) return false; f.ttl = (int32_t)v;
  return true;
}

inline void encode(char *out, const Frame &f) {
  int n = snprintf(out, MAX_FRAME, "RR1|%08lX|%lu|%s|%ld|%ld|%ld", (unsigned long)f.session,
    (unsigned long)f.sequence, f.op, (long)f.a, (long)f.b, (long)f.ttl);
  uint16_t crc = crc16(out, n);
  snprintf(out + n, MAX_FRAME - n, "|%04X\n", crc);
}

class Controller {
 public:
  bool armed = false;
  int left = 0, right = 0;
  uint32_t session = 0, sequence = 0, lastMotion = 0, lease = 0;
  void stop() { left = right = 0; armed = false; lease = 0; }
  bool tick(uint32_t now) {
    if (lease && (uint32_t)(now - lastMotion) >= lease) { stop(); return true; }
    return false;
  }
  Frame process(const Frame &f, uint32_t now) {
    tick(now);
    Frame reply = {f.session, f.sequence, "NACK", 1, 0, 0};
    bool hello = !strcmp(f.op, "HELLO");
    bool stopCommand = !strcmp(f.op, "STOP") || !strcmp(f.op, "DISARM");
    // STOP válido sempre reduz a atuação, mesmo em sessão/seq antiga.
    if (stopCommand) stop();
    if (hello) {
      stop(); session = f.session; sequence = f.sequence;
      reply.a = 1;
    } else {
      if (f.session != session || f.sequence <= sequence) { reply.b = armed; return reply; }
      sequence = f.sequence;
      if (!strcmp(f.op, "ARM") && !f.a && !f.b && !f.ttl) {
        stop(); armed = true; reply.a = 2;
      } else if (!strcmp(f.op, "WHEELS") && armed && f.a >= -MAX_PWM && f.a <= MAX_PWM &&
                 f.b >= -MAX_PWM && f.b <= MAX_PWM && f.ttl >= 1 && f.ttl <= 500) {
        // Uma inversão requer primeiro um comando zero, impedindo reversão brusca.
        if ((left && f.a && (left < 0) != (f.a < 0)) ||
            (right && f.b && (right < 0) != (f.b < 0))) { stop(); reply.a = 3; return reply; }
        left = f.a; right = f.b; lastMotion = now; lease = f.ttl; reply.a = 3;
      } else if (stopCommand) { reply.a = !strcmp(f.op, "STOP") ? 4 : 5; }
      else { stop(); reply.a = 2; return reply; }
    }
    strcpy(reply.op, "ACK"); reply.b = armed;
    return reply;
  }
};
}
