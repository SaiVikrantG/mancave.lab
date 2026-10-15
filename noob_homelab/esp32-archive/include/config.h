#pragma once

// Non-secret compile-time constants. Secrets live in include/secrets.h (gitignored).

constexpr uint16_t kWizPort = 38899;
constexpr uint32_t kWizDiscoveryTimeoutMs = 2000;

// WiFiManager captive-portal AP name shown during first-time setup.
constexpr const char* kProvisionApName = "ESP32-WizLight-Setup";
