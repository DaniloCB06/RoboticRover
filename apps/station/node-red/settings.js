module.exports = {
    flowFile: process.env.NODE_RED_FLOW_FILE || "/data/flows.json",
    uiPort: process.env.PORT || 1880,
    uiHost: process.env.NODE_RED_HOST || "0.0.0.0",
    mqttReconnectTime: 1000,
    functionExternalModules: false,
    functionGlobalContext: { crypto: require("crypto") },
    logging: { console: { level: "info", metrics: false, audit: false } }
};
