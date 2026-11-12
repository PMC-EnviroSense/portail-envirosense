#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <LittleFS.h>
#include <time.h>
#include "envirosense_proto.h"   // protocole binaire (meme fichier que les STM32)

HardwareSerial STMSerial(1);

// NE TOUCHEZ PAS (ligne sans // = erreur de compilation, corrigee)
// ===== WIFI =====
const char* WIFI_SSID = "iPhone";
const char* WIFI_PASSWORD = "mikasa23";

// ===== MQTT =====
const char* MQTT_HOST = "172.20.10.13";   // IP du broker MQTT
const int   MQTT_PORT = 1883;
const char* MQTT_USER = "";                // si pas d'utilisateur, laisse vide
const char* MQTT_PASS = "";                // si pas de mot de passe, laisse vide

// IMPORTANT : adapte l'ID de la station
const char* STATION_ID = "1";

// ===== ENVOI DES MESURES AU SITE : 2 FOIS PAR JOUR =====
// Les stations mesurent toujours en continu (LoRa inchange). L'ESP32 garde
// chaque mesure dans sa memoire flash (fichier /tampon.bin, conserve meme
// si l'ESP32 redemarre) et envoie tout au site aux heures ci-dessous.
// Heure du Quebec, obtenue par Internet (NTP), heure d'ete comprise.
//   ENVOI_GROUPE = false  -> ancien fonctionnement : chaque mesure envoyee tout de suite.
//   Envoi immediat pour un test : taper ENVOYER dans le moniteur serie, ou
//   publier {"cmd":"envoyer_maintenant"} sur envirosense/station/<id>/cmd.
const bool ENVOI_GROUPE = true;
const int  HEURES_ENVOI[] = {6, 18};                  // 6 h et 18 h
const char* FUSEAU = "EST5EDT,M3.2.0,M11.1.0";        // heure de l'Est (Sherbrooke)
const char* NTP_1 = "pool.ntp.org";
const char* NTP_2 = "time.google.com";
const char* NTP_3 = "time.nist.gov";

const char* F_TAMPON = "/tampon.bin";   // mesures en attente
const char* F_ENVOI  = "/envoi.bin";    // lot en cours d'envoi (garde si l'envoi echoue)
const size_t TAMPON_MAX_OCTETS = 1000000;   // ~9 000 mesures, environ 2 jours a 20 s
const unsigned long SANS_HEURE_PERIODE_MS = 12UL * 3600UL * 1000UL;

WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Decodeur des trames binaires recues de la station de liaison (STM32)
es_uart_rx_t stmRx;
uint16_t stmCrcErrorsShown = 0;

// Etat de l'envoi groupe
bool fsOk = false;                  // memoire flash utilisable
long mesuresEnTampon = 0;
unsigned long mesuresPerdues = 0;   // tampon plein
long dernierCreneau = -1;           // dernier creneau (jour + heure) deja envoye
bool envoiEnAttente = false;        // un envoi a echoue : nouvel essai chaque minute
bool envoiDemande = false;          // commande ENVOYER / envoyer_maintenant
unsigned long dernierEssaiMs = 0;
unsigned long dernierEnvoiMs = 0;

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

void lireUart();

// ===== HEURE (NTP) =====
bool heureOk() {
  return time(nullptr) > 1700000000;   // apres nov. 2023 = heure recue d'Internet
}

void isoUtc(uint32_t t, char *out, size_t cap) {
  time_t tt = (time_t)t;
  struct tm g;
  gmtime_r(&tt, &g);
  strftime(out, cap, "%Y-%m-%dT%H:%M:%SZ", &g);
}

