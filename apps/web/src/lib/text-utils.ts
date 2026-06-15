function flattenTexts(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => flattenTexts(item));
  }
  const text = String(value ?? "").trim();
  if (!text || text === "-" || text === "undefined" || text === "null") {
    return [];
  }
  return [text];
}

export function uniqueTexts(values: unknown[]) {
  const seen = new Set<string>();
  const items: string[] = [];
  values
    .flatMap((value) => flattenTexts(value))
    .forEach((text) => {
      if (seen.has(text)) {
        return;
      }
      seen.add(text);
      items.push(text);
    });
  return items;
}
