#include "prescription.h"

#include <ArduinoJson.h>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <vector>

#include "limits.h"

namespace {

// ArduinoJson intentionally accepts a few JavaScript extensions (single quotes
// and unquoted keys). Gate its input with the actual JSON grammar first.
class JsonSyntax {
 public:
  JsonSyntax(const char* text, size_t length) : text_(text), length_(length) {}
  bool objectDocument() {
    if (!text_ || !length_ || std::memchr(text_, '\0', length_)) return false;
    whitespace();
    if (peek() != '{' || !value(0)) return false;
    whitespace();
    return offset_ == length_;
  }
  uint32_t readableVersion() const { return ambiguousVersion_ ? 0 : readableVersion_; }
  bool duplicateKeys() const { return duplicateKeys_; }

 private:
  char peek() const { return offset_ < length_ ? text_[offset_] : '\0'; }
  void whitespace() {
    while (peek() == ' ' || peek() == '\t' || peek() == '\r' || peek() == '\n')
      ++offset_;
  }
  bool consume(char character) {
    if (peek() != character) return false;
    ++offset_;
    return true;
  }
  bool string() {
    if (!consume('"')) return false;
    while (offset_ < length_) {
      const unsigned char c = static_cast<unsigned char>(text_[offset_++]);
      if (c == '"') return true;
      if (c < 0x20) return false;
      if (c >= 0x80) {
        unsigned continuation = 0;
        uint32_t point = c;
        if (c >= 0xc2 && c <= 0xdf) { continuation = 1; point = c & 0x1f; }
        else if (c >= 0xe0 && c <= 0xef) { continuation = 2; point = c & 0x0f; }
        else if (c >= 0xf0 && c <= 0xf4) { continuation = 3; point = c & 0x07; }
        else return false;
        if (length_ - offset_ < continuation) return false;
        for (unsigned i = 0; i < continuation; ++i) {
          const unsigned char next = static_cast<unsigned char>(text_[offset_++]);
          if ((next & 0xc0) != 0x80) return false;
          point = (point << 6) | (next & 0x3f);
        }
        if ((continuation == 1 && point < 0x80) ||
            (continuation == 2 && point < 0x800) ||
            (continuation == 3 && point < 0x10000) || point > 0x10ffff ||
            (point >= 0xd800 && point <= 0xdfff)) return false;
      }
      if (c == '\\') {
        if (offset_ == length_) return false;
        const char escaped = text_[offset_++];
        if (escaped == 'u') {
          for (unsigned i = 0; i < 4; ++i) {
            const char hex = peek();
            if (!((hex >= '0' && hex <= '9') || (hex >= 'a' && hex <= 'f') ||
                  (hex >= 'A' && hex <= 'F'))) return false;
            ++offset_;
          }
        } else if (escaped != '"' && escaped != '\\' && escaped != '/' &&
                   escaped != 'b' && escaped != 'f' && escaped != 'n' &&
                   escaped != 'r' && escaped != 't') return false;
      }
    }
    return false;
  }
  bool digit() const { return peek() >= '0' && peek() <= '9'; }
  bool number() {
    consume('-');
    if (!consume('0')) {
      if (peek() < '1' || peek() > '9') return false;
      while (digit()) ++offset_;
    }
    if (consume('.')) {
      if (!digit()) return false;
      while (digit()) ++offset_;
    }
    if (consume('e') || consume('E')) {
      if (!consume('+')) consume('-');
      if (!digit()) return false;
      while (digit()) ++offset_;
    }
    return true;
  }
  bool literal(const char* text) {
    const size_t size = std::strlen(text);
    if (length_ - offset_ < size || std::memcmp(text_ + offset_, text, size)) return false;
    offset_ += size;
    return true;
  }
  bool value(unsigned depth) {
    if (depth > 10) return false;
    whitespace();
    if (peek() == '"') return string();
    if (peek() == '{') {
      ++offset_;
      whitespace();
      if (consume('}')) return true;
      std::vector<std::string> keys;
      do {
        whitespace();
        const size_t keyBegin = offset_;
        if (!string()) return false;
        const size_t keyEnd = offset_;
        JsonDocument key;
        if (deserializeJson(key, text_ + keyBegin, keyEnd - keyBegin)) return false;
        const std::string name = key.as<std::string>();
        // Compare decoded names so escaped aliases cannot overwrite a field.
        if (std::find(keys.begin(), keys.end(), name) != keys.end()) {
          duplicateKeys_ = true;
          if (depth == 0 && name == "version") ambiguousVersion_ = true;
        }
        keys.push_back(name);
        whitespace();
        if (!consume(':')) return false;
        whitespace();
        const size_t valueBegin = offset_;
        if (!value(depth + 1)) return false;
        if (depth == 0) {
          if (name == "version") {
            readableVersion_ = 0;
            uint32_t candidate = 0;
            bool integer = valueBegin < offset_;
            for (size_t i = valueBegin; i < offset_; ++i) {
              const char digit = text_[i];
              if (digit < '0' || digit > '9' ||
                  candidate > (2147483647U - static_cast<uint32_t>(digit - '0')) / 10U) {
                integer = false;
                break;
              }
              candidate = candidate * 10U + static_cast<uint32_t>(digit - '0');
            }
            if (integer && candidate) readableVersion_ = candidate;
          }
        }
        whitespace();
        if (consume('}')) return true;
      } while (consume(','));
      return false;
    }
    if (peek() == '[') {
      ++offset_;
      whitespace();
      if (consume(']')) return true;
      do {
        if (!value(depth + 1)) return false;
        whitespace();
        if (consume(']')) return true;
      } while (consume(','));
      return false;
    }
    if (peek() == 't') return literal("true");
    if (peek() == 'f') return literal("false");
    if (peek() == 'n') return literal("null");
    return number();
  }
  const char* text_;
  size_t length_;
  size_t offset_ = 0;
  uint32_t readableVersion_ = 0;
  bool duplicateKeys_ = false;
  bool ambiguousVersion_ = false;
};

bool allowedKey(JsonString key) {
  static const char* keys[] = {"pump_id", "version", "mode", "rate_ml_hr",
      "volume_ml", "proposed_by", "proposed_at", "confirmed_by",
      "confirmed_at", "note"};
  for (const char* allowed : keys)
    if (key.size() == std::strlen(allowed) &&
        std::memcmp(key.c_str(), allowed, key.size()) == 0) return true;
  return false;
}

int digits(const std::string& value, size_t begin, size_t count) {
  if (begin + count > value.size()) return -1;
  int result = 0;
  for (size_t i = begin; i < begin + count; ++i) {
    if (value[i] < '0' || value[i] > '9') return -1;
    result = result * 10 + value[i] - '0';
  }
  return result;
}

bool dateTime(const std::string& value) {
  if (value.size() < 20 || value[4] != '-' || value[7] != '-' ||
      (value[10] != 'T' && value[10] != 't') || value[13] != ':' ||
      value[16] != ':') return false;
  const int year = digits(value, 0, 4), month = digits(value, 5, 2);
  const int day = digits(value, 8, 2), hour = digits(value, 11, 2);
  const int minute = digits(value, 14, 2), second = digits(value, 17, 2);
  if (year < 1 || month < 1 || month > 12 || day < 1 || hour < 0 ||
      hour > 23 || minute < 0 || minute > 59 || second < 0 || second > 59)
    return false;
  const int days[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
  const bool leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
  if (day > days[month - 1] + (month == 2 && leap ? 1 : 0)) return false;
  size_t offset = 19;
  if (value[offset] == '.') {
    ++offset;
    const size_t start = offset;
    while (offset < value.size() && value[offset] >= '0' && value[offset] <= '9')
      ++offset;
    if (start == offset) return false;
  }
  if (offset >= value.size()) return false;
  if (value[offset] == 'Z' || value[offset] == 'z') return offset + 1 == value.size();
  if ((value[offset] != '+' && value[offset] != '-') ||
      value.size() != offset + 6 || value[offset + 3] != ':') return false;
  const int zoneHour = digits(value, offset + 1, 2);
  const int zoneMinute = digits(value, offset + 4, 2);
  return zoneHour >= 0 && zoneHour <= 23 && zoneMinute >= 0 && zoneMinute <= 59;
}

// JSON Schema maxLength counts Unicode characters, not UTF-8 bytes.
bool validNote(const std::string& value) {
  size_t count = 0;
  for (size_t i = 0; i < value.size();) {
    const unsigned char c = static_cast<unsigned char>(value[i]);
    size_t bytes = 1;
    uint32_t codepoint = c;
    if (c >= 0xc2 && c <= 0xdf) { bytes = 2; codepoint = c & 0x1f; }
    else if (c >= 0xe0 && c <= 0xef) { bytes = 3; codepoint = c & 0x0f; }
    else if (c >= 0xf0 && c <= 0xf4) { bytes = 4; codepoint = c & 0x07; }
    else if (c >= 0x80) return false;
    if (i + bytes > value.size()) return false;
    for (size_t j = 1; j < bytes; ++j) {
      const unsigned char next = static_cast<unsigned char>(value[i + j]);
      if ((next & 0xc0) != 0x80) return false;
      codepoint = (codepoint << 6) | (next & 0x3f);
    }
    if ((bytes == 2 && codepoint < 0x80) || (bytes == 3 && codepoint < 0x800) ||
        (bytes == 4 && codepoint < 0x10000) || codepoint > 0x10ffff ||
        (codepoint >= 0xd800 && codepoint <= 0xdfff)) return false;
    i += bytes;
    if (++count > 200) return false;
  }
  return true;
}

bool number(JsonVariantConst value) {
  return !value.is<bool>() && value.is<double>() && std::isfinite(value.as<double>());
}

PrescriptionValidation reject(PrescriptionValidation result, const char* reason) {
  result.outcome = PrescriptionValidation::REJECTED;
  result.reason = reason;
  return result;
}

}  // namespace

PrescriptionValidation parsePrescription(const char* payload, size_t length,
                                        const std::string& pumpId,
                                        uint32_t currentVersion,
                                        uint32_t pendingVersion) {
  PrescriptionValidation result;
  JsonSyntax syntax(payload, length);
  if (!syntax.objectDocument()) return reject(result, "malformed");
  result.version = syntax.readableVersion();
  if (syntax.duplicateKeys()) return reject(result, "malformed");
  JsonDocument document;
  if (deserializeJson(document, payload, length) || !document.is<JsonObject>())
    return reject(result, "malformed");
  JsonObjectConst object = document.as<JsonObjectConst>();
  for (JsonPairConst pair : object)
    if (!allowedKey(pair.key())) return reject(result, "malformed");
  const char* stringKeys[] = {"pump_id", "mode", "proposed_by", "proposed_at"};
  for (const char* key : stringKeys)
    if (!object[key].is<const char*>()) return reject(result, "malformed");
  const char* optionalStrings[] = {"confirmed_by", "confirmed_at", "note"};
  for (const char* key : optionalStrings)
    if (!object[key].isUnbound() && !object[key].is<const char*>())
      return reject(result, "malformed");
  if (!result.version || !number(object["rate_ml_hr"]) ||
      !number(object["volume_ml"]))
    return reject(result, "malformed");
  const std::string actualPump = object["pump_id"].as<std::string>();
  Prescription& prescription = result.prescription;
  prescription.version = result.version;
  prescription.mode = object["mode"].as<std::string>();
  prescription.rateMlHr = object["rate_ml_hr"].as<double>();
  prescription.volumeMl = object["volume_ml"].as<double>();
  prescription.proposedBy = object["proposed_by"].as<std::string>();
  prescription.proposedAt = object["proposed_at"].as<std::string>();
  prescription.confirmedBy = object["confirmed_by"].isUnbound() ? "" : object["confirmed_by"].as<std::string>();
  prescription.confirmedAt = object["confirmed_at"].isUnbound() ? "" : object["confirmed_at"].as<std::string>();
  prescription.note = object["note"].isUnbound() ? "" : object["note"].as<std::string>();
  if (actualPump.empty() || prescription.proposedBy.empty() ||
      (prescription.mode != "continuous" && prescription.mode != "bolus") ||
      !dateTime(prescription.proposedAt) ||
      (!prescription.confirmedAt.empty() && !dateTime(prescription.confirmedAt)) ||
      !validNote(prescription.note)) return reject(result, "malformed");
  if (actualPump != pumpId) return reject(result, "wrong_pump");
  if (prescription.confirmedBy.empty() || prescription.confirmedAt.empty())
    return reject(result, "not_confirmed");
  if (prescription.version == currentVersion || prescription.version == pendingVersion) {
    result.outcome = PrescriptionValidation::IGNORED;
    return result;
  }
  if (prescription.version <= currentVersion || prescription.version <= pendingVersion)
    return reject(result, "stale_version");
  if (prescription.rateMlHr < LIMIT_RATE_MIN_ML_HR ||
      prescription.rateMlHr > LIMIT_RATE_MAX_ML_HR) return reject(result, "rate_out_of_range");
  if (prescription.volumeMl < LIMIT_VOLUME_MIN_ML ||
      prescription.volumeMl > LIMIT_VOLUME_MAX_ML) return reject(result, "volume_out_of_range");
  result.outcome = PrescriptionValidation::ACCEPTED;
  return result;
}

std::string serializePrescription(const Prescription& p, const std::string& pumpId) {
  JsonDocument document;
  document["pump_id"] = pumpId;
  document["version"] = p.version;
  document["mode"] = p.mode;
  document["rate_ml_hr"] = p.rateMlHr;
  document["volume_ml"] = p.volumeMl;
  document["proposed_by"] = p.proposedBy;
  document["proposed_at"] = p.proposedAt;
  document["confirmed_by"] = p.confirmedBy;
  document["confirmed_at"] = p.confirmedAt;
  if (!p.note.empty()) document["note"] = p.note;
  std::string output;
  serializeJson(document, output);
  return output;
}