void connectWiFi() {
  Serial.print("Connexion WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    lireUart();   // ne pas perdre les mesures pendant une coupure WiFi
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

  // Envoi immediat des mesures gardees (test / demonstration).
  // Fait dans loop() : on ne publie pas un gros lot depuis le callback.
  if (msg.indexOf("\"cmd\":\"envoyer_maintenant\"") >= 0) {
    envoiDemande = true;
    return;
  }

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

      // Station visee = l'ID dans le topic : envirosense/station/<id>/cmd
      String t = String(topic);
      int a = t.indexOf("/station/");
      int b = t.indexOf("/cmd");
      String target = (a >= 0 && b > a) ? t.substring(a + 9, b) : String(STATION_ID);
      long targetId = target.toInt();   // 1 ou 255 = toutes les collectes

      if (intervalSec > 0 && targetId >= 1 && targetId <= 255) {
        // Trame binaire lue par la liaison (envirosense_proto.h, ES_UART_SET_INTERVAL)
        uint8_t pl[5];
        uint8_t frame[5 + ES_UART_OVERHEAD];
        pl[0] = (uint8_t)targetId;
        es_put_u32(pl + 1, (uint32_t)intervalSec);
        uint16_t n = es_uart_frame(ES_UART_SET_INTERVAL, pl, sizeof(pl), frame, sizeof(frame));
        STMSerial.write(frame, n);

        Serial.printf("Envoye au STM32 (trame binaire %u octets) : SET_INTERVAL station=%ld periode=%d s\n",
                      (unsigned)n, targetId, intervalSec);

        String ack = "{\"station_id\":" + String(targetId) +
                     ",\"result\":\"sent_to_stm32\",\"cmd\":\"set_interval\",\"value\":" +
                     String(intervalSec) + "}";

        mqttClient.publish(("envirosense/station/" + String(targetId) + "/ack").c_str(), ack.c_str());
      } else {
        Serial.println("Commande ignoree : station ou periode invalide");
      }
    }
  }
}

// ===== TRAMES BINAIRES DE LA LIAISON -> JSON MQTT =====
// Meme JSON qu'avant, plus "recu" : l'heure (UTC) ou l'ESP32 a recu la
// mesure. Avec l'envoi groupe, Django s'en sert pour dater la mesure
// au lieu de l'heure d'arrivee du lot (6 h ou 18 h).

// Mesure : {"station_id":11,"src":11,"seq":3,"mid":12,"hop":0,"rssi":-45,"snr":9,
//           "recu":"2026-11-12T15:00:08Z","csv":"<35 champs>"}
bool buildDataJson(const uint8_t *pl, uint8_t len, uint32_t recu, char *out, size_t cap) {
  static char csv[400];
  char champRecu[40] = "";
  if (len < ES_UART_DATA_HDR_LEN + ES_BITMAP_LEN) return false;
  if (es_rec_to_csv(pl + ES_UART_DATA_HDR_LEN, (uint16_t)(len - ES_UART_DATA_HDR_LEN),
                    csv, sizeof(csv)) < 0) return false;
  if (recu != 0) {
    char iso[24];
    isoUtc(recu, iso, sizeof(iso));
    snprintf(champRecu, sizeof(champRecu), ",\"recu\":\"%s\"", iso);
  }
  int n = snprintf(out, cap,
                   "{\"station_id\":%u,\"src\":%u,\"seq\":%u,\"mid\":%lu,"
                   "\"hop\":%u,\"rssi\":%d,\"snr\":%d%s,\"csv\":\"%s\"}",
                   (unsigned)pl[0], (unsigned)pl[1], (unsigned)es_get_u16(pl + 2),
                   (unsigned long)es_get_u32(pl + 4), (unsigned)pl[8],
                   (int)(int16_t)es_get_u16(pl + 9), (int)(int8_t)pl[11], champRecu, csv);
  return n > 0 && (size_t)n < cap;
}

