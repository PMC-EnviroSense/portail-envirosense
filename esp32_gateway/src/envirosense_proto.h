/*
 * envirosense_proto.h
 *
 * Protocole BINAIRE EnviroSense (remplace l'ancien encodage JSON).
 * Fichier partage, IDENTIQUE dans les 3 projets :
 *   STM32/Nucleo_LoRa_COLLECTE/Core/Inc/envirosense_proto.h
 *   STM32/Nucleo_LoRa_LIAISON/Core/Inc/envirosense_proto.h
 *   portail-envirosense/esp32_gateway/src/envirosense_proto.h
 * Toute modification doit etre recopiee dans les 3 (puis tout reflasher).
 *
 * Contenu :
 *   1. Outils communs (petit-boutiste, CRC16)
 *   2. Paquets LoRa du maillage (collecte <-> liaison, relais)
 *   3. Enregistrement capteurs : les 35 champs CSV en binaire
 *   4. Trames UART liaison <-> ESP32
 *
 * Tout est en octets explicites (pas de struct "packed") : le format ne
 * depend ni du compilateur ni du processeur (STM32 Cortex-M0+ / ESP32-S3).
 * Les entiers multi-octets sont en PETIT-BOUTISTE (octet de poids faible en premier).
 * Aucun calcul en virgule flottante : les valeurs decimales sont transportees
 * en entiers mis a l'echelle (ex. 19.6 C avec 2 decimales -> 1960).
 */
#ifndef ENVIROSENSE_PROTO_H
#define ENVIROSENSE_PROTO_H

#include <stdint.h>
#include <stddef.h>

#define ES_PROTO_VERSION 1u

/* ======================================================================
 * 1. OUTILS COMMUNS
 * ====================================================================== */

static inline void es_put_u16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}

static inline void es_put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static inline uint16_t es_get_u16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static inline uint32_t es_get_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

/* CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) : meme CRC que l'ancien JSON */
static inline uint16_t es_crc16_update(uint16_t crc, const uint8_t *d, uint16_t n)
{
    uint16_t i;
    uint8_t b;
    for (i = 0; i < n; i++) {
        crc ^= (uint16_t)((uint16_t)d[i] << 8);
        for (b = 0; b < 8u; b++)
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
    }
    return crc;
}

static inline uint16_t es_crc16(const uint8_t *d, uint16_t n)
{
    return es_crc16_update(0xFFFFu, d, n);
}

/* ======================================================================
 * 2. PAQUETS LORA DU MAILLAGE
 *
 *  Octet  Champ    Taille  Description
 *  0      ver_typ  1       (version << 4) | type
 *  1      st_id    1       station qui a cree le paquet
 *  2      dst      1       destinataire (1 = liaison, 255 = toutes)
 *  3      src      1       emetteur d'origine
 *  4-5    seq      2       numero de mesure (DATA / ACK)
 *  6-9    mid      4       identifiant de message (anti-doublon)
 *  10     hop      1       sauts deja faits
 *  11     ttl      1       sauts restants
 *  12..   corps    0-108   selon le type (ci-dessous)
 *  fin    crc      2       CRC16 de tous les octets precedents
 *
 *  Corps selon le type :
 *   DATA   (1) : per_s u16 (periode actuelle, s) + enregistrement capteurs (section 3)
 *   ACK    (2) : cfg_ms u32 (nouvelle periode demandee, 0 = aucune)
 *   CONFIG (3) : period_ms u32
 *   REPLY  (4) : period_ms u32 + ok u8
 *
 *  Pour relayer un paquet, on le copie tel quel, on fait hop+1 / ttl-1
 *  et on recalcule le CRC (es_pkt_relay).
 * ====================================================================== */

#define ES_PKT_DATA    1u
#define ES_PKT_ACK     2u
#define ES_PKT_CONFIG  3u
#define ES_PKT_REPLY   4u

#define ES_OFF_VERTYP  0u
#define ES_OFF_ST      1u
#define ES_OFF_DST     2u
#define ES_OFF_SRC     3u
#define ES_OFF_SEQ     4u
#define ES_OFF_MID     6u
#define ES_OFF_HOP     10u
#define ES_OFF_TTL     11u
#define ES_HDR_LEN     12u
#define ES_CRC_LEN     2u

