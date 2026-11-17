// SoC tracker: clamped remaining-Ah counter + Victron-style "charged" sync
// Voidbox Industries & Chloe Madison
// VDBX.io / @clomads
// CC-BY-SA 4.0
//
// AI disclaimer: parts written or revised with AI assistance
//
// Header-only and free of ESPHome dependencies so it builds on the host:
//   g++ -std=c++17 -Wall -Wextra -I components tests/soc_tracker_test.cpp
// The ESPHome glue lives in packages/parts/ina2xx-soc.yaml.
//
// Model
//   remaining_ah  owned counter, clamped to [0, capacity] on every step, so charge
//                 above full / below empty is never banked.
//   step()        integrates signed current (+ = charging) in Battery mode only.
//                 Positive charge is scaled by charge efficiency.
//   sync          V >= charged_v AND I <= tail_a, held continuously for detect_s
//                 -> remaining = capacity (100 %). Latched: fires once per full
//                 event, re-armed when V drops below charged_v.
//                 charged_v <= 0 disables auto-sync.
//   capacity      changing capacity keeps the SoC % (rescales remaining) and clears
//                 the Synchronized flag, since the new Ah figure is a guess.

#pragma once

#include <cmath>

namespace soc_tracker {

struct Settings {
  float capacity_ah = 100.0f;
  float charged_v = 0.0f;     // <= 0: auto-sync disabled
  float tail_a = 4.0f;        // signed current must be <= this
  float detect_s = 180.0f;    // condition must hold this long
  float charge_eff_pct = 100.0f;
};

class SocTracker {
 public:
  // Persistent state (mirrored into restored ESPHome globals by the glue)
  // double: a 1 s step at 0.1 A is ~2.8e-5 Ah, about one float ulp at 314 Ah, so a
  // float accumulator would mis-count small loads. Persisted as float (fine for storage).
  double remaining_ah = NAN;
  bool synchronized = false;

  // Runtime state (not persisted)
  double capacity_ref = 0.0;  // capacity remaining_ah is expressed against
  double timer_s = 0.0;        // how long the charged condition has held
  bool latched = false;       // sync fired; waiting for V < charged_v to re-arm
  bool started = false;

  // Max dt honoured per step. A longer gap (loop stall, first call) is clipped
  // so a single bad dt can't swing the counter or satisfy the timer at once.
  static constexpr float kMaxDtS = 10.0f;

  // Call once at boot.
  //   restored_ah: restored counter, NAN when this firmware has never run (upgrade
  //                or fresh flash)
  //   legacy_pct:  restored soc_percent from the old firmware (100 on fresh flash)
  void begin(float restored_ah, float legacy_pct, float capacity_ah) {
    this->capacity_ref = capacity_ah > 0.0f ? capacity_ah : 0.0f;
    if (std::isnan(restored_ah)) {
      float pct = std::isnan(legacy_pct) ? 100.0f : clampf(legacy_pct, 0.0f, 100.0f);
      this->remaining_ah = this->capacity_ref * pct / 100.0;
      this->synchronized = false;
    } else {
      this->remaining_ah = clampd(restored_ah, 0.0, this->capacity_ref);
    }
    this->timer_s = 0.0f;
    this->latched = false;
    this->started = true;
  }

  // Follow a capacity change. Keeps SoC %, clears Synchronized.
  void set_capacity(float capacity_ah) {
    if (!(capacity_ah > 0.0f)) capacity_ah = 0.0f;
    if (capacity_ah == this->capacity_ref) return;
    if (this->capacity_ref > 0.0f && !std::isnan(this->remaining_ah)) {
      this->remaining_ah *= capacity_ah / this->capacity_ref;
    } else {
      // No meaningful previous value (capacity was 0): assume full, unsynced.
      this->remaining_ah = capacity_ah;
    }
    this->remaining_ah = clampd(this->remaining_ah, 0.0, capacity_ah);
    this->capacity_ref = capacity_ah;
    this->synchronized = false;
    this->timer_s = 0.0f;
  }

  // Set to full (manual "Reset SoC to 100%" or auto-sync).
  void sync_full() {
    this->remaining_ah = this->capacity_ref;
    this->synchronized = true;
    this->timer_s = 0.0f;
  }

  // One integration step. Returns true when an auto-sync fired on this step.
  bool step(float current_a, float voltage_v, float dt_s, bool battery_mode, const Settings &s) {
    if (!this->started) this->begin(NAN, 100.0f, s.capacity_ah);
    this->set_capacity(s.capacity_ah);

    if (!(dt_s > 0.0f)) return false;
    if (dt_s > kMaxDtS) dt_s = kMaxDtS;

    // Load/Charger modes report |I| and don't describe the battery: freeze.
    if (!battery_mode || this->capacity_ref <= 0.0f || std::isnan(current_a)) {
      this->timer_s = 0.0f;
      return false;
    }

    double dah = (double) current_a * dt_s / 3600.0;
    if (dah > 0.0) dah *= clampd(s.charge_eff_pct, 0.0, 100.0) / 100.0;
    this->remaining_ah = clampd(this->remaining_ah + dah, 0.0, this->capacity_ref);

    // --- auto-sync ---
    if (!(s.charged_v > 0.0f) || std::isnan(voltage_v)) {
      this->timer_s = 0.0f;
      this->latched = false;
      return false;
    }
    if (voltage_v < s.charged_v) this->latched = false;  // full event over: re-arm

    bool charged = voltage_v >= s.charged_v && current_a <= s.tail_a;
    if (!charged || this->latched) {
      this->timer_s = 0.0f;
      return false;
    }
    this->timer_s += dt_s;
    if (this->timer_s < s.detect_s) return false;

    this->sync_full();
    this->latched = true;
    return true;
  }

  // SoC in percent; NAN when capacity is 0 (undefined).
  float soc_percent() const {
    if (!(this->capacity_ref > 0.0) || std::isnan(this->remaining_ah)) return NAN;
    return (float) clampd(100.0 * this->remaining_ah / this->capacity_ref, 0.0, 100.0);
  }

  static float clampf(float v, float lo, float hi) { return (float) clampd(v, lo, hi); }
  static double clampd(double v, double lo, double hi) {
    if (std::isnan(v)) return lo;
    return v < lo ? lo : (v > hi ? hi : v);
  }
};

// Single instance shared by the YAML lambdas.
inline SocTracker &tracker() {
  static SocTracker t;
  return t;
}

}  // namespace soc_tracker
