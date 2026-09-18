/** Follow a scan's server-sent events into the scan store.
 *
 * The browser resends `Last-Event-ID` after a dropped connection, so a
 * reconnect resumes where it left off. The stream is closed as soon as the
 * scan reports `done` or `failed`.
 */
import { useEffect } from 'react'

import { eventsUrl } from '@/lib/api'
import { EVENT_KINDS, type ScanEvent } from '@/lib/events'
import { useScanStore } from '@/store/scan-store'

export function useScanEvents(scanId: string, onFinished?: () => void): void {
  useEffect(() => {
    const { start, apply } = useScanStore.getState()
    start(scanId)
    const source = new EventSource(eventsUrl(scanId))

    const handle = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as ScanEvent
      apply(event)
      if (event.kind === 'status' && (event.status === 'done' || event.status === 'failed')) {
        source.close()
        onFinished?.()
      }
    }

    for (const kind of EVENT_KINDS) source.addEventListener(kind, handle as EventListener)
    return () => source.close()
    // onFinished is only used to refresh queries; changing it must not reconnect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanId])
}
