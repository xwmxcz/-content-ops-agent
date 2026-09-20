// Reads a Server-Sent Events body from fetch(). EventSource cannot send a POST
// body or an Authorization header, which the chat stream needs, so the framing
// EventSource would do is done here.
export interface SseFrame {
  event: string
  data: string
}

/**
 * Calls `onFrame` for every complete frame in `body`. A frame may arrive split
 * across any number of chunks, including in the middle of a multi-byte
 * character or of the blank line that terminates it.
 */
export async function readSseStream(body: ReadableStream<Uint8Array>, onFrame: (frame: SseFrame) => void) {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const drain = (final: boolean) => {
    buffer = buffer.replace(/\r\n?/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      emit(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')
    }
    // A stream that ends without the closing blank line still delivered a frame.
    if (final && buffer.trim()) emit(buffer)
  }

  const emit = (block: string) => {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (!line || line.startsWith(':')) continue
      const separator = line.indexOf(':')
      const field = separator === -1 ? line : line.slice(0, separator)
      const value = separator === -1 ? '' : line.slice(separator + 1).replace(/^ /, '')
      if (field === 'event') event = value
      else if (field === 'data') data.push(value)
    }
    // A comment-only block is a keepalive, not a frame.
    if (data.length) onFrame({ event, data: data.join('\n') })
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      drain(false)
    }
    buffer += decoder.decode()
    drain(true)
  } finally {
    reader.releaseLock()
  }
}
