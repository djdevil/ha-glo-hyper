#include "glo_bond_clone.h"

#include <cstring>

#include <esp_mac.h>
#include <nvs.h>

#include "esphome/core/log.h"

namespace esphome::glo_bond_clone {

static const char *const TAG = "glo_bond_clone";
// Namespace e chiave in cui Bluedroid (ESP-IDF) salva gli abbinamenti BLE.
static const char *const BT_NAMESPACE = "bt_config.conf";
static const char *const BT_KEY = "bt_cfg_key0";

void GloBondClone::setup() {
  this->mac_ok_ = this->apply_mac_();
  if (!this->mac_ok_) {
    // Senza il MAC giusto il glo rifiuterebbe comunque: non tocco la NVS.
    this->mark_failed();
    return;
  }
  if (!this->apply_bond_()) {
    this->mark_failed();
  }
}

bool GloBondClone::apply_mac_() {
  uint8_t mac[6];
  for (int i = 0; i < 6; i++) {
    mac[i] = static_cast<uint8_t>(this->bt_mac_ >> (8 * (5 - i)));
  }
  esp_err_t err = esp_iface_mac_addr_set(mac, ESP_MAC_BT);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Impossibile impostare il MAC Bluetooth: %s", esp_err_to_name(err));
    return false;
  }
  return true;
}

bool GloBondClone::apply_bond_() {
  nvs_handle_t handle;
  esp_err_t err = nvs_open(BT_NAMESPACE, NVS_READWRITE, &handle);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "nvs_open fallito: %s", esp_err_to_name(err));
    return false;
  }

  // Riscrivo solo se diverso: evita di consumare la flash a ogni avvio.
  size_t size = 0;
  bool same = false;
  if (nvs_get_blob(handle, BT_KEY, nullptr, &size) == ESP_OK && size == this->bond_.size()) {
    std::vector<uint8_t> current(size);
    if (nvs_get_blob(handle, BT_KEY, current.data(), &size) == ESP_OK) {
      same = std::memcmp(current.data(), this->bond_.data(), size) == 0;
    }
  }

  if (!same) {
    err = nvs_set_blob(handle, BT_KEY, this->bond_.data(), this->bond_.size());
    if (err == ESP_OK) {
      err = nvs_commit(handle);
    }
    if (err != ESP_OK) {
      ESP_LOGE(TAG, "Scrittura dell'abbinamento fallita: %s", esp_err_to_name(err));
      nvs_close(handle);
      return false;
    }
    this->bond_written_ = true;
  }
  nvs_close(handle);
  return true;
}

void GloBondClone::dump_config() {
  uint8_t mac[6] = {};
  esp_read_mac(mac, ESP_MAC_BT);
  ESP_LOGCONFIG(TAG,
                "glo bond clone:\n"
                "  MAC Bluetooth: %02X:%02X:%02X:%02X:%02X:%02X (%s)\n"
                "  Abbinamento: %u byte, %s",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], this->mac_ok_ ? "impostato" : "ERRORE",
                static_cast<unsigned>(this->bond_.size()),
                this->bond_written_ ? "scritto ora" : "già presente");
}

}  // namespace esphome::glo_bond_clone
