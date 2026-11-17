"use strict";

// Run after editing dashboard.html to refresh Node-RED's embedded template.
const fs = require("fs");
const path = require("path");
const file = path.join(__dirname, "flows.json");
const nodes = JSON.parse(fs.readFileSync(file, "utf8"));
const template = nodes.find((node) => node.id === "dashboard-ui-template");
if (!template) throw new Error("Dashboard template node missing");
template.template = fs.readFileSync(path.join(__dirname, "dashboard.html"), "utf8");
fs.writeFileSync(file, JSON.stringify(nodes, null, 2) + "\n");
console.log("Dashboard sincronizada com flows.json");
