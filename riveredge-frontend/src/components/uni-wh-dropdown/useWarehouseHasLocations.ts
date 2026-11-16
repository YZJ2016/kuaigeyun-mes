import { useEffect, useState } from 'react';
import { probeWarehouseHasLocations, readWarehouseHasLocationsCache } from './warehouseLocationProbe';

/** undefined = 探测中或未选仓；true/false = 仓下是否有库位。 */
export function useWarehouseHasLocations(warehouseId: number | undefined): boolean | undefined {
  const wid =
    warehouseId != null && Number.isFinite(Number(warehouseId)) && Number(warehouseId) > 0
      ? Number(warehouseId)
      : undefined;
  const [hasLocations, setHasLocations] = useState<boolean | undefined>(() =>
    wid != null ? readWarehouseHasLocationsCache(wid) : undefined,
  );

  useEffect(() => {
    if (wid == null) {
      setHasLocations(undefined);
      return;
    }
    const cached = readWarehouseHasLocationsCache(wid);
    if (cached !== undefined) {
      setHasLocations(cached);
      return;
    }
    let cancelled = false;
    setHasLocations(undefined);
    void probeWarehouseHasLocations(wid)
      .then((hasLoc) => {
        if (!cancelled) setHasLocations(hasLoc);
      })
      .catch(() => {
        if (!cancelled) setHasLocations(true);
      });
    return () => {
      cancelled = true;
    };
  }, [wid]);

  return hasLocations;
}
