#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <WiFiUdp.h>
#include <ArduinoJson.h>

#include "config.h"

WiFiUDP udp;

// Broadcasts a WiZ getPilot discovery packet and collects replies for kWizDiscoveryTimeoutMs.
// Returns the IP of the first bulb that responds, or IPAddress() if none replied.
IPAddress discoverWizBulb() {
  const char* discoveryMsg = R"({"method":"getPilot","params":{}})";

  udp.begin(kWizPort);
  udp.beginPacket(IPAddress(255, 255, 255, 255), kWizPort);
  udp.write(reinterpret_cast<const uint8_t*>(discoveryMsg), strlen(discoveryMsg));
  udp.endPacket();

  Serial.println("Broadcast sent, listening for WiZ bulb replies...");

  uint32_t startMs = millis();
  IPAddress found;

  while (millis() - startMs < kWizDiscoveryTimeoutMs) {
    int packetSize = udp.parsePacket();
    if (packetSize > 0) {
      char buf[512];
      int len = udp.read(buf, sizeof(buf) - 1);
      buf[len > 0 ? len : 0] = '\0';

      IPAddress replyIp = udp.remoteIP();
      Serial.printf("Reply from %s: %s\n", replyIp.toString().c_str(), buf);

      if (!found) {
        found = replyIp;
      }
    }
    delay(10);
  }

  return found;
}

void sendWizState(const IPAddress& bulbIp, bool on) {
  StaticJsonDocument<128> doc;
  doc["id"] = 1;
  doc["method"] = "setState";
  doc["params"]["state"] = on;

  char payload[128];
  size_t len = serializeJson(doc, payload, sizeof(payload));

  udp.beginPacket(bulbIp, kWizPort);
  udp.write(reinterpret_cast<const uint8_t*>(payload), len);
  udp.endPacket();

  Serial.printf("Sent setState(%s) to %s\n", on ? "true" : "false", bulbIp.toString().c_str());
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\nESP32 WiZ + Spotify mood lighting - Phase 1 smoke test");

  WiFiManager wm;
  bool connected = wm.autoConnect(kProvisionApName);

  if (!connected) {
    Serial.println("WiFi provisioning failed or timed out - restarting.");
    ESP.restart();
    return;
  }

  Serial.printf("WiFi connected. IP: %s\n", WiFi.localIP().toString().c_str());

  IPAddress bulbIp = discoverWizBulb();

  if (!bulbIp) {
    Serial.println("No WiZ bulb found on the network. Check the bulb is powered and on the same WiFi.");
    return;
  }

  Serial.printf("Using bulb at %s\n", bulbIp.toString().c_str());

  sendWizState(bulbIp, true);
  delay(2000);
  sendWizState(bulbIp, false);
}

void loop() {
  // Phase 1 is a one-shot smoke test; later phases move this into the module system.
}
