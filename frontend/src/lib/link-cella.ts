/** La cella di un link diretto (`#/dashboard?cella=…&lon=…&lat=…`), come
 *  quelli della mail di un contributo: senza, il link apriva la home. */
export function cellaDaHash(hash: string): { cellId: string; lon: number; lat: number } | null {
  const query = hash.split("?")[1];
  if (!query) return null;
  const p = new URLSearchParams(query);
  const cellId = p.get("cella");
  const lon = Number(p.get("lon") ?? "");
  const lat = Number(p.get("lat") ?? "");
  if (!cellId || !p.get("lon") || !p.get("lat")) return null;
  return Number.isFinite(lon) && Number.isFinite(lat) ? { cellId, lon, lat } : null;
}
