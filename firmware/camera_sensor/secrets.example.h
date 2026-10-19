// Copy to secrets.h (git-ignored) and fill in.
#pragma once

const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* GATE_NAME = "entry";  // "entry" or "exit"

// Shared secret the backend sends as X-Gate-Token (set BARRIER_TOKEN to the
// same value). Leave empty to skip the check.
const char* GATE_TOKEN = "change-me";
