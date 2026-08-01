import { useEffect, useState } from "react";
import type { SemanticLayerMeta } from "../types";
import { fetchActiveSemanticLayer } from "../api";

export function useSemanticLayer(selectedProjectId: string, onError: (msg: string) => void) {
  const [semanticLayer, setSemanticLayer] = useState<SemanticLayerMeta | null>(null);

  useEffect(() => {
    if (!selectedProjectId) {
      setSemanticLayer(null);
      return;
    }
    fetchActiveSemanticLayer(selectedProjectId)
      .then(setSemanticLayer)
      .catch((err) => {
        onError(err instanceof Error ? err.message : String(err));
        setSemanticLayer(null);
      });
  }, [selectedProjectId]);

  return {
    semanticLayer,
    onSemanticLayerChange: setSemanticLayer,
  };
}
