export function reviewModeEnabled(reviewBuild: boolean, hasScene: boolean) {
  return reviewBuild && hasScene
}
