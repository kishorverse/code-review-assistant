/** Remove the indentation that all non-blank lines share, so snippets start at the code. */
export function dedent(text: string): string {
  const lines = text.split(/\r?\n/)
  const indents = lines
    .filter((line) => line.trim())
    .map((line) => line.length - line.trimStart().length)
  const common = indents.length > 0 ? Math.min(...indents) : 0
  return lines.map((line) => line.slice(common)).join('\n')
}
