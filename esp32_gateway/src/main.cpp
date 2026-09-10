#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>

HardwareSerial STMSerial(1);

/*
// ===== WIFI =====
const char* WIFI_SSID = "TON_WIFI";
const char* WIFI_PASSWORD = "TON_MOT_DE_PASSE_WIFI";

// ===== MQTT =====
const char* MQTT_HOST = "192.168.1.100";   // IP du broker MQTT
const int   MQTT_PORT = 1883;
const char* MQTT_USER = "";                // si pas d'utilisateur, laisse vide
const char* MQTT_PASS = "";                // si pas de mot de passe, laisse vide

// IMPORTANT : adapte l'ID de la station
const char* STATION_ID = "1";

WiFiClient espClient;
PubSubClient mqttClient(espClient);

String uartLine = "";

String topicData() {
  return "envirosense/station/" + String(STATION_ID) + "/data";
}

String topicCmd() {
  return "envirosense/station/" + String(STATION_ID) + "/cmd";
}

String topicAck() {
  return "envirosense/station/" + String(STATION_ID) + "/ack";
}

String topicStatus() {
  return "envirosense/station/" + String(STATION_ID) + "/status";
}

void connectWiFi() {
  Serial.print("Connexion WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi connecte");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }

  Serial.print("MQTT recu [");
  Serial.print(topic);
  Serial.print("] : ");
  Serial.println(msg);

  // On attend un JSON simple du genre:
  // {"cmd":"set_interval","value":30}

  if (msg.indexOf("\"cmd\":\"set_interval\"") >= 0) {
    int pos = msg.indexOf("\"value\":");
    if (pos >= 0) {
      String numberPart = msg.substring(pos + 8);
      numberPart.trim();

      int end1 = numberPart.indexOf("}");
      int end2 = numberPart.indexOf(",");
      int end = -1;

      if (end1 >= 0 && end2 >= 0) end = min(end1, end2);
      else if (end1 >= 0) end = end1;
      else if (end2 >= 0) end = end2;

      if (end >= 0) {
        numberPart = numberPart.substring(0, end);
      }

      numberPart.trim();
      int intervalSec = numberPart.toInt();

      if (intervalSec > 0) {
        String uartCmd = "SET_INTERVAL:" + String(intervalSec);
        STMSerial.println(uartCmd);

        Serial.print("Envoye au STM32: ");
        Serial.println(uartCmd);

        String ack = "{\"station_id\":" + String(STATION_ID) +
                     ",\"result\":\"sent_to_stm32\",\"cmd\":\"set_interval\",\"value\":" +
                     String(intervalSec) + "}";

        mqttClient.publish(topicAck().c_str(), ack.c_str());
      }
    }
  }
}

void connectMQTT() {
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);

  while (!mqttClient.connected()) {
    Serial.print("Connexion MQTT... ");

    bool ok;
    if (strlen(MQTT_USER) == 0) {
      ok = mqttClient.connect(("esp32-" + String(STATION_ID)).c_str());
    } else {
      ok = mqttClient.connect(("esp32-" + String(STATION_ID)).c_str(), MQTT_USER, MQTT_PASS);
    }

    if (ok) {
      Serial.println("OK");
      mqttClient.subscribe(topicCmd().c_str());

      String statusMsg = "{\"station_id\":" + String(STATION_ID) + ",\"status\":\"online\"}";
      mqttClient.publish(topicStatus().c_str(), statusMsg.c_str());
    } else {
      Serial.print("echec, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" nouvelle tentative dans 2 sec");
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  STMSerial.begin(115200, SERIAL_8N1, 18, 17); // RX=18, TX=17

  Serial.println("ESP32 READY");

  connectWiFi();
  connectMQTT();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  if (!mqttClient.connected()) {
    connectMQTT();
  }

  mqttClient.loop();

  while (STMSerial.available()) {
    char c = STMSerial.read();

    if (c == '\n') {
      uartLine.trim();

      if (uartLine.length() > 0) {
        Serial.print("UART recu du STM32: ");
        Serial.println(uartLine);

        // On publie tel quel le JSON reçu du STM32
        mqttClient.publish(topicData().c_str(), uartLine.c_str());
      }

      uartLine = "";
    } else if (c != '\r') {
      uartLine += c;
    }
  }
}

*/
// ===== WIFI =====
// Mets ici le nom EXACT du Wi-Fi public
const char* WIFI_SSID = "UdeS-Public";

void connectWiFi() {
  Serial.println();
  Serial.println("=== TEST WIFI ESP32-S3 ===");

  WiFi.mode(WIFI_STA);

  Serial.print("Connexion au WiFi : ");
  Serial.println(WIFI_SSID);

  // WiFi sans mot de passe
  WiFi.begin(WIFI_SSID);

  unsigned long startTime = millis();

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");

    // Timeout après 20 secondes
    if (millis() - startTime > 20000) {
      Serial.println();
      Serial.println("Echec de connexion WiFi");
      Serial.print("Statut WiFi : ");
      Serial.println(WiFi.status());
      return;
    }
  }

  Serial.println();
  Serial.println("WiFi connecte !");
  Serial.print("Adresse IP : ");
  Serial.println(WiFi.localIP());

  Serial.print("RSSI : ");
  Serial.print(WiFi.RSSI());
  Serial.println(" dBm");
}

void setup() {
  Serial.begin(115200);

  delay(2000);

  Serial.println();
  Serial.println("ESP32 READY");

  connectWiFi();
}
void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi OK | IP : ");
    Serial.print(WiFi.localIP());

    Serial.print(" | RSSI : ");
    Serial.print(WiFi.RSSI());

    Serial.println(" dBm");
  }
  else {
    Serial.println("WiFi non connecte");
  }

  delay(5000);
}