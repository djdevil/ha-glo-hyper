#include "glo_bond_clone.h"

#include <cstring>

#include <esp_mac.h>
#include <nvs.h>

#include "esphome/core/defines.h"
#include "esphome/core/log.h"

namespace esphome::glo_bond_clone {

static const char *const TAG = "glo_bond_clone";
// Namespace e chiave in cui Bluedroid (ESP-IDF) salva gli abbinamenti BLE.
static const char *const BT_NAMESPACE = "bt_config.conf";
static const char *const BT_KEY = "bt_cfg_key0";

/// MAC Bluetooth vero del chip: MAC base di fabbrica + 2, come fa ESP-IDF sull'ESP32.
static void real_bt_mac(uint8_t mac[6]) {
  esp_efuse_mac_get_default(mac);
  mac[5] += 2;
}

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
  uint8_t radio[6] = {};
  esp_read_mac(radio, ESP_MAC_BT);
  uint8_t real[6] = {};
  real_bt_mac(real);
#ifdef USE_GLO_BOND_CLONE_REAL_MAC
  const char *reported = "MAC vero";
#else
  const char *reported = "MAC clonato";
#endif
  ESP_LOGCONFIG(TAG,
                "glo bond clone:\n"
                "  MAC Bluetooth radio: %02X:%02X:%02X:%02X:%02X:%02X (%s)\n"
                "  MAC vero del chip: %02X:%02X:%02X:%02X:%02X:%02X\n"
                "  Comunicato a Home Assistant: %s\n"
                "  Abbinamento: %u byte, %s",
                radio[0], radio[1], radio[2], radio[3], radio[4], radio[5],
                this->mac_ok_ ? "impostato" : "ERRORE", real[0], real[1], real[2], real[3], real[4],
                real[5], reported, static_cast<unsigned>(this->bond_.size()),
                this->bond_written_ ? "scritto ora" : "già presente");
}

}  // namespace esphome::glo_bond_clone

#ifdef USE_GLO_BOND_CLONE_REAL_MAC
// Con -Wl,--wrap=esp_bt_dev_get_address ogni chiamata a esp_bt_dev_get_address()
// arriva qui. ESPHome la usa solo per comunicare il MAC dell'adattatore a Home
// Assistant: restituendo quello vero, ogni ESP resta uno scanner distinto, mentre la
// radio (che prende l'indirizzo dal controller) usa quello clonato verso il glo.
extern "C" const uint8_t *__wrap_esp_bt_dev_get_address(void) {
  static uint8_t mac[6] = {};
  esphome::glo_bond_clone::real_bt_mac(mac);
  return mac;
}
#endif