// Confirmation : {"type":"ack","station_id":11,"cmd":"set_interval","value":30,"ok":1}
bool buildAckJson(const uint8_t *pl, uint8_t len, char *out, size_t cap) {
  if (len < 6) return false;
  int n = snprintf(out, cap,
                   "{\"type\":\"ack\",\"station_id\":%u,\"cmd\":\"set_interval\","
                   "\"value\":%lu,\"ok\":%u}",
                   (unsigned)pl[0], (unsigned long)es_get_u32(pl + 1), (unsigned)pl[5]);
  return n > 0 && (size_t)n < cap;
}

// ===== TAMPON EN MEMOIRE FLASH =====
// Chaque mesure : [heure de reception u32][longueur u8][trame binaire de la liaison]

bool stockerMesure(const uint8_t *pl, uint8_t len, uint32_t recu) {
  File f = LittleFS.open(F_TAMPON, FILE_APPEND);
  if (!f) return false;
  if (f.size() + 5 + len > TAMPON_MAX_OCTETS) {
    f.close();
    mesuresPerdues++;
    Serial.printf("ATTENTION : tampon plein, mesure perdue (total %lu)\n", mesuresPerdues);
    return true;   // traitee (perdue) : ne pas l'envoyer en dehors des heures prevues
  }
  uint8_t h[5];
  es_put_u32(h, recu);
  h[4] = len;
  bool ok = f.write(h, 5) == 5 && f.write(pl, len) == len;
  f.close();
  return ok;
}

long compterMesures(const char *chemin) {
  File f = LittleFS.open(chemin, FILE_READ);
  if (!f) return 0;
  long n = 0;
  uint8_t h[5];
  while (f.read(h, 5) == 5) {
    if (!f.seek(f.position() + h[4])) break;
    n++;
  }
  f.close();
  return n;
}

// Publie toutes les mesures d'un fichier. false = MQTT coupe (on reessaiera).
bool envoyerFichier(const char *chemin, long *nbEnvoyees) {
  static char json[640];
  static uint8_t pl[ES_UART_MAX_PAYLOAD];
  File f = LittleFS.open(chemin, FILE_READ);
  if (!f) return true;
  uint8_t h[5];
  *nbEnvoyees = 0;
  while (f.read(h, 5) == 5) {
    uint8_t len = h[4];
    if (len > sizeof(pl) || f.read(pl, len) != len) break;   // fin abimee : ignoree
    if (!buildDataJson(pl, len, es_get_u32(h), json, sizeof(json))) continue;
    if (!mqttClient.publish(topicData().c_str(), json)) {
      f.close();
      return false;
    }
    (*nbEnvoyees)++;
    if (*nbEnvoyees % 20 == 0) {
      // garder MQTT vivant et ne pas perdre les mesures qui arrivent pendant l'envoi
      mqttClient.loop();
      lireUart();
      delay(10);
    }
  }
  f.close();
  return true;
}

bool envoyerTampon(const char *raison) {
  if (!fsOk) return true;
  if (!mqttClient.connected()) {
    envoiEnAttente = true;
    return false;
  }
  // 2 tours : un lot reste d'un envoi rate, puis les nouvelles mesures
  for (int tour = 0; tour < 2; tour++) {
    if (!LittleFS.exists(F_ENVOI)) {
      if (!LittleFS.exists(F_TAMPON)) break;
      if (!LittleFS.rename(F_TAMPON, F_ENVOI)) break;
      mesuresEnTampon = 0;
    }
    long n = 0;
    Serial.printf("[ENVOI] Envoi des mesures au site (%s)...\n", raison);
    if (!envoyerFichier(F_ENVOI, &n)) {
      Serial.printf("[ENVOI] Interrompu apres %ld mesures (MQTT coupe), nouvel essai dans 1 min\n", n);
      envoiEnAttente = true;
      return false;
    }
    LittleFS.remove(F_ENVOI);
    Serial.printf("[ENVOI] %ld mesures envoyees au site\n", n);
  }
  envoiEnAttente = false;
  dernierEnvoiMs = millis();
  return true;
}