typedef struct {
    uint8_t  type;
    uint8_t  st_id;
    uint8_t  dst;
    uint8_t  src;
    uint16_t seq;
    uint32_t mid;
    uint8_t  hop;
    uint8_t  ttl;
} es_hdr_t;

/* Ecrit l'en-tete (12 octets). Le corps s'ecrit ensuite a out + ES_HDR_LEN. */
static inline void es_hdr_write(uint8_t *out, const es_hdr_t *h)
{
    out[ES_OFF_VERTYP] = (uint8_t)((ES_PROTO_VERSION << 4) | (h->type & 0x0Fu));
    out[ES_OFF_ST]  = h->st_id;
    out[ES_OFF_DST] = h->dst;
    out[ES_OFF_SRC] = h->src;
    es_put_u16(out + ES_OFF_SEQ, h->seq);
    es_put_u32(out + ES_OFF_MID, h->mid);
    out[ES_OFF_HOP] = h->hop;
    out[ES_OFF_TTL] = h->ttl;
}

/* Ajoute le CRC apres 'used' octets. Retourne la longueur totale, 0 si trop long. */
static inline uint16_t es_pkt_finish(uint8_t *buf, uint16_t used, uint16_t cap)
{
    if (used < ES_HDR_LEN || (uint16_t)(used + ES_CRC_LEN) > cap) return 0;
    es_put_u16(buf + used, es_crc16(buf, used));
    return (uint16_t)(used + ES_CRC_LEN);
}

/* Verifie version + CRC et lit l'en-tete. Retourne 1 si le paquet est valide.
   *body / *body_len : corps du paquet (entre l'en-tete et le CRC). */
static inline uint8_t es_pkt_parse(const uint8_t *buf, uint16_t len, es_hdr_t *h,
                                   const uint8_t **body, uint16_t *body_len)
{
    if (len < (uint16_t)(ES_HDR_LEN + ES_CRC_LEN)) return 0;
    if ((buf[ES_OFF_VERTYP] >> 4) != ES_PROTO_VERSION) return 0;
    if (es_get_u16(buf + len - ES_CRC_LEN) != es_crc16(buf, (uint16_t)(len - ES_CRC_LEN))) return 0;
    h->type  = (uint8_t)(buf[ES_OFF_VERTYP] & 0x0Fu);
    h->st_id = buf[ES_OFF_ST];
    h->dst   = buf[ES_OFF_DST];
    h->src   = buf[ES_OFF_SRC];
    h->seq   = es_get_u16(buf + ES_OFF_SEQ);
    h->mid   = es_get_u32(buf + ES_OFF_MID);
    h->hop   = buf[ES_OFF_HOP];
    h->ttl   = buf[ES_OFF_TTL];
    *body     = buf + ES_HDR_LEN;
    *body_len = (uint16_t)(len - ES_HDR_LEN - ES_CRC_LEN);
    return 1;
}

/* Copie un paquet valide pour le relayer : hop+1, ttl-1, nouveau CRC.
   Retourne la longueur, 0 si ttl deja a 0 ou tampon trop petit. */
static inline uint16_t es_pkt_relay(const uint8_t *in, uint16_t len, uint8_t *out, uint16_t cap)
{
    uint16_t i;
    if (len < (uint16_t)(ES_HDR_LEN + ES_CRC_LEN) || len > cap) return 0;
    if (in[ES_OFF_TTL] == 0u) return 0;
    for (i = 0; i < len; i++) out[i] = in[i];
    out[ES_OFF_HOP] = (uint8_t)(in[ES_OFF_HOP] + 1u);
    out[ES_OFF_TTL] = (uint8_t)(in[ES_OFF_TTL] - 1u);
    return es_pkt_finish(out, (uint16_t)(len - ES_CRC_LEN), cap);
}

