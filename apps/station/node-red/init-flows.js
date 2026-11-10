"use strict";

const fs = require("fs");

const source = process.env.ROVER_FLOW_FILE || "/opt/rover/flows.json";
const target = process.env.NODE_RED_FLOW_FILE || "/data/flows.json";

function isStockOrOutdatedRoverFlow(file) {
    try {
        const nodes = JSON.parse(fs.readFileSync(file, "utf8"));
        if (!Array.isArray(nodes)) return false;
        const isStock = nodes.length === 2 &&
            nodes.some((node) => node.type === "tab" && node.label === "Flow 1") &&
            nodes.some((node) => node.type === "comment" &&
                node.name.startsWith("WARNING: please check you have started this container"));
        const isOutdatedRover = nodes.some((node) => node.id === "rover-tab") && (
            !nodes.some((node) => node.id === "dashboard-http-in") ||
            nodes.some((node) => node.id === "validate" && typeof node.func === "string" && node.func.includes("p.simulated !== true"))
        );
        return isStock || isOutdatedRover;
    } catch (_) {
        // Arquivos existentes inválidos são preservados para diagnóstico.
        return false;
    }
}

if (!fs.existsSync(target) || isStockOrOutdatedRoverFlow(target)) {
    const nodes = JSON.parse(fs.readFileSync(source, "utf8"));
    for (const node of nodes) {
        if (node.id === "broker") {
            node.broker = "${MQTT_HOST}";
            node.port = "${MQTT_PORT}";
            node.clientid = "${STATION_CLIENT_ID}";
        }
    }
    fs.writeFileSync(target, JSON.stringify(nodes, null, 2) + "\n", "utf8");
    console.log("Fluxo RoboticRover inicializado/atualizado em " + target);
} else {
    console.log("Fluxo existente preservado em " + target);
}

// A imagem executa Node-RED como uid/gid 1000; o init roda como root somente
// para corrigir arquivos que o Docker possa ter criado como root no volume.
fs.chownSync(target, 1000, 1000);
