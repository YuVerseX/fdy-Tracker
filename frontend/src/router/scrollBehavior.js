export function resolveScrollBehavior(_to, _from, savedPosition) {
  if (savedPosition) {
    return savedPosition
  }

  return { left: 0, top: 0 }
}
