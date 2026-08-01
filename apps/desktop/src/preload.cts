import { contextBridge } from "electron";
import fs from "node:fs";

type RuntimeConfig = {
  apiBaseUrl?: string;
};

const configPath = process.argv
  .find((item) => item.startsWith("--data-agent-config="))
  ?.slice("--data-agent-config=".length);

const config = readRuntimeConfig(configPath);

contextBridge.exposeInMainWorld("__DATA_AGENT_DESKTOP__", {
  apiBaseUrl: config.apiBaseUrl,
});

function readRuntimeConfig(filePath: string | undefined): RuntimeConfig {
  if (!filePath) return {};
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8")) as RuntimeConfig;
  } catch {
    return {};
  }
}
