// The stream runs on its own server (port 81) because a stream request never
// ends; on the same server it would block /open while the backend is watching.

#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"

#include "secrets.h"

#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

#define STREAM_BOUNDARY "frame"

// Barrier relay. GPIO 13 is free on the AI-Thinker board when the SD card is
// unused; avoid GPIO 12 (a boot strapping pin). Wire it to a relay module's IN.
#define RELAY_PIN 13
#define RELAY_ACTIVE HIGH
#define MAX_OPEN_MS 15000

static httpd_handle_t controlServer = NULL;
static httpd_handle_t streamServer = NULL;
static volatile unsigned long relayCloseAt = 0;

static bool initCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 14;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  sensor->set_gain_ctrl(sensor, 1);
  sensor->set_exposure_ctrl(sensor, 1);
  sensor->set_aec2(sensor, 1);
  return true;
}

static esp_err_t captureHandler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  esp_err_t res = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

static esp_err_t streamHandler(httpd_req_t *req) {
  char part[96];
  esp_err_t res = httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=" STREAM_BOUNDARY);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");

  while (true) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Frame capture failed");
      res = ESP_FAIL;
      break;
    }

    size_t headerLength = snprintf(
      part, sizeof(part),
      "\r\n--" STREAM_BOUNDARY "\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
      fb->len
    );
    res = httpd_resp_send_chunk(req, part, headerLength);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);

    if (res != ESP_OK) break;
  }
  return res;
}

static esp_err_t statusHandler(httpd_req_t *req) {
  char body[192];
  sensor_t *sensor = esp_camera_sensor_get();
  snprintf(
    body, sizeof(body),
    "{\"gate\":\"%s\",\"uptime_s\":%lu,\"rssi\":%d,\"frame_size\":%d,\"psram\":%s,\"barrier_open\":%s}",
    GATE_NAME, millis() / 1000, WiFi.RSSI(), sensor->status.framesize,
    psramFound() ? "true" : "false", relayCloseAt ? "true" : "false"
  );
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, body, HTTPD_RESP_USE_STRLEN);
}

static bool tokenOk(httpd_req_t *req) {
  if (strlen(GATE_TOKEN) == 0) return true;
  char supplied[65] = {0};
  if (httpd_req_get_hdr_value_str(req, "X-Gate-Token", supplied, sizeof(supplied)) != ESP_OK) return false;
  return strcmp(supplied, GATE_TOKEN) == 0;
}

static esp_err_t openHandler(httpd_req_t *req) {
  httpd_resp_set_type(req, "application/json");
  if (!tokenOk(req)) {
    httpd_resp_set_status(req, "401 Unauthorized");
    return httpd_resp_send(req, "{\"error\":\"bad token\"}", HTTPD_RESP_USE_STRLEN);
  }

  unsigned long ms = 4000;
  char query[32], value[8];
  if (httpd_req_get_url_query_str(req, query, sizeof(query)) == ESP_OK &&
      httpd_query_key_value(query, "ms", value, sizeof(value)) == ESP_OK) {
    ms = strtoul(value, NULL, 10);
  }
  if (ms == 0 || ms > MAX_OPEN_MS) ms = 4000;

  digitalWrite(RELAY_PIN, RELAY_ACTIVE);
  relayCloseAt = millis() + ms;  // loop() releases it; never block the server
  Serial.printf("Barrier open for %lu ms\n", ms);

  char body[48];
  snprintf(body, sizeof(body), "{\"open\":true,\"ms\":%lu}", ms);
  return httpd_resp_send(req, body, HTTPD_RESP_USE_STRLEN);
}

static void startServers() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.ctrl_port = 32768;

  httpd_uri_t controlRoutes[] = {
    {"/capture", HTTP_GET, captureHandler, NULL},
    {"/status", HTTP_GET, statusHandler, NULL},
    {"/open", HTTP_POST, openHandler, NULL},
  };
  if (httpd_start(&controlServer, &config) == ESP_OK) {
    for (auto &route : controlRoutes) httpd_register_uri_handler(controlServer, &route);
  }

  config.server_port = 81;
  config.ctrl_port = 32769;
  httpd_uri_t streamRoute = {"/stream", HTTP_GET, streamHandler, NULL};
  if (httpd_start(&streamServer, &config) == ESP_OK) {
    httpd_register_uri_handler(streamServer, &streamRoute);
  }
}

static void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setHostname(strcmp(GATE_NAME, "exit") == 0 ? "parking-exit-cam" : "parking-entry-cam");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nGate %s camera ready: http://%s:81/stream\n", GATE_NAME, WiFi.localIP().toString().c_str());
}

void setup() {
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, !RELAY_ACTIVE);

  Serial.begin(115200);
  Serial.printf("Gate camera starting: %s\n", GATE_NAME);

  if (!initCamera()) {
    delay(5000);
    ESP.restart();
  }

  connectWiFi();
  startServers();
}

void loop() {
  static unsigned long lastWifiCheck = 0;

  if (relayCloseAt && (long)(millis() - relayCloseAt) >= 0) {
    digitalWrite(RELAY_PIN, !RELAY_ACTIVE);
    relayCloseAt = 0;
  }

  if (millis() - lastWifiCheck > 5000) {
    lastWifiCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("WiFi lost, reconnecting");
      WiFi.reconnect();
    }
  }
  delay(20);
}
