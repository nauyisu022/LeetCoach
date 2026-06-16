import { useCallback, useEffect, useState } from "react";
import { fetchLatestRecommendationSet } from "../lib/api";
import type { AgentRecommendationSet } from "../types/api";

type UseRecommendationRefreshOptions = {
  storageKey: string;
  onError: (message: string) => void;
};

export function useRecommendationRefresh({ storageKey, onError }: UseRecommendationRefreshOptions) {
  const [activeRecommendationSourceTaskId, setActiveRecommendationSourceTaskId] = useState<string | null>(() => (
    window.localStorage.getItem(storageKey)
  ));
  const [activeRecommendationSet, setActiveRecommendationSet] = useState<AgentRecommendationSet | null>(null);

  useEffect(() => {
    if (activeRecommendationSourceTaskId) {
      window.localStorage.setItem(storageKey, activeRecommendationSourceTaskId);
    } else {
      window.localStorage.removeItem(storageKey);
    }
  }, [activeRecommendationSourceTaskId, storageKey]);

  useEffect(() => {
    if (!activeRecommendationSourceTaskId) {
      setActiveRecommendationSet(null);
      return;
    }

    let isCurrent = true;
    fetchLatestRecommendationSet(activeRecommendationSourceTaskId)
      .then((response) => {
        if (isCurrent) setActiveRecommendationSet(response.recommendation_set);
      })
      .catch((err: Error) => {
        if (isCurrent) onError(err.message);
      });

    return () => {
      isCurrent = false;
    };
  }, [activeRecommendationSourceTaskId, onError]);

  const refreshRecommendationForTask = useCallback((taskId: string) => {
    fetchLatestRecommendationSet(taskId)
      .then((response) => {
        setActiveRecommendationSourceTaskId(taskId);
        setActiveRecommendationSet(response.recommendation_set);
      })
      .catch((err: Error) => onError(err.message));
  }, [onError]);

  return {
    activeRecommendationSet,
    refreshRecommendationForTask
  };
}
