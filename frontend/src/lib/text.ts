/** Remove the indentation that all non-blank lines share, so snippets start at the code. */
export function dedent(text: string): string {
  const lines = text.split(/\r?\n/)
  const indents = lines
    .filter((line) => line.trim())
    .map((line) => line.length - line.trimStart().length)
  const common = indents.length > 0 ? Math.min(...indents) : 0
  return lines.map((line) => line.slice(common)).join('\n')
}

/** The folder every path lies in, with its trailing slash, or '' when they share none. */
export function commonFolder(paths: string[]): string {
  const [first, ...rest] = paths
  if (first === undefined) return ''
  let folder = first.slice(0, first.lastIndexOf('/') + 1)
  for (const path of rest) {
    while (folder && !path.startsWith(folder)) {
      folder = folder.slice(0, folder.slice(0, -1).lastIndexOf('/') + 1)
    }
  }
  return folder
}
