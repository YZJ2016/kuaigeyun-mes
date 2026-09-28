/**
 * 数据字典项缓存：TTL 复用 + 同 code 并发去重。
 *
 * 缓存键仅为字典 code（项内容按租户，不随 host_resource 变化）。
 * hostResource 仅参与鉴权请求参数，成功写入后供全页复用。
 *
 * - `getDictionaryBundleCached(code)`：返回 dictionary + items（供 DictionarySelect 快速创建）。
 * - `getDictionaryItemsCached(code)`：仅 items。
 * - `getDictionaryItemsSync(code)`：命中未过期缓存时同步可读（首帧）。
 * - `clearDictionaryCache(code?)`：字典维护 / 快速创建后失效。
 */

import {
  getDataDictionaryByCode,
  getDictionaryItemList,
  type DataDictionary,
  type DictionaryItem,
  type DictionaryLoadOptions,
} from './dataDictionary'

const TTL_MS = 5 * 60 * 1000

type CacheEntry = {
  expiresAt: number
  dictionary: DataDictionary
  items: DictionaryItem[]
}

const cache = new Map<string, CacheEntry>()
const inflight = new Map<string, Promise<CacheEntry>>()

function cacheKey(code: string): string {
  return String(code || '').trim()
}

function isFresh(entry: CacheEntry | undefined): entry is CacheEntry {
  return !!entry && entry.expiresAt > Date.now()
}

async function loadBundle(
  code: string,
  options?: DictionaryLoadOptions,
): Promise<CacheEntry> {
  const dictionary = await getDataDictionaryByCode(code, options)
  const items = await getDictionaryItemList(dictionary.uuid, true, options)
  const sorted = [...items].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
  return {
    expiresAt: Date.now() + TTL_MS,
    dictionary,
    items: sorted,
  }
}

export function getDictionaryItemsSync(code: string): DictionaryItem[] | undefined {
  const key = cacheKey(code)
  if (!key) return undefined
  const entry = cache.get(key)
  return isFresh(entry) ? entry.items : undefined
}

export function getDictionaryLabelMapSync(code: string): Record<string, string> | undefined {
  const items = getDictionaryItemsSync(code)
  if (!items) return undefined
  const map: Record<string, string> = {}
  for (const item of items) {
    map[item.value] = item.label
  }
  return map
}

export async function getDictionaryBundleCached(
  code: string,
  options?: DictionaryLoadOptions,
): Promise<{ dictionary: DataDictionary; items: DictionaryItem[] }> {
  const key = cacheKey(code)
  if (!key) {
    throw new Error('dictionary code is required')
  }

  const hit = cache.get(key)
  if (isFresh(hit)) {
    return { dictionary: hit.dictionary, items: hit.items }
  }

  const existing = inflight.get(key)
  if (existing) {
    const entry = await existing
    return { dictionary: entry.dictionary, items: entry.items }
  }

  const promise = loadBundle(key, options)
    .then((entry) => {
      cache.set(key, entry)
      return entry
    })
    .finally(() => {
      inflight.delete(key)
    })
  inflight.set(key, promise)
  const entry = await promise
  return { dictionary: entry.dictionary, items: entry.items }
}

export async function getDictionaryItemsCached(
  code: string,
  options?: DictionaryLoadOptions,
): Promise<DictionaryItem[]> {
  const { items } = await getDictionaryBundleCached(code, options)
  return items
}

export function clearDictionaryCache(code?: string): void {
  if (!code) {
    cache.clear()
    inflight.clear()
    return
  }
  const key = cacheKey(code)
  cache.delete(key)
  inflight.delete(key)
}
