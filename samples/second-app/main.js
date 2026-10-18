export const versionMarker = 'SECOND_TARGET_ONLY';
export function renderStatus(value) {
  return { ready: Boolean(value), versionMarker };
}
