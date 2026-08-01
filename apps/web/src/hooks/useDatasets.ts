import { useEffect, useState } from "react";
import type { Dataset } from "../types";
import { fetchDatasets, uploadDataset as apiUpload } from "../api";

export function useDatasets(selectedProjectId: string, onError: (msg: string) => void) {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetIds, setSelectedDatasetIds] = useState<string[]>([]);

  useEffect(() => {
    setSelectedDatasetIds([]);
    const projectId = selectedProjectId || undefined;
    fetchDatasets(projectId)
      .then(setDatasets)
      .catch((err) => {
        onError(err instanceof Error ? err.message : String(err));
        setDatasets([]);
      });
  }, [selectedProjectId]);

  async function uploadDataset(file: File | null) {
    if (!file) return;
    try {
      const projectId = selectedProjectId || undefined;
      await apiUpload(file, projectId);
      const nextDatasets = await fetchDatasets(projectId);
      setDatasets(nextDatasets);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  function toggleDataset(datasetId: string) {
    setSelectedDatasetIds((current) =>
      current.includes(datasetId) ? current.filter((id) => id !== datasetId) : [...current, datasetId]
    );
  }

  return {
    datasets,
    selectedDatasetIds,
    uploadDataset,
    toggleDataset,
  };
}
