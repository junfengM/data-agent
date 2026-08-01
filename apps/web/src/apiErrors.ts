export async function parseApiError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) {
      return payload.detail.map(String).join("; ");
    }
    return JSON.stringify(payload);
  } catch {
    return response.statusText || `HTTP ${response.status}`;
  }
}
