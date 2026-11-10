process.env.MQTT_HOST = process.env.MQTT_HOST || "127.0.0.1";
process.env.MQTT_PORT = process.env.MQTT_PORT || "1883";
process.env.STATION_CLIENT_ID = process.env.STATION_CLIENT_ID || "station-nodered-01";
process.env.STATION_SOURCE = process.env.STATION_SOURCE || "station-nodered";

module.exports = {
    flowFile: process.env.NODE_RED_FLOW_FILE || "flows.json",
    uiPort: process.env.PORT || 1880,
    uiHost: process.env.NODE_RED_HOST || "0.0.0.0",
    mqttReconnectTime: 1000,
    functionExternalModules: false,
    functionGlobalContext: { crypto: require("crypto") },
    logging: { console: { level: "info", metrics: false, audit: false } }
};
