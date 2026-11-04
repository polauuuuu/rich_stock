// A failed request or a view that unmounted must remain retryable on the next poll.
export async function loadResult<T>(id: string, loaded: Set<string>, inflight: Set<string>, fetcher: () => Promise<T>, accept: (result: T) => boolean): Promise<void> {
  if (loaded.has(id) || inflight.has(id)) return
  inflight.add(id)
  try {
    const result = await fetcher()
    if (accept(result)) loaded.add(id)
  } finally {
    inflight.delete(id)
  }
}
