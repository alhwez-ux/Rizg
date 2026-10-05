export function formatRelativeAgo(elapsedMs: number): string {
  const seconds = Math.max(0, Math.floor(elapsedMs / 1000));
  if (seconds < 5) return "قبل لحظات";
  if (seconds < 60) return `قبل ${arabicCount(seconds, "ثانية", "ثانيتين", "ثوانٍ", "ثانية")}`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `قبل ${arabicCount(minutes, "دقيقة", "دقيقتين", "دقائق", "دقيقة")}`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `قبل ${arabicCount(hours, "ساعة", "ساعتين", "ساعات", "ساعة")}`;
  const days = Math.floor(hours / 24);
  return `قبل ${arabicCount(days, "يوم", "يومين", "أيام", "يوماً")}`;
}

function arabicCount(count: number, one: string, two: string, few: string, many: string): string {
  if (count === 1) return one;
  if (count === 2) return two;
  if (count >= 3 && count <= 10) return `${count} ${few}`;
  return `${count} ${many}`;
}
