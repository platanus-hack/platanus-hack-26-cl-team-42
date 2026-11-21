import { useState } from "react";
import { useReviewItem, useValidateReport, type Report, type ReviewItem } from "./api";
import { nextReviewItemId, pendingReviewItems } from "./review";

/** Estado de la revisión por excepción: qué falta, cuál se muestra y las acciones del encabezado. */
export function useReportReview(report: Report, focusSection?: string) {
  const topicFor = (item: ReviewItem) => report.topics.find((topic) => topic.sections.includes(item.section))?.id;
  const [selectedTopicId, selectTopic] = useState(() =>
    report.topics.find((topic) => focusSection && topic.sections.includes(focusSection))?.id
  );
  const review = useReviewItem();
  const save = useValidateReport();
  const pending = pendingReviewItems(report);
  const current = selectedTopicId ? pending.find((item) => topicFor(item) === selectedTopicId) : pending[0];
  const activeTopicId = selectedTopicId ?? (current ? topicFor(current) : report.topics[0]?.id);

  /** Da por revisado el punto actual y pasa directo al siguiente. */
  const validateAndContinue = () => {
    if (!current) {
      selectTopic(undefined);
      return;
    }
    const nextId = nextReviewItemId(pending, current.id);
    const next = pending.find((item) => item.id === nextId);
    review.mutate(
      { reportId: report.id, itemId: current.id },
      { onSuccess: () => selectTopic(next ? topicFor(next) : activeTopicId) },
    );
  };

  return {
    pending,
    current,
    activeTopicId,
    selectTopic,
    validateAndContinue,
    reviewing: review.isPending,
    save: () => save.mutate(report.id),
    saving: save.isPending,
    error: review.isError ? review.error.message : save.isError ? save.error.message : undefined,
  };
}

export type ReportReview = ReturnType<typeof useReportReview>;
