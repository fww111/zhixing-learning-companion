const activeMaterialStatuses = new Set([
  "queued",
  "pending",
  "processing",
  "mineru_submitted",
  "mineru_polling",
  "ocr_running",
  "chunking",
  "indexing"
]);

const finalMaterialStatuses = new Set(["parsed", "index_failed", "failed"]);

export interface MaterialStatusLike {
  id: number;
  parse_status: string;
}

export function materialStatusesSettledAfterBackgroundWork(
  previous: MaterialStatusLike[],
  next: MaterialStatusLike[]
): boolean {
  const previousById = new Map(previous.map((material) => [material.id, material.parse_status]));
  return next.some((material) => (
    activeMaterialStatuses.has(previousById.get(material.id) || "")
    && finalMaterialStatuses.has(material.parse_status)
  ));
}
