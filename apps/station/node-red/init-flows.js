"use strict";

const fs = require("fs");

const source = process.env.ROVER_FLOW_FILE || "/opt/rover/flows.json";
const target = process.env.NODE_RED_FLOW_FILE || "/data/flows.json";

function isStockDockerFlow(file) {
    try {
        const nodes = JSON.parse(fs.readFileSync(file, "utf8"));
        return nodes.length === 2 &&
            nodes.some((node) => node.type === "tab" && node.label === "Flow 1") &&
            nodes.some((node) => node.type === "comment" &&
                node.name.startsWith("WARNING: please check you have started this container"));
    } catch (_) {
        // Arquivos existentes inválidos são preservados para diagnóstico.
        return false;
    }
}

if (!fs.existsSync(target) || isStockDockerFlow(target)) {
    fs.copyFileSync(source, target);
    console.log("Fluxo RoboticRover inicializado em " + target);
} else {
    console.log("Fluxo existente preservado em " + target);
}

// A imagem executa Node-RED como uid/gid 1000; o init roda como root somente
// para corrigir arquivos que o Docker possa ter criado como root no volume.
fs.chownSync(target, 1000, 1000);
