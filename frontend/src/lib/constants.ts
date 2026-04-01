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

export const DECISION_LABELS: Record<string, string> = {
  accepted: "Принято",
  corrected: "Исправлено",
  rejected: "Отклонено",
};

export const DECISION_COLORS: Record<string, string> = {
  accepted: "bg-green-50 text-green-700 border-green-200",
  corrected: "bg-blue-50 text-blue-700 border-blue-200",
  rejected: "bg-red-50 text-red-700 border-red-200",
};