/* ======================================================================
 * 3. ENREGISTREMENT CAPTEURS (35 champs)
 *
 *  Octets 0-4 : masque de presence, 1 bit par champ (bit i = champ i present ;
 *               champ i dans l'octet i/8, bit i%8). Un champ vide dans le CSV
 *               (ou illisible / hors plage) est absent et ne prend AUCUN octet.
 *  Octets 5.. : les valeurs des champs presents, dans l'ordre du CSV,
 *               chacune sur la taille de son type.
 *
 *  Taille : 5 octets (aucune valeur) a 92 octets (35 valeurs).
 *  La ligne de test complete du simulateur (31 valeurs) fait 76 octets,
 *  contre 177 caracteres en CSV texte.
 *
 *  Pour changer la precision d'un champ : modifier ES_FIELD_FMT ci-dessous
 *  (dans les 3 copies de ce fichier), puis reflasher collecte, liaison et ESP32.
 * ====================================================================== */

#define ES_NFIELDS      35u
#define ES_BITMAP_LEN   5u
#define ES_REC_MAX_LEN  92u

/* Types (4 bits de poids fort de ES_FIELD_FMT) */
#define ES_T_U8    1u   /* 1 octet, 0..255                        */
#define ES_T_U16   2u   /* 2 octets, 0..65535                     */
#define ES_T_I16   3u   /* 2 octets, -32768..32767                */
#define ES_T_U32   4u   /* 4 octets, 0..4294967295                */
#define ES_T_I32   5u   /* 4 octets, -2147483648..2147483647      */
#define ES_T_TIME  6u   /* 4 octets : "AAAA-MM-JJTHH:MM:SS" UTC -> secondes depuis 1970 */

#define ES_FMT(t, dec) (uint8_t)(((t) << 4) | (dec))

/* Format de chaque colonne : type + nombre de decimales transportees.
   Plage resultante = plage du type / 10^decimales. */
static const uint8_t ES_FIELD_FMT[ES_NFIELDS] = {
    ES_FMT(ES_T_U32, 0),  /*  0 tick_ms                                 */
    ES_FMT(ES_T_U16, 0),  /*  1 dropped                                 */
    ES_FMT(ES_T_U8,  0),  /*  2 valid                                   */
    ES_FMT(ES_T_TIME,0),  /*  3 utc_iso                                 */
    ES_FMT(ES_T_U8,  0),  /*  4 fix_ok                                  */
    ES_FMT(ES_T_U8,  0),  /*  5 sats                                    */
    ES_FMT(ES_T_U16, 2),  /*  6 pdop          0..655.35                 */
    ES_FMT(ES_T_I32, 7),  /*  7 lat           +-214.7483647 deg         */
    ES_FMT(ES_T_I32, 7),  /*  8 lon           +-214.7483647 deg         */
    ES_FMT(ES_T_I32, 2),  /*  9 alt_m         +-21474836.47 m           */
    ES_FMT(ES_T_U16, 2),  /* 10 speed_kmh     0..655.35                 */
    ES_FMT(ES_T_U32, 0),  /* 11 gps_pvt                                 */
    ES_FMT(ES_T_U16, 1),  /* 12 pm1_0         0..6553.5 ug/m3           */
    ES_FMT(ES_T_U16, 1),  /* 13 pm2_5                                   */
    ES_FMT(ES_T_U16, 1),  /* 14 pm4_0                                   */
    ES_FMT(ES_T_U16, 1),  /* 15 pm10                                    */
    ES_FMT(ES_T_U16, 1),  /* 16 nc_0p5        0..6553.5 #/cm3           */
    ES_FMT(ES_T_U16, 1),  /* 17 nc_1p0                                  */
    ES_FMT(ES_T_U16, 1),  /* 18 nc_2p5                                  */
    ES_FMT(ES_T_U16, 1),  /* 19 nc_4p0                                  */
    ES_FMT(ES_T_U16, 1),  /* 20 nc_10p0                                 */
    ES_FMT(ES_T_I16, 2),  /* 21 temp_c        +-327.67 C                */
    ES_FMT(ES_T_U16, 2),  /* 22 humidity_rh   0..655.35 %               */
    ES_FMT(ES_T_I16, 3),  /* 23 x_g           +-32.767 g                */
    ES_FMT(ES_T_I16, 3),  /* 24 y_g                                     */
    ES_FMT(ES_T_I16, 3),  /* 25 z_g                                     */
    ES_FMT(ES_T_I32, 2),  /* 26 no2_na        +-21474836.47 nA          */
    ES_FMT(ES_T_I32, 2),  /* 27 ox_na                                   */
    ES_FMT(ES_T_I32, 4),  /* 28 no2_ppm       +-214748.3647 ppm         */
    ES_FMT(ES_T_I32, 4),  /* 29 o3_ppm                                  */
    ES_FMT(ES_T_U16, 1),  /* 30 no2we_mv      0..6553.5 mV              */
    ES_FMT(ES_T_U16, 1),  /* 31 no2ae_mv                                */
    ES_FMT(ES_T_U16, 1),  /* 32 o3we_mv                                 */
    ES_FMT(ES_T_U16, 1),  /* 33 o3ae_mv                                 */
    ES_FMT(ES_T_U16, 0),  /* 34 batt_mv       0..65535 mV               */
};

