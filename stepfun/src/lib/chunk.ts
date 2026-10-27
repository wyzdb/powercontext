export interface SourceDoc {
  id: string;
  title: string;
  text: string;
  source?: string;
}

export interface Chunk {
  id: string;
  text: string;
  metadata: Record<string, unknown>;
}

export interface ChunkOptions {
  size?: number;
  overlap?: number;
}

export async function sha256(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function splitSentences(text: string): string[] {
  const parts = text
    .replace(/\r\n/g, "\n")
    .split(/(?<=[。！？!?；;])\s*/)
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts : [text.trim()];
}

function splitLongText(text: string, size: number, overlap: number): string[] {
  const sentences = splitSentences(text);
  const chunks: string[] = [];
  let current = "";

  for (const sentence of sentences) {
    if (!current) {
      current = sentence;
      continue;
    }
    if ((current + sentence).length <= size) {
      current += sentence;
      continue;
    }
    chunks.push(current);
    const tail = current.slice(Math.max(0, current.length - overlap));
    current = tail + sentence;
    while (current.length > size * 1.5) {
      chunks.push(current.slice(0, size));
      current = current.slice(size - overlap);
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

export function splitText(
  text: string,
  { size = 300, overlap = 50 }: ChunkOptions = {},
): string[] {
  const normalized = text.replace(/\r\n/g, "\n").replace(/[ \t]+/g, " ").trim();
  if (!normalized) return [];

  const paragraphs = normalized
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  const chunks: string[] = [];
  let buffer = "";
  for (const paragraph of paragraphs) {
    if (paragraph.length > size) {
      if (buffer) {
        chunks.push(buffer);
        buffer = "";
      }
      chunks.push(...splitLongText(paragraph, size, overlap));
      continue;
    }
    if ((buffer + "\n" + paragraph).length <= size) {
      buffer = buffer ? `${buffer}\n${paragraph}` : paragraph;
    } else {
      if (buffer) chunks.push(buffer);
      buffer = paragraph;
    }
  }
  if (buffer) chunks.push(buffer);
  return chunks.filter((chunk) => chunk.trim().length > 0);
}

export async function buildChunks(
  doc: SourceDoc,
  options: ChunkOptions = {},
): Promise<Chunk[]> {
  const texts = splitText(doc.text, options);
  const chunks: Chunk[] = [];
  for (let index = 0; index < texts.length; index += 1) {
    const text = texts[index];
    const digest = await sha256(`${doc.id}:${index}:${text}`);
    chunks.push({
      id: `${doc.id}-${index}-${digest.slice(0, 10)}`,
      text,
      metadata: {
        source: doc.source ?? doc.title,
        title: doc.title,
        chunk: index,
        chunks: texts.length,
        chars: text.length,
      },
    });
  }
  return chunks;
}

export function parseJsonDocs(raw: string, fallbackTitle: string): SourceDoc[] {
  const parsed: unknown = JSON.parse(raw);
  const list = Array.isArray(parsed)
    ? parsed
    : parsed && typeof parsed === "object" && "documents" in parsed
      ? (parsed as { documents: unknown[] }).documents
      : [parsed];

  return list.map((item, index) => {
    if (typeof item === "string") {
      return {
        id: `json-${index}`,
        title: `${fallbackTitle} #${index + 1}`,
        text: item,
      };
    }
    const record = item as Record<string, unknown>;
    const title = String(record.title ?? record.name ?? `${fallbackTitle} #${index + 1}`);
    const text = String(record.text ?? record.content ?? record.body ?? "");
    return {
      id: String(record.id ?? `${fallbackTitle}-${index}`),
      title,
      text,
      source: String(record.source ?? fallbackTitle),
    };
  }).filter((doc) => doc.text.trim().length > 0);
}
