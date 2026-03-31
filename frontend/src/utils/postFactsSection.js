const getItemCount = (items) => Array.isArray(items) ? items.length : 0

export function shouldShowPostFactsSection(facts = [], supplementalFacts = []) {
  return getItemCount(facts) > 0 || getItemCount(supplementalFacts) > 0
}