static inline uint8_t es_type_size(uint8_t t)
{
    switch (t) {
    case ES_T_U8:  return 1u;
    case ES_T_U16:
    case ES_T_I16: return 2u;
    default:       return 4u;
    }
}

/* ---- Dates : algorithme de H. Hinnant (calendrier gregorien, sans table) ---- */
static inline int32_t es_days_from_civil(int32_t y, uint32_t m, uint32_t d)
{
    int32_t era;
    uint32_t yoe, doy, doe;
    y -= (m <= 2u) ? 1 : 0;
    era = (y >= 0 ? y : y - 399) / 400;
    yoe = (uint32_t)(y - era * 400);
    doy = (153u * (m + (m > 2u ? (uint32_t)-3 : 9u)) + 2u) / 5u + d - 1u;
    doe = yoe * 365u + yoe / 4u - yoe / 100u + doy;
    return era * 146097 + (int32_t)doe - 719468;
}

static inline void es_civil_from_days(int32_t z, int32_t *y, uint32_t *m, uint32_t *d)
{
    int32_t era;
    uint32_t doe, yoe, doy, mp;
    z += 719468;
    era = (z >= 0 ? z : z - 146096) / 146097;
    doe = (uint32_t)(z - era * 146097);
    yoe = (doe - doe / 1460u + doe / 36524u - doe / 146096u) / 365u;
    doy = doe - (365u * yoe + yoe / 4u - yoe / 100u);
    mp  = (5u * doy + 2u) / 153u;
    *d  = doy - (153u * mp + 2u) / 5u + 1u;
    *m  = mp < 10u ? mp + 3u : mp - 9u;
    *y  = (int32_t)yoe + era * 400 + (*m <= 2u ? 1 : 0);
}

/* Lit n chiffres a partir de s. Retourne 1 si ok. */
static inline uint8_t es_read_digits(const char *s, const char *e, uint8_t n, uint32_t *v)
{
    uint8_t i;
    *v = 0;
    if ((size_t)(e - s) < (size_t)n) return 0;
    for (i = 0; i < n; i++) {
        if (s[i] < '0' || s[i] > '9') return 0;
        *v = *v * 10u + (uint32_t)(s[i] - '0');
    }
    return 1;
}

/* "AAAA-MM-JJTHH:MM:SS" (suivi eventuellement de ".xxx" ou "Z", ignores)
   -> secondes UTC depuis 1970. Retourne 1 si ok. */
static inline uint8_t es_parse_time(const char *s, const char *e, uint32_t *out)
{
    uint32_t y, mo, d, h, mi, se;
    int32_t days;
    if ((size_t)(e - s) < 19u) return 0;
    if (!es_read_digits(s, e, 4, &y) || s[4] != '-' ||
        !es_read_digits(s + 5, e, 2, &mo) || s[7] != '-' ||
        !es_read_digits(s + 8, e, 2, &d) || (s[10] != 'T' && s[10] != ' ') ||
        !es_read_digits(s + 11, e, 2, &h) || s[13] != ':' ||
        !es_read_digits(s + 14, e, 2, &mi) || s[16] != ':' ||
        !es_read_digits(s + 17, e, 2, &se))
        return 0;
    if (y < 1970u || y > 2105u || mo < 1u || mo > 12u || d < 1u || d > 31u ||
        h > 23u || mi > 59u || se > 60u)
        return 0;
    days = es_days_from_civil((int32_t)y, mo, d);
    *out = (uint32_t)days * 86400u + h * 3600u + mi * 60u + se;
    return 1;
}

