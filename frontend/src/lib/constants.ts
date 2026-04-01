export const STATUS_COLORS = {
  auto_match: "bg-green-100 text-green-800 border-green-200",
  review_needed: "bg-yellow-100 text-yellow-800 border-yellow-200",
  no_match: "bg-red-100 text-red-800 border-red-200",
} as const;

export const STATUS_LABELS: Record<string, string> = {
  auto_match: "Найдено",
  review_needed: "На проверку",
  no_match: "Не найдено",
};

export const REQUEST_STATUS_LABELS: Record<string, string> = {
  queued: "В очереди",
  running: "Обработка",
  done: "Готово",
  failed: "Ошибка",
};

export const POLLING_INTERVAL = 3000;