// Appelee dans loop() : envoie aux heures prevues
void verifierHoraire() {
  if (!ENVOI_GROUPE || !fsOk) return;

  if (envoiDemande) {
    envoiDemande = false;
    envoyerTampon("demande manuelle");
  }

  struct tm t;
  if (heureOk() && getLocalTime(&t, 0)) {
    for (size_t i = 0; i < sizeof(HEURES_ENVOI) / sizeof(HEURES_ENVOI[0]); i++) {
      if (t.tm_hour != HEURES_ENVOI[i]) continue;
      long creneau = (long)t.tm_year * 10000L + (long)t.tm_yday * 24L + t.tm_hour;
      if (creneau != dernierCreneau) {
        dernierCreneau = creneau;
        dernierEssaiMs = millis();
        char raison[32];
        snprintf(raison, sizeof(raison), "envoi programme de %d h", HEURES_ENVOI[i]);
        envoyerTampon(raison);
      }
    }
  } else if (millis() - dernierEnvoiMs >= SANS_HEURE_PERIODE_MS) {
    // Pas d'heure Internet (NTP bloque ?) : envoi toutes les 12 h de fonctionnement
    dernierEssaiMs = millis();
    envoyerTampon("heure inconnue, envoi toutes les 12 h");
    dernierEnvoiMs = millis();
  }

  if (envoiEnAttente && millis() - dernierEssaiMs >= 60000UL) {
    dernierEssaiMs = millis();
    envoyerTampon("nouvel essai");
  }
}

void handleStmFrame() {
  static char json[640];
  if (stmRx.type == ES_UART_DATA) {
    uint32_t recu = heureOk() ? (uint32_t)time(nullptr) : 0;
    if (!buildDataJson(stmRx.buf, stmRx.len, recu, json, sizeof(json))) {
      Serial.printf("Trame mesure invalide (%u octets), ignoree\n", (unsigned)stmRx.len);
      return;
    }
    if (ENVOI_GROUPE && fsOk) {
      if (stockerMesure(stmRx.buf, stmRx.len, recu)) {
        mesuresEnTampon++;
        Serial.printf("UART recu du STM32 : mesure station %u gardee pour le prochain envoi (%ld en attente)\n",
                      (unsigned)stmRx.buf[0], mesuresEnTampon);
        return;
      }
      Serial.println("ERREUR memoire flash : mesure envoyee tout de suite");
    }
    Serial.printf("UART recu du STM32 : mesure binaire %u octets -> %s\n", (unsigned)stmRx.len, json);
    bool ok = mqttClient.publish(topicData().c_str(), json);
    Serial.println(ok ? "-> MQTT publie" : "-> ERREUR publication MQTT");
  } else if (stmRx.type == ES_UART_CFG_ACK) {
    // Les confirmations de commande restent immediates (ce ne sont pas des mesures)
    if (!buildAckJson(stmRx.buf, stmRx.len, json, sizeof(json))) return;
    Serial.printf("UART recu du STM32 : confirmation -> %s\n", json);
    bool ok = mqttClient.publish(topicAck().c_str(), json);
    Serial.println(ok ? "-> confirmation publiee (ack)" : "-> ERREUR publication ack");
  } else {
    Serial.printf("Trame inconnue type=0x%02X, ignoree\n", (unsigned)stmRx.type);
  }
}

// Trames binaires de la liaison (0xA5 0x5A | type | longueur | donnees | CRC16)
void lireUart() {
  while (STMSerial.available()) {
    if (es_uart_rx_feed(&stmRx, (uint8_t)STMSerial.read())) {
      handleStmFrame();
    }
  }
}

// Commande tapee dans le moniteur serie : ENVOYER = envoi immediat
void lireCommandeSerie() {
  static char ligne[16];
  static uint8_t n = 0;
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r' || c == '\n') {
      ligne[n] = '\0';
      if (n > 0 && strcasecmp(ligne, "ENVOYER") == 0) {
        Serial.println("Commande ENVOYER recue");
        envoiDemande = true;
      }
      n = 0;
    } else if (n < sizeof(ligne) - 1) {
      ligne[n++] = c;
    }
  }
}