/* Nombre decimal texte -> entier mis a l'echelle (10^dec), arrondi au plus proche.
   Retourne 1 si ok, 0 si vide, -1 si illisible. Accepte "-0.0", "12", ".5", "3.". */
static inline int8_t es_parse_scaled(const char *s, const char *e, uint8_t dec, int64_t *out)
{
    int64_t v = 0;
    uint8_t neg = 0, ndig = 0, nfrac = 0, seen_dot = 0, round_up = 0;
    while (s < e && (*s == ' ' || *s == '\t')) s++;
    while (e > s && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\r' || e[-1] == '\n')) e--;
    if (s == e) return 0;
    if (*s == '-' || *s == '+') { neg = (uint8_t)(*s == '-'); s++; }
    for (; s < e; s++) {
        if (*s == '.' && !seen_dot) { seen_dot = 1; continue; }
        if (*s < '0' || *s > '9') return -1;
        ndig++;
        if (seen_dot && nfrac >= dec) {            /* decimale en trop : arrondi */
            if (nfrac == dec) { round_up = (uint8_t)(*s >= '5'); nfrac++; }
            continue;
        }
        if (v > 100000000000000LL) return -1;      /* trop grand pour tous les types */
        v = v * 10 + (*s - '0');
        if (seen_dot) nfrac++;
    }
    if (ndig == 0) return -1;
    if (nfrac > dec) nfrac = dec;                  /* compte des decimales gardees */
    while (nfrac < dec) { v *= 10; nfrac++; }
    if (round_up) v++;
    *out = neg ? -v : v;
    return 1;
}

static inline uint8_t es_fits(uint8_t t, int64_t v)
{
    switch (t) {
    case ES_T_U8:  return (uint8_t)(v >= 0 && v <= 255);
    case ES_T_U16: return (uint8_t)(v >= 0 && v <= 65535);
    case ES_T_I16: return (uint8_t)(v >= -32768 && v <= 32767);
    case ES_T_U32: return (uint8_t)(v >= 0 && v <= 4294967295LL);
    default:       return (uint8_t)(v >= -2147483647LL - 1 && v <= 2147483647LL);
    }
}

/* Ligne CSV des capteurs (sans "DATA,") -> enregistrement binaire.
   Retourne la longueur de l'enregistrement (>= 5), 0 si cap trop petit.
   *nfields : nombre de champs dans la ligne ; *nbad : champs illisibles ou
   hors plage (envoyes comme absents). Les champs au-dela du 35e sont ignores. */
static inline uint8_t es_rec_from_csv(const char *csv, uint8_t *out, uint8_t cap,
                                      uint8_t *nfields, uint8_t *nbad)
{
    const char *s = csv, *e;
    uint8_t i, n = ES_BITMAP_LEN, t, sz;
    int64_t v = 0;
    int8_t r;
    *nfields = 0;
    *nbad = 0;
    if (cap < ES_REC_MAX_LEN) return 0;
    for (i = 0; i < ES_BITMAP_LEN; i++) out[i] = 0;
    for (i = 0; ; i++) {
        e = s;
        while (*e && *e != ',') e++;
        (*nfields)++;
        if (i < ES_NFIELDS) {
            t = (uint8_t)(ES_FIELD_FMT[i] >> 4);
            sz = es_type_size(t);
            if (t == ES_T_TIME) {
                uint32_t sec;
                const char *a = s, *b = e;
                while (a < b && *a == ' ') a++;
                if (a == b) r = 0;
                else if (es_parse_time(a, b, &sec)) { r = 1; v = (int64_t)sec; }
                else r = -1;
            } else {
                r = es_parse_scaled(s, e, (uint8_t)(ES_FIELD_FMT[i] & 0x0Fu), &v);
                if (r == 1 && !es_fits(t, v)) r = -1;
            }
            if (r == 1) {
                out[i >> 3] |= (uint8_t)(1u << (i & 7u));
                if (sz == 1u)      out[n] = (uint8_t)v;
                else if (sz == 2u) es_put_u16(out + n, (uint16_t)v);
                else               es_put_u32(out + n, (uint32_t)v);
                n = (uint8_t)(n + sz);
            } else if (r < 0) {
                (*nbad)++;
            }
        }
        if (*e == '\0') break;
        s = e + 1;
    }
    return n;
}

/* Ecrit un entier mis a l'echelle sous forme decimale ("-12.34"). Retourne la longueur. */
static inline uint8_t es_fmt_scaled(char *o, int64_t v, uint8_t dec)
{
    char tmp[24];
    uint8_t n = 0, len = 0, i;
    uint64_t u;
    if (v < 0) { o[len++] = '-'; u = (uint64_t)(-v); } else u = (uint64_t)v;
    do { tmp[n++] = (char)('0' + (u % 10u)); u /= 10u; } while (u || n <= dec);
    for (i = n; i > 0; i--) {
        o[len++] = tmp[i - 1u];
        if (dec && i - 1u == dec) o[len++] = '.';
    }
    return len;
}

/* Enregistrement binaire -> ligne CSV texte de 35 champs (meme format que
   la carte capteurs ; les champs absents sont vides).
   Retourne la longueur de la ligne, ou -1 si l'enregistrement est invalide
   ou si 'cap' est trop petit (prevoir au moins 400 octets). */
static inline int es_rec_to_csv(const uint8_t *rec, uint16_t len, char *out, size_t cap)
{
    uint16_t n = ES_BITMAP_LEN;
    size_t o = 0;
    uint8_t i, t, sz;
    if (len < ES_BITMAP_LEN || cap < 400u) return -1;
    for (i = 0; i < ES_NFIELDS; i++) {
        if (i) out[o++] = ',';
        if (!(rec[i >> 3] & (1u << (i & 7u)))) continue;
        t = (uint8_t)(ES_FIELD_FMT[i] >> 4);
        sz = es_type_size(t);
        if ((uint16_t)(n + sz) > len) return -1;
        if (t == ES_T_TIME) {
            uint32_t sec = es_get_u32(rec + n), sod = sec % 86400u, mo, d;
            int32_t y;
            uint32_t parts[5];
            uint8_t k;
            es_civil_from_days((int32_t)(sec / 86400u), &y, &mo, &d);
            parts[0] = mo; parts[1] = d; parts[2] = sod / 3600u;
            parts[3] = (sod / 60u) % 60u; parts[4] = sod % 60u;
            o += es_fmt_scaled(out + o, y, 0);
            for (k = 0; k < 5u; k++) {
                out[o++] = (char)(k < 2u ? '-' : (k == 2u ? 'T' : ':'));
                out[o++] = (char)('0' + parts[k] / 10u);
                out[o++] = (char)('0' + parts[k] % 10u);
            }
        } else {
            int64_t v;
            if (t == ES_T_U8)       v = rec[n];
            else if (t == ES_T_U16) v = es_get_u16(rec + n);
            else if (t == ES_T_I16) v = (int16_t)es_get_u16(rec + n);
            else if (t == ES_T_U32) v = es_get_u32(rec + n);
            else                    v = (int32_t)es_get_u32(rec + n);
            o += es_fmt_scaled(out + o, v, (uint8_t)(ES_FIELD_FMT[i] & 0x0Fu));
        }
        n = (uint16_t)(n + sz);
    }
    if (n != len) return -1;      /* octets en trop : enregistrement incoherent */
    out[o] = '\0';
    return (int)o;
}

/* ======================================================================
 * 4. TRAMES UART LIAISON <-> ESP32 (115200 8N1)
 *
 *  0xA5 0x5A | type (1) | longueur L (1) | donnees (L) | CRC16 (2)
 *  Le CRC16 couvre type, longueur et donnees.
 *
 *  ES_UART_DATA (0x01), liaison -> ESP32, une par mesure recue :
 *    st_id u8, src u8, seq u16, mid u32, hop u8, rssi i16 (dBm), snr i8 (dB),
 *    puis l'enregistrement capteurs (section 3), recopie tel quel du paquet LoRa.
 *  ES_UART_CFG_ACK (0x02), liaison -> ESP32 :
 *    station u8, periode_s u32, ok u8 (1 = appliquee, 0 = refusee)
 *  ES_UART_SET_INTERVAL (0x81), ESP32 -> liaison :
 *    station u8 (1 ou 255 = toutes les collectes), periode_s u32
 * ====================================================================== */

#define ES_UART_SYNC0         0xA5u
#define ES_UART_SYNC1         0x5Au
#define ES_UART_DATA          0x01u
#define ES_UART_CFG_ACK       0x02u
#define ES_UART_SET_INTERVAL  0x81u
#define ES_UART_DATA_HDR_LEN  12u
#define ES_UART_MAX_PAYLOAD   (ES_UART_DATA_HDR_LEN + ES_REC_MAX_LEN)
#define ES_UART_OVERHEAD      6u
#define ES_UART_MAX_FRAME     (ES_UART_MAX_PAYLOAD + ES_UART_OVERHEAD)

/* Construit une trame. Retourne sa longueur, 0 si trop longue. */
static inline uint16_t es_uart_frame(uint8_t type, const uint8_t *pl, uint8_t len,
                                     uint8_t *out, uint16_t cap)
{
    uint16_t crc, i;
    if (len > ES_UART_MAX_PAYLOAD || (uint16_t)(len + ES_UART_OVERHEAD) > cap) return 0;
    out[0] = ES_UART_SYNC0;
    out[1] = ES_UART_SYNC1;
    out[2] = type;
    out[3] = len;
    for (i = 0; i < len; i++) out[4u + i] = pl[i];
    crc = es_crc16(out + 2, (uint16_t)(len + 2u));
    es_put_u16(out + 4u + len, crc);
    return (uint16_t)(len + ES_UART_OVERHEAD);
}

/* Decodeur de trames, octet par octet (se resynchronise tout seul sur 0xA5 0x5A). */
typedef struct {
    uint8_t  state;
    uint8_t  type;
    uint8_t  len;
    uint8_t  idx;
    uint16_t crc_rx;
    uint16_t crc_errors;
    uint8_t  buf[ES_UART_MAX_PAYLOAD];
} es_uart_rx_t;

static inline void es_uart_rx_init(es_uart_rx_t *p)
{
    p->state = 0;
    p->crc_errors = 0;
}

/* Retourne 1 quand une trame complete et valide est disponible
   (p->type, p->len, p->buf) ; 0 sinon. */
static inline uint8_t es_uart_rx_feed(es_uart_rx_t *p, uint8_t c)
{
    switch (p->state) {
    case 0: if (c == ES_UART_SYNC0) p->state = 1; return 0;
    case 1: p->state = (c == ES_UART_SYNC1) ? 2u : (c == ES_UART_SYNC0 ? 1u : 0u); return 0;
    case 2: p->type = c; p->state = 3; return 0;
    case 3:
        if (c > ES_UART_MAX_PAYLOAD) { p->state = 0; return 0; }
        p->len = c; p->idx = 0; p->state = c ? 4u : 5u; return 0;
    case 4:
        p->buf[p->idx++] = c;
        if (p->idx >= p->len) p->state = 5;
        return 0;
    case 5: p->crc_rx = c; p->state = 6; return 0;
    default: {
        uint8_t hdr[2];
        uint16_t crc;
        p->state = 0;
        p->crc_rx |= (uint16_t)((uint16_t)c << 8);
        hdr[0] = p->type;
        hdr[1] = p->len;
        crc = es_crc16_update(es_crc16(hdr, 2u), p->buf, p->len);
        if (crc != p->crc_rx) { p->crc_errors++; return 0; }
        return 1;
    }
    }
}

#endif /* ENVIROSENSE_PROTO_H */
