/**
 * Strips markdown/HTML artifacts from LLM output before it hits a plain <Text>.
 * brain.py's prompts ask for plain text, but models inconsistently comply
 * (bold, bullets, stray tags slip through), so this is the reliable backstop.
 */
export function stripMarkdown(text: string): string {
  return text
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/?[a-z][^>]*>/gi, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/(?<!\w)\*(.+?)\*(?!\w)/g, "$1")
    .replace(/^[-*]\s+/gm, "• ")
    .replace(/\|/g, " ")
    // The app never sets an em or en dash of its own, so model prose gets
    // normalised to match rather than standing out against everything else.
    .replace(/\s*[\u2014\u2013]\s*/g, ", ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
