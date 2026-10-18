import { normalizeLabel } from './helper.js';

// The test inspects this module without running it.
export function describeFeature(input) {
  return { route: '/demo/search', label: normalizeLabel(input) };
}