void connectMQTT() {
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  // PubSubClient limite les messages a 256 octets par defaut :
  // une mesure en JSON fait ~300 octets + le topic.
  mqttClient.setBufferSize(1024);

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
      // Commandes du site pour TOUTES les stations (la liaison relaie en LoRa)
      mqttClient.subscribe("envirosense/station/+/cmd");

      String statusMsg = "{\"station_id\":" + String(STATION_ID) + ",\"status\":\"online\"}";
      mqttClient.publish(topicStatus().c_str(), statusMsg.c_str());
    } else {
      Serial.print("echec, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" nouvelle tentative dans 2 sec");
      for (int i = 0; i < 20; i++) {   // 2 s, sans perdre les mesures de la liaison
        delay(100);
        lireUart();
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  STMSerial.setRxBufferSize(4096);   // garde les trames recues pendant un envoi
  STMSerial.begin(115200, SERIAL_8N1, 18, 17); // RX=18, TX=17
  es_uart_rx_init(&stmRx);

  // Laisse le temps au moniteur serie USB de se connecter
  delay(3000);
  Serial.println("ESP32 READY");

  if (ENVOI_GROUPE) {
    fsOk = LittleFS.begin(true);   // true = formate la memoire au 1er demarrage
    if (fsOk) {
      mesuresEnTampon = compterMesures(F_TAMPON);
      envoiEnAttente = LittleFS.exists(F_ENVOI);
      Serial.printf("Envoi groupe a 6 h et 18 h : %ld mesure(s) deja en attente%s\n",
                    mesuresEnTampon, envoiEnAttente ? " + 1 lot a renvoyer" : "");
    } else {
      Serial.println("ERREUR memoire flash (LittleFS) : envoi immediat de chaque mesure");
    }
  }

  connectWiFi();
  configTzTime(FUSEAU, NTP_1, NTP_2, NTP_3);   // heure du Quebec par Internet
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

  // Message d'etat toutes les 5 s (diagnostic)
  static unsigned long lastStatus = 0;
  if (millis() - lastStatus >= 5000) {
    lastStatus = millis();
    Serial.print("[ETAT] WiFi=");
    Serial.print(WiFi.status() == WL_CONNECTED ? "OK" : "NON");
    Serial.print(" IP=");
    Serial.print(WiFi.localIP());
    Serial.print(" MQTT=");
    Serial.print(mqttClient.connected() ? "OK" : "NON");
    if (ENVOI_GROUPE && fsOk) {
      struct tm t;
      if (heureOk() && getLocalTime(&t, 0)) {
        Serial.printf(" HEURE=%02d:%02d", t.tm_hour, t.tm_min);
      } else {
        Serial.print(" HEURE=inconnue");
      }
      Serial.printf(" EN_ATTENTE=%ld", mesuresEnTampon);
    }
    Serial.println("");
  }

  // Signal de vie toutes les 20 s : garde la station de liaison "En ligne"
  // dans le portail (ce n'est pas une mesure : il reste en temps reel)
  static unsigned long lastHeartbeat = 0;
  if (mqttClient.connected() && millis() - lastHeartbeat >= 20000) {
    lastHeartbeat = millis();
    String statusMsg = "{\"station_id\":" + String(STATION_ID) + ",\"status\":\"online\"}";
    mqttClient.publish(topicStatus().c_str(), statusMsg.c_str());
  }

  lireUart();
  lireCommandeSerie();
  verifierHoraire();

  if (stmRx.crc_errors != stmCrcErrorsShown) {
    stmCrcErrorsShown = stmRx.crc_errors;
    Serial.printf("ATTENTION : trame UART corrompue (CRC), total=%u\n", (unsigned)stmCrcErrorsShown);
  }
}

/*
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

*/