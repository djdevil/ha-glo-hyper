#pragma once

#include <cstdint>
#include <vector>

#include "esphome/core/component.h"

namespace esphome::glo_bond_clone {

/// Clona l'abbinamento BLE di un altro ESP32 prima che il Bluetooth parta.
///
/// ESPHome accende il Bluetooth nel loop(): con priorità HARDWARE questo setup()
/// arriva prima, quando la NVS è già aperta ma il controller BT non ancora.
class GloBondClone : public Component {
 public:
  void set_bt_mac(uint64_t mac) { this->bt_mac_ = mac; }
  void set_bond(std::vector<uint8_t> bond) { this->bond_ = std::move(bond); }

  void setup() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::HARDWARE; }

 protected:
  bool apply_mac_();
  bool apply_bond_();

  uint64_t bt_mac_{0};
  std::vector<uint8_t> bond_;
  bool mac_ok_{false};
  bool bond_written_{false};
};

}  // namespace esphome::glo_bond_clone
