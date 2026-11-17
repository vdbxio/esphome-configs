// Host test for components/soc_tracker/soc_tracker.h
//   g++ -std=c++17 -Wall -Wextra -I components tests/soc_tracker_test.cpp -o soc_test && ./soc_test
// Scenarios mirror an 8S 314 Ah LiFePO4 pack charged at 28.0 V CV.

#include "soc_tracker/soc_tracker.h"

#include <cmath>
#include <cstdio>

using soc_tracker::Settings;
using soc_tracker::SocTracker;

static int g_fail = 0, g_pass = 0;

#define CHECK(cond)                                                    \
  do {                                                                 \
    if (cond) {                                                        \
      g_pass++;                                                        \
    } else {                                                           \
      g_fail++;                                                        \
      std::printf("  FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);    \
    }                                                                  \
  } while (0)
#define NEAR(a, b, eps) CHECK(std::fabs((a) - (b)) <= (eps))

static Settings pack() {
  Settings s;
  s.capacity_ah = 314.0f;
  s.charged_v = 27.7f;
  s.tail_a = 4.0f;
  s.detect_s = 180.0f;
  s.charge_eff_pct = 100.0f;
  return s;
}

// Run n one-second steps; returns how many syncs fired.
static int run(SocTracker &t, float amps, float volts, int n, bool battery, const Settings &s) {
  int fired = 0;
  for (int i = 0; i < n; i++) fired += t.step(amps, volts, 1.0f, battery, s) ? 1 : 0;
  return fired;
}

static void test_overcharge_clamp() {
  std::puts("overcharge clamp: charge past full is not banked");
  Settings s = pack();
  s.charged_v = 0.0f;  // isolate the clamp from sync
  SocTracker t;
  t.begin(NAN, 90.0f, s.capacity_ah);
  NEAR(t.remaining_ah, 282.6f, 0.01f);
  run(t, 50.0f, 28.0f, 3600, true, s);  // +50 Ah offered, only 31.4 fit
  NEAR(t.remaining_ah, 314.0f, 1e-3f);
  NEAR(t.soc_percent(), 100.0f, 1e-3f);
  run(t, 10.0f, 28.0f, 3600, true, s);  // keep pushing: still capped
  NEAR(t.remaining_ah, 314.0f, 1e-3f);
  run(t, -31.4f, 26.0f, 360, true, s);  // 6 min at 31.4 A = 3.14 Ah = 1 %
  NEAR(t.soc_percent(), 99.0f, 0.01f);  // moves immediately (old firmware: stuck at 100)
}

static void test_underflow_clamp() {
  std::puts("underflow clamp: deficit below empty is not banked");
  Settings s = pack();
  SocTracker t;
  t.begin(NAN, 1.0f, s.capacity_ah);
  run(t, -100.0f, 24.0f, 600, true, s);
  NEAR(t.remaining_ah, 0.0f, 1e-6f);
  run(t, 31.4f, 25.5f, 360, true, s);  // 3.14 Ah back in
  NEAR(t.soc_percent(), 1.0f, 0.01f);
}

static void test_sync_timer() {
  std::puts("sync timer: fires after detect time, once, sets 100 %");
  Settings s = pack();
  SocTracker t;
  t.begin(200.0f, NAN, s.capacity_ah);
  t.synchronized = false;
  // 28.0 V CV, PwrTool reads ~1 A (offset) — within 4 A tail
  CHECK(run(t, 1.0f, 28.0f, 179, true, s) == 0);
  CHECK(!t.synchronized);
  CHECK(t.remaining_ah < 314.0f);
  CHECK(run(t, 1.0f, 28.0f, 1, true, s) == 1);  // t = 180 s
  CHECK(t.synchronized);
  NEAR(t.soc_percent(), 100.0f, 1e-4f);
  // Latched: holding in float does not re-fire
  CHECK(run(t, 1.0f, 28.0f, 3600, true, s) == 0);
  // Voltage drops below charged_v -> re-arm; next full event fires again
  run(t, -20.0f, 26.5f, 600, true, s);
  CHECK(t.soc_percent() < 100.0f);
  CHECK(run(t, 2.0f, 27.9f, 180, true, s) == 1);
  NEAR(t.soc_percent(), 100.0f, 1e-4f);
}

static void test_timer_resets() {
  std::puts("sync timer resets when the condition breaks");
  Settings s = pack();
  SocTracker t;
  t.begin(250.0f, NAN, s.capacity_ah);
  CHECK(run(t, 3.0f, 28.0f, 170, true, s) == 0);
  CHECK(run(t, 6.0f, 28.0f, 1, true, s) == 0);   // current spike above tail
  CHECK(t.timer_s == 0.0f);
  CHECK(run(t, 3.0f, 28.0f, 170, true, s) == 0);
  CHECK(run(t, 3.0f, 27.6f, 1, true, s) == 0);   // voltage dip below charged_v
  CHECK(t.timer_s == 0.0f);
  CHECK(run(t, 3.0f, 28.0f, 179, true, s) == 0);
  CHECK(run(t, 3.0f, 28.0f, 1, true, s) == 1);
  // Bulk charging at high current never syncs, no matter how long
  SocTracker u;
  u.begin(100.0f, NAN, s.capacity_ah);
  CHECK(run(u, 40.0f, 28.0f, 600, true, s) == 0);
  // Discharging at high voltage (signed current < tail) does count
  SocTracker w;
  w.begin(250.0f, NAN, s.capacity_ah);
  CHECK(run(w, -0.5f, 27.8f, 180, true, s) == 1);
}

static void test_disabled() {
  std::puts("charged voltage 0 disables auto-sync");
  Settings s = pack();
  s.charged_v = 0.0f;
  SocTracker t;
  t.begin(250.0f, NAN, s.capacity_ah);
  CHECK(run(t, 0.0f, 28.0f, 7200, true, s) == 0);
  NEAR(t.remaining_ah, 250.0f, 1e-3f);
}

static void test_mode_switching() {
  std::puts("mode switching: counter frozen outside Battery mode, no jump on return");
  Settings s = pack();
  SocTracker t;
  t.begin(157.0f, NAN, s.capacity_ah);
  // Load / Charger modes report |I| — must not move the counter or the timer
  run(t, 30.0f, 28.0f, 3600, false, s);
  NEAR(t.remaining_ah, 157.0f, 1e-4f);
  run(t, 1.0f, 28.0f, 170, true, s);
  CHECK(t.timer_s > 0.0f);
  run(t, 1.0f, 28.0f, 1, false, s);
  CHECK(t.timer_s == 0.0f);  // leaving Battery mode resets the timer
  float before = t.soc_percent();
  run(t, 0.0f, 26.6f, 1, true, s);
  NEAR(t.soc_percent(), before, 1e-4f);
}

static void test_capacity_change() {
  std::puts("capacity change keeps SoC %, rescales Ah, clears Synchronized");
  Settings s = pack();
  s.capacity_ah = 100.0f;  // default placeholder
  SocTracker t;
  t.begin(NAN, 80.0f, s.capacity_ah);
  t.sync_full();
  run(t, -20.0f, 26.0f, 3600, true, s);  // -20 Ah -> 80 %
  NEAR(t.soc_percent(), 80.0f, 0.01f);
  CHECK(t.synchronized);
  s.capacity_ah = 314.0f;
  run(t, 0.0f, 26.0f, 1, true, s);
  NEAR(t.soc_percent(), 80.0f, 0.01f);
  NEAR(t.remaining_ah, 251.2f, 0.01f);
  CHECK(!t.synchronized);
  // Shrinking can't push remaining above the new capacity
  t.sync_full();
  s.capacity_ah = 200.0f;
  run(t, 0.0f, 26.0f, 1, true, s);
  NEAR(t.remaining_ah, 200.0f, 1e-3f);
  // Capacity 0 -> SoC undefined; recovering capacity starts full, unsynced
  s.capacity_ah = 0.0f;
  run(t, -5.0f, 26.0f, 10, true, s);
  CHECK(std::isnan(t.soc_percent()));
  s.capacity_ah = 314.0f;
  run(t, 0.0f, 26.0f, 1, true, s);
  NEAR(t.soc_percent(), 100.0f, 1e-3f);
  CHECK(!t.synchronized);
}

static void test_upgrade_seeding() {
  std::puts("upgrade seeding from the old soc_percent; restored counter wins after");
  SocTracker t;
  t.begin(NAN, 63.5f, 314.0f);  // first boot of new firmware on an old device
  NEAR(t.soc_percent(), 63.5f, 1e-3f);
  NEAR(t.remaining_ah, 199.39f, 0.01f);
  CHECK(!t.synchronized);
  SocTracker fresh;
  fresh.begin(NAN, 100.0f, 100.0f);  // fresh flash: old initial_value 100
  NEAR(fresh.soc_percent(), 100.0f, 1e-4f);
  SocTracker bad;
  bad.begin(NAN, 250.0f, 100.0f);  // out-of-range legacy value is clamped
  NEAR(bad.soc_percent(), 100.0f, 1e-4f);
  SocTracker nan_legacy;
  nan_legacy.begin(NAN, NAN, 100.0f);
  NEAR(nan_legacy.soc_percent(), 100.0f, 1e-4f);
  SocTracker later;  // second boot: restored counter is used, legacy ignored
  later.synchronized = true;
  later.begin(120.0f, 10.0f, 314.0f);
  NEAR(later.remaining_ah, 120.0f, 1e-4f);
  CHECK(later.synchronized);
}

static void test_small_current_precision() {
  std::puts("small currents are counted accurately on a large pack (no float ulp loss)");
  Settings s = pack();
  s.charged_v = 0.0f;
  SocTracker t;
  t.begin(NAN, 100.0f, s.capacity_ah);
  run(t, -0.1f, 26.6f, 86400, true, s);  // 0.1 A standby load for 24 h = 2.4 Ah
  NEAR(t.remaining_ah, 311.6, 0.001);
}

static void test_charge_efficiency_and_dt() {
  std::puts("charge efficiency applies to charging only; dt guards");
  Settings s = pack();
  s.charged_v = 0.0f;
  s.charge_eff_pct = 95.0f;
  SocTracker t;
  t.begin(100.0f, NAN, s.capacity_ah);
  run(t, 10.0f, 27.0f, 3600, true, s);
  NEAR(t.remaining_ah, 109.5f, 0.01f);
  run(t, -10.0f, 26.0f, 3600, true, s);
  NEAR(t.remaining_ah, 99.5f, 0.01f);
  float r = t.remaining_ah;
  t.step(-10.0f, 26.0f, 0.0f, true, s);       // dt 0
  t.step(-10.0f, 26.0f, -5.0f, true, s);      // negative dt
  t.step(NAN, 26.0f, 1.0f, true, s);          // sensor unavailable
  NEAR(t.remaining_ah, r, 1e-6f);
  t.step(-36.0f, 26.0f, 3600.0f, true, s);    // stall: clipped to 10 s
  NEAR(t.remaining_ah, r - 0.1f, 1e-3f);
}

int main() {
  test_overcharge_clamp();
  test_underflow_clamp();
  test_sync_timer();
  test_timer_resets();
  test_disabled();
  test_mode_switching();
  test_capacity_change();
  test_upgrade_seeding();
  test_small_current_precision();
  test_charge_efficiency_and_dt();
  std::printf("\n%d checks passed, %d failed\n", g_pass, g_fail);
  return g_fail ? 1 : 0;
}
