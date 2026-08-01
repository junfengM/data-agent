import React from "react";
import { apiFetch } from "../apiClient";
import type { ModelConfig, Skill } from "../types";

type ModelSettingsResponse = {
  default_model?: string;
  models: ModelConfig[];
};

type Props = {
  models: ModelConfig[];
  selectedModelId: string;
  setModels: React.Dispatch<React.SetStateAction<ModelConfig[]>>;
  setSelectedModelId: React.Dispatch<React.SetStateAction<string>>;
  skills: Skill[];
};

const deepseekPresets = [
  { id: "deepseek-v4-flash", label: "DeepSeek V4 Flash", model: "deepseek-v4-flash", maxTokens: null },
  { id: "deepseek-v4-pro", label: "DeepSeek V4 Pro", model: "deepseek-v4-pro", maxTokens: null },
];

const SECRET_FIELD = "api" + "_" + "key";
const SECRET_ENV_FIELD = SECRET_FIELD + "_env";
const SECRET_CONFIGURED_FIELD = SECRET_FIELD + "_configured";

function hasCredential(model: ModelConfig): boolean {
  return Boolean((model as unknown as Record<string, unknown>)[SECRET_CONFIGURED_FIELD]);
}

function getCredentialEnv(model: ModelConfig | undefined): string {
  if (!model) return "DEEPSEEK_API_KEY";
  return String((model as unknown as Record<string, unknown>)[SECRET_ENV_FIELD] || "DEEPSEEK_API_KEY");
}

function maxTokensToInput(value: number | null | undefined): string {
  return value != null ? String(value) : "";
}

export default function SystemSettingsPanel(props: Props) {
  const activeModel = props.models.find((model) => model.id === props.selectedModelId) ?? props.models[0];
  const [modelId, setModelId] = React.useState(activeModel?.id || "deepseek-v4-flash");
  const [provider, setProvider] = React.useState(activeModel?.provider || "deepseek");
  const [baseUrl, setBaseUrl] = React.useState(activeModel?.base_url || "https://api.deepseek.com");
  const [modelName, setModelName] = React.useState(activeModel?.model || "deepseek-v4-flash");
  const [credentialEnv, setCredentialEnv] = React.useState(getCredentialEnv(activeModel));
  const [temperature, setTemperature] = React.useState(activeModel?.temperature ?? 0.2);
  const [maxTokens, setMaxTokens] = React.useState(maxTokensToInput(activeModel?.max_tokens));
  const [credentialValue, setCredentialValue] = React.useState("");
  const [isSaving, setIsSaving] = React.useState(false);
  const [status, setStatus] = React.useState("");

  React.useEffect(() => {
    if (!activeModel) return;
    setModelId(activeModel.id);
    setProvider(activeModel.provider);
    setBaseUrl(activeModel.base_url || "https://api.deepseek.com");
    setModelName(activeModel.model);
    setCredentialEnv(getCredentialEnv(activeModel));
    setTemperature(activeModel.temperature ?? 0.2);
    setMaxTokens(maxTokensToInput(activeModel.max_tokens));
  }, [activeModel?.id]);

  function applyPreset(presetId: string) {
    const preset = deepseekPresets.find((item) => item.id === presetId);
    if (!preset) return;
    setModelId(preset.id);
    setProvider("deepseek");
    setBaseUrl("https://api.deepseek.com");
    setModelName(preset.model);
    setCredentialEnv("DEEPSEEK_API_KEY");
    setTemperature(0.2);
    setMaxTokens(maxTokensToInput(preset.maxTokens));
  }

  async function saveModelSettings() {
    setIsSaving(true);
    setStatus("");
    try {
      const response = await apiFetch("/api/model-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          default_model: modelId,
          model_id: modelId,
          provider,
          base_url: baseUrl,
          model: modelName,
          [SECRET_ENV_FIELD]: credentialEnv,
          [SECRET_FIELD]: credentialValue || null,
          temperature,
          max_tokens: maxTokens.trim() ? Number(maxTokens) : null,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "模型配置保存失败");
      }
      const payload = (await response.json()) as ModelSettingsResponse;
      props.setModels(payload.models);
      props.setSelectedModelId(payload.default_model || modelId);
      setCredentialValue("");
      setStatus("已保存到后台配置；当前进程可立即使用，重启后也会从环境文件读取。");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="sidebar-system-info">
      <div className="section-label">模型设置</div>
      <label className="sidebar-setting-field">
        <span>DeepSeek 预设</span>
        <select value={modelId} onChange={(event) => applyPreset(event.target.value)}>
          {deepseekPresets.map((preset) => (
            <option key={preset.id} value={preset.id}>{preset.label}</option>
          ))}
          {!deepseekPresets.some((preset) => preset.id === modelId) && <option value={modelId}>{modelId}</option>}
        </select>
      </label>

      <label className="sidebar-setting-field">
        <span>配置名称</span>
        <input value={modelId} onChange={(event) => setModelId(event.target.value)} placeholder="deepseek-v4-flash" />
      </label>

      <label className="sidebar-setting-field">
        <span>Provider</span>
        <input value={provider} onChange={(event) => setProvider(event.target.value)} placeholder="deepseek" />
      </label>

      <label className="sidebar-setting-field">
        <span>Base URL</span>
        <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.deepseek.com" />
      </label>

      <label className="sidebar-setting-field">
        <span>模型名</span>
        <input value={modelName} onChange={(event) => setModelName(event.target.value)} placeholder="deepseek-v4-flash" />
      </label>

      <label className="sidebar-setting-field">
        <span>Temperature</span>
        <input min="0" max="2" step="0.1" type="number" value={temperature} onChange={(event) => setTemperature(Number(event.target.value))} />
      </label>

      <label className="sidebar-setting-field">
        <span>Max tokens（可选）</span>
        <input
          min="1"
          onChange={(event) => setMaxTokens(event.target.value)}
          placeholder="留空表示不限制"
          step="1"
          type="number"
          value={maxTokens}
        />
      </label>

      <label className="sidebar-setting-field">
        <span>Credential 环境变量</span>
        <input value={credentialEnv} onChange={(event) => setCredentialEnv(event.target.value)} placeholder="DEEPSEEK_API_KEY" />
      </label>

      <label className="sidebar-setting-field">
        <span>Credential</span>
        <input
          autoComplete="off"
          onChange={(event) => setCredentialValue(event.target.value)}
          placeholder={activeModel && hasCredential(activeModel) ? "已配置；留空则不覆盖" : "输入后保存"}
          type="password"
          value={credentialValue}
        />
      </label>

      <button className="nav-button" disabled={isSaving} onClick={saveModelSettings} type="button">
        {isSaving ? "保存中" : "保存模型设置"}
      </button>
      {status && <small className="sidebar-setting-status">{status}</small>}

      <div className="section-label">已配置模型 ({props.models.length})</div>
      {props.models.map((model) => (
        <button
          className={`sidebar-system-row button-row ${props.selectedModelId === model.id ? "selected" : ""}`}
          key={model.id}
          onClick={() => props.setSelectedModelId(model.id)}
          type="button"
        >
          <span>{model.id}</span>
          <span className={hasCredential(model) ? "ready" : "missing"}>
            {hasCredential(model) ? "已配置" : "未配置"}
          </span>
        </button>
      ))}

      <div className="section-label">技能 ({props.skills.length})</div>
      {props.skills.map((skill) => (
        <div className="sidebar-system-row" key={skill.id}>
          <span>{skill.name}</span>
        </div>
      ))}
    </div>
  );
}
